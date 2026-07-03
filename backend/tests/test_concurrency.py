"""
Test 1: Concurrency "Zero Duplicates" Test (Highest Priority)

Setup:   Seed 1 queue with 100 "immediate" jobs.
Execute: Spawn 10 concurrent worker coroutines to poll simultaneously.
Assert:  Exactly 100 unique job_executions. 0 duplicates.
         COUNT(jobs WHERE status='completed') == 100.
"""
import asyncio
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from config import settings
from models import Job, JobExecution, JobStatus, Queue, Organization, Project, User, Worker
from auth import hash_password
from worker.poller import WorkerProcess

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def engine():
    return create_async_engine(settings.database_url, poolclass=NullPool)


@pytest.fixture(scope="module")
def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


async def _seed(session_factory):
    """Seed 1 queue + 100 immediate jobs."""
    async with session_factory() as db:
        user = User(email=f"t_{uuid.uuid4()}@test.com", name="T", password_hash="dummy_hash")
        db.add(user)
        await db.flush()
        org = Organization(name="Org", owner_id=user.id)
        db.add(org)
        await db.flush()
        project = Project(name="Proj", org_id=org.id)
        db.add(project)
        await db.flush()
        # Paused prevents any separately running demo worker from stealing this test's jobs.
        queue = Queue(project_id=project.id, name=f"q_{uuid.uuid4()}", concurrency_limit=100, is_paused=True)
        db.add(queue)
        await db.flush()
        jobs = [
            Job(queue_id=queue.id, status=JobStatus.queued, payload={"n": i},
                run_at=datetime.now(timezone.utc))
            for i in range(100)
        ]
        db.add_all(jobs)
        workers = [Worker(hostname=f"test-{i}", pid=10_000 + i) for i in range(10)]
        db.add_all(workers)
        await db.commit()
        return queue.id, [j.id for j in jobs], [worker.id for worker in workers]


async def _worker(session_factory, claimed: list, worker_id, queue_id) -> None:
    """Claim and complete all available jobs via SKIP LOCKED."""
    while True:
        async with session_factory() as db:
            async with db.begin():
                wid = str(worker_id)
                result = await db.execute(
                    text("""
                        UPDATE jobs
                        SET status = 'claimed',
                            claimed_by = :wid,
                            claimed_at = NOW()
                        WHERE id = (
                            SELECT id FROM jobs
                            WHERE status = 'queued' AND queue_id = :queue_id
                            ORDER BY priority DESC, run_at ASC
                            LIMIT 1
                            FOR UPDATE SKIP LOCKED
                        )
                        RETURNING id
                    """),
                    {"wid": wid, "queue_id": str(queue_id)},
                )
                row = result.fetchone()
            if not row:
                break
            job_id = row[0]
            claimed.append(str(job_id))
            # Create execution record + mark completed (simulating full execution)
            async with db.begin():
                exec_row = JobExecution(job_id=job_id, worker_id=uuid.UUID(wid), attempt=1)
                db.add(exec_row)
                await db.execute(
                    update(Job).where(Job.id == job_id).values(
                        status=JobStatus.completed,
                        completed_at=datetime.now(timezone.utc),
                        attempt_count=1,
                    )
                )


@pytest.mark.asyncio
async def test_zero_duplicate_claims(session_factory):
    queue_id, job_ids, worker_ids = await _seed(session_factory)

    claimed_by_all: list[list[str]] = [[] for _ in range(10)]
    await asyncio.gather(*[_worker(session_factory, claimed_by_all[i], worker_ids[i], queue_id) for i in range(10)])

    all_claimed = [jid for w in claimed_by_all for jid in w]

    # Assertion 1: 100 unique claims — zero duplicates
    assert len(all_claimed) == 100, f"Expected 100 claims, got {len(all_claimed)}"
    assert len(set(all_claimed)) == 100, f"Duplicates: {len(all_claimed) - len(set(all_claimed))}"

    # Assertion 2: COUNT(jobs WHERE status='completed') == 100
    async with session_factory() as db:
        count = (await db.execute(
            select(func.count()).select_from(Job)
            .where(Job.queue_id == queue_id, Job.status == JobStatus.completed)
        )).scalar()
    assert count == 100, f"Expected 100 completed jobs, got {count}"

    # Assertion 3: Exactly 100 job_executions — zero double-executions
    async with session_factory() as db:
        exec_count = (await db.execute(
            select(func.count()).select_from(JobExecution)
            .where(JobExecution.job_id.in_([uuid.UUID(j) for j in all_claimed]))
        )).scalar()
    assert exec_count == 100, f"Expected 100 executions, got {exec_count}"


@pytest.mark.asyncio
async def test_production_claim_respects_queue_concurrency(session_factory):
    async with session_factory() as db:
        user = User(email=f"limit_{uuid.uuid4()}@test.com", name="L", password_hash="dummy_hash")
        db.add(user)
        await db.flush()
        org = Organization(name="Org", owner_id=user.id)
        db.add(org)
        await db.flush()
        project = Project(name="Proj", org_id=org.id)
        db.add(project)
        await db.flush()
        queue = Queue(project_id=project.id, name=f"limit_{uuid.uuid4()}", priority=1_000_000, concurrency_limit=2)
        db.add(queue)
        await db.flush()
        db.add_all([Job(queue_id=queue.id, status=JobStatus.queued, payload={}) for _ in range(10)])
        workers = [Worker(hostname=f"limit-{i}", pid=20_000 + i) for i in range(10)]
        db.add_all(workers)
        await db.commit()
        queue_id = queue.id

    processes = []
    for worker in workers:
        process = WorkerProcess()
        process.worker_id = worker.id
        processes.append(process)

    async def claim(process):
        async with session_factory() as db:
            return await process.poll_and_claim(db)

    await asyncio.gather(*(claim(process) for process in processes))
    async with session_factory() as db:
        claimed = (await db.execute(
            select(func.count()).select_from(Job).where(
                Job.queue_id == queue_id,
                Job.status == JobStatus.claimed,
            )
        )).scalar()
    assert claimed == 2
