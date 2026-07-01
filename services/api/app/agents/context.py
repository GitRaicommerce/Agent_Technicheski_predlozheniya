from __future__ import annotations

import json
import re
from typing import Any, TYPE_CHECKING

from sqlalchemy import select

from app.core.models import ExtractedChunk, ProjectFile, ScheduleNormalized

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
    if schedule:
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
            "available": schedule is not None,
            "locked": schedule.status_locked if schedule else None,
            "version": schedule.version if schedule else None,
            "tasks": schedule_tasks,
        },
    }


def format_grounding_context(context: dict[str, Any] | None) -> str:
    if not context:
        return ""
    return json.dumps(context, ensure_ascii=False, indent=2)
