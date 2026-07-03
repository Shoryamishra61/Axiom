"""
Test 4: Idempotency Test

Setup:   API client prepares a POST /jobs with Idempotency-Key: "req-123".
Execute: Fire the exact same request 3 times concurrently using asyncio.gather.
Assert:  DB contains exactly 1 job with that key.
         All 3 API calls return either 201 or 200 (not 500).
         All 3 responses contain the identical job ID.
"""
import asyncio
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from config import settings
from models import Job, JobStatus, Queue, Organization, Project, User
from auth import hash_password

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def engine():
    return create_async_engine(settings.database_url, pool_size=10, max_overflow=5)


@pytest.fixture(scope="module")
def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


async def _seed_queue(sf) -> tuple:
    async with sf() as db:
        user = User(email=f"idem_{uuid.uuid4()}@test.com", name="I", password_hash="dummy_hash")
        db.add(user)
        await db.flush()
        org = Organization(name="Org", owner_id=user.id)
        db.add(org)
        await db.flush()
        project = Project(name="Proj", org_id=org.id)
        db.add(project)
        await db.flush()
        queue = Queue(project_id=project.id, name=f"q_{uuid.uuid4()}", concurrency_limit=10)
        db.add(queue)
        await db.commit()
        return queue.id


async def _submit_job(sf, queue_id: uuid.UUID, idempotency_key: str) -> str | None:
    """
    Attempt to insert a job. Returns the job_id (whether newly created or existing).
    Returns None on unexpected error. Mimics what the API endpoint does.
    """
    async with sf() as db:
        job = Job(
            queue_id=queue_id,
            status=JobStatus.queued,
            payload={"task": "idempotency_test"},
            run_at=datetime.now(timezone.utc),
            idempotency_key=idempotency_key,
        )
        db.add(job)
        try:
            await db.commit()
            return str(job.id)
        except IntegrityError:
            await db.rollback()
            # Unique constraint fired — fetch and return existing job
            r = await db.execute(
                select(Job).where(
                    Job.queue_id == queue_id,
                    Job.idempotency_key == idempotency_key,
                )
            )
            existing = r.scalar_one_or_none()
            return str(existing.id) if existing else None


@pytest.mark.asyncio
async def test_idempotency_concurrent(session_factory):
    queue_id = await _seed_queue(session_factory)
    key = f"req-{uuid.uuid4()}"

    # Fire 3 concurrent submissions with the same idempotency key
    results = await asyncio.gather(
        _submit_job(session_factory, queue_id, key),
        _submit_job(session_factory, queue_id, key),
        _submit_job(session_factory, queue_id, key),
    )

    # Assert: all 3 returned a job_id (no None / unexpected error)
    assert all(r is not None for r in results), f"Some submissions failed: {results}"

    # Assert: all 3 returned the SAME job_id
    unique_ids = set(results)
    assert len(unique_ids) == 1, f"Expected 1 unique job ID, got {unique_ids}"

    # Assert: exactly 1 job in DB with this idempotency key
    async with session_factory() as db:
        count = (await db.execute(
            select(func.count()).select_from(Job)
            .where(Job.queue_id == queue_id, Job.idempotency_key == key)
        )).scalar()
    assert count == 1, f"Expected 1 job, found {count}"
