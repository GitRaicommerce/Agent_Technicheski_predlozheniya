"""API for the independent plan audit (K-25) and the drafting eligibility gate."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.plan_audit import (
    apply_resolution,
    create_plan_audit_job,
    current_fingerprint,
    drafting_eligibility,
    ensure_v2_enabled,
    fingerprints_match,
    latest_audit_for_plan,
    latest_content_plan,
    overall_status,
)
from app.core.database import get_db
from app.core.models import GenerationJob, Project

router = APIRouter()


def _require_v2() -> None:
    try:
        ensure_v2_enabled()
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


class PlanAuditResponse(BaseModel):
    id: str
    status: str
    error: str | None = None
    overall: str | None = None
    stale: bool = False
    report: dict[str, Any] | None = None
    created_at: datetime
    completed_at: datetime | None = None


class PlanAuditState(BaseModel):
    audit: PlanAuditResponse | None
    eligibility: dict[str, Any]


class ResolutionRequest(BaseModel):
    key: str = Field(pattern=r"^(finding|addition):.+$")
    interpretation: str = Field(min_length=5, max_length=2000)
    reason: str = Field(min_length=10, max_length=2000)


def _audit_response(job: GenerationJob, *, stale: bool) -> PlanAuditResponse:
    report = job.result_json if isinstance(job.result_json, dict) else None
    overall = "stale" if stale and job.status == "done" else (
        overall_status(report) if report and job.status == "done" else report.get("overall") if report else None
    )
    return PlanAuditResponse(
        id=job.id,
        status=job.status,
        error=job.error,
        overall=overall,
        stale=stale,
        report=report,
        created_at=job.created_at,
        completed_at=job.completed_at,
    )


async def _project_or_404(project_id: str, db: AsyncSession) -> Project:
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/{project_id}", response_model=PlanAuditState)
async def get_plan_audit_state(project_id: str, db: AsyncSession = Depends(get_db)):
    _require_v2()
    await _project_or_404(project_id, db)
    outline = await latest_content_plan(project_id, db)
    audit = None
    if outline is not None:
        job = await latest_audit_for_plan(project_id, str(outline.id), db)
        if job is not None:
            stale = False
            if job.status == "done" and isinstance(job.result_json, dict):
                current = await current_fingerprint(project_id, outline, db)
                stale = not fingerprints_match(job.result_json.get("input_fingerprint"), current)
            audit = _audit_response(job, stale=stale)
    eligibility = await drafting_eligibility(project_id, db, outline)
    return PlanAuditState(audit=audit, eligibility=eligibility)


@router.post(
    "/{project_id}/jobs",
    response_model=PlanAuditResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_plan_audit(project_id: str, db: AsyncSession = Depends(get_db)):
    _require_v2()
    project = await _project_or_404(project_id, db)
    try:
        job = await create_plan_audit_job(project, db)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _audit_response(job, stale=False)


@router.post("/{project_id}/audits/{audit_id}/resolutions", response_model=PlanAuditResponse)
async def resolve_audit_finding(
    project_id: str,
    audit_id: str,
    data: ResolutionRequest,
    db: AsyncSession = Depends(get_db),
):
    """Record a human interpretation for one blocking verdict. The auditor's
    verdict itself is never edited; the resolution is stored beside it."""
    _require_v2()
    job = await db.get(GenerationJob, audit_id)
    if not job or job.project_id != project_id or job.job_type != "plan_audit":
        raise HTTPException(status_code=404, detail="Plan audit not found")
    if job.status != "done" or not isinstance(job.result_json, dict):
        raise HTTPException(status_code=409, detail="Решение се записва само за завършен одит.")
    outline = await latest_content_plan(project_id, db)
    if outline is None or not fingerprints_match(
        job.result_json.get("input_fingerprint"),
        await current_fingerprint(project_id, outline, db),
    ):
        raise HTTPException(
            status_code=409,
            detail="Одитът е остарял; решение се записва само за актуален одит.",
        )
    try:
        job.result_json = apply_resolution(
            job.result_json, data.key, interpretation=data.interpretation, reason=data.reason
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await db.flush()
    return _audit_response(job, stale=False)
