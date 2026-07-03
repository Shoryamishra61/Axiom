from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_db
from models import DeadLetterEntry, Job, JobStatus, Organization, Project, Queue, User
from schemas import DLQEntryOut

router = APIRouter(prefix="/queues/{queue_id}/dlq", tags=["dlq"])


async def _check_queue_access(queue_id: str, user_id, db: AsyncSession) -> Queue:
    r = await db.execute(
        select(Queue)
        .join(Project, Queue.project_id == Project.id)
        .join(Organization, Project.org_id == Organization.id)
        .where(Queue.id == queue_id, Organization.owner_id == user_id)
    )
    q = r.scalar_one_or_none()
    if not q:
        raise HTTPException(404, "Queue not found")
    return q


@router.get("", response_model=list[DLQEntryOut])
async def list_dlq(queue_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await _check_queue_access(queue_id, user.id, db)
    r = await db.execute(
        select(DeadLetterEntry)
        .where(DeadLetterEntry.queue_id == queue_id)
        .order_by(DeadLetterEntry.dead_at.desc())
    )
    return r.scalars().all()


@router.post("/{entry_id}/retry", response_model=dict, status_code=202)
async def retry_dlq_entry(
    queue_id: str,
    entry_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _check_queue_access(queue_id, user.id, db)
    r = await db.execute(
        select(DeadLetterEntry)
        .where(DeadLetterEntry.id == entry_id, DeadLetterEntry.queue_id == queue_id)
        .with_for_update()
    )
    entry = r.scalar_one_or_none()
    if not entry:
        raise HTTPException(404, "DLQ entry not found")

    # Re-queue: reset the original job back to queued
    rj = await db.execute(select(Job).where(Job.id == entry.job_id))
    job = rj.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Original job no longer exists")

    job.status = JobStatus.queued
    job.attempt_count = 0
    job.claimed_by = None
    job.claimed_at = None
    job.lease_expires_at = None
    job.run_at = datetime.now(timezone.utc)
    job.completed_at = None
    await db.delete(entry)
    await db.commit()
    return {"requeued": str(job.id)}


@router.delete("/{entry_id}", status_code=204)
async def delete_dlq_entry(
    queue_id: str,
    entry_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _check_queue_access(queue_id, user.id, db)
    r = await db.execute(
        select(DeadLetterEntry).where(DeadLetterEntry.id == entry_id, DeadLetterEntry.queue_id == queue_id)
    )
    entry = r.scalar_one_or_none()
    if not entry:
        raise HTTPException(404, "DLQ entry not found")
    await db.delete(entry)
    await db.commit()
