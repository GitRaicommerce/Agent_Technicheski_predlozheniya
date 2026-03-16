"""
Ingest worker — RQ job за детерминирана обработка на файлове.
Без LLM. Само OCR / парсинг / chunking / ембединги.
"""

from __future__ import annotations

import hashlib
import structlog
from sqlalchemy import select

log = structlog.get_logger()


def enqueue_ingest(file_id: str):
    """Постави задача в Redis queue 'ingest'."""
    from redis import Redis
    from rq import Queue
    from app.core.config import settings

    redis = Redis.from_url(settings.redis_url)
    q = Queue("ingest", connection=redis)
    q.enqueue(process_file, file_id, job_timeout=600)


def process_file(file_id: str):
    """
    Синхронна RQ задача. Изпълнява се от worker процеса.
    Детерминирана обработка — без LLM.
    """
    import asyncio

    asyncio.run(_process_file_async(file_id))


async def _process_file_async(file_id: str):
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.core.database import AsyncSessionLocal
    from app.core.models import ProjectFile

    async with AsyncSessionLocal() as db:
        file = await db.get(ProjectFile, file_id)
        if not file:
            log.error("ingest_file_not_found", file_id=file_id)
            return

        file.ingest_status = "processing"
        await db.commit()

        try:
            from app.core.storage import storage

            content = await storage.get_object(file.storage_key)

            if file.module == "examples":
                await _ingest_examples(file, content, db)
            elif file.module == "tender_docs":
                await _ingest_tender_docs(file, content, db)
            elif file.module == "schedule":
                await _ingest_schedule(file, content, db)
            elif file.module == "legislation":
                await _ingest_legislation(file, content, db)

            file.ingest_status = "done"
            await db.commit()
            log.info("ingest_done", file_id=file_id, module=file.module)

        except Exception as e:
            file.ingest_status = "error"
            file.ingest_error = str(e)
            await db.commit()
            log.error("ingest_error", file_id=file_id, error=str(e))
            raise


async def _ingest_examples(file, content: bytes, db):
    from app.ingestion.parsers import extract_chunks
    from app.core.models import ExtractedChunk, ExampleSnippet
    import uuid

    chunks = extract_chunks(content, file.filename)
    for chunk in chunks:
        extracted = ExtractedChunk(
            project_id=file.project_id,
            file_id=file.id,
            chunk_type=chunk["type"],
            text=chunk["text"],
            page=chunk.get("page"),
            section_path=chunk.get("section_path"),
        )
        db.add(extracted)

        # Тагване: basic snippet detection (без LLM)
        snippet = ExampleSnippet(
            project_id=file.project_id,
            file_id=file.id,
            chunk_id=extracted.id,
            text=chunk["text"],
            snippet_kind="generic_boilerplate",  # детерминирано тагване — ще се разшири
            source_group=chunk.get("source_group", "unknown"),
        )
        db.add(snippet)


async def _ingest_tender_docs(file, content: bytes, db):
    from app.ingestion.parsers import extract_chunks
    from app.core.models import ExtractedChunk

    chunks = extract_chunks(content, file.filename)
    for chunk in chunks:
        extracted = ExtractedChunk(
            project_id=file.project_id,
            file_id=file.id,
            chunk_type=chunk["type"],
            text=chunk["text"],
            page=chunk.get("page"),
            section_path=chunk.get("section_path"),
        )
        db.add(extracted)


async def _ingest_schedule(file, content: bytes, db):
    from app.ingestion.schedule_parser import parse_schedule
    from app.core.models import (
        ScheduleSnapshot,
        ScheduleNormalized,
        ScheduleMppTask,
        ScheduleMppResource,
    )

    result = parse_schedule(content, file.filename)

    snapshot = ScheduleSnapshot(
        project_id=file.project_id,
        file_id=file.id,
        file_hash=file.file_hash,
        parser_version="1.0.0",
    )
    db.add(snapshot)
    await db.flush()

    normalized = ScheduleNormalized(
        project_id=file.project_id,
        schedule_snapshot_id=snapshot.id,
        schedule_json=result["normalized"],
    )
    db.add(normalized)

    for task in result.get("tasks", []):
        db.add(
            ScheduleMppTask(
                project_id=file.project_id,
                schedule_snapshot_id=snapshot.id,
                mpp_task_uid=task["uid"],
                raw_json=task,
            )
        )


async def _ingest_legislation(file, content: bytes, db):
    """Lex snapshots се създават отделно от Lex.bg pipeline."""
    log.info("ingest_legislation_placeholder", file_id=file.id)
