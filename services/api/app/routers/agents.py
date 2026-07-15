"""
Agents router — оркестратор endpoint.
Всички LLM агенти се извикват тук чрез оркестратора.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any
from types import SimpleNamespace
import uuid
import re
import structlog
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.database import get_db
from app.core.models import Project

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)
log = structlog.get_logger()


class ChatMessage(BaseModel):
    role: str  # user|assistant
    content: str


class DuplicateSelectionResolutionItem(BaseModel):
    section_uid: str
    generation_id: str
    previous_selected_count: int


class DuplicateSelectionResolutionResponse(BaseModel):
    status: str
    resolved_count: int
    sections: list[DuplicateSelectionResolutionItem]


class OrchestratorRequest(BaseModel):
    project_id: str
    message: str
    history: list[ChatMessage] = []


class RemediationActionRequest(BaseModel):
    section_uids: list[str] = Field(default_factory=list)
    section_title_hints: list[str] = Field(default_factory=list)
    gap_reasons: list[str] = Field(default_factory=list)
    reference_section: str | None = None
    generated_section: str | None = None
    operational_detail_missing_signals: list[str] = Field(default_factory=list)


@router.post("/chat")
@limiter.limit("20/minute")
async def orchestrator_chat(
    request: Request,
    req: OrchestratorRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    project = await db.get(Project, req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    from app.agents.orchestrator import run_orchestrator
    from app.core.llm_gateway import LLMNotConfiguredError

    try:
        result = await run_orchestrator(
            project=project,
            message=req.message,
            history=req.history,
            db=db,
        )
    except LLMNotConfiguredError as exc:
        result = {
            "schema_version": "v1.3",
            "status": "needs_user_action",
            "trace_id": "",
            "assistant_message": (
                "⚙️ **LLM не е конфигуриран.** "
                "Добавете `OPENAI_API_KEY` (или `ANTHROPIC_API_KEY`) в `.env` файла "
                "и рестартирайте контейнерите с `docker compose up -d --build`."
            ),
            "ui_actions": [],
            "questions_to_user": [],
            "agent_called": None,
        }
        log.warning("llm_not_configured", error=str(exc))
    except Exception as exc:
        result = {
            "schema_version": "v1.3",
            "status": "error",
            "trace_id": "",
            "assistant_message": f"⚠ Грешка при генерирането: {exc}",
            "ui_actions": [],
            "questions_to_user": [],
            "agent_called": None,
        }
        log.error("orchestrator_unexpected_error", error=str(exc))
    return result


@router.post("/{project_id}/outline/lock")
async def lock_outline(
    project_id: str, outline_id: str, db: AsyncSession = Depends(get_db)
):
    from app.core.models import TpOutline
    from sqlalchemy import select

    result = await db.execute(
        select(TpOutline).where(
            TpOutline.id == outline_id, TpOutline.project_id == project_id
        )
    )
    outline = result.scalar_one_or_none()
    if not outline:
        raise HTTPException(status_code=404, detail="Outline not found")
    outline.status_locked = True
    from datetime import datetime, timezone

    outline.approved_at = datetime.now(timezone.utc)
    return {"status": "locked", "outline_id": outline_id}


@router.post("/{project_id}/outline/unlock")
async def unlock_outline(
    project_id: str, outline_id: str, db: AsyncSession = Depends(get_db)
):
    from app.core.models import TpOutline
    from sqlalchemy import select

    result = await db.execute(
        select(TpOutline).where(
            TpOutline.id == outline_id, TpOutline.project_id == project_id
        )
    )
    outline = result.scalar_one_or_none()
    if not outline:
        raise HTTPException(status_code=404, detail="Outline not found")
    outline.status_locked = False
    return {"status": "unlocked", "outline_id": outline_id}


@router.delete("/{project_id}/outline", status_code=status.HTTP_204_NO_CONTENT)
async def delete_outlines(project_id: str, db: AsyncSession = Depends(get_db)):
    """Изтрива всички outline версии за проекта — за ново генериране."""
    from app.core.models import TpOutline
    from sqlalchemy import select, delete

    await db.execute(delete(TpOutline).where(TpOutline.project_id == project_id))
    log.info("outlines_deleted", project_id=project_id)


@router.post("/{project_id}/schedule/lock")
async def lock_schedule(
    project_id: str, schedule_id: str, db: AsyncSession = Depends(get_db)
):
    from app.core.models import ScheduleNormalized
    from sqlalchemy import select

    result = await db.execute(
        select(ScheduleNormalized).where(
            ScheduleNormalized.id == schedule_id,
            ScheduleNormalized.project_id == project_id,
        )
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    schedule.status_locked = True
    from datetime import datetime, timezone

    schedule.approved_at = datetime.now(timezone.utc)
    return {"status": "locked", "schedule_id": schedule_id}


@router.post("/{project_id}/schedule/unlock")
async def unlock_schedule(
    project_id: str, schedule_id: str, db: AsyncSession = Depends(get_db)
):
    from app.core.models import ScheduleNormalized
    from sqlalchemy import select

    result = await db.execute(
        select(ScheduleNormalized).where(
            ScheduleNormalized.id == schedule_id,
            ScheduleNormalized.project_id == project_id,
        )
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    schedule.status_locked = False
    return {"status": "unlocked", "schedule_id": schedule_id}


class TpOutlineResponse(BaseModel):
    id: str
    outline_json: dict
    status_locked: bool
    version: int

    model_config = {"from_attributes": True}


@router.get("/{project_id}/outline", response_model=TpOutlineResponse | None)
async def get_outline(project_id: str, db: AsyncSession = Depends(get_db)):
    """Връща последния (най-нов) outline за проекта."""
    from app.core.models import TpOutline
    from sqlalchemy import select

    result = await db.execute(
        select(TpOutline)
        .where(TpOutline.project_id == project_id)
        .order_by(TpOutline.version.desc())
        .limit(1)
    )
    outline = result.scalar_one_or_none()
    return outline


@router.post("/{project_id}/generations/{generation_id}/select")
async def select_generation(
    project_id: str, generation_id: str, db: AsyncSession = Depends(get_db)
):
    """Закрепва конкретна генерация като предпочитана за раздела в .docx."""
    from app.core.models import Generation
    from sqlalchemy import update

    gen = await db.get(Generation, generation_id)
    if not gen or gen.project_id != project_id:
        raise HTTPException(status_code=404, detail="Generation not found")

    # Отмаркираме всички останали за същия раздел
    await db.execute(
        update(Generation)
        .where(
            Generation.project_id == project_id,
            Generation.section_uid == gen.section_uid,
        )
        .values(selected=False)
    )
    gen.selected = True
    return {"status": "selected", "generation_id": generation_id}


@router.post(
    "/{project_id}/generations/resolve-duplicates",
    response_model=DuplicateSelectionResolutionResponse,
)
async def resolve_duplicate_selected_generations(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> DuplicateSelectionResolutionResponse:
    from app.core.models import Generation
    from sqlalchemy import select, update

    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    result = await db.execute(
        select(Generation)
        .where(
            Generation.project_id == project_id,
            Generation.selected.is_(True),
        )
        .order_by(
            Generation.section_uid.asc(),
            Generation.created_at.desc(),
            Generation.variant.desc(),
            Generation.id.desc(),
        )
    )
    selected_generations = list(result.scalars().all())
    grouped: dict[str, list[Generation]] = {}
    for generation in selected_generations:
        if generation.section_uid:
            grouped.setdefault(generation.section_uid, []).append(generation)

    resolved: list[DuplicateSelectionResolutionItem] = []
    for section_uid, generations in grouped.items():
        if len(generations) <= 1:
            continue

        chosen = generations[0]
        await db.execute(
            update(Generation)
            .where(
                Generation.project_id == project_id,
                Generation.section_uid == section_uid,
            )
            .values(selected=False)
        )
        chosen.selected = True
        resolved.append(
            DuplicateSelectionResolutionItem(
                section_uid=section_uid,
                generation_id=chosen.id,
                previous_selected_count=len(generations),
            )
        )

    return DuplicateSelectionResolutionResponse(
        status="resolved",
        resolved_count=len(resolved),
        sections=resolved,
    )


class ScheduleNormalizedResponse(BaseModel):
    id: str
    schedule_json: dict
    status_locked: bool
    version: int

    model_config = {"from_attributes": True}


@router.get("/{project_id}/schedule", response_model=ScheduleNormalizedResponse | None)
async def get_schedule(project_id: str, db: AsyncSession = Depends(get_db)):
    """Връща последния нормализиран график за проекта."""
    from app.core.models import ScheduleNormalized
    from sqlalchemy import select

    result = await db.execute(
        select(ScheduleNormalized)
        .where(ScheduleNormalized.project_id == project_id)
        .order_by(ScheduleNormalized.version.desc())
        .limit(1)
    )
    schedule = result.scalar_one_or_none()
    return schedule


class RequirementChecklistItemResponse(BaseModel):
    id: str
    text: str
    category: str
    category_label: str
    topic: str
    importance: str
    suggested_section: str
    coverage_question: str
    source_chunk_id: str
    source_page: int | None = None
    source_section_path: str | None = None
    source_file: str | None = None
    source_excerpt: str
    evidence_cues: list[str]


class RequirementChecklistResponse(BaseModel):
    project_id: str
    total: int
    importance_counts: dict[str, int]
    category_counts: dict[str, int]
    items: list[RequirementChecklistItemResponse]


@router.get(
    "/{project_id}/requirements-checklist",
    response_model=RequirementChecklistResponse,
)
async def get_requirements_checklist(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> RequirementChecklistResponse:
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    from app.agents.requirements import extract_requirement_checklist
    from app.core.models import ExtractedChunk, ProjectFile
    from sqlalchemy import select

    result = await db.execute(
        select(ExtractedChunk, ProjectFile.filename)
        .join(ProjectFile, ExtractedChunk.file_id == ProjectFile.id)
        .where(ExtractedChunk.project_id == project_id)
        .where(ProjectFile.project_id == project_id)
        .where(ProjectFile.module == "tender_docs")
        .order_by(ProjectFile.filename, ExtractedChunk.page, ExtractedChunk.id)
    )
    chunks = [
        SimpleNamespace(
            id=chunk.id,
            text=chunk.text,
            page=chunk.page,
            section_path=chunk.section_path,
            source_file=filename,
        )
        for chunk, filename in result.all()
    ]
    items = extract_requirement_checklist(chunks)

    importance_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}
    for item in items:
        importance_counts[item.importance] = importance_counts.get(item.importance, 0) + 1
        category_counts[item.category_label] = category_counts.get(item.category_label, 0) + 1

    return RequirementChecklistResponse(
        project_id=project_id,
        total=len(items),
        importance_counts=importance_counts,
        category_counts=category_counts,
        items=[
            RequirementChecklistItemResponse(**item.as_dict())
            for item in items
        ],
    )


# ---------------------------------------------------------------------------
# GET /api/v1/agents/{project_id}/generations
# ---------------------------------------------------------------------------

class GenerationResponse(BaseModel):
    id: str
    section_uid: str
    variant: int
    text: str
    evidence_map_json: dict | None = None
    used_sources_json: dict | None = None
    flags_json: dict | None = None
    evidence_status: str
    selected: bool
    created_at: str
    trace_id: str | None = None

    model_config = {"from_attributes": True}


class SectionGenerations(BaseModel):
    section_uid: str
    section_title: str | None = None
    variants: list[GenerationResponse]


class GenerationJobResponse(BaseModel):
    id: str
    project_id: str
    job_type: str
    status: str
    total_sections: int
    completed_sections: int
    skipped_sections: int
    current_section_uid: str | None = None
    current_section_title: str | None = None
    error: str | None = None
    result_json: dict | None = None
    trace_id: str | None = None
    created_at: str
    updated_at: str
    completed_at: str | None = None


@router.get("/{project_id}/generations", response_model=list[SectionGenerations])
async def list_generations(project_id: str, db: AsyncSession = Depends(get_db)):
    """
    Връща всички генерации за проекта, групирани по section_uid.
    Сортирани: selected DESC, variant ASC, created_at DESC.
    """
    from app.core.models import Generation, TpOutline
    from sqlalchemy import select

    # Load section titles from the latest outline (best-effort)
    outline_result = await db.execute(
        select(TpOutline)
        .where(TpOutline.project_id == project_id)
        .order_by(TpOutline.version.desc())
        .limit(1)
    )
    outline = outline_result.scalar_one_or_none()

    section_title_map: dict[str, str] = {}
    section_order: list[str] = []
    if outline:
        sections = outline.outline_json.get("sections", outline.outline_json.get("outline", []))

        def _collect(secs: list) -> None:
            for s in secs:
                uid = s.get("uid") or s.get("section_uid", "")
                if uid:
                    section_title_map[uid] = s.get("title", "")
                    section_order.append(uid)
                _collect(s.get("subsections", s.get("children", [])))

        _collect(sections)

    gen_result = await db.execute(
        select(Generation)
        .where(Generation.project_id == project_id)
        .order_by(
            Generation.section_uid,
            Generation.selected.desc(),
            Generation.variant.asc(),
            Generation.created_at.desc(),
        )
    )
    generations = gen_result.scalars().all()

    if section_title_map:
        generations = [g for g in generations if g.section_uid in section_title_map]

    # Group by section_uid preserving order
    grouped: dict[str, list[Generation]] = {}
    for g in generations:
        grouped.setdefault(g.section_uid, []).append(g)

    result = []
    ordered_section_uids = section_order if section_order else list(grouped.keys())
    for section_uid in ordered_section_uids:
        variants = grouped.get(section_uid)
        if not variants:
            continue
        result.append(
            SectionGenerations(
                section_uid=section_uid,
                section_title=section_title_map.get(section_uid),
                variants=[
                    GenerationResponse(
                        id=v.id,
                        section_uid=v.section_uid,
                        variant=v.variant,
                        text=v.text,
                        evidence_map_json=v.evidence_map_json,
                        used_sources_json=v.used_sources_json,
                        flags_json=v.flags_json,
                        evidence_status=v.evidence_status,
                        selected=v.selected,
                        created_at=v.created_at.isoformat(),
                        trace_id=v.trace_id,
                    )
                    for v in variants
                ],
            )
        )
    return result


@router.get(
    "/{project_id}/generation-jobs/latest",
    response_model=GenerationJobResponse | None,
)
async def get_latest_generation_job(
    project_id: str, db: AsyncSession = Depends(get_db)
):
    from app.core.models import GenerationJob
    from sqlalchemy import select

    result = await db.execute(
        select(GenerationJob)
        .where(GenerationJob.project_id == project_id)
        .order_by(GenerationJob.created_at.desc())
        .limit(1)
    )
    job = result.scalar_one_or_none()
    return _generation_job_response(job) if job else None


@router.post(
    "/{project_id}/generation-jobs/retry",
    response_model=GenerationJobResponse,
)
async def retry_generation_job(
    project_id: str, db: AsyncSession = Depends(get_db)
):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    from app.agents.generation_jobs import create_drafting_all_job

    job = await create_drafting_all_job(project=project, db=db)
    return _generation_job_response(job)


@router.post(
    "/{project_id}/generation-jobs/stale",
    response_model=GenerationJobResponse,
)
async def regenerate_stale_generation_job(
    project_id: str, db: AsyncSession = Depends(get_db)
):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    from app.agents.generation_jobs import create_drafting_stale_job

    try:
        job = await create_drafting_stale_job(project=project, db=db)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _generation_job_response(job)


@router.post(
    "/{project_id}/generation-jobs/quality",
    response_model=GenerationJobResponse,
)
async def regenerate_quality_generation_job(
    project_id: str, db: AsyncSession = Depends(get_db)
):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    from app.agents.generation_jobs import create_drafting_quality_job

    try:
        job = await create_drafting_quality_job(project=project, db=db)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _generation_job_response(job)


@router.post(
    "/{project_id}/generation-jobs/missing-requirements",
    response_model=GenerationJobResponse,
)
async def regenerate_missing_requirements_generation_job(
    project_id: str, db: AsyncSession = Depends(get_db)
):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    from app.agents.generation_jobs import create_drafting_requirements_job

    try:
        job = await create_drafting_requirements_job(project=project, db=db)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _generation_job_response(job)


@router.post("/{project_id}/remediation-actions/{action_key}")
async def run_generation_remediation_action(
    project_id: str,
    action_key: str,
    req: RemediationActionRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if action_key == "resolve_duplicate_selected":
        result = await resolve_duplicate_selected_generations(project_id, db)
        return {
            "action_key": action_key,
            "status": result.status,
            "result": result.model_dump(),
        }

    from app.agents.generation_jobs import (
        create_drafting_job,
        create_drafting_quality_job,
        create_drafting_requirements_job,
        create_drafting_stale_job,
    )

    generation_action_keys = {
        "regenerate_stale",
        "regenerate_missing_requirements",
        "regenerate_quality_depth",
    }
    if action_key not in generation_action_keys:
        raise HTTPException(status_code=404, detail="Unknown remediation action")

    try:
        requested_section_uids = await _remediation_target_section_uids(
            project_id,
            db,
            req,
        )
        if requested_section_uids and action_key == "regenerate_missing_requirements":
            job = await create_drafting_requirements_job(
                project=project,
                db=db,
                target_section_uids=requested_section_uids,
                target_reason=f"calibration_gap:{action_key}",
            )
        elif requested_section_uids and action_key == "regenerate_quality_depth":
            quality_guidance = _calibration_quality_target_guidance(
                requested_section_uids,
                req,
            )
            job_kwargs: dict[str, Any] = {
                "project": project,
                "db": db,
                "target_section_uids": requested_section_uids,
                "target_reason": f"calibration_gap:{action_key}",
                "job_type": "drafting_quality",
            }
            if quality_guidance:
                job_kwargs["target_guidance"] = quality_guidance
            job = await create_drafting_job(**job_kwargs)
        elif action_key == "regenerate_stale":
            job = await create_drafting_stale_job(project=project, db=db)
        elif action_key == "regenerate_missing_requirements":
            job = await create_drafting_requirements_job(project=project, db=db)
        elif action_key == "regenerate_quality_depth":
            job = await create_drafting_quality_job(project=project, db=db)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return {
        "action_key": action_key,
        "status": "queued",
        "result": _generation_job_response(job).model_dump(),
    }


def _calibration_quality_target_guidance(
    section_uids: list[str],
    req: RemediationActionRequest | None,
) -> dict[str, dict[str, Any]] | None:
    if not req:
        return None

    reasons = [
        str(reason).strip()
        for reason in req.gap_reasons
        if str(reason).strip()
    ]
    operational_signals = [
        str(signal).strip()
        for signal in req.operational_detail_missing_signals
        if str(signal).strip()
    ]
    reference_section = str(req.reference_section or "").strip()
    generated_section = str(req.generated_section or "").strip()
    instructions: list[str] = []

    if reasons:
        instructions.append(
            "Address calibration gap reasons from the reference comparison: "
            + ", ".join(reasons)
            + "."
        )
    if reference_section:
        instructions.append(
            "Align the regenerated section with reference-calibration topic: "
            f"{reference_section}."
        )
    if generated_section:
        instructions.append(
            "Use the current generated section as the base to improve: "
            f"{generated_section}."
        )
    if any(reason in {"too short", "thin detail"} for reason in reasons):
        instructions.append(
            "Expand the section into developed tender-specific narrative depth "
            "instead of a short generic summary."
        )
    if any(reason in {"missing key terms", "weak lexical coverage"} for reason in reasons):
        instructions.append(
            "Recover missing tender concepts and source-grounded terminology from "
            "the project documents while keeping the text coherent."
        )
    if operational_signals or any(
        reason in {"weak operational detail", "partial operational detail"}
        for reason in reasons
    ):
        instructions.append(
            "Add concrete operational detail: responsible roles, controls, records, "
            "monitoring evidence, acceptance criteria, reporting sequence, "
            "escalation, and corrective actions."
        )
    if operational_signals:
        instructions.append(
            "Calibration missing operational signals to cover where source support "
            "exists: "
            + ", ".join(operational_signals[:12])
            + "."
        )

    unique_instructions = list(dict.fromkeys(instructions))
    if not unique_instructions:
        return None

    return {
        section_uid: {"instructions": unique_instructions}
        for section_uid in section_uids
    }


def _normalize_remediation_title(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


async def _remediation_target_section_uids(
    project_id: str,
    db: AsyncSession,
    req: RemediationActionRequest | None,
) -> list[str]:
    if not req:
        return []

    explicit_uids = [str(uid).strip() for uid in req.section_uids if str(uid).strip()]
    title_hints = [
        _normalize_remediation_title(str(title))
        for title in req.section_title_hints
        if str(title).strip()
    ]
    if not explicit_uids and not title_hints:
        return []

    from app.core.models import TpOutline
    from sqlalchemy import select

    outline_res = await db.execute(
        select(TpOutline)
        .where(TpOutline.project_id == project_id)
        .order_by(TpOutline.version.desc())
        .limit(1)
    )
    outline = outline_res.scalar_one_or_none()
    if not outline:
        raise ValueError("No outline available to resolve remediation section targets.")

    sections: list[dict[str, Any]] = []
    _collect_outline_sections(
        outline.outline_json.get("sections", outline.outline_json.get("outline", [])),
        sections,
    )
    outline_uids = {
        str(section.get("uid") or section.get("section_uid") or "").strip()
        for section in sections
        if str(section.get("uid") or section.get("section_uid") or "").strip()
    }
    matched_uids = [uid for uid in explicit_uids if uid in outline_uids]
    for section in sections:
        uid = str(section.get("uid") or section.get("section_uid") or "").strip()
        title = _normalize_remediation_title(str(section.get("title") or ""))
        if not uid or not title:
            continue
        if any(hint == title or hint in title or title in hint for hint in title_hints):
            matched_uids.append(uid)

    resolved = list(dict.fromkeys(uid for uid in matched_uids if uid))
    if (explicit_uids or title_hints) and not resolved:
        raise ValueError("No outline sections matched remediation section targets.")
    return resolved


def _collect_outline_sections(
    sections: list[dict[str, Any]],
    result: list[dict[str, Any]],
) -> None:
    for section in sections:
        if not isinstance(section, dict):
            continue
        result.append(section)
        children = section.get("subsections") or section.get("children") or []
        if isinstance(children, list):
            _collect_outline_sections(children, result)


@router.get(
    "/{project_id}/generation-jobs/{job_id}",
    response_model=GenerationJobResponse,
)
async def get_generation_job(
    project_id: str, job_id: str, db: AsyncSession = Depends(get_db)
):
    from app.core.models import GenerationJob

    job = await db.get(GenerationJob, job_id)
    if not job or job.project_id != project_id:
        raise HTTPException(status_code=404, detail="Generation job not found")
    return _generation_job_response(job)


def _generation_job_response(job) -> GenerationJobResponse:
    return GenerationJobResponse(
        id=job.id,
        project_id=job.project_id,
        job_type=job.job_type,
        status=job.status,
        total_sections=job.total_sections,
        completed_sections=job.completed_sections,
        skipped_sections=job.skipped_sections,
        current_section_uid=job.current_section_uid,
        current_section_title=job.current_section_title,
        error=job.error,
        result_json=job.result_json,
        trace_id=job.trace_id,
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
    )


# ---------------------------------------------------------------------------
# POST /{project_id}/sections/{section_uid}/regenerate
# ---------------------------------------------------------------------------


class RegenerateResponse(BaseModel):
    generation_ids: dict[str, str]
    trace_id: str


@router.post(
    "/{project_id}/sections/{section_uid}/regenerate",
    response_model=RegenerateResponse,
)
async def regenerate_section(
    project_id: str,
    section_uid: str,
    db: AsyncSession = Depends(get_db),
) -> RegenerateResponse:
    """
    Тригерира пълен drafting pipeline (examples→legislation→drafting→verifier)
    за конкретен раздел и връща generation_ids на новите варианти.
    """
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Load the latest outline to resolve section title + requirements
    from sqlalchemy import select
    from app.core.models import TpOutline

    outline_res = await db.execute(
        select(TpOutline)
        .where(TpOutline.project_id == project_id)
        .order_by(TpOutline.version.desc())
        .limit(1)
    )
    outline = outline_res.scalar_one_or_none()

    section_title = section_uid
    section_requirements: list[str] = []
    section_requirement_items: list[dict] = []

    if outline:
        def _find(secs: list) -> bool:
            for s in secs:
                uid = s.get("uid") or s.get("section_uid", "")
                if uid == section_uid:
                    nonlocal section_title, section_requirements, section_requirement_items
                    section_title = s.get("title", section_uid)
                    section_requirements = s.get("requirements", [])
                    section_requirement_items = s.get("requirement_checklist_items", [])
                    return True
                if _find(s.get("subsections", s.get("children", []))):
                    return True
            return False

        sections = outline.outline_json.get(
            "sections", outline.outline_json.get("outline", [])
        )
        _find(sections)

    from app.agents.orchestrator import _run_drafting_pipeline

    trace_id = str(uuid.uuid4())
    result = await _run_drafting_pipeline(
        project_id=project_id,
        params={
            "section_uid": section_uid,
            "section_title": section_title,
            "section_requirements": section_requirements,
            "section_requirement_items": section_requirement_items,
        },
        db=db,
        trace_id=trace_id,
    )

    generation_ids: dict[str, str] = result.get("generation_ids") or {}
    return RegenerateResponse(generation_ids=generation_ids, trace_id=trace_id)
