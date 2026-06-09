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


async def create_drafting_all_job(project: Project, db) -> GenerationJob:
    trace_id = str(uuid.uuid4())
    job = GenerationJob(
        id=str(uuid.uuid4()),
        project_id=project.id,
        job_type="drafting_all",
        status="queued",
        trace_id=trace_id,
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
            raise


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
        select(Generation.section_uid)
        .where(Generation.project_id == project.id)
        .distinct()
    )
    already_generated = {row.section_uid for row in gen_result}

    all_sections: list[dict[str, Any]] = []
    _collect_sections(outline.outline_json.get("sections", []), all_sections)
    pending_sections = [
        section
        for section in all_sections
        if section.get("uid") and section.get("uid") not in already_generated
    ]

    job.status = "processing"
    job.total_sections = len(all_sections)
    job.skipped_sections = len(all_sections) - len(pending_sections)
    job.updated_at = datetime.now(timezone.utc)
    await db.commit()

    from app.agents.schedule import run_schedule

    schedule_result = await run_schedule(project_id=project.id, db=db, trace_id=job.trace_id)
    schedule_summary = (
        schedule_result.get("tp_section_text")
        if "error" not in schedule_result.get("status", "")
        else None
    )
    await db.commit()

    results = []
    for section in pending_sections:
        uid = section.get("uid")
        title = section.get("title", "")
        requirements = section.get("requirements", [])

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

        examples_result = await run_examples(
            project_id=project.id,
            query=title,
            db=db,
            max_snippets=5,
            trace_id=job.trace_id,
        )
        lex_result = await run_legislation(
            project_id=project.id,
            query=title,
            db=db,
            trace_id=job.trace_id,
        )
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
        )

        job.completed_sections += 1
        job.result_json = {
            "outline_id": outline.id,
            "outline_version": outline.version,
            "sections": [
                *results,
                {
                    "section_uid": uid,
                    "title": title,
                    "generation_ids": drafting_result.get("generation_ids"),
                },
            ],
        }
        job.updated_at = datetime.now(timezone.utc)
        await db.commit()
        results = job.result_json["sections"]

    job.status = "done"
    job.current_section_uid = None
    job.current_section_title = None
    job.completed_at = datetime.now(timezone.utc)
    job.updated_at = datetime.now(timezone.utc)
    await db.commit()


def _collect_sections(sections: list[dict[str, Any]], result: list[dict[str, Any]]) -> None:
    for section in sections:
        result.append(section)
        _collect_sections(section.get("subsections", []), result)
