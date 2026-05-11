"""
Ingest worker — RQ job за детерминирана обработка на файлове.
Без LLM. Само OCR / парсинг / chunking / ембединги.
"""

from __future__ import annotations

import hashlib
import structlog
from sqlalchemy import select

log = structlog.get_logger()


def _chunk_embedding_meta(text: str, embedding: list | None) -> dict:
    from app.core.config import settings

    return {
        "chunk_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "embedding_model": settings.embedding_model if embedding else None,
        "embedding_dims": len(embedding) if embedding else 0,
        "embedding_status": "ok" if embedding else "missing",
    }


def _chunk_storage_meta(chunk: dict, embedding: list | None) -> dict:
    meta = _chunk_embedding_meta(str(chunk.get("text", "")), embedding)
    chunk_meta = chunk.get("meta")
    if isinstance(chunk_meta, dict):
        meta.update(chunk_meta)

    parser_method = chunk.get("parser_method")
    if parser_method:
        meta.setdefault("parser_method", parser_method)

    return meta


def _embedding_report(texts: list[str], embeddings: list | None) -> dict:
    from app.core.config import settings

    embeddings = embeddings or []
    valid = 0
    missing = 0
    invalid_dims = 0

    for index, text in enumerate(texts):
        if not text.strip():
            continue
        embedding = embeddings[index] if index < len(embeddings) else None
        if not embedding:
            missing += 1
        elif len(embedding) == settings.embedding_dims:
            valid += 1
        else:
            invalid_dims += 1

    warnings = []
    if missing:
        warnings.append("missing_embeddings")
    if invalid_dims:
        warnings.append("invalid_embedding_dimensions")

    return {
        "model": settings.embedding_model,
        "expected_dims": settings.embedding_dims,
        "text_count": len([text for text in texts if text.strip()]),
        "valid_count": valid,
        "missing_count": missing,
        "invalid_dims_count": invalid_dims,
        "warnings": warnings,
    }


def _set_ingest_report(file, report: dict, texts: list[str] | None = None, embeddings=None) -> None:
    report = dict(report)
    warnings = list(report.get("warnings") or [])
    errors = list(report.get("errors") or [])

    if texts is not None:
        embedding = _embedding_report(texts, embeddings)
        report["embedding"] = embedding
        warnings.extend(embedding["warnings"])

    quality_status = report.get("quality_status", "ok")
    if errors:
        quality_status = "error"
    elif warnings or report.get("page_issue_count", 0):
        quality_status = "warning"

    report["warnings"] = sorted(set(warnings))
    report["errors"] = sorted(set(errors))
    report["quality_status"] = quality_status
    file.ingest_quality_status = quality_status
    file.ingest_report_json = report


def _mark_no_chunks(file, report: dict, message: str) -> None:
    errors = list(report.get("errors") or [])
    errors.append("no_chunks_extracted")
    report["errors"] = sorted(set(errors))
    report["quality_status"] = "error"
    file.ingest_status = "error"
    file.ingest_error = message
    _set_ingest_report(file, report)


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
        file.ingest_quality_status = "pending"
        file.ingest_report_json = None
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

            if file.ingest_status != "error":
                file.ingest_status = "done"
            await db.commit()
            log.info("ingest_done", file_id=file_id, module=file.module)

        except Exception as e:
            file.ingest_status = "error"
            file.ingest_error = str(e)
            file.ingest_quality_status = "error"
            file.ingest_report_json = {
                "schema_version": 1,
                "quality_status": "error",
                "errors": [str(e)],
                "warnings": [],
            }
            await db.commit()
            log.error("ingest_error", file_id=file_id, error=str(e))
            raise


async def _ingest_examples(file, content: bytes, db):
    from app.ingestion.parsers import extract_chunks_with_audit
    from app.core.models import ExtractedChunk, ExampleSnippet
    from app.core.embedding import embed_texts
    import uuid

    chunks, report = extract_chunks_with_audit(content, file.filename)
    if not chunks:
        _mark_no_chunks(
            file,
            report,
            "No extractable text was found in the examples document.",
        )
        return

    texts = [c.get("text", "") for c in chunks]

    # Generate embeddings in batch; gracefully degrade if unavailable
    try:
        embeddings = await embed_texts(texts)
    except Exception as e:
        log.warning("ingest_examples_embedding_failed", error=str(e))
        embeddings = [None] * len(chunks)

    _set_ingest_report(file, report, texts, embeddings)

    for i, chunk in enumerate(chunks):
        emb = embeddings[i] if i < len(embeddings) and embeddings[i] else None
        extracted = ExtractedChunk(
            project_id=file.project_id,
            file_id=file.id,
            chunk_type=chunk["type"],
            text=chunk["text"],
            page=chunk.get("page"),
            section_path=chunk.get("section_path"),
            embedding=emb,
            meta_json=_chunk_storage_meta(chunk, emb),
        )
        db.add(extracted)
        await db.flush()  # ensure extracted.id is populated

        # Тагване: basic snippet detection (без LLM)
        snippet = ExampleSnippet(
            project_id=file.project_id,
            file_id=file.id,
            chunk_id=extracted.id,
            text=chunk["text"],
            snippet_kind="generic_boilerplate",  # детерминирано тагване — ще се разшири
            source_group=chunk.get("source_group", "unknown"),
            embedding=emb,
        )
        db.add(snippet)


async def _ingest_tender_docs(file, content: bytes, db):
    from app.ingestion.parsers import extract_chunks_with_audit
    from app.core.models import ExtractedChunk
    from app.core.embedding import embed_texts

    chunks, report = extract_chunks_with_audit(content, file.filename)
    if not chunks:
        _mark_no_chunks(
            file,
            report,
            "No extractable text was found in the tender document.",
        )
        return

    texts = [c.get("text", "") for c in chunks]
    try:
        embeddings = await embed_texts(texts)
    except Exception as e:
        log.warning("ingest_tender_embedding_failed", error=str(e))
        embeddings = [None] * len(chunks)

    _set_ingest_report(file, report, texts, embeddings)

    for i, chunk in enumerate(chunks):
        emb = embeddings[i] if i < len(embeddings) and embeddings[i] else None
        extracted = ExtractedChunk(
            project_id=file.project_id,
            file_id=file.id,
            chunk_type=chunk["type"],
            text=chunk["text"],
            page=chunk.get("page"),
            section_path=chunk.get("section_path"),
            embedding=emb,
            meta_json=_chunk_storage_meta(chunk, emb),
        )
        db.add(extracted)


async def _ingest_schedule(file, content: bytes, db):
    from app.ingestion.schedule_parser import parse_schedule
    from app.core.models import (
        ScheduleSnapshot,
        ScheduleNormalized,
        ScheduleMppTask,
        ScheduleMppResource,
        ScheduleMppAssignment,
    )

    result = parse_schedule(content, file.filename)
    warnings = []
    if result.get("warning"):
        warnings.append(str(result["warning"]))
    file.ingest_quality_status = (
        "error" if result.get("error") else ("warning" if warnings else "ok")
    )
    file.ingest_report_json = {
        "schema_version": 1,
        "filename": file.filename,
        "file_type": (
            file.filename.rsplit(".", 1)[-1].lower()
            if "." in file.filename
            else "unknown"
        ),
        "quality_status": file.ingest_quality_status,
        "primary_method": result.get("parser", "schedule_parser"),
        "warnings": warnings,
        "errors": [result["error"]] if result.get("error") else [],
        "tasks_count": len(result.get("tasks", [])),
        "resources_count": len(result.get("resources", [])),
    }

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

    for resource in result.get("resources", []):
        db.add(
            ScheduleMppResource(
                project_id=file.project_id,
                schedule_snapshot_id=snapshot.id,
                mpp_resource_uid=resource["uid"],
                raw_json=resource,
            )
        )

    for assignment in result.get("assignments", []):
        db.add(
            ScheduleMppAssignment(
                project_id=file.project_id,
                schedule_snapshot_id=snapshot.id,
                mpp_assignment_uid=assignment.get("uid", 0),
                raw_json=assignment,
            )
        )

    log.info(
        "ingest_schedule_done",
        file_id=file.id,
        tasks=len(result.get("tasks", [])),
        resources=len(result.get("resources", [])),
        assignments=len(result.get("assignments", [])),
        parser=result.get("parser", "unknown"),
    )


async def _ingest_legislation(file, content: bytes, db):
    """
    Парсва качен нормативен акт (PDF/DOCX) и създава LexSnapshot + LexChunk редове.
    act_name се взима от filename; article_ref се извлича от текста чрез прост regex.
    """
    import re
    import hashlib
    from app.ingestion.parsers import extract_chunks_with_audit
    from app.core.models import LexSnapshot, LexChunk

    chunks, report = extract_chunks_with_audit(content, file.filename)
    if not chunks:
        log.warning("ingest_legislation_no_chunks", file_id=file.id)
        _mark_no_chunks(
            file,
            report,
            "No extractable text was found in the legislation document.",
        )
        return

    act_name = file.filename.rsplit(".", 1)[0]  # filename without extension as act name
    content_hash = hashlib.sha256(content).hexdigest()

    snapshot = LexSnapshot(
        project_id=file.project_id,
        act_name=act_name,
        lex_url=f"file://{file.filename}",
        content_hash=content_hash,
        parser_version="1.0.0",
        storage_key_raw=file.storage_key,
    )
    db.add(snapshot)
    await db.flush()  # get snapshot.snapshot_id

    # Regex patterns for Bulgarian legal article references
    article_pattern = re.compile(
        r"(чл\.?\s*\d+[\w,\s\.]*(?:ал\.?\s*\d+)?)",
        re.IGNORECASE | re.UNICODE,
    )

    texts = [c.get("text", "").strip() for c in chunks if c.get("text", "").strip()]
    try:
        from app.core.embedding import embed_texts as _embed
        embeddings = await _embed(texts)
    except Exception as e:
        log.warning("ingest_legislation_embedding_failed", error=str(e))
        embeddings = [None] * len(texts)

    _set_ingest_report(file, report, texts, embeddings)

    emb_idx = 0
    for chunk in chunks:
        text = chunk.get("text", "").strip()
        if not text:
            continue

        # Try to extract first article reference from the chunk text
        match = article_pattern.search(text)
        article_ref = match.group(0).strip() if match else chunk.get("section_path", "")

        db.add(
            LexChunk(
                project_id=file.project_id,
                snapshot_id=snapshot.snapshot_id,
                act_name=act_name,
                article_ref=article_ref or "—",
                text=text,
                embedding=embeddings[emb_idx]
                if emb_idx < len(embeddings) and embeddings[emb_idx]
                else None,
            )
        )
        emb_idx += 1

    log.info(
        "ingest_legislation_done",
        file_id=file.id,
        act_name=act_name,
        chunks=len(chunks),
    )
