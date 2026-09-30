"""Review and approval API for the Phase 2 technical-proposal content plan."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.content_plan import build_content_plan, sync_outline_from_content_plan
from app.agents.understanding import ensure_v2_enabled
from app.core.database import get_db
from app.core.models import (
    ContentPlanItem,
    GenerationJob,
    Project,
    ProjectFactSheet,
    RequirementRegister,
    TpOutline,
    WbsItem,
)

router = APIRouter()


def _require_v2() -> None:
    try:
        ensure_v2_enabled()
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


class ContentPlanItemResponse(BaseModel):
    id: str
    project_id: str
    outline_id: str
    parent_id: str | None
    uid: str
    number: str
    title: str
    source_quotes_json: list[dict[str, Any]]
    acceptance_criteria_json: list[dict[str, Any]]
    content_kind: Literal["reuse", "specific", "mixed"]
    linked_wbs_ids: list[str]
    linked_fact_keys: list[str]
    order_index: int
    status: Literal["draft", "approved"]
    generation_uid: str | None
    drafting_guidance_json: dict[str, Any] | None = None

    model_config = {"from_attributes": True}


class ContentPlanResponse(BaseModel):
    outline_id: str
    version: int
    status_locked: bool
    source: str
    understanding_status: dict[str, bool] = Field(default_factory=dict)
    items: list[ContentPlanItemResponse]
    # K-03: disposition of every confirmed applicable requirement.
    requirement_coverage: dict[str, Any] | None = None
    requirement_dispositions: list[dict[str, Any]] = Field(default_factory=list)
    global_controls: list[dict[str, Any]] = Field(default_factory=list)
    plan_author: dict[str, Any] | None = None


class RequirementResolution(BaseModel):
    action: Literal["assign", "exclude", "global_control"]
    item_id: str | None = None
    reason: str | None = Field(default=None, max_length=2000)


class ContentPlanItemUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=1024)
    acceptance_criteria_json: list[dict[str, Any]] | None = None
    content_kind: Literal["reuse", "specific", "mixed"] | None = None
    linked_wbs_ids: list[str] | None = None
    linked_fact_keys: list[str] | None = None
    order_index: int | None = Field(default=None, ge=0)


async def _latest_plan(project_id: str, db: AsyncSession) -> TpOutline | None:
    result = await db.execute(
        select(TpOutline)
        .where(TpOutline.project_id == project_id)
        .order_by(TpOutline.version.desc())
    )
    for outline in result.scalars().all():
        if isinstance(outline.outline_json, dict) and outline.outline_json.get("source") == "understanding_content_plan":
            return outline
    return None


async def _response(outline: TpOutline, db: AsyncSession) -> ContentPlanResponse:
    result = await db.execute(
        select(ContentPlanItem)
        .where(ContentPlanItem.outline_id == outline.id)
        .order_by(ContentPlanItem.order_index, ContentPlanItem.id)
    )
    understanding_status = await _understanding_status(outline.project_id, db)
    outline_json = outline.outline_json if isinstance(outline.outline_json, dict) else {}
    return ContentPlanResponse(
        outline_id=outline.id,
        version=outline.version,
        status_locked=outline.status_locked,
        source="understanding_content_plan",
        understanding_status=understanding_status,
        items=list(result.scalars().all()),
        requirement_coverage=outline_json.get("requirement_coverage"),
        requirement_dispositions=list(outline_json.get("requirement_dispositions") or []),
        global_controls=list(outline_json.get("global_controls") or []),
        plan_author=outline_json.get("plan_author"),
    )


async def _understanding_status(project_id: str, db: AsyncSession) -> dict[str, bool]:
    wbs_result = await db.execute(
        select(WbsItem).where(WbsItem.project_id == project_id, WbsItem.status.not_in(["rejected", "superseded"]))
    )
    wbs_items = list(wbs_result.scalars().all())
    fact_result = await db.execute(
        select(ProjectFactSheet)
        .where(ProjectFactSheet.project_id == project_id)
        .order_by(ProjectFactSheet.version.desc())
        .limit(1)
    )
    fact_sheet = fact_result.scalar_one_or_none()
    return {
        "requirements_confirmed": True,
        "wbs_confirmed": bool(wbs_items) and all(item.status == "confirmed" for item in wbs_items),
        "fact_sheet_confirmed": bool(fact_sheet and fact_sheet.status == "confirmed"),
    }


@router.get("/{project_id}", response_model=ContentPlanResponse | None)
async def get_content_plan(project_id: str, db: AsyncSession = Depends(get_db)):
    _require_v2()
    if not await db.get(Project, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    outline = await _latest_plan(project_id, db)
    return await _response(outline, db) if outline else None


@router.post(
    "/{project_id}/build",
    response_model=ContentPlanResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_content_plan(project_id: str, db: AsyncSession = Depends(get_db)):
    _require_v2()
    if not await db.get(Project, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        outline = await build_content_plan(project_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return await _response(outline, db)


_CRITERION_ORIGIN_FIELDS = ("source_quote", "requirement_id", "requirement_text")


def validate_item_criteria(
    submitted: list[dict[str, Any]],
    existing: list[dict[str, Any]],
    ids_used_elsewhere: set[str],
) -> list[dict[str, Any]]:
    """Validate edited criteria as records with stable ids (K-13).

    Existing ids keep their server-side origin (quote, requirement); a new id
    never inherits a quote and may not collide with any other criterion.
    """
    known = {
        str(criterion.get("id")): criterion
        for criterion in existing
        if isinstance(criterion, dict) and criterion.get("id")
    }
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for index, criterion in enumerate(submitted):
        criterion_id = str(criterion.get("id") or "").strip()
        text = str(criterion.get("text") or "").strip()
        if not criterion_id:
            raise HTTPException(status_code=422, detail=f"Критерий {index + 1} няма идентификатор.")
        if not text:
            raise HTTPException(status_code=422, detail=f"Критерий {index + 1} е празен.")
        if criterion_id in seen:
            raise HTTPException(status_code=422, detail=f"Повторен идентификатор на критерий: {criterion_id}.")
        seen.add(criterion_id)
        record = {**criterion, "id": criterion_id, "text": text}
        record["kind"] = str(record.get("kind") or "content")
        if criterion_id in known:
            original = known[criterion_id]
            for field in _CRITERION_ORIGIN_FIELDS:
                if field in original:
                    record[field] = original[field]
                else:
                    record.pop(field, None)
        else:
            if criterion_id in ids_used_elsewhere:
                raise HTTPException(
                    status_code=422,
                    detail=f"Идентификаторът {criterion_id} вече се използва в друга точка.",
                )
            if record.get("source_quote"):
                raise HTTPException(
                    status_code=422,
                    detail="Нов критерий не може да наследи цитат-източник.",
                )
            for field in _CRITERION_ORIGIN_FIELDS:
                record.pop(field, None)
        result.append(record)
    return result


@router.put(
    "/{project_id}/items/{item_id}", response_model=ContentPlanItemResponse
)
async def update_content_plan_item(
    project_id: str,
    item_id: str,
    data: ContentPlanItemUpdate,
    db: AsyncSession = Depends(get_db),
):
    _require_v2()
    item = await db.get(ContentPlanItem, item_id)
    if not item or item.project_id != project_id:
        raise HTTPException(status_code=404, detail="Content plan item not found")
    outline = await db.get(TpOutline, item.outline_id)
    if not outline or outline.status_locked:
        raise HTTPException(status_code=409, detail="Одобреният план първо трябва да бъде отключен.")
    changes = data.model_dump(exclude_unset=True)
    mandatory = any(
        isinstance(source, dict) and source.get("source_kind") == "mandatory_heading"
        for source in (item.source_quotes_json or [])
    )
    if mandatory and "title" in changes and changes["title"].strip() != item.title:
        raise HTTPException(
            status_code=409,
            detail="Заглавието е задължително и е извлечено дословно от документацията.",
        )
    if changes.get("acceptance_criteria_json") is not None:
        siblings = await db.execute(
            select(ContentPlanItem).where(
                ContentPlanItem.outline_id == item.outline_id,
                ContentPlanItem.id != item.id,
            )
        )
        elsewhere = {
            str(criterion.get("id"))
            for other in siblings.scalars().all()
            for criterion in (other.acceptance_criteria_json or [])
            if isinstance(criterion, dict) and criterion.get("id")
        }
        changes["acceptance_criteria_json"] = validate_item_criteria(
            changes["acceptance_criteria_json"],
            list(item.acceptance_criteria_json or []),
            elsewhere,
        )
    for field, value in changes.items():
        setattr(item, field, value)
    await db.flush()
    await sync_outline_from_content_plan(item.outline_id, db)
    await db.refresh(item)
    return item


class PlanAuthorStart(BaseModel):
    correction_audit_id: str | None = None


class PlanAuthorJobResponse(BaseModel):
    id: str
    status: str
    error: str | None = None
    result_json: dict[str, Any] | None = None
    created_at: datetime
    completed_at: datetime | None = None


def _author_job_response(job: GenerationJob) -> PlanAuthorJobResponse:
    return PlanAuthorJobResponse(
        id=job.id,
        status=job.status,
        error=job.error,
        result_json=job.result_json,
        created_at=job.created_at,
        completed_at=job.completed_at,
    )


@router.post(
    "/{project_id}/author",
    response_model=PlanAuthorJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_plan_author(
    project_id: str,
    data: PlanAuthorStart | None = None,
    db: AsyncSession = Depends(get_db),
):
    """K-26: the plan author proposes a detailed draft on the protected structure.
    With ``correction_audit_id`` it corrects the plan by the audit's findings
    (bounded number of automated cycles, K-25)."""
    _require_v2()
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    from app.agents.plan_author import create_plan_author_job

    try:
        job = await create_plan_author_job(
            project,
            db,
            correction_audit_id=data.correction_audit_id if data else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _author_job_response(job)


@router.get("/{project_id}/author/latest", response_model=PlanAuthorJobResponse | None)
async def latest_plan_author_job(project_id: str, db: AsyncSession = Depends(get_db)):
    _require_v2()
    result = await db.execute(
        select(GenerationJob)
        .where(GenerationJob.project_id == project_id, GenerationJob.job_type == "plan_author")
        .order_by(GenerationJob.created_at.desc())
        .limit(1)
    )
    job = result.scalar_one_or_none()
    return _author_job_response(job) if job else None


@router.post(
    "/{project_id}/requirements/{requirement_id}/resolution",
    response_model=ContentPlanResponse,
)
async def resolve_requirement_disposition(
    project_id: str,
    requirement_id: str,
    data: RequirementResolution,
    db: AsyncSession = Depends(get_db),
):
    """Human decision for a requirement: assign a receiver, keep as a global
    rule, or exclude with a recorded reason. There is no reason-less override."""
    _require_v2()
    outline = await _latest_plan(project_id, db)
    if not outline:
        raise HTTPException(status_code=404, detail="Content plan not found")
    if outline.status_locked:
        raise HTTPException(status_code=409, detail="Одобреният план първо трябва да бъде отключен.")
    requirement = await db.get(RequirementRegister, requirement_id)
    if not requirement or requirement.project_id != project_id:
        raise HTTPException(status_code=404, detail="Requirement not found")
    outline_json = dict(outline.outline_json or {})
    resolutions = dict(outline_json.get("requirement_resolutions") or {})
    if data.action == "exclude":
        if not (data.reason or "").strip() or len(data.reason.strip()) < 10:
            raise HTTPException(
                status_code=422,
                detail="Изключването изисква обосновка (поне 10 знака).",
            )
        resolutions[requirement_id] = {
            "action": "exclude",
            "reason": data.reason.strip(),
            "decided_at": datetime.now(timezone.utc).isoformat(),
        }
    elif data.action == "global_control":
        resolutions[requirement_id] = {
            "action": "global_control",
            "reason": (data.reason or "").strip() or None,
            "decided_at": datetime.now(timezone.utc).isoformat(),
        }
    else:
        item = await db.get(ContentPlanItem, data.item_id) if data.item_id else None
        if not item or item.outline_id != outline.id or not item.generation_uid:
            raise HTTPException(
                status_code=422,
                detail="Посочете работна подточка от текущия план.",
            )
        criteria_texts = [
            str(value).strip()
            for value in (requirement.acceptance_criteria_json or [])
            if str(value).strip()
        ] or [requirement.normalized_text]
        criteria = list(item.acceptance_criteria_json or [])
        for index, text in enumerate(criteria_texts, start=1):
            criterion_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{requirement.id}:{index}:{text}"))
            if any(entry.get("id") == criterion_id for entry in criteria if isinstance(entry, dict)):
                continue
            criteria.append(
                {
                    "id": criterion_id,
                    "text": text,
                    "kind": requirement.kind,
                    "source_quote": requirement.source_quote,
                    "requirement_id": requirement.id,
                    "requirement_text": requirement.normalized_text,
                    "scope": requirement.scope,
                    "assigned_by": "human",
                }
            )
        item.acceptance_criteria_json = criteria
        resolutions.pop(requirement_id, None)
    outline_json["requirement_resolutions"] = resolutions
    outline.outline_json = outline_json
    await db.flush()
    await sync_outline_from_content_plan(outline.id, db)
    return await _response(outline, db)


@router.post("/{project_id}/approve", response_model=ContentPlanResponse)
async def approve_content_plan(project_id: str, db: AsyncSession = Depends(get_db)):
    _require_v2()
    outline = await _latest_plan(project_id, db)
    if not outline:
        raise HTTPException(status_code=404, detail="Content plan not found")
    item_result = await db.execute(
        select(ContentPlanItem).where(ContentPlanItem.outline_id == outline.id)
    )
    items = list(item_result.scalars().all())
    generatable = [item for item in items if item.generation_uid]
    if not generatable:
        raise HTTPException(status_code=409, detail="Планът няма работни подточки за генериране.")
    missing = [item.number for item in generatable if not item.acceptance_criteria_json]
    if missing:
        raise HTTPException(
            status_code=409,
            detail="Липсват критерии за приемане в точки: " + ", ".join(missing),
        )
    # K-03: recompute dispositions from the current items and confirmed
    # requirements; an unaccounted requirement blocks approval.
    await sync_outline_from_content_plan(outline.id, db)
    coverage = (getattr(outline, "outline_json", None) or {}).get("requirement_coverage")
    if isinstance(coverage, dict) and coverage.get("unresolved"):
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    "Има потвърдени изисквания без получател в плана. Посочете "
                    "подточка, глобално правило или обосновано изключение."
                ),
                "unresolved_requirement_ids": coverage.get("unresolved_requirement_ids", []),
            },
        )
    await db.execute(
        update(TpOutline)
        .where(TpOutline.project_id == project_id, TpOutline.id != outline.id)
        .values(status_locked=False, approved_at=None)
    )
    await db.execute(
        update(ContentPlanItem)
        .where(ContentPlanItem.outline_id == outline.id)
        .values(status="approved")
    )
    outline.status_locked = True
    outline.approved_at = datetime.now(timezone.utc)
    await sync_outline_from_content_plan(outline.id, db)
    return await _response(outline, db)


@router.post("/{project_id}/unlock", response_model=ContentPlanResponse)
async def unlock_content_plan(project_id: str, db: AsyncSession = Depends(get_db)):
    _require_v2()
    outline = await _latest_plan(project_id, db)
    if not outline:
        raise HTTPException(status_code=404, detail="Content plan not found")
    outline.status_locked = False
    outline.approved_at = None
    await db.execute(
        update(ContentPlanItem)
        .where(ContentPlanItem.outline_id == outline.id)
        .values(status="draft")
    )
    return await _response(outline, db)
