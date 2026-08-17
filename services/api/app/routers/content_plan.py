"""Review and approval API for the Phase 2 technical-proposal content plan."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.content_plan import build_content_plan, sync_outline_from_content_plan
from app.agents.understanding import ensure_v2_enabled
from app.core.database import get_db
from app.core.models import ContentPlanItem, Project, ProjectFactSheet, TpOutline, WbsItem

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
    forlage_section_id: str | None
    order_index: int
    status: Literal["draft", "approved"]
    generation_uid: str | None

    model_config = {"from_attributes": True}


class ContentPlanResponse(BaseModel):
    outline_id: str
    version: int
    status_locked: bool
    source: str
    understanding_status: dict[str, bool] = Field(default_factory=dict)
    items: list[ContentPlanItemResponse]


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
    return ContentPlanResponse(
        outline_id=outline.id,
        version=outline.version,
        status_locked=outline.status_locked,
        source="understanding_content_plan",
        understanding_status=understanding_status,
        items=list(result.scalars().all()),
    )


async def _understanding_status(project_id: str, db: AsyncSession) -> dict[str, bool]:
    wbs_result = await db.execute(
        select(WbsItem).where(WbsItem.project_id == project_id, WbsItem.status != "rejected")
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
    for field, value in changes.items():
        setattr(item, field, value)
    await db.flush()
    await sync_outline_from_content_plan(item.outline_id, db)
    await db.refresh(item)
    return item


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
    understanding_status = await _understanding_status(project_id, db)
    missing_reviews = []
    if not understanding_status["wbs_confirmed"]:
        missing_reviews.append("дейностите (WBS)")
    if not understanding_status["fact_sheet_confirmed"]:
        missing_reviews.append("fact sheet")
    if missing_reviews:
        raise HTTPException(
            status_code=409,
            detail=(
                "Преди одобряване на подробния план потвърдете в „Разбиране на изискванията“: "
                + ", ".join(missing_reviews)
                + "."
            ),
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
