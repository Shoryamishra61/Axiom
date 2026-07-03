"""
Core worker: polls PostgreSQL using FOR UPDATE SKIP LOCKED,
executes jobs, sends heartbeats, handles graceful shutdown.
"""
import asyncio
import logging
import os
import socket
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import AsyncSessionLocal
from models import (
    DeadLetterEntry, Job, JobExecution, JobLog, JobStatus,
    Queue, RetryPolicy, RetryStrategy, Worker, WorkerHeartbeat, WorkerStatus,
)
from worker.retry import compute_delay_ms

log = logging.getLogger(__name__)


class WorkerProcess:
    def __init__(self):
        self.worker_id: uuid.UUID | None = None
        self._shutdown = asyncio.Event()
        self._active_jobs: set[asyncio.Task] = set()

    # ---- Registration ----

    async def register(self, db: AsyncSession) -> None:
        w = Worker(hostname=socket.gethostname(), pid=os.getpid(), status=WorkerStatus.active)
        db.add(w)
        await db.commit()
        await db.refresh(w)
        self.worker_id = w.id
        log.info("Worker registered: %s", self.worker_id)

    # ---- Heartbeat ----

    async def heartbeat_loop(self) -> None:
        while not self._shutdown.is_set() or self._active_jobs:
            try:
                async with AsyncSessionLocal() as db:
                    lease_until = datetime.now(timezone.utc) + timedelta(seconds=settings.worker_lease_seconds)
                    hb = WorkerHeartbeat(worker_id=self.worker_id, active_jobs=len(self._active_jobs))
                    db.add(hb)
                    await db.execute(
                        update(Worker)
                        .where(Worker.id == self.worker_id)
                        .values(last_seen=datetime.now(timezone.utc))
                    )
                    await db.execute(
                        update(Job)
                        .where(
                            Job.claimed_by == self.worker_id,
                            Job.status.in_([JobStatus.claimed, JobStatus.running]),
                        )
                        .values(lease_expires_at=lease_until)
                    )
                    await db.commit()
            except Exception:
                log.exception("Worker heartbeat failed")
            await asyncio.sleep(5)

    # ---- Poll + Claim (SKIP LOCKED) ----

    async def poll_and_claim(self, db: AsyncSession) -> Job | None:
        """Atomically claim one job from any non-paused, non-full queue."""
        from sqlalchemy import text
        lease_until = datetime.now(timezone.utc) + timedelta(seconds=settings.worker_lease_seconds)

        # Single atomic transaction: SELECT ... FOR UPDATE SKIP LOCKED + UPDATE
        async with db.begin():
            result = await db.execute(
                text("""
                WITH eligible_queue AS MATERIALIZED (
                    SELECT q.id
                    FROM queues q
                    WHERE q.is_paused = FALSE
                      AND EXISTS (
                          SELECT 1 FROM jobs due
                          WHERE due.queue_id = q.id
                            AND due.status IN ('queued', 'scheduled')
                            AND due.run_at <= NOW()
                      )
                      AND (
                          SELECT COUNT(*) FROM jobs active
                          WHERE active.queue_id = q.id
                            AND active.status IN ('claimed', 'running')
                      ) < q.concurrency_limit
                    ORDER BY q.priority DESC, q.created_at ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                ), candidate AS (
                    SELECT j.id FROM jobs j
                    JOIN eligible_queue q ON q.id = j.queue_id
                    WHERE j.status IN ('queued', 'scheduled')
                      AND j.run_at <= NOW()
                    ORDER BY j.priority DESC, j.run_at ASC
                    LIMIT 1
                    FOR UPDATE OF j SKIP LOCKED
                )
                UPDATE jobs
                SET status = 'claimed',
                    claimed_by = :worker_id,
                    claimed_at = NOW(),
                    lease_expires_at = :lease_until
                WHERE id = (SELECT id FROM candidate)
                RETURNING id
                """),
                {"worker_id": str(self.worker_id), "lease_until": lease_until},
            )
            row = result.fetchone()

        if not row:
            return None

        r = await db.execute(select(Job).where(Job.id == row[0]))
        return r.scalar_one_or_none()

    # ---- Execute ----

    async def execute_job(self, job: Job) -> None:
        async with AsyncSessionLocal() as db:
            # Transition to running
            started = await db.execute(
                update(Job)
                .where(
                    Job.id == job.id,
                    Job.claimed_by == self.worker_id,
                    Job.status == JobStatus.claimed,
                )
                .values(status=JobStatus.running, attempt_count=job.attempt_count + 1)
            )
            if started.rowcount != 1:
                await db.rollback()
                return
            execution = JobExecution(
                job_id=job.id,
                worker_id=self.worker_id,
                attempt=job.attempt_count + 1,
            )
            db.add(execution)
            await db.commit()
            await db.refresh(execution)

            # Minimal deterministic demo handler. Real deployments replace this
            # block with an idempotent task registry or HTTP dispatch adapter.
            log_msg = f"Executing job {job.id} (attempt {execution.attempt})"
            log.info(log_msg)
            db.add(JobLog(execution_id=execution.id, level="info", message=log_msg))
            await db.commit()

            try:
                duration_ms = min(max(int(job.payload.get("duration_ms", 100)), 0), 300_000)
                await asyncio.sleep(duration_ms / 1000)
                if job.payload.get("fail"):
                    raise RuntimeError(str(job.payload.get("error", "Job requested failure")))

                # Success
                now = datetime.now(timezone.utc)
                duration = int((now - execution.started_at.replace(tzinfo=timezone.utc)).total_seconds() * 1000)
                execution.status = JobStatus.completed
                execution.finished_at = now
                execution.duration_ms = duration
                await db.execute(
                    update(Job).where(Job.id == job.id).values(
                        status=JobStatus.completed,
                        completed_at=now,
                        attempt_count=execution.attempt,
                        claimed_by=None,
                        claimed_at=None,
                        lease_expires_at=None,
                    )
                )
                db.add(JobLog(execution_id=execution.id, level="info", message="Job completed successfully"))

            except Exception as exc:
                await self._handle_failure(db, job, execution, str(exc))

            await db.commit()

    async def _handle_failure(self, db: AsyncSession, job: Job, execution: JobExecution, error: str) -> None:
        now = datetime.now(timezone.utc)
        new_attempt = execution.attempt
        execution.status = JobStatus.failed
        execution.finished_at = now
        execution.error_msg = error
        duration = int((now - execution.started_at.replace(tzinfo=timezone.utc)).total_seconds() * 1000)
        execution.duration_ms = duration
        db.add(JobLog(execution_id=execution.id, level="error", message=f"Job failed: {error}"))

        if new_attempt >= job.max_attempts:
            # Route to DLQ
            first_failed_at = (await db.execute(
                select(func.min(JobExecution.finished_at)).where(
                    JobExecution.job_id == job.id,
                    JobExecution.status == JobStatus.failed,
                )
            )).scalar() or now
            entry = DeadLetterEntry(
                job_id=job.id,
                queue_id=job.queue_id,
                payload=job.payload,
                failure_reason=error,
                attempt_count=new_attempt,
                first_failed_at=first_failed_at,
            )
            db.add(entry)
            await db.execute(
                update(Job).where(Job.id == job.id).values(
                    status=JobStatus.dead,
                    attempt_count=new_attempt,
                    completed_at=now,
                )
            )
            log.warning("Job %s exhausted retries → DLQ", job.id)
        else:
            # Schedule retry with backoff
            retry_delay_ms = await self._get_retry_delay(db, job.queue_id, new_attempt)
            retry_at = now + timedelta(milliseconds=retry_delay_ms)
            await db.execute(
                update(Job).where(Job.id == job.id).values(
                    status=JobStatus.scheduled,
                    attempt_count=new_attempt,
                    run_at=retry_at,
                    claimed_by=None,
                    claimed_at=None,
                    lease_expires_at=None,
                )
            )
            log.info("Job %s scheduled for retry at %s", job.id, retry_at)

    async def _get_retry_delay(self, db: AsyncSession, queue_id, attempt: int) -> int:
        r = await db.execute(
            select(RetryPolicy)
            .join(Queue, Queue.retry_policy_id == RetryPolicy.id)
            .where(Queue.id == queue_id)
        )
        rp = r.scalar_one_or_none()
        if not rp:
            return 1000 * (2 ** (attempt - 1))  # sensible default
        return compute_delay_ms(rp.strategy, attempt, rp.base_delay_ms, rp.max_delay_ms)

    # ---- Main loop ----

    async def run(self) -> None:
        async with AsyncSessionLocal() as db:
            await self.register(db)

        heartbeat_task = asyncio.create_task(self.heartbeat_loop())

        while not self._shutdown.is_set():
            if len(self._active_jobs) >= settings.worker_concurrency:
                await asyncio.wait(self._active_jobs, return_when=asyncio.FIRST_COMPLETED)
                continue
            async with AsyncSessionLocal() as db:
                job = await self.poll_and_claim(db)
            if job:
                task = asyncio.create_task(self.execute_job(job))
                self._active_jobs.add(task)
                task.add_done_callback(self._active_jobs.discard)
            else:
                try:
                    await asyncio.wait_for(self._shutdown.wait(), timeout=settings.worker_poll_interval)
                except asyncio.TimeoutError:
                    pass

        # Graceful shutdown: wait for in-flight jobs
        log.info("Shutdown: waiting for %d in-flight jobs", len(self._active_jobs))
        if self._active_jobs:
            await asyncio.gather(*self._active_jobs, return_exceptions=True)
        self._shutdown.set()
        await heartbeat_task

        # Mark worker dead
        async with AsyncSessionLocal() as db:
            await db.execute(update(Worker).where(Worker.id == self.worker_id).values(status=WorkerStatus.dead))
            await db.commit()
        log.info("Worker %s shut down cleanly", self.worker_id)

    def stop(self):
        self._shutdown.set()
