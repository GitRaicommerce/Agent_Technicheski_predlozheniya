"""Phase 3 API: reviewable links between reusable forlage and the content plan."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.content_plan import sync_outline_from_content_plan
from app.agents.forlage import (
    AUTO_MATCH_MIN_SCORE,
    candidate_match_map,
    replace_forlage_sections,
)
from app.core.database import get_db
from app.core.models import ContentPlanItem, ExampleSnippet, Project, ProjectFile, TpOutline
from app.core.storage import storage
from app.ingestion.parsers import extract_chunks_with_audit

router = APIRouter()


class ForlageCandidateResponse(BaseModel):
    section_id: str
    score: float
    reason: str


class ForlageSectionResponse(BaseModel):
    id: str
    file_id: str
    filename: str
    number: str | None
    title: str
    path: list[str]
    order_index: int
    page_start: int | None
    page_end: int | None
    text_preview: str


class ForlageMappingResponse(BaseModel):
    item_id: str
    item_number: str
    item_title: str
    selected_section_id: str | None
    candidates: list[ForlageCandidateResponse]


class ForlageWorkspaceResponse(BaseModel):
    project_id: str
    outline_id: str | None
    outline_version: int | None
    analyzed: bool
    section_count: int
    mapped_count: int
    review_confirmed: bool
    sections: list[ForlageSectionResponse]
    mappings: list[ForlageMappingResponse]


class ForlageLinkUpdate(BaseModel):
    section_id: str | None = None


async def _latest_content_plan(project_id: str, db: AsyncSession) -> TpOutline | None:
    result = await db.execute(
        select(TpOutline)
        .where(TpOutline.project_id == project_id)
        .order_by(TpOutline.version.desc())
    )
    for outline in result.scalars().all():
        if isinstance(outline.outline_json, dict) and outline.outline_json.get("source") == "understanding_content_plan":
            return outline
    return None


def _section_title(snippet: ExampleSnippet) -> str:
    topics = snippet.topics_json if isinstance(snippet.topics_json, dict) else {}
    return str(topics.get("section_title") or snippet.text.splitlines()[0][:220]).strip()


async def _workspace(project_id: str, db: AsyncSession) -> ForlageWorkspaceResponse:
    outline = await _latest_content_plan(project_id, db)
    item_rows: list[ContentPlanItem] = []
    if outline:
        item_result = await db.execute(
            select(ContentPlanItem)
            .where(
                ContentPlanItem.outline_id == outline.id,
                ContentPlanItem.generation_uid.is_not(None),
            )
            .order_by(ContentPlanItem.order_index, ContentPlanItem.id)
        )
        item_rows = list(item_result.scalars().all())

    file_result = await db.execute(
        select(ProjectFile).where(
            ProjectFile.project_id == project_id,
            ProjectFile.module == "examples",
        )
    )
    files = list(file_result.scalars().all())
    filenames = {file.id: file.filename for file in files}
    snippet_result = await db.execute(
        select(ExampleSnippet).where(
            ExampleSnippet.project_id == project_id,
            ExampleSnippet.snippet_kind == "forlage_section",
        )
    )
    snippets = list(snippet_result.scalars().all())
    valid_snippet_ids = {snippet.id for snippet in snippets}
    snippets.sort(
        key=lambda snippet: (
            filenames.get(snippet.file_id, "").lower(),
            int((snippet.topics_json or {}).get("order_index") or 0),
        )
    )
    sections = []
    for snippet in snippets:
        topics = snippet.topics_json if isinstance(snippet.topics_json, dict) else {}
        sections.append(
            ForlageSectionResponse(
                id=snippet.id,
                file_id=snippet.file_id,
                filename=filenames.get(snippet.file_id, "Неизвестен файл"),
                number=topics.get("section_number"),
                title=_section_title(snippet),
                path=[str(value) for value in topics.get("section_path") or []],
                order_index=int(topics.get("order_index") or 0),
                page_start=topics.get("page_start"),
                page_end=topics.get("page_end"),
                text_preview=snippet.text[:700],
            )
        )

    candidates_by_item = candidate_match_map(item_rows, snippets)
    mappings = [
        ForlageMappingResponse(
            item_id=item.id,
            item_number=item.number,
            item_title=item.title,
            selected_section_id=(
                item.forlage_section_id
                if item.forlage_section_id in valid_snippet_ids
                else None
            ),
            candidates=candidates_by_item.get(item.id, []),
        )
        for item in item_rows
    ]
    return ForlageWorkspaceResponse(
        project_id=project_id,
        outline_id=outline.id if outline else None,
        outline_version=outline.version if outline else None,
        analyzed=bool(snippets),
        section_count=len(sections),
        mapped_count=sum(
            1 for item in item_rows if item.forlage_section_id in valid_snippet_ids
        ),
        review_confirmed=bool(
            outline
            and isinstance(outline.outline_json, dict)
            and (outline.outline_json.get("forlage_review") or {}).get("status") == "confirmed"
        ),
        sections=sections,
        mappings=mappings,
    )


@router.get("/{project_id}", response_model=ForlageWorkspaceResponse)
async def get_forlage_workspace(project_id: str, db: AsyncSession = Depends(get_db)):
    if not await db.get(Project, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return await _workspace(project_id, db)


@router.post("/{project_id}/analyze", response_model=ForlageWorkspaceResponse)
async def analyze_and_match_forlage(project_id: str, db: AsyncSession = Depends(get_db)):
    if not await db.get(Project, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    outline = await _latest_content_plan(project_id, db)
    if not outline:
        raise HTTPException(status_code=409, detail="Първо създайте подробен план на ТП.")
    file_result = await db.execute(
        select(ProjectFile).where(
            ProjectFile.project_id == project_id,
            ProjectFile.module == "examples",
            ProjectFile.ingest_status == "done",
        )
    )
    files = list(file_result.scalars().all())
    if not files:
        raise HTTPException(status_code=409, detail="Няма успешно обработени примерни ТП.")

    item_result = await db.execute(
        select(ContentPlanItem).where(ContentPlanItem.outline_id == outline.id)
    )
    items = list(item_result.scalars().all())
    for item in items:
        item.forlage_section_id = None

    snippets: list[ExampleSnippet] = []
    for file in files:
        content = await storage.get_object(file.storage_key)
        chunks, _report = extract_chunks_with_audit(content, file.filename)
        snippets.extend(
            await replace_forlage_sections(
                project_id=project_id,
                file_id=file.id,
                chunks=chunks,
                embeddings=None,
                db=db,
            )
        )

    generatable_items = [item for item in items if item.generation_uid]
    candidates_by_item = candidate_match_map(generatable_items, snippets, limit=1)
    for item in generatable_items:
        suggestions = candidates_by_item.get(item.id, [])
        if suggestions and suggestions[0]["score"] >= AUTO_MATCH_MIN_SCORE:
            item.forlage_section_id = suggestions[0]["section_id"]
    await sync_outline_from_content_plan(outline.id, db)
    outline.outline_json = {
        **(outline.outline_json or {}),
        "forlage_review": {"status": "pending", "mapped_count": sum(1 for item in generatable_items if item.forlage_section_id)},
    }
    await db.flush()
    return await _workspace(project_id, db)


@router.put("/{project_id}/items/{item_id}", response_model=ForlageWorkspaceResponse)
async def update_forlage_link(
    project_id: str,
    item_id: str,
    data: ForlageLinkUpdate,
    db: AsyncSession = Depends(get_db),
):
    item = await db.get(ContentPlanItem, item_id)
    if not item or item.project_id != project_id:
        raise HTTPException(status_code=404, detail="Content plan item not found")
    if data.section_id:
        snippet = await db.get(ExampleSnippet, data.section_id)
        if (
            not snippet
            or snippet.project_id != project_id
            or snippet.snippet_kind != "forlage_section"
        ):
            raise HTTPException(status_code=409, detail="Избраният раздел не принадлежи на това форлаге.")
    item.forlage_section_id = data.section_id
    outline = await sync_outline_from_content_plan(item.outline_id, db)
    outline.outline_json = {
        **(outline.outline_json or {}),
        "forlage_review": {"status": "pending"},
    }
    await db.flush()
    return await _workspace(project_id, db)


@router.post("/{project_id}/confirm", response_model=ForlageWorkspaceResponse)
async def confirm_forlage_review(project_id: str, db: AsyncSession = Depends(get_db)):
    outline = await _latest_content_plan(project_id, db)
    if not outline:
        raise HTTPException(status_code=409, detail="Първо създайте подробен план на ТП.")
    item_result = await db.execute(
        select(ContentPlanItem).where(
            ContentPlanItem.outline_id == outline.id,
            ContentPlanItem.generation_uid.is_not(None),
        )
    )
    items = list(item_result.scalars().all())
    mapped_count = sum(1 for item in items if item.forlage_section_id)
    outline.outline_json = {
        **(outline.outline_json or {}),
        "forlage_review": {
            "status": "confirmed",
            "mapped_count": mapped_count,
            "unmapped_count": len(items) - mapped_count,
        },
    }
    await db.flush()
    return await _workspace(project_id, db)
