"""API for Phase 5.2 cross-section consistency checks."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.consistency import (
    create_consistency_job,
    ensure_v2_enabled,
    render_consistency_report,
)
from app.core.database import get_db
from app.core.models import GenerationJob, Project

router = APIRouter()


def _require_v2() -> None:
    try:
        ensure_v2_enabled()
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


class ConsistencyJobResponse(BaseModel):
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


def _job_response(job: GenerationJob) -> ConsistencyJobResponse:
    return ConsistencyJobResponse(
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


async def _latest_job(
    project_id: str, db: AsyncSession
) -> GenerationJob | None:
    result = await db.execute(
        select(GenerationJob)
        .where(
            GenerationJob.project_id == project_id,
            GenerationJob.job_type == "consistency_check",
        )
        .order_by(GenerationJob.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


@router.get("/{project_id}", response_model=ConsistencyJobResponse | None)
async def get_latest_consistency_job(
    project_id: str, db: AsyncSession = Depends(get_db)
):
    _require_v2()
    await _project_or_404(project_id, db)
    job = await _latest_job(project_id, db)
    return _job_response(job) if job else None


@router.get("/{project_id}/report", response_class=PlainTextResponse)
async def get_consistency_report(
    project_id: str, db: AsyncSession = Depends(get_db)
):
    _require_v2()
    await _project_or_404(project_id, db)
    job = await _latest_job(project_id, db)
    if not job or job.status != "done" or not isinstance(job.result_json, dict):
        raise HTTPException(
            status_code=404,
            detail="Няма завършена проверка за съгласуваност.",
        )
    return PlainTextResponse(
        render_consistency_report(job.result_json),
        media_type="text/markdown; charset=utf-8",
    )


@router.post(
    "/{project_id}/jobs",
    response_model=ConsistencyJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_consistency_job(
    project_id: str, db: AsyncSession = Depends(get_db)
):
    _require_v2()
    project = await _project_or_404(project_id, db)
    try:
        job = await create_consistency_job(project, db)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _job_response(job)


@router.get("/{project_id}/jobs/{job_id}", response_model=ConsistencyJobResponse)
async def get_consistency_job(
    project_id: str, job_id: str, db: AsyncSession = Depends(get_db)
):
    _require_v2()
    job = await db.get(GenerationJob, job_id)
    if (
        not job
        or job.project_id != project_id
        or job.job_type != "consistency_check"
    ):
        raise HTTPException(status_code=404, detail="Consistency job not found")
    return _job_response(job)
