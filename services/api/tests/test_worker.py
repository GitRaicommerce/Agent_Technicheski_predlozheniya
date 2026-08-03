from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ingestion.worker import _ingest_tender_docs
from app.ingestion.worker import _chunk_storage_meta


def test_chunk_storage_meta_merges_parser_metadata():
    chunk = {
        "text": "Примерен chunk",
        "parser_method": "opendataloader_pdf",
        "meta": {
            "parser_method": "opendataloader_pdf",
            "source_format": "markdown",
        },
    }

    meta = _chunk_storage_meta(chunk, embedding=None)

    assert meta["chunk_hash"]
    assert meta["embedding_status"] == "missing"
    assert meta["parser_method"] == "opendataloader_pdf"
    assert meta["source_format"] == "markdown"


@pytest.mark.asyncio
async def test_tender_ingest_persists_embedding_and_audit_snapshot():
    file = SimpleNamespace(
        id="file-1",
        project_id="project-1",
        filename="documentation.pdf",
        ingest_quality_status="pending",
        ingest_report_json=None,
    )
    db = MagicMock()
    db.add = MagicMock()
    embedding = [0.25] * 1536
    report = {
        "schema_version": 1,
        "quality_status": "ok",
        "warnings": [],
        "errors": [],
        "primary_method": "opendataloader_pdf",
    }
    chunks = [
        {
            "type": "text",
            "text": "Изискване за изпълнение.",
            "page": 7,
            "section_path": "Техническа спецификация",
            "parser_method": "opendataloader_pdf",
        }
    ]

    with (
        patch(
            "app.ingestion.parsers.extract_chunks_with_audit",
            return_value=(chunks, report),
        ),
        patch(
            "app.core.embedding.embed_texts",
            new=AsyncMock(return_value=[embedding]),
        ) as embed_texts,
    ):
        await _ingest_tender_docs(file, b"pdf", db)

    embed_texts.assert_awaited_once_with(["Изискване за изпълнение."])
    stored_chunk = db.add.call_args.args[0]
    assert stored_chunk.embedding == embedding
    assert stored_chunk.meta_json == {
        "chunk_hash": stored_chunk.meta_json["chunk_hash"],
        "embedding_model": "text-embedding-3-small",
        "embedding_dims": 1536,
        "embedding_status": "ok",
        "parser_method": "opendataloader_pdf",
    }
    assert file.ingest_report_json["embedding"] == {
        "model": "text-embedding-3-small",
        "expected_dims": 1536,
        "text_count": 1,
        "valid_count": 1,
        "missing_count": 0,
        "invalid_dims_count": 0,
        "warnings": [],
    }
