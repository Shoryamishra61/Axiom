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

            # 5. Seed Worker
            worker = Worker(hostname="demo-worker-01", pid=1024, status=WorkerStatus.active)
            db.add(worker)
            await db.commit()
            await db.refresh(worker)

            hb = WorkerHeartbeat(worker_id=worker.id, active_jobs=3)
            db.add(hb)

            # 6. Seed Jobs
            now = datetime.datetime.now(datetime.timezone.utc)
            job_done = Job(queue_id=q1.id, job_type=JobType.immediate, status=JobStatus.completed, payload={"to": "user@example.com"}, run_at=now, completed_at=now)
            job_run = Job(queue_id=q1.id, job_type=JobType.immediate, status=JobStatus.running, payload={"to": "admin@example.com"}, claimed_by=worker.id, run_at=now)
            job_queue = Job(queue_id=q1.id, job_type=JobType.immediate, status=JobStatus.queued, payload={"to": "billing@example.com"}, run_at=now)
            db.add_all([job_done, job_run, job_queue])
            await db.commit()
            await db.refresh(job_done)
            await db.refresh(job_run)

            from models import JobExecution
            exec_done = JobExecution(job_id=job_done.id, worker_id=worker.id, status=JobStatus.completed, started_at=now - datetime.timedelta(seconds=5), finished_at=now, duration_ms=5000)
            exec_run = JobExecution(job_id=job_run.id, worker_id=worker.id, status=JobStatus.running, started_at=now)
            db.add_all([exec_done, exec_run])
            await db.commit()

            # 7. Seed DLQ Entry
            dlq_job = Job(queue_id=q1.id, job_type=JobType.immediate, status=JobStatus.dead, payload={"to": "invalid-email"}, attempt_count=5, max_attempts=5, run_at=datetime.datetime.now(datetime.timezone.utc))
            db.add(dlq_job)
            await db.commit()
            await db.refresh(dlq_job)
            
            dlq_entry = DeadLetterEntry(job_id=dlq_job.id, queue_id=q1.id, payload=dlq_job.payload, failure_reason="SMTP Connect Error", attempt_count=5, first_failed_at=datetime.datetime.now(datetime.timezone.utc))
            db.add(dlq_entry)
            await db.commit()

            log.info("Realistic demo data seeded.")


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
