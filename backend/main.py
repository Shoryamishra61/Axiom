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
    db_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
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
    """Seed the default test user if it doesn't exist."""
    from auth import hash_password
    from database import AsyncSessionLocal
    from models import User
    from sqlalchemy import select
    async with AsyncSessionLocal() as db:
        exists = await db.execute(select(User).where(User.email == "shoryamishra61@gmail.com"))
        if not exists.scalar_one_or_none():
            db.add(User(email="shoryamishra61@gmail.com", name="Shorya Mishra", password_hash=hash_password("password")))
            await db.commit()
            log.info("Test user seeded.")


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
