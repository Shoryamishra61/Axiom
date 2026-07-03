import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from auth import get_current_user
from database import get_db
from models import Job, JobExecution, JobLog, JobStatus, JobType, Organization, Project, Queue, ScheduledJob, User
from schemas import BatchJobOut, ExecutionOut, JobCreate, JobLogOut, JobOut, JobPage, ScheduledJobCreate, ScheduledJobOut

router = APIRouter(tags=["jobs"])


# ---- multi-tenant queue guard ----
async def _get_queue_for_user(queue_id: str, user_id, db: AsyncSession) -> Queue:
    r = await db.execute(
        select(Queue).options(selectinload(Queue.retry_policy))
        .join(Project, Queue.project_id == Project.id)
        .join(Organization, Project.org_id == Organization.id)
        .where(Queue.id == queue_id, Organization.owner_id == user_id)
    )
    q = r.scalar_one_or_none()
    if not q:
        raise HTTPException(404, "Queue not found")
    return q


async def _get_job_for_user(job_id: str, user_id, db: AsyncSession) -> Job:
    r = await db.execute(
        select(Job)
        .join(Queue, Job.queue_id == Queue.id)
        .join(Project, Queue.project_id == Project.id)
        .join(Organization, Project.org_id == Organization.id)
        .where(Job.id == job_id, Organization.owner_id == user_id)
    )
    j = r.scalar_one_or_none()
    if not j:
        raise HTTPException(404, "Job not found")
    return j


# ---- Job submission ----

@router.post(
    "/queues/{queue_id}/jobs",
    response_model=JobOut | ScheduledJobOut | BatchJobOut,
    status_code=201,
)
async def create_job(
    queue_id: str,
    body: JobCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    queue = await _get_queue_for_user(queue_id, user.id, db)

    job_type = body.job_type

    if job_type == "cron":
        from croniter import croniter
        if not croniter.is_valid(body.cron_expr):
            raise HTTPException(422, f"Invalid cron expression: {body.cron_expr}")
        sj = ScheduledJob(
            queue_id=queue.id,
            cron_expr=body.cron_expr,
            payload=body.payload,
            priority=body.priority,
            max_attempts=_max_attempts(queue, body),
        )
        db.add(sj)
        await db.commit()
        await db.refresh(sj)
        return sj

    if job_type == "batch":
        batch_id = uuid.uuid4()
        jobs = [_make_job(queue, bj, None, batch_id=batch_id) for bj in body.batch_jobs]
        db.add_all(jobs)
        await db.commit()
        for job in jobs:
            await db.refresh(job)
        return BatchJobOut(batch_id=batch_id, jobs=jobs)

    # --- Idempotency: concurrent-safe INSERT with ON CONFLICT handling ---
    # We attempt the insert; if the unique constraint fires (concurrent dup),
    # we catch IntegrityError and return the already-existing job with 200.
    job = _make_job(queue, body, idempotency_key)
    db.add(job)
    try:
        await db.commit()
        await db.refresh(job)
        return job
    except IntegrityError:
        # Unique constraint on (queue_id, idempotency_key) fired — return existing
        await db.rollback()
        if not idempotency_key:
            raise HTTPException(409, "Duplicate job")
        r = await db.execute(
            select(Job).where(Job.queue_id == queue.id, Job.idempotency_key == idempotency_key)
        )
        existing = r.scalar_one_or_none()
        if not existing:
            raise HTTPException(409, "Conflict: duplicate submission")
        # Return 200 (not 201) with the identical existing job
        from fastapi.responses import JSONResponse
        from schemas import JobOut as JobOutSchema
        return JSONResponse(
            status_code=200,
            content=JobOutSchema.model_validate(existing).model_dump(mode="json"),
        )


def _make_job(queue: Queue, body: JobCreate, idempotency_key=None, batch_id=None) -> Job:
    run_at = body.run_at or datetime.now(timezone.utc)
    status = JobStatus.queued
    if body.run_at and body.run_at > datetime.now(timezone.utc):
        status = JobStatus.scheduled
    return Job(
        queue_id=queue.id,
        job_type=body.job_type,
        status=status,
        payload=body.payload,
        priority=body.priority,
        run_at=run_at,
        idempotency_key=idempotency_key,
        max_attempts=_max_attempts(queue, body),
        batch_id=batch_id,
    )


def _max_attempts(queue: Queue, body: JobCreate) -> int:
    if body.max_attempts is not None:
        return body.max_attempts
    return queue.retry_policy.max_attempts if queue.retry_policy else 3


# ---- List / filter jobs ----

@router.get("/queues/{queue_id}/jobs", response_model=JobPage)
async def list_jobs(
    queue_id: str,
    status: Optional[JobStatus] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _get_queue_for_user(queue_id, user.id, db)
    filters = [Job.queue_id == queue_id]
    if status:
        filters.append(Job.status == status)
    total = (await db.execute(select(func.count()).select_from(Job).where(*filters))).scalar() or 0
    q = select(Job).where(*filters)
    q = q.order_by(Job.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    r = await db.execute(q)
    return JobPage(total=total, page=page, page_size=page_size, items=r.scalars().all())


@router.get("/jobs/{job_id}", response_model=JobOut)
async def get_job(job_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await _get_job_for_user(job_id, user.id, db)


@router.delete("/jobs/{job_id}", status_code=204)
async def cancel_job(job_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    from sqlalchemy import update
    job = await _get_job_for_user(job_id, user.id, db)
    if job.status in (JobStatus.running, JobStatus.claimed):
        raise HTTPException(409, "Cannot cancel a running/claimed job")
    await db.execute(update(Job).where(Job.id == job.id).values(status=JobStatus.cancelled))
    await db.commit()


# ---- Executions + Logs ----

@router.get("/jobs/{job_id}/executions", response_model=list[ExecutionOut])
async def list_executions(job_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await _get_job_for_user(job_id, user.id, db)
    r = await db.execute(select(JobExecution).where(JobExecution.job_id == job_id).order_by(JobExecution.started_at))
    return r.scalars().all()


@router.get("/executions/{execution_id}/logs", response_model=list[JobLogOut])
async def list_logs(execution_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    access = await db.execute(
        select(JobExecution.id)
        .join(Job, JobExecution.job_id == Job.id)
        .join(Queue, Job.queue_id == Queue.id)
        .join(Project, Queue.project_id == Project.id)
        .join(Organization, Project.org_id == Organization.id)
        .where(JobExecution.id == execution_id, Organization.owner_id == user.id)
    )
    if access.scalar_one_or_none() is None:
        raise HTTPException(404, "Execution not found")
    r = await db.execute(select(JobLog).where(JobLog.execution_id == execution_id).order_by(JobLog.logged_at))
    return r.scalars().all()


# ---- Scheduled jobs (cron definitions) ----

@router.post("/queues/{queue_id}/scheduled-jobs", response_model=ScheduledJobOut, status_code=201)
async def create_scheduled_job(
    queue_id: str,
    body: ScheduledJobCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from croniter import croniter
    if not croniter.is_valid(body.cron_expr):
        raise HTTPException(422, f"Invalid cron expression: {body.cron_expr}")
    queue = await _get_queue_for_user(queue_id, user.id, db)
    sj = ScheduledJob(
        queue_id=queue_id,
        cron_expr=body.cron_expr,
        payload=body.payload,
        priority=body.priority,
        max_attempts=body.max_attempts or (queue.retry_policy.max_attempts if queue.retry_policy else 3),
    )
    db.add(sj)
    await db.commit()
    await db.refresh(sj)
    return sj


@router.get("/queues/{queue_id}/scheduled-jobs", response_model=list[ScheduledJobOut])
async def list_scheduled_jobs(
    queue_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _get_queue_for_user(queue_id, user.id, db)
    r = await db.execute(select(ScheduledJob).where(ScheduledJob.queue_id == queue_id))
    return r.scalars().all()


@router.delete("/scheduled-jobs/{sj_id}", status_code=204)
async def delete_scheduled_job(sj_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    r = await db.execute(select(ScheduledJob).where(ScheduledJob.id == sj_id))
    sj = r.scalar_one_or_none()
    if not sj:
        raise HTTPException(404, "Scheduled job not found")
    await _get_queue_for_user(str(sj.queue_id), user.id, db)
    await db.delete(sj)
    await db.commit()
