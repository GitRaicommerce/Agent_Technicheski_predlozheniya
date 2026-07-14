from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.models import Generation, GenerationJob, Project, TpOutline

log = structlog.get_logger()


TERMINAL_JOB_STATUSES = {"done", "error"}


def _section_result(
    uid: str,
    title: str,
    *,
    generation_ids: dict[str, str] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "section_uid": uid,
        "title": title,
    }
    if generation_ids is not None:
        result["generation_ids"] = generation_ids
    if error is not None:
        result["error"] = error
    return result


def _set_job_result(
    job: GenerationJob,
    outline: TpOutline,
    results: list[dict[str, Any]],
    failed_sections: list[dict[str, Any]],
) -> None:
    previous_result = job.result_json if isinstance(job.result_json, dict) else {}
    job.result_json = {
        "target_section_uids": previous_result.get("target_section_uids"),
        "target_reason": previous_result.get("target_reason"),
        "outline_id": outline.id,
        "outline_version": outline.version,
        "sections": results,
        "failed_sections": failed_sections,
    }
    if previous_result.get("target_guidance") is not None:
        job.result_json["target_guidance"] = previous_result.get("target_guidance")


def _generation_statuses_by_section(
    generation_rows: list[Any],
) -> dict[str, set[str]]:
    statuses: dict[str, set[str]] = {}
    for row in generation_rows:
        if not row.section_uid:
            continue
        statuses.setdefault(row.section_uid, set()).add(row.evidence_status or "ok")
    return statuses


def _has_fresh_generation(statuses: set[str] | None) -> bool:
    return bool(statuses) and any(status != "stale" for status in statuses)


def _sections_pending_generation(
    all_sections: list[dict[str, Any]],
    generation_statuses: dict[str, set[str]],
) -> list[dict[str, Any]]:
    return [
        section
        for section in all_sections
        if section.get("uid")
        and not _has_fresh_generation(generation_statuses.get(section.get("uid")))
    ]


def _target_section_uids(job: GenerationJob) -> set[str] | None:
    result_json = job.result_json if isinstance(job.result_json, dict) else {}
    target_uids = result_json.get("target_section_uids")
    if not isinstance(target_uids, list):
        return None

    return {str(uid) for uid in target_uids if uid}


def _target_guidance_by_section(job: GenerationJob) -> dict[str, dict[str, Any]]:
    result_json = job.result_json if isinstance(job.result_json, dict) else {}
    raw_guidance = result_json.get("target_guidance")
    if not isinstance(raw_guidance, dict):
        return {}

    guidance_by_section: dict[str, dict[str, Any]] = {}
    for section_uid, guidance in raw_guidance.items():
        if not section_uid or not isinstance(guidance, dict):
            continue
        guidance_by_section[str(section_uid)] = guidance
    return guidance_by_section


def _merge_section_drafting_guidance(
    base_guidance: Any,
    targeted_guidance: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if isinstance(base_guidance, dict):
        merged: dict[str, Any] = {
            key: value
            for key, value in base_guidance.items()
        }
    else:
        merged = {}

    if not targeted_guidance:
        return merged or None

    existing_instructions = [
        str(item).strip()
        for item in merged.get("instructions") or []
        if str(item).strip()
    ]
    targeted_instructions = [
        str(item).strip()
        for item in targeted_guidance.get("instructions") or []
        if str(item).strip()
    ]
    if targeted_instructions:
        merged["instructions"] = existing_instructions + targeted_instructions

    missing_items = [
        item
        for item in targeted_guidance.get("missing_requirement_items") or []
        if isinstance(item, dict)
    ]
    if missing_items:
        merged["missing_requirement_items"] = missing_items

    missing_ids = [
        str(item).strip()
        for item in targeted_guidance.get("missing_requirement_ids") or []
        if str(item).strip()
    ]
    if missing_ids:
        merged["missing_requirement_ids"] = missing_ids

    return merged or None


def _targeted_sections(
    all_sections: list[dict[str, Any]],
    target_uids: set[str] | None,
) -> list[dict[str, Any]]:
    if target_uids is None:
        return []

    return [
        section
        for section in all_sections
        if section.get("uid") and str(section.get("uid")) in target_uids
    ]


async def create_drafting_all_job(project: Project, db) -> GenerationJob:
    return await create_drafting_job(project=project, db=db)


async def create_drafting_stale_job(project: Project, db) -> GenerationJob:
    stale_result = await db.execute(
        select(Generation.section_uid)
        .where(
            Generation.project_id == project.id,
            Generation.selected.is_(True),
            Generation.evidence_status == "stale",
        )
        .distinct()
    )
    section_uids = [
        row[0]
        for row in stale_result
        if row[0]
    ]
    if not section_uids:
        raise ValueError("No stale selected sections to regenerate.")

    return await create_drafting_job(
        project=project,
        db=db,
        target_section_uids=section_uids,
        target_reason="stale_selected",
        job_type="drafting_stale",
    )


async def create_drafting_quality_job(project: Project, db) -> GenerationJob:
    from app.routers.export import _build_export_readiness, _load_selected_generations

    selected_generations = await _load_selected_generations(project.id, db)
    readiness = await _build_export_readiness(project.id, selected_generations, db)
    quality_sections = [
        section
        for section in readiness.get("quality_sections") or []
        if isinstance(section, dict) and section.get("section_uid")
    ]
    section_uids = list(
        dict.fromkeys(str(section["section_uid"]) for section in quality_sections)
    )
    if not section_uids:
        raise ValueError("No shallow selected sections to regenerate.")

    return await create_drafting_job(
        project=project,
        db=db,
        target_section_uids=section_uids,
        target_reason="quality_review",
        job_type="drafting_quality",
    )


async def create_drafting_requirements_job(
    project: Project,
    db,
    *,
    target_section_uids: list[str] | None = None,
    target_reason: str = "missing_requirements",
) -> GenerationJob:
    from app.routers.export import _build_export_readiness, _load_selected_generations

    selected_generations = await _load_selected_generations(project.id, db)
    readiness = await _build_export_readiness(project.id, selected_generations, db)
    target_uids = {
        str(uid)
        for uid in target_section_uids or []
        if str(uid).strip()
    }
    missing_sections = [
        section
        for section in readiness.get("missing_requirement_sections") or []
        if isinstance(section, dict)
        and section.get("section_uid")
        and (
            not target_uids
            or str(section.get("section_uid")) in target_uids
        )
    ]
    section_uids = list(
        dict.fromkeys(str(section["section_uid"]) for section in missing_sections)
    )
    if not section_uids:
        raise ValueError("No selected sections with missing requirements to regenerate.")

    target_guidance = _missing_requirement_target_guidance(missing_sections)

    return await create_drafting_job(
        project=project,
        db=db,
        target_section_uids=section_uids,
        target_reason=target_reason,
        target_guidance=target_guidance,
        job_type="drafting_requirements",
    )


def _missing_requirement_target_guidance(
    missing_sections: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    guidance_by_section: dict[str, dict[str, Any]] = {}
    for section in missing_sections:
        section_uid = str(section.get("section_uid") or "")
        if not section_uid:
            continue
        section_guidance = guidance_by_section.setdefault(
            section_uid,
            {
                "instructions": [],
                "missing_requirement_ids": [],
                "missing_requirement_items": [],
            },
        )
        missing_ids = [
            str(item)
            for item in section.get("missing_requirement_ids") or []
            if item is not None
        ]
        for requirement_id in missing_ids:
            if requirement_id not in section_guidance["missing_requirement_ids"]:
                section_guidance["missing_requirement_ids"].append(requirement_id)

        for item in section.get("missing_items") or []:
            if not isinstance(item, dict):
                continue
            requirement_id = str(item.get("id") or "")
            if requirement_id and requirement_id not in section_guidance[
                "missing_requirement_ids"
            ]:
                section_guidance["missing_requirement_ids"].append(requirement_id)
            guidance_text = str(item.get("remediation_guidance") or "").strip()
            if guidance_text and guidance_text not in section_guidance["instructions"]:
                section_guidance["instructions"].append(guidance_text)
            section_guidance["missing_requirement_items"].append(
                {
                    "id": requirement_id,
                    "text": item.get("text"),
                    "reason": item.get("reason"),
                    "reasons": item.get("reasons") or [],
                    "remediation_guidance": guidance_text or None,
                    "missing_terms": item.get("missing_terms") or [],
                    "matched_terms": item.get("matched_terms") or [],
                    "distinctive_terms": item.get("distinctive_terms") or [],
                    "distinctive_matches": item.get("distinctive_matches") or [],
                    "coherent_matched_terms": item.get(
                        "coherent_matched_terms"
                    )
                    or [],
                    "operational_signals": item.get("operational_signals") or [],
                    "operational_execution_signals": item.get(
                        "operational_execution_signals"
                    )
                    or [],
                    "required_match_count": item.get("required_match_count"),
                    "required_distinctive_count": item.get(
                        "required_distinctive_count"
                    ),
                    "required_coherent_match_count": item.get(
                        "required_coherent_match_count"
                    ),
                    "required_operational_signal_count": item.get(
                        "required_operational_signal_count"
                    ),
                    "required_operational_execution_signal_count": item.get(
                        "required_operational_execution_signal_count"
                    ),
                }
            )
    return guidance_by_section


async def create_drafting_job(
    project: Project,
    db,
    *,
    target_section_uids: list[str] | None = None,
    target_reason: str | None = None,
    target_guidance: dict[str, dict[str, Any]] | None = None,
    job_type: str = "drafting_all",
) -> GenerationJob:
    trace_id = str(uuid.uuid4())
    result_json = None
    if target_section_uids is not None:
        result_json = {
            "target_section_uids": target_section_uids,
            "target_reason": target_reason,
        }
        if target_guidance is not None:
            result_json["target_guidance"] = target_guidance

    job = GenerationJob(
        id=str(uuid.uuid4()),
        project_id=project.id,
        job_type=job_type,
        status="queued",
        trace_id=trace_id,
        result_json=result_json,
    )
    db.add(job)
    await db.flush()

    # Make the job visible before RQ can pick it up.
    await db.commit()
    try:
        _enqueue_generation_job(job.id)
    except Exception as exc:
        job.status = "error"
        job.error = str(exc)
        job.completed_at = datetime.now(timezone.utc)
        job.updated_at = datetime.now(timezone.utc)
        await db.commit()
        raise
    return job


def _enqueue_generation_job(job_id: str) -> None:
    from redis import Redis
    from rq import Queue

    redis = Redis.from_url(settings.redis_url)
    q = Queue("ingest", connection=redis)
    q.enqueue(process_generation_job, job_id, job_timeout=3600)


def process_generation_job(job_id: str) -> None:
    asyncio.run(_process_generation_job_async(job_id))


async def _process_generation_job_async(job_id: str) -> None:
    async with AsyncSessionLocal() as db:
        job = await db.get(GenerationJob, job_id)
        if not job:
            log.error("generation_job_not_found", job_id=job_id)
            return

        try:
            await _run_drafting_all_job(job, db)
        except Exception as exc:
            await db.rollback()
            job = await db.get(GenerationJob, job_id)
            if job:
                job.status = "error"
                job.error = str(exc)
                job.current_section_uid = None
                job.current_section_title = None
                job.completed_at = datetime.now(timezone.utc)
                job.updated_at = datetime.now(timezone.utc)
                await db.commit()
            log.error("generation_job_failed", job_id=job_id, error=str(exc))
            return


async def _run_drafting_all_job(job: GenerationJob, db) -> None:
    project = await db.get(Project, job.project_id)
    if not project:
        job.status = "error"
        job.error = "Project not found"
        job.completed_at = datetime.now(timezone.utc)
        await db.commit()
        return

    outline_result = await db.execute(
        select(TpOutline)
        .where(TpOutline.project_id == project.id)
        .order_by(TpOutline.version.desc())
        .limit(1)
    )
    outline = outline_result.scalar_one_or_none()
    if not outline:
        job.status = "error"
        job.error = "Няма налично съдържание (outline). Генерирайте разделите първо."
        job.completed_at = datetime.now(timezone.utc)
        await db.commit()
        return

    gen_result = await db.execute(
        select(Generation.section_uid, Generation.evidence_status)
        .where(Generation.project_id == project.id)
    )
    generation_statuses = _generation_statuses_by_section(list(gen_result))

    all_sections: list[dict[str, Any]] = []
    _collect_sections(outline.outline_json.get("sections", []), all_sections)
    target_uids = _target_section_uids(job)
    target_guidance = _target_guidance_by_section(job)
    if target_uids is not None:
        pending_sections = _targeted_sections(all_sections, target_uids)
        section_scope_count = len(pending_sections)
    else:
        pending_sections = _sections_pending_generation(all_sections, generation_statuses)
        section_scope_count = len(all_sections)

    job.status = "processing"
    job.total_sections = section_scope_count
    job.skipped_sections = max(0, section_scope_count - len(pending_sections))
    job.updated_at = datetime.now(timezone.utc)
    await db.commit()

    from app.agents.schedule import run_schedule

    try:
        schedule_result = await run_schedule(
            project_id=project.id,
            db=db,
            trace_id=job.trace_id,
        )
        schedule_summary = (
            schedule_result.get("tp_section_text")
            if "error" not in schedule_result.get("status", "")
            else None
        )
    except Exception as exc:
        await db.rollback()
        job = await db.get(GenerationJob, job.id)
        if not job:
            raise
        schedule_summary = None
        job.error = (
            "Schedule summary failed; continuing with raw schedule grounding. "
            f"{exc}"
        )
        job.updated_at = datetime.now(timezone.utc)
    await db.commit()

    results: list[dict[str, Any]] = []
    failed_sections: list[dict[str, Any]] = []
    for section in pending_sections:
        uid = section.get("uid")
        title = section.get("title", "")
        requirements = section.get("requirements", [])
        requirement_items = section.get("requirement_checklist_items", [])
        drafting_guidance = _merge_section_drafting_guidance(
            section.get("drafting_guidance"),
            target_guidance.get(str(uid)),
        )

        job.current_section_uid = uid
        job.current_section_title = title
        job.updated_at = datetime.now(timezone.utc)
        await db.commit()

        log.info(
            "generation_job_section",
            job_id=job.id,
            project_id=project.id,
            section=title,
            trace_id=job.trace_id,
        )

        from app.agents.examples import run_examples
        from app.agents.legislation import run_legislation
        from app.agents.drafting import run_drafting
        from app.agents.context import build_project_grounding_context

        try:
            examples_result = await run_examples(
                project_id=project.id,
                query=title,
                db=db,
                max_snippets=5,
                trace_id=job.trace_id,
            )
            try:
                lex_result = await run_legislation(
                    project_id=project.id,
                    query=title,
                    db=db,
                    trace_id=job.trace_id,
                )
            except Exception as exc:
                await db.rollback()
                job = await db.get(GenerationJob, job.id)
                if not job:
                    raise
                log.warning(
                    "generation_job_legislation_failed",
                    job_id=job.id,
                    project_id=project.id,
                    section=title,
                    error=str(exc),
                    trace_id=job.trace_id,
                )
                lex_result = {
                    "citations": [],
                    "total_found": 0,
                    "warning": (
                        "Legislation module failed; drafting continued "
                        "without Lex.bg citations."
                    ),
                }
            project_grounding_context = await build_project_grounding_context(
                project_id=project.id,
                section_title=title,
                section_requirements=requirements,
                db=db,
            )
            drafting_result = await run_drafting(
                project_id=project.id,
                section_uid=uid,
                section_title=title,
                section_requirements=requirements,
                evidence_snippets=examples_result.get("selected_snippets", []),
                schedule_summary=schedule_summary,
                lex_citations=lex_result.get("citations", []),
                db=db,
                trace_id=job.trace_id,
                project_grounding_context=project_grounding_context,
                section_requirement_items=requirement_items,
                section_drafting_guidance=drafting_guidance,
            )
        except Exception as exc:
            await db.rollback()
            job = await db.get(GenerationJob, job.id)
            if not job:
                raise
            error = str(exc)
            log.warning(
                "generation_job_section_failed",
                job_id=job.id,
                project_id=project.id,
                section=title,
                error=error,
                trace_id=job.trace_id,
            )
            failed_sections.append(_section_result(uid, title, error=error))
            job.skipped_sections += 1
            job.error = (
                f"{len(failed_sections)} section(s) failed. "
                "Run generation again to retry remaining sections."
            )
            _set_job_result(job, outline, results, failed_sections)
            job.updated_at = datetime.now(timezone.utc)
            await db.commit()
            continue

        job.completed_sections += 1
        results.append(
            _section_result(
                uid,
                title,
                generation_ids=drafting_result.get("generation_ids"),
            )
        )
        _set_job_result(job, outline, results, failed_sections)
        job.updated_at = datetime.now(timezone.utc)
        await db.commit()

    job.status = "error" if failed_sections else "done"
    if failed_sections:
        job.error = (
            f"{len(failed_sections)} section(s) failed. "
            "Run generation again to retry remaining sections."
        )
    job.current_section_uid = None
    job.current_section_title = None
    job.completed_at = datetime.now(timezone.utc)
    job.updated_at = datetime.now(timezone.utc)
    await db.commit()


def _collect_sections(sections: list[dict[str, Any]], result: list[dict[str, Any]]) -> None:
    for section in sections:
        result.append(section)
        _collect_sections(section.get("subsections", []), result)
