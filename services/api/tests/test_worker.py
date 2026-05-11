from __future__ import annotations

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
