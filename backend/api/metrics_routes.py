from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_db
from models import (
    DeadLetterEntry, Job, JobExecution, JobStatus, Organization, Project,
    Queue, Worker, WorkerHeartbeat, WorkerStatus, User,
)
from schemas import QueueMetrics, SystemMetrics, WorkerOut

router = APIRouter(tags=["metrics"])


@router.get("/workers", response_model=list[WorkerOut])
async def list_workers(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    active_jobs = (
        select(WorkerHeartbeat.active_jobs)
        .where(WorkerHeartbeat.worker_id == Worker.id)
        .order_by(WorkerHeartbeat.beat_at.desc())
        .limit(1)
        .scalar_subquery()
    )
    r = await db.execute(select(Worker, func.coalesce(active_jobs, 0)).order_by(Worker.last_seen.desc()))
    return [
        {
            "id": worker.id,
            "hostname": worker.hostname,
            "pid": worker.pid,
            "status": worker.status,
            "started_at": worker.started_at,
            "last_seen": worker.last_seen,
            "active_jobs": count,
        }
        for worker, count in r.all()
    ]


@router.get("/metrics", response_model=SystemMetrics)
async def system_metrics(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    one_hour_ago = now - timedelta(hours=1)
    chart_start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=11)
    owned_jobs = (
        select(Job.id)
        .join(Queue, Job.queue_id == Queue.id)
        .join(Project, Queue.project_id == Project.id)
        .join(Organization, Project.org_id == Organization.id)
        .where(Organization.owner_id == user.id)
    )
    owned_queues = (
        select(Queue.id)
        .join(Project, Queue.project_id == Project.id)
        .join(Organization, Project.org_id == Organization.id)
        .where(Organization.owner_id == user.id)
    )

    # ponytail: 5 focused count queries — simple and correct for demo scale
    total_queues = (await db.execute(select(func.count()).select_from(owned_queues.subquery()))).scalar()
    active_workers = (await db.execute(
        select(func.count()).select_from(Worker).where(Worker.status == WorkerStatus.active)
    )).scalar()
    pending = (await db.execute(
        select(func.count()).select_from(Job).where(
            Job.id.in_(owned_jobs), Job.status.in_([JobStatus.queued, JobStatus.scheduled])
        )
    )).scalar()
    running = (await db.execute(
        select(func.count()).select_from(Job).where(Job.id.in_(owned_jobs), Job.status == JobStatus.running)
    )).scalar()
    completed_last_hour = (await db.execute(
        select(func.count()).select_from(Job)
        .where(Job.id.in_(owned_jobs), Job.status == JobStatus.completed, Job.completed_at >= one_hour_ago)
    )).scalar()
    failed_last_hour = (await db.execute(
        select(func.count()).select_from(JobExecution)
        .where(
            JobExecution.job_id.in_(owned_jobs),
            JobExecution.status == JobStatus.failed,
            JobExecution.finished_at >= one_hour_ago,
        )
    )).scalar()

    throughput_rows = (await db.execute(
        select(
            func.date_trunc("hour", JobExecution.finished_at).label("bucket"),
            func.count().filter(JobExecution.status == JobStatus.completed).label("completed"),
            func.count().filter(JobExecution.status == JobStatus.failed).label("failed"),
        )
        .where(JobExecution.job_id.in_(owned_jobs), JobExecution.finished_at >= chart_start)
        .group_by("bucket")
        .order_by("bucket")
    )).all()

    return SystemMetrics(
        total_queues=total_queues or 0,
        active_workers=active_workers or 0,
        jobs_pending=pending or 0,
        jobs_running=running or 0,
        jobs_completed_last_hour=completed_last_hour or 0,
        jobs_failed_last_hour=failed_last_hour or 0,
        throughput=_throughput_series(throughput_rows, chart_start),
    )


def _throughput_series(rows, start: datetime) -> list[dict]:
    """Fill missing hours so an idle system renders a useful chart, not a blank box."""
    counts = {
        row.bucket.astimezone(timezone.utc): (row.completed, row.failed)
        for row in rows
    }
    return [
        {
            "time": (bucket := start + timedelta(hours=offset)).isoformat(),
            "completed": counts.get(bucket, (0, 0))[0],
            "failed": counts.get(bucket, (0, 0))[1],
        }
        for offset in range(12)
    ]


@router.get("/queues/{queue_id}/metrics", response_model=QueueMetrics)
async def queue_metrics(
    queue_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Verify access
    r = await db.execute(
        select(Queue)
        .join(Project, Queue.project_id == Project.id)
        .join(Organization, Project.org_id == Organization.id)
        .where(Queue.id == queue_id, Organization.owner_id == user.id)
    )
    queue = r.scalar_one_or_none()
    if not queue:
        from fastapi import HTTPException
        raise HTTPException(404, "Queue not found")

    counts = {}
    for st in (JobStatus.queued, JobStatus.scheduled, JobStatus.running, JobStatus.completed, JobStatus.failed):
        c = (await db.execute(
            select(func.count()).select_from(Job).where(Job.queue_id == queue_id, Job.status == st)
        )).scalar() or 0
        counts[st.value] = c

    dead = (await db.execute(
        select(func.count()).select_from(DeadLetterEntry).where(DeadLetterEntry.queue_id == queue_id)
    )).scalar() or 0

    return QueueMetrics(
        queue_id=queue.id,
        queue_name=queue.name,
        pending=counts.get("queued", 0) + counts.get("scheduled", 0),
        running=counts.get("running", 0),
        completed=counts.get("completed", 0),
        failed=counts.get("failed", 0),
        dead=dead,
    )
