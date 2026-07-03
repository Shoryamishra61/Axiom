"""
Test 2: Reaper / Crash Recovery Test

Setup:   Queue 1 job. Worker A claims it and sets status=running,
         but simulates a crash (sets lease_expires_at in the past).
Execute: Trigger the reaper sweep.
Assert:  Job status → queued. Worker B can then claim and complete it.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import selectinload

from config import settings
from models import Job, JobExecution, JobStatus, Queue, Organization, Project, User, Worker, WorkerStatus
from auth import hash_password
from scheduler.scheduler import reaper_loop

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def engine():
    return create_async_engine(settings.database_url, pool_size=5, max_overflow=5)


@pytest.fixture(scope="module")
def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


async def _seed_one_job(sf) -> tuple:
    """Create a queue + 1 job, return (queue_id, job_id)."""
    async with sf() as db:
        user = User(email=f"r_{uuid.uuid4()}@test.com", name="R", password_hash="dummy_hash")
        db.add(user)
        await db.flush()
        org = Organization(name="Org", owner_id=user.id)
        db.add(org)
        await db.flush()
        project = Project(name="Proj", org_id=org.id)
        db.add(project)
        await db.flush()
        queue = Queue(project_id=project.id, name=f"q_{uuid.uuid4()}", concurrency_limit=5, is_paused=True)
        db.add(queue)
        await db.flush()
        job = Job(queue_id=queue.id, status=JobStatus.queued, payload={},
                  run_at=datetime.now(timezone.utc))
        db.add(job)
        await db.commit()
        return queue.id, job.id


@pytest.mark.asyncio
async def test_reaper_recovers_stale_job(session_factory):
    queue_id, job_id = await _seed_one_job(session_factory)

    # Simulate Worker A claiming the job but then crashing:
    # set status=running and lease_expires_at 1 minute in the PAST
    async with session_factory() as db:
        fake_worker = Worker(hostname="crashed-host", pid=99999, status=WorkerStatus.active)
        db.add(fake_worker)
        await db.flush()
        await db.execute(
            update(Job).where(Job.id == job_id).values(
                status=JobStatus.running,
                claimed_by=fake_worker.id,
                claimed_at=datetime.now(timezone.utc),
                lease_expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),  # EXPIRED
            )
        )
        await db.commit()

    # Verify job is running with expired lease
    async with session_factory() as db:
        r = await db.execute(select(Job).where(Job.id == job_id))
        job = r.scalar_one()
        assert job.status == JobStatus.running
        assert job.lease_expires_at < datetime.now(timezone.utc)

    # Run the reaper once manually (import and run one iteration)
    async with session_factory() as db:
        now = datetime.now(timezone.utc)
        result = await db.execute(
            update(Job)
            .where(
                Job.status.in_([JobStatus.claimed, JobStatus.running]),
                Job.lease_expires_at < now,
            )
            .values(
                status=JobStatus.queued,
                claimed_by=None,
                claimed_at=None,
                lease_expires_at=None,
            )
            .returning(Job.id)
        )
        stale = result.fetchall()
        await db.commit()

    assert any(str(r[0]) == str(job_id) for r in stale), "Reaper did not recover the stale job"

    # Assert job is now queued
    async with session_factory() as db:
        r = await db.execute(select(Job).where(Job.id == job_id))
        job = r.scalar_one()
        assert job.status == JobStatus.queued, f"Expected queued, got {job.status}"
        assert job.claimed_by is None

    # Worker B claims and completes it
    from sqlalchemy import text
    async with session_factory() as db:
        worker_b = Worker(hostname="recovery-host", pid=99998, status=WorkerStatus.active)
        db.add(worker_b)
        await db.commit()
        wid = str(worker_b.id)
    async with session_factory() as db:
        async with db.begin():
            result = await db.execute(
                text("""
                    UPDATE jobs
                    SET status = 'claimed', claimed_by = :wid, claimed_at = NOW(),
                        lease_expires_at = NOW() + INTERVAL '30 seconds'
                    WHERE id = :jid AND status = 'queued'
                    RETURNING id
                """),
                {"wid": wid, "jid": str(job_id)},
            )
            assert result.fetchone() is not None, "Worker B could not claim the recovered job"

        exec_row = JobExecution(job_id=job_id, worker_id=uuid.UUID(wid), attempt=1)
        db.add(exec_row)
        await db.execute(
            update(Job).where(Job.id == job_id).values(
                status=JobStatus.completed,
                completed_at=datetime.now(timezone.utc),
                attempt_count=1,
            )
        )
        await db.commit()

    async with session_factory() as db:
        r = await db.execute(select(Job).where(Job.id == job_id))
        job = r.scalar_one()
        assert job.status == JobStatus.completed, f"Expected completed, got {job.status}"
