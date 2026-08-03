"""Review and editing API for the v2 understanding artifacts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.understanding import (
    create_understanding_job,
    ensure_v2_enabled,
)
from app.core.database import get_db
from app.core.models import (
    ExtractedChunk,
    GenerationJob,
    Project,
    ProjectFactSheet,
    ProjectFile,
    RequirementRegister,
    WbsItem,
)

router = APIRouter()


def _require_v2() -> None:
    try:
        ensure_v2_enabled()
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


class RequirementCreate(BaseModel):
    source_file_id: str
    source_page: int | None = None
    source_quote: str = Field(min_length=1)
    normalized_text: str = Field(min_length=1)
    kind: Literal["obligation", "prohibition", "format", "content", "evaluation"]
    target_section_hint: str | None = None
    status: Literal["extracted", "confirmed", "rejected"] = "extracted"


class RequirementUpdate(BaseModel):
    source_file_id: str | None = None
    source_page: int | None = None
    source_quote: str | None = Field(default=None, min_length=1)
    normalized_text: str | None = Field(default=None, min_length=1)
    kind: Literal["obligation", "prohibition", "format", "content", "evaluation"] | None = None
    target_section_hint: str | None = None
    status: Literal["extracted", "confirmed", "rejected"] | None = None


class RequirementResponse(RequirementCreate):
    id: str
    project_id: str
    created_at: datetime

    model_config = {"from_attributes": True}


class WbsCreate(BaseModel):
    parent_id: str | None = None
    level: int = Field(default=0, ge=0, le=10)
    kind: Literal["etap", "activity", "subactivity", "task"]
    title: str = Field(min_length=1, max_length=1024)
    description: str | None = None
    source_refs_json: list[dict[str, Any]] = Field(default_factory=list)
    schedule_task_uid: str | None = None
    order_index: int = Field(default=0, ge=0)
    status: Literal["extracted", "confirmed", "rejected"] = "extracted"


class WbsUpdate(BaseModel):
    parent_id: str | None = None
    level: int | None = Field(default=None, ge=0, le=10)
    kind: Literal["etap", "activity", "subactivity", "task"] | None = None
    title: str | None = Field(default=None, min_length=1, max_length=1024)
    description: str | None = None
    source_refs_json: list[dict[str, Any]] | None = None
    schedule_task_uid: str | None = None
    order_index: int | None = Field(default=None, ge=0)
    status: Literal["extracted", "confirmed", "rejected"] | None = None


class WbsResponse(WbsCreate):
    id: str
    project_id: str

    model_config = {"from_attributes": True}


class FactSheetUpdate(BaseModel):
    facts_json: dict[str, Any]
    status: Literal["draft", "confirmed"] = "draft"


class FactSheetResponse(FactSheetUpdate):
    id: str
    project_id: str
    version: int

    model_config = {"from_attributes": True}


class UnderstandingJobResponse(BaseModel):
    id: str
    project_id: str
    status: str
    total_batches: int
    completed_batches: int
    current_step: str | None = None
    error: str | None = None
    result_json: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class UnderstandingWorkspaceResponse(BaseModel):
    enabled: bool = True
    sources: list[dict[str, str]]
    requirements: list[RequirementResponse]
    wbs_items: list[WbsResponse]
    fact_sheet: FactSheetResponse | None
    latest_job: UnderstandingJobResponse | None


def _job_response(job: GenerationJob) -> UnderstandingJobResponse:
    return UnderstandingJobResponse(
        id=job.id,
        project_id=job.project_id,
        status=job.status,
        total_batches=job.total_sections or 0,
        completed_batches=job.completed_sections or 0,
        current_step=job.current_section_title,
        error=job.error,
        result_json=job.result_json,
        created_at=job.created_at,
        updated_at=job.updated_at,
        completed_at=job.completed_at,
    )


async def _project_or_404(project_id: str, db: AsyncSession) -> Project:
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def _validate_requirement_source(
    project_id: str,
    source_file_id: str,
    source_quote: str,
    db: AsyncSession,
) -> None:
    file = await db.get(ProjectFile, source_file_id)
    if not file or file.project_id != project_id or file.module != "tender_docs":
        raise HTTPException(status_code=400, detail="Invalid tender source file")
    quote_result = await db.execute(
        select(ExtractedChunk.text)
        .where(
            ExtractedChunk.project_id == project_id,
            ExtractedChunk.file_id == source_file_id,
        )
    )
    if not any(source_quote in (text or "") for text in quote_result.scalars().all()):
        raise HTTPException(
            status_code=400,
            detail="Source quote must be verbatim text from the selected file",
        )


@router.get("/{project_id}", response_model=UnderstandingWorkspaceResponse)
async def get_understanding_workspace(
    project_id: str, db: AsyncSession = Depends(get_db)
):
    _require_v2()
    await _project_or_404(project_id, db)
    source_result = await db.execute(
        select(ProjectFile)
        .where(
            ProjectFile.project_id == project_id,
            ProjectFile.module == "tender_docs",
        )
        .order_by(ProjectFile.filename, ProjectFile.id)
    )
    requirement_result = await db.execute(
        select(RequirementRegister)
        .where(RequirementRegister.project_id == project_id)
        .order_by(RequirementRegister.created_at, RequirementRegister.id)
    )
    wbs_result = await db.execute(
        select(WbsItem)
        .where(WbsItem.project_id == project_id)
        .order_by(WbsItem.order_index, WbsItem.id)
    )
    fact_result = await db.execute(
        select(ProjectFactSheet)
        .where(ProjectFactSheet.project_id == project_id)
        .order_by(ProjectFactSheet.version.desc())
        .limit(1)
    )
    job_result = await db.execute(
        select(GenerationJob)
        .where(
            GenerationJob.project_id == project_id,
            GenerationJob.job_type == "understanding",
        )
        .order_by(GenerationJob.created_at.desc())
        .limit(1)
    )
    job = job_result.scalar_one_or_none()
    return UnderstandingWorkspaceResponse(
        sources=[
            {"id": file.id, "filename": file.filename}
            for file in source_result.scalars().all()
        ],
        requirements=requirement_result.scalars().all(),
        wbs_items=wbs_result.scalars().all(),
        fact_sheet=fact_result.scalar_one_or_none(),
        latest_job=_job_response(job) if job else None,
    )


@router.post(
    "/{project_id}/jobs",
    response_model=UnderstandingJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_understanding_job(
    project_id: str, db: AsyncSession = Depends(get_db)
):
    _require_v2()
    project = await _project_or_404(project_id, db)
    try:
        job = await create_understanding_job(project, db)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _job_response(job)


@router.get(
    "/{project_id}/jobs/{job_id}", response_model=UnderstandingJobResponse
)
async def get_understanding_job(
    project_id: str, job_id: str, db: AsyncSession = Depends(get_db)
):
    _require_v2()
    job = await db.get(GenerationJob, job_id)
    if not job or job.project_id != project_id or job.job_type != "understanding":
        raise HTTPException(status_code=404, detail="Understanding job not found")
    return _job_response(job)


@router.post(
    "/{project_id}/requirements",
    response_model=RequirementResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_requirement(
    project_id: str,
    data: RequirementCreate,
    db: AsyncSession = Depends(get_db),
):
    _require_v2()
    await _project_or_404(project_id, db)
    await _validate_requirement_source(
        project_id, data.source_file_id, data.source_quote, db
    )
    item = RequirementRegister(project_id=project_id, **data.model_dump())
    db.add(item)
    await db.flush()
    await db.refresh(item)
    return item


@router.put(
    "/{project_id}/requirements/{item_id}", response_model=RequirementResponse
)
async def update_requirement(
    project_id: str,
    item_id: str,
    data: RequirementUpdate,
    db: AsyncSession = Depends(get_db),
):
    _require_v2()
    item = await db.get(RequirementRegister, item_id)
    if not item or item.project_id != project_id:
        raise HTTPException(status_code=404, detail="Requirement not found")
    values = data.model_dump(exclude_unset=True)
    source_file_id = values.get("source_file_id", item.source_file_id)
    source_quote = values.get("source_quote", item.source_quote)
    if "source_file_id" in values or "source_quote" in values:
        await _validate_requirement_source(
            project_id, source_file_id, source_quote, db
        )
    for field, value in values.items():
        setattr(item, field, value)
    await db.flush()
    return item


@router.delete(
    "/{project_id}/requirements/{item_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_requirement(
    project_id: str, item_id: str, db: AsyncSession = Depends(get_db)
):
    _require_v2()
    item = await db.get(RequirementRegister, item_id)
    if not item or item.project_id != project_id:
        raise HTTPException(status_code=404, detail="Requirement not found")
    await db.delete(item)


@router.post("/{project_id}/requirements/confirm")
async def confirm_requirements(
    project_id: str, db: AsyncSession = Depends(get_db)
):
    _require_v2()
    await _project_or_404(project_id, db)
    result = await db.execute(
        update(RequirementRegister)
        .where(
            RequirementRegister.project_id == project_id,
            RequirementRegister.status != "rejected",
        )
        .values(status="confirmed")
    )
    return {"status": "confirmed", "updated": result.rowcount or 0}


@router.post(
    "/{project_id}/wbs",
    response_model=WbsResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_wbs_item(
    project_id: str, data: WbsCreate, db: AsyncSession = Depends(get_db)
):
    _require_v2()
    await _project_or_404(project_id, db)
    if data.parent_id:
        parent = await db.get(WbsItem, data.parent_id)
        if not parent or parent.project_id != project_id:
            raise HTTPException(status_code=400, detail="Invalid WBS parent")
    item = WbsItem(project_id=project_id, **data.model_dump())
    db.add(item)
    await db.flush()
    return item


@router.put("/{project_id}/wbs/{item_id}", response_model=WbsResponse)
async def update_wbs_item(
    project_id: str,
    item_id: str,
    data: WbsUpdate,
    db: AsyncSession = Depends(get_db),
):
    _require_v2()
    item = await db.get(WbsItem, item_id)
    if not item or item.project_id != project_id:
        raise HTTPException(status_code=404, detail="WBS item not found")
    values = data.model_dump(exclude_unset=True)
    parent_id = values.get("parent_id")
    if parent_id == item_id:
        raise HTTPException(status_code=400, detail="WBS item cannot parent itself")
    if parent_id:
        parent = await db.get(WbsItem, parent_id)
        if not parent or parent.project_id != project_id:
            raise HTTPException(status_code=400, detail="Invalid WBS parent")
    for field, value in values.items():
        setattr(item, field, value)
    await db.flush()
    return item


@router.delete("/{project_id}/wbs/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_wbs_item(
    project_id: str, item_id: str, db: AsyncSession = Depends(get_db)
):
    _require_v2()
    item = await db.get(WbsItem, item_id)
    if not item or item.project_id != project_id:
        raise HTTPException(status_code=404, detail="WBS item not found")
    await db.delete(item)


@router.post("/{project_id}/wbs/confirm")
async def confirm_wbs(project_id: str, db: AsyncSession = Depends(get_db)):
    _require_v2()
    await _project_or_404(project_id, db)
    result = await db.execute(
        update(WbsItem)
        .where(WbsItem.project_id == project_id, WbsItem.status != "rejected")
        .values(status="confirmed")
    )
    return {"status": "confirmed", "updated": result.rowcount or 0}


@router.put("/{project_id}/fact-sheet", response_model=FactSheetResponse)
async def update_fact_sheet(
    project_id: str,
    data: FactSheetUpdate,
    db: AsyncSession = Depends(get_db),
):
    _require_v2()
    await _project_or_404(project_id, db)
    result = await db.execute(
        select(ProjectFactSheet)
        .where(ProjectFactSheet.project_id == project_id)
        .order_by(ProjectFactSheet.version.desc())
        .limit(1)
    )
    fact_sheet = result.scalar_one_or_none()
    if fact_sheet:
        fact_sheet.facts_json = data.facts_json
        fact_sheet.status = data.status
    else:
        fact_sheet = ProjectFactSheet(
            project_id=project_id,
            version=1,
            facts_json=data.facts_json,
            status=data.status,
        )
        db.add(fact_sheet)
    await db.flush()
    return fact_sheet


@router.post("/{project_id}/fact-sheet/confirm", response_model=FactSheetResponse)
async def confirm_fact_sheet(
    project_id: str, db: AsyncSession = Depends(get_db)
):
    _require_v2()
    result = await db.execute(
        select(ProjectFactSheet)
        .where(ProjectFactSheet.project_id == project_id)
        .order_by(ProjectFactSheet.version.desc())
        .limit(1)
    )
    fact_sheet = result.scalar_one_or_none()
    if not fact_sheet:
        raise HTTPException(status_code=404, detail="Fact sheet not found")
    fact_sheet.status = "confirmed"
    await db.flush()
    return fact_sheet
