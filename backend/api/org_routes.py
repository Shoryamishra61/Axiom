from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_db
from models import Organization, User
from schemas import OrgCreate, OrgOut

router = APIRouter(prefix="/orgs", tags=["organizations"])


@router.post("", response_model=OrgOut, status_code=201)
async def create_org(body: OrgCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    org = Organization(name=body.name, owner_id=user.id)
    db.add(org)
    await db.commit()
    await db.refresh(org)
    return org


@router.get("", response_model=list[OrgOut])
async def list_orgs(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(select(Organization).where(Organization.owner_id == user.id))
    return result.scalars().all()


@router.get("/{org_id}", response_model=OrgOut)
async def get_org(org_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(
        select(Organization).where(Organization.id == org_id, Organization.owner_id == user.id)
    )
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(404, "Organization not found")
    return org


@router.delete("/{org_id}", status_code=204)
async def delete_org(org_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(
        select(Organization).where(Organization.id == org_id, Organization.owner_id == user.id)
    )
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(404, "Organization not found")
    await db.delete(org)
    await db.commit()
