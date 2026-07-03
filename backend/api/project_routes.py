from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_db
from models import Organization, Project, User
from schemas import ProjectCreate, ProjectOut

router = APIRouter(prefix="/projects", tags=["projects"])


async def _assert_org_owned(org_id, user_id, db: AsyncSession):
    """Verify org belongs to user — multi-tenancy guard."""
    r = await db.execute(select(Organization).where(Organization.id == org_id, Organization.owner_id == user_id))
    org = r.scalar_one_or_none()
    if not org:
        raise HTTPException(404, "Organization not found")
    return org


async def _get_project_for_user(project_id, user_id, db: AsyncSession) -> Project:
    r = await db.execute(
        select(Project)
        .join(Organization, Project.org_id == Organization.id)
        .where(Project.id == project_id, Organization.owner_id == user_id)
    )
    p = r.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Project not found")
    return p


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(body: ProjectCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await _assert_org_owned(body.org_id, user.id, db)
    project = Project(name=body.name, org_id=body.org_id)
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.get("", response_model=list[ProjectOut])
async def list_projects(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    r = await db.execute(
        select(Project)
        .join(Organization, Project.org_id == Organization.id)
        .where(Organization.owner_id == user.id)
    )
    return r.scalars().all()


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await _get_project_for_user(project_id, user.id, db)


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    p = await _get_project_for_user(project_id, user.id, db)
    await db.delete(p)
    await db.commit()
