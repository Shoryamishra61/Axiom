import logging
import pathlib
import time
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.auth_routes import router as auth_router
from api.dlq_routes import router as dlq_router
from api.job_routes import router as job_router
from api.metrics_routes import router as metrics_router
from api.org_routes import router as org_router
from api.project_routes import router as project_router
from api.queue_routes import router as queue_router
from config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("api")

MIGRATIONS_DIR = pathlib.Path(__file__).parent / "migrations"


async def run_migrations():
    """Run all SQL migrations on startup. Safe to run multiple times."""
    db_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://").replace(":6543", ":5432")
    try:
        conn = await asyncpg.connect(db_url)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS _migrations (
                filename TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ DEFAULT now()
            )
        """)
        for mf in sorted(MIGRATIONS_DIR.glob("*.sql")):
            already = await conn.fetchval("SELECT 1 FROM _migrations WHERE filename=$1", mf.name)
            if already:
                log.info("Migration already applied: %s", mf.name)
                continue
            log.info("Applying migration: %s", mf.name)
            await conn.execute(mf.read_text(encoding="utf-8"))
            await conn.execute("INSERT INTO _migrations(filename) VALUES($1)", mf.name)
            log.info("Migration applied: %s", mf.name)
        await conn.close()
        log.info("All migrations complete.")
    except Exception as e:
        log.error("Migration error (non-fatal): %s", e)


async def run_seed():
    """Seed the default test user and realistic demo data if it doesn't exist."""
    from auth import hash_password
    from database import AsyncSessionLocal
    from models import (
        User, Organization, Project, Queue, RetryPolicy, RetryStrategy,
        Worker, WorkerStatus, WorkerHeartbeat, Job, JobStatus, JobType,
        DeadLetterEntry
    )
    from sqlalchemy import select
    import uuid
    import datetime

    async with AsyncSessionLocal() as db:
        # 1. Seed User
        result = await db.execute(select(User).where(User.email == "shoryamishra61@gmail.com"))
        user = result.scalar_one_or_none()
        if not user:
            user = User(email="shoryamishra61@gmail.com", name="Shorya Mishra", password_hash=hash_password("password"))
            db.add(user)
            await db.commit()
            await db.refresh(user)
            log.info("Test user seeded.")
        
        # 2. Seed Organization & Project
        result = await db.execute(select(Organization).where(Organization.owner_id == user.id))
        org = result.scalar_one_or_none()
        if not org:
            org = Organization(name="Axiom Demo Corp", owner_id=user.id)
            db.add(org)
            await db.commit()
            await db.refresh(org)
            
            proj = Project(name="Production Workloads", org_id=org.id)
            db.add(proj)
            await db.commit()
            await db.refresh(proj)
            
            # 3. Seed Retry Policies
            policy1 = RetryPolicy(strategy=RetryStrategy.exponential, max_attempts=5, base_delay_ms=1000, max_delay_ms=60000)
            db.add(policy1)
            await db.commit()
            await db.refresh(policy1)

            # 4. Seed Queues
            q1 = Queue(project_id=proj.id, name="email-deliveries", concurrency_limit=20, retry_policy_id=policy1.id)
            q2 = Queue(project_id=proj.id, name="video-encoding", concurrency_limit=5, retry_policy_id=policy1.id)
            db.add_all([q1, q2])
            await db.commit()
            await db.refresh(q1)

            # 5. Seed Workers
            worker = Worker(hostname="demo-worker-01", pid=1024, status=WorkerStatus.active)
            worker2 = Worker(hostname="demo-worker-02", pid=1025, status=WorkerStatus.active)
            db.add_all([worker, worker2])
            await db.commit()
            await db.refresh(worker)
            await db.refresh(worker2)

            db.add_all([
                WorkerHeartbeat(worker_id=worker.id, active_jobs=4),
                WorkerHeartbeat(worker_id=worker2.id, active_jobs=2),
            ])

            # 6. Seed Jobs + spread JobExecution rows across all 12 hourly buckets
            #    so the throughput chart has solid bars from hour 0 to hour 11.
            from models import JobExecution
            import random

            now = datetime.datetime.now(datetime.timezone.utc)
            # Truncate to the current hour, then go back 11 hours
            chart_start = now.replace(minute=0, second=0, microsecond=0) - datetime.timedelta(hours=11)

            # Realistic completed/failed counts per hour bucket
            hourly_plan = [
                (10, 1), (14, 2), (8, 0),  (18, 3),
                (22, 1), (16, 2), (25, 4),  (30, 2),
                (20, 3), (28, 1), (35, 5),  (12, 2),
            ]

            all_exec_jobs = []
            executions = []
            for offset, (n_completed, n_failed) in enumerate(hourly_plan):
                bucket_start = chart_start + datetime.timedelta(hours=offset)
                bucket_end   = bucket_start + datetime.timedelta(minutes=55)

                for i in range(n_completed):
                    started = bucket_start + datetime.timedelta(minutes=random.randint(0, 50))
                    duration = random.randint(300, 8000)
                    finished = started + datetime.timedelta(milliseconds=duration)
                    j = Job(
                        queue_id=q1.id,
                        job_type=JobType.immediate,
                        status=JobStatus.completed,
                        payload={"task": f"email-{offset}-{i}", "to": f"user{i}@example.com"},
                        run_at=started,
                        completed_at=finished,
                    )
                    all_exec_jobs.append((j, JobStatus.completed, started, finished, duration))

                for i in range(n_failed):
                    started = bucket_start + datetime.timedelta(minutes=random.randint(0, 50))
                    duration = random.randint(100, 3000)
                    finished = started + datetime.timedelta(milliseconds=duration)
                    j = Job(
                        queue_id=q1.id,
                        job_type=JobType.immediate,
                        status=JobStatus.failed,
                        payload={"task": f"fail-{offset}-{i}"},
                        run_at=started,
                        attempt_count=3,
                        max_attempts=3,
                        completed_at=finished,
                    )
                    all_exec_jobs.append((j, JobStatus.failed, started, finished, duration))

            # Also add a few live jobs visible in the dashboard stat cards
            job_run   = Job(queue_id=q1.id, job_type=JobType.immediate, status=JobStatus.running,
                            payload={"to": "admin@example.com"}, claimed_by=worker.id, run_at=now)
            job_run2  = Job(queue_id=q1.id, job_type=JobType.immediate, status=JobStatus.running,
                            payload={"to": "ops@example.com"}, claimed_by=worker2.id, run_at=now)
            job_q1    = Job(queue_id=q1.id, job_type=JobType.immediate, status=JobStatus.queued,
                            payload={"to": "billing@example.com"}, run_at=now)
            job_q2    = Job(queue_id=q1.id, job_type=JobType.immediate, status=JobStatus.queued,
                            payload={"to": "support@example.com"}, run_at=now)
            job_q3    = Job(queue_id=q2.id, job_type=JobType.delayed,  status=JobStatus.scheduled,
                            payload={"video": "promo-reel.mp4"}, run_at=now + datetime.timedelta(minutes=30))

            db.add_all([job_run, job_run2, job_q1, job_q2, job_q3])
            # Add all throughput jobs
            for job, *_ in all_exec_jobs:
                db.add(job)
            await db.commit()
            await db.refresh(job_run)
            await db.refresh(job_run2)
            for item in all_exec_jobs:
                await db.refresh(item[0])

            # Create execution records (these are what the /metrics query reads)
            exec_run  = JobExecution(job_id=job_run.id,  worker_id=worker.id,  status=JobStatus.running, started_at=now - datetime.timedelta(seconds=12))
            exec_run2 = JobExecution(job_id=job_run2.id, worker_id=worker2.id, status=JobStatus.running, started_at=now - datetime.timedelta(seconds=7))
            db.add_all([exec_run, exec_run2])

            for job, status, started, finished, duration in all_exec_jobs:
                db.add(JobExecution(
                    job_id=job.id,
                    worker_id=worker.id if random.random() > 0.4 else worker2.id,
                    status=status,
                    started_at=started,
                    finished_at=finished,
                    duration_ms=duration,
                    error_msg="Simulated error" if status == JobStatus.failed else None,
                ))
            await db.commit()

            # 7. Seed DLQ Entry
            dlq_job = Job(queue_id=q1.id, job_type=JobType.immediate, status=JobStatus.dead,
                          payload={"to": "invalid-email"}, attempt_count=5, max_attempts=5,
                          run_at=now)
            db.add(dlq_job)
            await db.commit()
            await db.refresh(dlq_job)

            dlq_entry = DeadLetterEntry(
                job_id=dlq_job.id, queue_id=q1.id, payload=dlq_job.payload,
                failure_reason="SMTP Connect Error: connection refused after 5 retries",
                attempt_count=5, first_failed_at=now,
            )
            db.add(dlq_entry)
            await db.commit()

            log.info("Realistic demo data seeded: %d throughput execution rows across 12 hours.",
                     len(all_exec_jobs))


@asynccontextmanager
async def lifespan(app: FastAPI):
    await run_migrations()
    await run_seed()
    yield


app = FastAPI(
    title="Distributed Job Scheduler",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(org_router, prefix="/api/v1")
app.include_router(project_router, prefix="/api/v1")
app.include_router(queue_router, prefix="/api/v1")
app.include_router(job_router, prefix="/api/v1")
app.include_router(dlq_router, prefix="/api/v1")
app.include_router(metrics_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok"}


# ---- Unified error envelope ----

@app.middleware("http")
async def request_log(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    log.info(
        "%s %s %s %.1fms",
        request.method,
        request.url.path,
        response.status_code,
        (time.perf_counter() - started) * 1000,
    )
    return response


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": str(exc.detail)},
        headers=exc.headers,
    )

@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"error": "Validation error", "detail": jsonable_encoder(exc.errors())},
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception):
    log.exception("Unhandled error for %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"error": "Internal server error"})
