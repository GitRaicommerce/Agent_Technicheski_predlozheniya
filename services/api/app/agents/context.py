from __future__ import annotations

import json
import re
from typing import Any, TYPE_CHECKING

from sqlalchemy import select

from app.core.models import (
    ExtractedChunk,
    ProjectFactSheet,
    ProjectFile,
    ScheduleNormalized,
    WbsItem,
)
from app.ingestion.schedule_parser import schedule_quality

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


DESIGN_SCOPE_TERMS = (
    "инвестиционен проект",
    "проектна част",
    "част водоснабдяване",
    "част канализация",
    "геодезия",
    "конструктивна",
    "пбз",
    "пусо",
    "сметна документация",
    "пожарна безопасност",
    "количествен",
    "количествено-стойностна",
)


def _normalize(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").lower()).strip()


def _task_text(task: dict[str, Any]) -> str:
    values = [
        task.get("name"),
        task.get("task_name"),
        task.get("wbs"),
        task.get("uid"),
        task.get("start"),
        task.get("finish"),
        task.get("duration_days"),
    ]
    return " ".join(str(value) for value in values if value is not None)


def _keyword_set(section_title: str, section_requirements: list[str]) -> set[str]:
    raw = " ".join([section_title, *section_requirements])
    normalized = _normalize(raw)
    keywords = {
        token
        for token in re.split(r"[^0-9a-zа-я]+", normalized)
        if len(token) >= 4
    }
    if any(term in normalized for term in DESIGN_SCOPE_TERMS):
        keywords.update(DESIGN_SCOPE_TERMS)
    return keywords


def _score_text(text: str, keywords: set[str]) -> int:
    normalized = _normalize(text)
    score = 0
    for keyword in keywords:
        if keyword and keyword in normalized:
            score += 4 if " " in keyword else 1
    if "част" in normalized:
        score += 3
    if "график" in normalized or "срок" in normalized:
        score += 2
    return score


def _compact_task(task: dict[str, Any]) -> dict[str, Any]:
    return {
        key: task.get(key)
        for key in (
            "uid",
            "wbs",
            "name",
            "task_name",
            "duration_days",
            "start",
            "finish",
        )
        if task.get(key) is not None
    }


async def build_project_grounding_context(
    project_id: str,
    section_title: str,
    section_requirements: list[str],
    db: "AsyncSession",
    max_tender_chunks: int = 14,
    max_schedule_tasks: int = 24,
) -> dict[str, Any]:
    """Build a compact evidence pack for drafting and verification.

    The pack intentionally includes raw tender excerpts and schedule tasks,
    because generated text must be checked against both sources, not only
    against example proposal snippets.
    """

    keywords = _keyword_set(section_title, section_requirements)

    schedule_result = await db.execute(
        select(ScheduleNormalized)
        .where(ScheduleNormalized.project_id == project_id)
        .order_by(ScheduleNormalized.version.desc())
        .limit(1)
    )
    schedule = schedule_result.scalar_one_or_none()
    schedule_tasks: list[dict[str, Any]] = []
    quality = schedule_quality(schedule.schedule_json) if schedule else {"reliable": False, "reasons": []}
    if schedule and quality["reliable"]:
        raw_tasks = schedule.schedule_json.get("tasks", [])
        scored_tasks = [
            (task, _score_text(_task_text(task), keywords))
            for task in raw_tasks
            if isinstance(task, dict)
        ]
        matched_tasks = [
            task
            for task, score in sorted(
                scored_tasks,
                key=lambda item: (-item[1], str(item[0].get("wbs", "")), str(item[0].get("uid", ""))),
            )
            if score > 0
        ]
        if not matched_tasks and raw_tasks:
            matched_tasks = [task for task in raw_tasks if isinstance(task, dict)]
        schedule_tasks = [_compact_task(task) for task in matched_tasks[:max_schedule_tasks]]

    file_ids_result = await db.execute(
        select(ProjectFile.id)
        .where(ProjectFile.project_id == project_id)
        .where(ProjectFile.module == "tender_docs")
    )
    tender_file_ids = [row.id for row in file_ids_result]

    tender_chunks: list[dict[str, Any]] = []
    if tender_file_ids:
        chunks_result = await db.execute(
            select(ExtractedChunk)
            .where(ExtractedChunk.project_id == project_id)
            .where(ExtractedChunk.file_id.in_(tender_file_ids))
            .order_by(ExtractedChunk.page, ExtractedChunk.id)
        )
        chunks = chunks_result.scalars().all()
        scored_chunks = [
            (chunk, _score_text(" ".join([chunk.section_path or "", chunk.text or ""]), keywords))
            for chunk in chunks
        ]
        selected_chunks = [
            chunk
            for chunk, score in sorted(
                scored_chunks,
                key=lambda item: (-(item[1]), item[0].page or 0, item[0].id),
            )
            if score > 0
        ][:max_tender_chunks]
        tender_chunks = [
            {
                "chunk_id": chunk.id,
                "page": chunk.page,
                "section_path": chunk.section_path,
                "text": (chunk.text or "")[:1800],
            }
            for chunk in selected_chunks
        ]

    return {
        "section": {
            "title": section_title,
            "requirements": section_requirements,
        },
        "tender_chunks": tender_chunks,
        "schedule": {
            "available": schedule is not None and quality["reliable"],
            "reliable": quality["reliable"],
            "quality_reasons": quality.get("reasons", []),
            "locked": schedule.status_locked if schedule else None,
            "version": schedule.version if schedule else None,
            "tasks": schedule_tasks,
        },
    }


def format_grounding_context(context: dict[str, Any] | None) -> str:
    if not context:
        return ""
    return json.dumps(context, ensure_ascii=False, indent=2)


async def build_project_grounding_context_v2(
    project_id: str,
    section_title: str,
    section_requirements: list[str],
    db: "AsyncSession",
    *,
    linked_wbs_ids: list[str] | None = None,
    linked_fact_keys: list[str] | None = None,
    max_tender_chunks: int = 18,
    max_schedule_tasks: int = 24,
) -> dict[str, Any]:
    """Build Phase 4 context with semantic tender retrieval and linked artifacts."""
    base = await build_project_grounding_context(
        project_id=project_id,
        section_title=section_title,
        section_requirements=section_requirements,
        db=db,
        max_tender_chunks=max_tender_chunks,
        max_schedule_tasks=max_schedule_tasks,
    )
    query = "\n".join([section_title, *section_requirements]).strip()

    semantic_chunks: list[ExtractedChunk] = []
    semantic_warning: str | None = None
    try:
        from app.core.embedding import embed_query

        query_embedding = await embed_query(query)
        if query_embedding:
            semantic_result = await db.execute(
                select(ExtractedChunk)
                .join(ProjectFile, ProjectFile.id == ExtractedChunk.file_id)
                .where(
                    ExtractedChunk.project_id == project_id,
                    ProjectFile.module == "tender_docs",
                    ExtractedChunk.embedding.is_not(None),
                )
                .order_by(ExtractedChunk.embedding.cosine_distance(query_embedding))
                .limit(max_tender_chunks)
            )
            semantic_chunks = list(semantic_result.scalars().all())
    except Exception as exc:
        semantic_chunks = []
        semantic_warning = str(exc)

    merged_chunks: list[dict[str, Any]] = []
    seen_chunk_ids: set[str] = set()
    for chunk in semantic_chunks:
        chunk_id = str(chunk.id)
        if chunk_id in seen_chunk_ids:
            continue
        seen_chunk_ids.add(chunk_id)
        merged_chunks.append(
            {
                "chunk_id": chunk_id,
                "page": chunk.page,
                "section_path": chunk.section_path,
                "text": (chunk.text or "")[:3000],
                "retrieval": "semantic",
            }
        )
    for chunk in base.get("tender_chunks") or []:
        chunk_id = str(chunk.get("chunk_id") or "")
        if not chunk_id or chunk_id in seen_chunk_ids:
            continue
        seen_chunk_ids.add(chunk_id)
        merged_chunks.append({**chunk, "retrieval": "keyword"})
    base["tender_chunks"] = merged_chunks[:max_tender_chunks]
    base["retrieval_mode"] = "semantic_plus_keyword" if semantic_chunks else "keyword_fallback"
    if semantic_warning:
        base["retrieval_warning"] = semantic_warning

    wbs_result = await db.execute(
        select(WbsItem)
        .where(WbsItem.project_id == project_id, WbsItem.status != "rejected")
        .order_by(WbsItem.order_index, WbsItem.id)
    )
    all_wbs = list(wbs_result.scalars().all())
    linked = {str(item) for item in linked_wbs_ids or [] if item}
    keywords = _keyword_set(section_title, section_requirements)
    selected_wbs = [item for item in all_wbs if str(item.id) in linked]
    if not selected_wbs:
        selected_wbs = [
            item
            for item in all_wbs
            if _score_text(f"{item.title} {item.description or ''}", keywords) > 0
        ][:20]
    base["wbs_items"] = [
        {
            "id": item.id,
            "parent_id": item.parent_id,
            "level": item.level,
            "kind": item.kind,
            "title": item.title,
            "description": item.description,
            "schedule_task_uid": item.schedule_task_uid,
            "source_refs": item.source_refs_json or [],
        }
        for item in selected_wbs
    ]

    fact_result = await db.execute(
        select(ProjectFactSheet)
        .where(ProjectFactSheet.project_id == project_id)
        .order_by(ProjectFactSheet.version.desc())
        .limit(1)
    )
    fact_sheet = fact_result.scalar_one_or_none()
    facts = fact_sheet.facts_json if fact_sheet and isinstance(fact_sheet.facts_json, dict) else {}
    requested_keys = [str(key) for key in linked_fact_keys or [] if key]
    if requested_keys:
        facts = {key: facts[key] for key in requested_keys if key in facts}
    base["project_fact_sheet"] = {
        "version": fact_sheet.version if fact_sheet else None,
        "status": fact_sheet.status if fact_sheet else None,
        "facts": facts,
    }
    return base
