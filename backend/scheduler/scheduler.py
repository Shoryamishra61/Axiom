"""
Scheduler process: two independent loops on one async event loop.
  1. Reaper — re-queues jobs whose lease has expired (worker crash recovery).
  2. Cron materializer — converts active ScheduledJob definitions into concrete job rows.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from croniter import croniter
from sqlalchemy import Integer, cast, func, select, update

from config import settings
from database import AsyncSessionLocal
from models import DeadLetterEntry, Job, JobExecution, JobStatus, ScheduledJob, Worker, WorkerStatus

log = logging.getLogger(__name__)


# ---- Reaper ----

async def reaper_loop() -> None:
    """Detects stale claimed/running jobs (missed heartbeat) and re-queues them."""
    while True:
        async with AsyncSessionLocal() as db:
            stale = await reap_once(db)
            if stale:
                log.warning("Reaper recovered %d stale jobs: %s", len(stale), [str(job_id) for job_id in stale])

            # Mark workers dead if they haven't been seen recently
            now = datetime.now(timezone.utc)
            await db.execute(
                update(Worker)
                .where(
                    Worker.status == WorkerStatus.active,
                    Worker.last_seen < now - timedelta(seconds=settings.worker_lease_seconds),
                )
                .values(status=WorkerStatus.dead)
            )
            await db.commit()

        await asyncio.sleep(settings.reaper_interval_seconds)


async def reap_once(db) -> list:
    """Recover expired leases while preserving an execution/retry audit trail."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(Job)
        .where(
            Job.status.in_([JobStatus.claimed, JobStatus.running]),
            Job.lease_expires_at < now,
        )
        .with_for_update(skip_locked=True)
    )
    stale_jobs = result.scalars().all()
    for job in stale_jobs:
        await db.execute(
            update(JobExecution)
            .where(JobExecution.job_id == job.id, JobExecution.status == JobStatus.running)
            .values(
                status=JobStatus.failed,
                finished_at=now,
                error_msg="Worker lease expired",
                duration_ms=cast(func.extract("epoch", now - JobExecution.started_at) * 1000, Integer),
            )
        )
        if job.attempt_count >= job.max_attempts:
            db.add(DeadLetterEntry(
                job_id=job.id,
                queue_id=job.queue_id,
                payload=job.payload,
                failure_reason="Worker lease expired",
                attempt_count=job.attempt_count,
                first_failed_at=now,
            ))
            job.status = JobStatus.dead
            job.completed_at = now
        else:
            job.status = JobStatus.queued
        job.claimed_by = None
        job.claimed_at = None
        job.lease_expires_at = None
    await db.commit()
    return [job.id for job in stale_jobs]


# ---- Cron Materializer ----

async def materializer_loop() -> None:
    """Materializes due cron definitions into concrete job rows."""
    while True:
        async with AsyncSessionLocal() as db:
            spawned = await materialize_once(db)
            if spawned:
                log.info("Materialized %d cron jobs", spawned)

        await asyncio.sleep(settings.materializer_interval_seconds)


async def materialize_once(db) -> int:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(ScheduledJob)
        .where(
            ScheduledJob.is_active == True,  # noqa: E712
            (ScheduledJob.next_run_at == None) | (ScheduledJob.next_run_at <= now),
        )
        .with_for_update(skip_locked=True)
    )
    due = result.scalars().all()
    for sj in due:
        db.add(Job(
            queue_id=sj.queue_id,
            job_type="cron",
            status=JobStatus.queued,
            payload=sj.payload,
            priority=sj.priority,
            run_at=now,
            max_attempts=sj.max_attempts,
        ))
        sj.next_run_at = croniter(sj.cron_expr, now).get_next(datetime)
        sj.last_run_at = now
    await db.commit()
    return len(due)
