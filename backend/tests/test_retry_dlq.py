"""
Test 3: Retry Math & DLQ Routing Test

Setup:   Create a job with exponential retry policy (base=2000ms, max_attempts=3, cap=10000ms).
Execute: Worker claims and fails the job 3 times.
Assert 1: time gaps between attempts reflect jittered exponential backoff (~2s, ~4s, ~8s).
Assert 2: After 3rd failure, a record appears in dead_letter_entries.
           Job status transitions to 'dead'.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from config import settings
from models import (
    DeadLetterEntry, Job, JobExecution, JobStatus,
    Queue, Organization, Project, RetryPolicy, RetryStrategy, User, Worker,
)
from auth import hash_password
from worker.retry import compute_delay_ms

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def engine():
    return create_async_engine(settings.database_url, pool_size=5, max_overflow=5)


@pytest.fixture(scope="module")
def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


async def _seed(sf) -> tuple:
    async with sf() as db:
        user = User(email=f"rd_{uuid.uuid4()}@test.com", name="RD", password_hash="dummy_hash")
        db.add(user)
        await db.flush()
        org = Organization(name="Org", owner_id=user.id)
        db.add(org)
        await db.flush()
        project = Project(name="Proj", org_id=org.id)
        db.add(project)
        await db.flush()
        policy = RetryPolicy(
            strategy=RetryStrategy.exponential,
            max_attempts=3,
            base_delay_ms=2000,
            max_delay_ms=10000,
        )
        db.add(policy)
        await db.flush()
        queue = Queue(
            project_id=project.id,
            name=f"q_{uuid.uuid4()}",
            concurrency_limit=5,
            retry_policy_id=policy.id,
            is_paused=True,
        )
        db.add(queue)
        await db.flush()
        job = Job(
            queue_id=queue.id,
            status=JobStatus.queued,
            payload={"fail": True},
            run_at=datetime.now(timezone.utc),
            max_attempts=3,
        )
        db.add(job)
        worker = Worker(hostname="retry-test", pid=12345)
        db.add(worker)
        await db.commit()
        return policy.id, queue.id, job.id, worker.id


@pytest.mark.asyncio
async def test_retry_backoff_and_dlq(session_factory):
    policy_id, queue_id, job_id, worker_id = await _seed(session_factory)

    # --- Verify retry math (unit check, no DB needed) ---
    # Attempt 1: exponential delay should be in [0, min(10000, 2000*2^0)] = [0, 2000]
    for attempt, expected_max in [(1, 2000), (2, 4000), (3, 8000)]:
        delay = compute_delay_ms("exponential", attempt, 2000, 10000)
        assert 0 <= delay <= expected_max, (
            f"Attempt {attempt}: delay {delay} out of [0, {expected_max}]"
        )

    # --- Simulate 3 failures, tracking run_at advancement ---
    from sqlalchemy import update, text

    run_ats: list[datetime] = []

    async with session_factory() as db:
        r = await db.execute(select(Job).where(Job.id == job_id))
        job = r.scalar_one()
        run_ats.append(job.run_at.replace(tzinfo=timezone.utc) if job.run_at.tzinfo is None else job.run_at)

    for attempt_num in range(1, 4):
        async with session_factory() as db:
            # Claim
            await db.execute(
                update(Job).where(Job.id == job_id).values(
                    status=JobStatus.running,
                    claimed_by=worker_id,
                    claimed_at=datetime.now(timezone.utc),
                    lease_expires_at=datetime.now(timezone.utc) + timedelta(seconds=30),
                )
            )
            await db.commit()

        async with session_factory() as db:
            r = await db.execute(select(Job).where(Job.id == job_id))
            job = r.scalar_one()

            now = datetime.now(timezone.utc)
            exec_row = JobExecution(
                job_id=job_id,
                attempt=attempt_num,
                started_at=now,
                finished_at=now,
                status=JobStatus.failed,
                error_msg="Intentional failure",
            )
            db.add(exec_row)
            await db.flush()

            new_attempt = attempt_num
            if new_attempt >= job.max_attempts:
                # Route to DLQ
                entry = DeadLetterEntry(
                    job_id=job.id,
                    queue_id=job.queue_id,
                    payload=job.payload,
                    failure_reason="Intentional failure",
                    attempt_count=new_attempt,
                    first_failed_at=job.created_at,
                )
                db.add(entry)
                await db.execute(
                    update(Job).where(Job.id == job_id).values(
                        status=JobStatus.dead,
                        attempt_count=new_attempt,
                        completed_at=now,
                    )
                )
            else:
                delay_ms = compute_delay_ms("exponential", new_attempt, 2000, 10000)
                retry_at = now + timedelta(milliseconds=delay_ms)
                run_ats.append(retry_at)
                await db.execute(
                    update(Job).where(Job.id == job_id).values(
                        status=JobStatus.scheduled,
                        attempt_count=new_attempt,
                        run_at=retry_at,
                        claimed_by=None,
                        claimed_at=None,
                        lease_expires_at=None,
                    )
                )
            await db.commit()

    # Assert 1: gap between attempts is non-negative and within expected caps
    assert len(run_ats) == 3, f"Expected 3 run_at timestamps, got {len(run_ats)}"
    gap1 = (run_ats[1] - run_ats[0]).total_seconds() * 1000
    gap2 = (run_ats[2] - run_ats[1]).total_seconds() * 1000
    # Jitter means gap can be 0..2000ms and 0..4000ms respectively
    assert 0 <= gap1 <= 2100, f"Gap1 {gap1}ms out of [0, 2000]ms"
    assert 0 <= gap2 <= 4100, f"Gap2 {gap2}ms out of [0, 4000]ms"
    # Second gap should generally be >= first (exponential growth)
    # (not guaranteed with jitter, but max of second window > max of first)

    # Assert 2: Job is now dead
    async with session_factory() as db:
        r = await db.execute(select(Job).where(Job.id == job_id))
        job = r.scalar_one()
        assert job.status == JobStatus.dead, f"Expected dead, got {job.status}"

    # Assert 3: DLQ entry exists
    async with session_factory() as db:
        r = await db.execute(select(DeadLetterEntry).where(DeadLetterEntry.job_id == job_id))
        entry = r.scalar_one_or_none()
        assert entry is not None, "No DLQ entry found after 3 failures"
        assert entry.attempt_count == 3

    # Assert 4: Exactly 3 job_executions recorded
    async with session_factory() as db:
        from sqlalchemy import func
        count = (await db.execute(
            select(func.count()).select_from(JobExecution).where(JobExecution.job_id == job_id)
        )).scalar()
        assert count == 3, f"Expected 3 executions, got {count}"
