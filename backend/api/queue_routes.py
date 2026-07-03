from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from auth import get_current_user
from database import get_db
from models import Organization, Project, Queue, RetryPolicy, User
from schemas import QueueCreate, QueueOut, QueueUpdate, RetryPolicyOut

router = APIRouter(prefix="/projects/{project_id}/queues", tags=["queues"])


async def _get_project(project_id, user_id, db: AsyncSession) -> Project:
    r = await db.execute(
        select(Project)
        .join(Organization, Project.org_id == Organization.id)
        .where(Project.id == project_id, Organization.owner_id == user_id)
    )
    p = r.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Project not found")
    return p


async def _get_queue(queue_id, project_id, db: AsyncSession) -> Queue:
    r = await db.execute(
        select(Queue).options(selectinload(Queue.retry_policy)).where(Queue.id == queue_id, Queue.project_id == project_id)
    )
    q = r.scalar_one_or_none()
    if not q:
        raise HTTPException(404, "Queue not found")
    return q


@router.post("", response_model=QueueOut, status_code=201)
async def create_queue(
    project_id: str,
    body: QueueCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _get_project(project_id, user.id, db)
    retry_policy_id = None
    if body.retry_policy:
        rp = RetryPolicy(**body.retry_policy.model_dump())
        db.add(rp)
        await db.flush()
        retry_policy_id = rp.id

    queue = Queue(
        project_id=project_id,
        name=body.name,
        priority=body.priority,
        concurrency_limit=body.concurrency_limit,
        retry_policy_id=retry_policy_id,
    )
    db.add(queue)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "A queue with this name already exists in the project")
    await db.refresh(queue, ["retry_policy"])
    return queue


@router.get("", response_model=list[QueueOut])
async def list_queues(project_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await _get_project(project_id, user.id, db)
    r = await db.execute(select(Queue).options(selectinload(Queue.retry_policy)).where(Queue.project_id == project_id))
    return r.scalars().all()


@router.get("/{queue_id}", response_model=QueueOut)
async def get_queue(project_id: str, queue_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await _get_project(project_id, user.id, db)
    return await _get_queue(queue_id, project_id, db)


@router.patch("/{queue_id}", response_model=QueueOut)
async def update_queue(
    project_id: str,
    queue_id: str,
    body: QueueUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _get_project(project_id, user.id, db)
    queue = await _get_queue(queue_id, project_id, db)
    changes = body.model_dump(exclude_none=True, exclude={"retry_policy"})
    for field, val in changes.items():
        setattr(queue, field, val)
    if body.retry_policy:
        if queue.retry_policy:
            for field, val in body.retry_policy.model_dump().items():
                setattr(queue.retry_policy, field, val)
        else:
            policy = RetryPolicy(**body.retry_policy.model_dump())
            db.add(policy)
            await db.flush()
            queue.retry_policy_id = policy.id
    await db.commit()
    await db.refresh(queue, ["retry_policy"])
    return queue


@router.post("/{queue_id}/pause", response_model=QueueOut)
async def pause_queue(project_id: str, queue_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await _get_project(project_id, user.id, db)
    queue = await _get_queue(queue_id, project_id, db)
    queue.is_paused = True
    await db.commit()
    await db.refresh(queue, ["retry_policy"])
    return queue


@router.post("/{queue_id}/resume", response_model=QueueOut)
async def resume_queue(project_id: str, queue_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await _get_project(project_id, user.id, db)
    queue = await _get_queue(queue_id, project_id, db)
    queue.is_paused = False
    await db.commit()
    await db.refresh(queue, ["retry_policy"])
    return queue


@router.delete("/{queue_id}", status_code=204)
async def delete_queue(project_id: str, queue_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await _get_project(project_id, user.id, db)
    queue = await _get_queue(queue_id, project_id, db)
    await db.delete(queue)
    await db.commit()
