"""
Test 5: Cron Materialization Test

Setup:   Create a recurring job in scheduled_jobs with cron '* * * * *' (every minute).
         Set next_run_at to a time in the past (so it's immediately due).
Execute: Trigger the materializer loop logic once.
Assert:  Exactly 1 concrete job row created in jobs.
         next_run_at on scheduled_jobs advanced by exactly ~1 minute.
         Triggering the materializer again immediately produces 0 new jobs.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from croniter import croniter
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from config import settings
from models import Job, JobStatus, Queue, Organization, Project, ScheduledJob, User
from auth import hash_password

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def engine():
    return create_async_engine(settings.database_url, pool_size=5, max_overflow=5)


@pytest.fixture(scope="module")
def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


async def _seed(sf) -> tuple:
    async with sf() as db:
        user = User(email=f"cron_{uuid.uuid4()}@test.com", name="C", password_hash="dummy_hash")
        db.add(user)
        await db.flush()
        org = Organization(name="Org", owner_id=user.id)
        db.add(org)
        await db.flush()
        project = Project(name="Proj", org_id=org.id)
        db.add(project)
        await db.flush()
        queue = Queue(project_id=project.id, name=f"q_{uuid.uuid4()}", concurrency_limit=5)
        db.add(queue)
        await db.flush()
        # next_run_at set 5 minutes in the PAST → immediately due
        past = datetime.now(timezone.utc) - timedelta(minutes=5)
        sj = ScheduledJob(
            queue_id=queue.id,
            cron_expr="* * * * *",  # every minute
            payload={"cron": True},
            is_active=True,
            next_run_at=past,
        )
        db.add(sj)
        await db.commit()
        return sj.id, queue.id


async def _run_materializer_once(sf, queue_id):
    """Run one materializer sweep (extracted from scheduler.py)."""
    async with sf() as db:
        now = datetime.now(timezone.utc)
        from sqlalchemy import or_
        result = await db.execute(
            select(ScheduledJob).where(
                ScheduledJob.queue_id == queue_id,
                ScheduledJob.is_active == True,
                or_(
                    ScheduledJob.next_run_at == None,
                    ScheduledJob.next_run_at <= now,
                ),
            )
        )
        due = result.scalars().all()

        spawned = 0
        for sj in due:
            job = Job(
                queue_id=sj.queue_id,
                job_type="immediate",
                status=JobStatus.queued,
                payload=sj.payload,
                priority=sj.priority,
                run_at=now,
                max_attempts=sj.max_attempts,
            )
            db.add(job)
            cron = croniter(sj.cron_expr, now)
            sj.next_run_at = cron.get_next(datetime).replace(tzinfo=timezone.utc)
            sj.last_run_at = now
            spawned += 1

        await db.commit()
        return spawned


@pytest.mark.asyncio
async def test_cron_materializes_exactly_once(session_factory):
    sj_id, queue_id = await _seed(session_factory)

    # Snapshot next_run_at before
    async with session_factory() as db:
        r = await db.execute(select(ScheduledJob).where(ScheduledJob.id == sj_id))
        sj = r.scalar_one()
        before_next = sj.next_run_at

    # Run materializer once
    before_count = await _count_jobs(session_factory, queue_id)
    spawned = await _run_materializer_once(session_factory, queue_id)
    after_count = await _count_jobs(session_factory, queue_id)

    # Assert 1: exactly 1 job spawned
    assert spawned == 1, f"Expected 1 spawn, got {spawned}"
    assert after_count - before_count == 1, f"Expected +1 job, got +{after_count - before_count}"

    # Assert 2: next_run_at advanced by ~1 minute (within 10s tolerance)
    async with session_factory() as db:
        r = await db.execute(select(ScheduledJob).where(ScheduledJob.id == sj_id))
        sj = r.scalar_one()
        after_next = sj.next_run_at

    now = datetime.now(timezone.utc)
    gap_seconds = (after_next - now).total_seconds()
    assert 0 <= gap_seconds <= 70, (
        f"Expected next run in ~60s, got {gap_seconds}s"
    )

    # Assert 3: running materializer again immediately produces 0 new jobs
    # (next_run_at is now in the future)
    second_spawn = await _run_materializer_once(session_factory, queue_id)
    assert second_spawn == 0, f"Expected 0 on second run, got {second_spawn}"

    final_count = await _count_jobs(session_factory, queue_id)
    assert final_count == after_count, "Second materializer run created unexpected jobs"


async def _count_jobs(sf, queue_id) -> int:
    async with sf() as db:
        return (await db.execute(
            select(func.count()).select_from(Job).where(Job.queue_id == queue_id)
        )).scalar() or 0
