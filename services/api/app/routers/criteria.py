"""API for Phase 5.1 criterion-level verification of generated text."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.criteria_verifier import (
    create_criteria_job,
    ensure_v2_enabled,
)
from app.core.database import get_db
from app.core.models import CriterionCheck, GenerationJob, Project

router = APIRouter()


def _require_v2() -> None:
    try:
        ensure_v2_enabled()
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


class CriterionCheckResponse(BaseModel):
    id: str
    generation_id: str
    section_uid: str
    criterion_id: str
    criterion_text: str
    criterion_kind: str
    requirement_id: str | None = None
    source_quote: str | None = None
    verdict: str
    evidence: str | None = None
    note: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CriteriaJobResponse(BaseModel):
    id: str
    project_id: str
    status: str
    total_sections: int
    completed_sections: int
    current_step: str | None = None
    error: str | None = None
    result_json: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class CriteriaWorkspaceResponse(BaseModel):
    enabled: bool = True
    checks: list[CriterionCheckResponse]
    totals: dict[str, int]
    latest_job: CriteriaJobResponse | None


def _job_response(job: GenerationJob) -> CriteriaJobResponse:
    return CriteriaJobResponse(
        id=job.id,
        project_id=job.project_id,
        status=job.status,
        total_sections=job.total_sections or 0,
        completed_sections=job.completed_sections or 0,
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


@router.get("/{project_id}", response_model=CriteriaWorkspaceResponse)
async def get_criteria_workspace(
    project_id: str, db: AsyncSession = Depends(get_db)
):
    _require_v2()
    await _project_or_404(project_id, db)
    checks_result = await db.execute(
        select(CriterionCheck)
        .where(CriterionCheck.project_id == project_id)
        .order_by(
            CriterionCheck.section_uid,
            CriterionCheck.criterion_id,
        )
    )
    checks = list(checks_result.scalars().all())
    totals = {
        "total": len(checks),
        "covered": 0,
        "partial": 0,
        "missing": 0,
        "violated": 0,
        "unchecked": 0,
    }
    for check in checks:
        if check.verdict in totals:
            totals[check.verdict] += 1
    job_result = await db.execute(
        select(GenerationJob)
        .where(
            GenerationJob.project_id == project_id,
            GenerationJob.job_type == "criteria_verification",
        )
        .order_by(GenerationJob.created_at.desc())
        .limit(1)
    )
    job = job_result.scalar_one_or_none()
    return CriteriaWorkspaceResponse(
        checks=checks,
        totals=totals,
        latest_job=_job_response(job) if job else None,
    )


@router.post(
    "/{project_id}/jobs",
    response_model=CriteriaJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_criteria_job(
    project_id: str, db: AsyncSession = Depends(get_db)
):
    _require_v2()
    project = await _project_or_404(project_id, db)
    try:
        job = await create_criteria_job(project, db)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _job_response(job)


@router.get("/{project_id}/jobs/{job_id}", response_model=CriteriaJobResponse)
async def get_criteria_job(
    project_id: str, job_id: str, db: AsyncSession = Depends(get_db)
):
    _require_v2()
    job = await db.get(GenerationJob, job_id)
    if (
        not job
        or job.project_id != project_id
        or job.job_type != "criteria_verification"
    ):
        raise HTTPException(status_code=404, detail="Criteria job not found")
    return _job_response(job)
