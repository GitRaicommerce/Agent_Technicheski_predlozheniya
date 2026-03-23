from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select, func, distinct
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from datetime import datetime, timezone

from app.core.database import get_db
from app.core.models import Project, ProjectFile, TpOutline, Generation
from app.core.storage import storage

router = APIRouter()


class ProjectCreate(BaseModel):
    name: str
    location: Optional[str] = None
    description: Optional[str] = None
    contracting_authority: Optional[str] = None
    tender_date: Optional[datetime] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    contracting_authority: Optional[str] = None
    tender_date: Optional[datetime] = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    location: Optional[str]
    description: Optional[str]
    contracting_authority: Optional[str]
    tender_date: Optional[datetime]
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


@router.post("/", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(data: ProjectCreate, db: AsyncSession = Depends(get_db)):
    project = Project(**data.model_dump())
    db.add(project)
    await db.flush()
    await db.refresh(project)
    return project


@router.get("/", response_model=list[ProjectResponse])
async def list_projects(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Project).order_by(Project.created_at.desc()).offset(offset).limit(limit)
    )
    return result.scalars().all()


class ProjectStat(BaseModel):
    files: int
    outline_locked: bool
    sections_generated: int
    sections_selected: int


@router.get("/stats", response_model=dict[str, ProjectStat])
async def project_stats(db: AsyncSession = Depends(get_db)):
    """Aggregate stats for all projects in a single round-trip."""
    files_result = await db.execute(
        select(ProjectFile.project_id, func.count(ProjectFile.id).label("cnt"))
        .group_by(ProjectFile.project_id)
    )
    files_map: dict[str, int] = {row.project_id: row.cnt for row in files_result}

    outlines_result = await db.execute(
        select(TpOutline.project_id)
        .where(TpOutline.status_locked.is_(True))
        .distinct()
    )
    outline_locked_set: set[str] = {row.project_id for row in outlines_result}

    gen_result = await db.execute(
        select(
            Generation.project_id,
            func.count(distinct(Generation.section_uid)).label("generated"),
        ).group_by(Generation.project_id)
    )
    gen_map: dict[str, int] = {row.project_id: row.generated for row in gen_result}

    sel_result = await db.execute(
        select(
            Generation.project_id,
            func.count(distinct(Generation.section_uid)).label("selected"),
        )
        .where(Generation.selected.is_(True))
        .group_by(Generation.project_id)
    )
    sel_map: dict[str, int] = {row.project_id: row.selected for row in sel_result}

    projects_result = await db.execute(select(Project.id))
    all_ids = [row.id for row in projects_result]

    return {
        pid: ProjectStat(
            files=files_map.get(pid, 0),
            outline_locked=pid in outline_locked_set,
            sections_generated=gen_map.get(pid, 0),
            sections_selected=sel_map.get(pid, 0),
        )
        for pid in all_ids
    }


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str,
    data: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    project.updated_at = datetime.now(timezone.utc)

    await db.flush()
    await db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: str, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Delete all files from MinIO before removing DB records
    files_result = await db.execute(
        select(ProjectFile).where(ProjectFile.project_id == project_id)
    )
    for pf in files_result.scalars().all():
        await storage.delete_object(pf.storage_key)

    await db.delete(project)
