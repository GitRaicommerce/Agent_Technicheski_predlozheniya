"""WP-02: the source manifest exposes incomplete extraction coverage."""

from __future__ import annotations

from types import SimpleNamespace

from app.agents.source_manifest import _file_entry, summarize_manifest


def _file(file_id, *, filename="tender.pdf", status="done", report=None, file_hash="h1"):
    return SimpleNamespace(
        id=file_id,
        filename=filename,
        module="tender_docs",
        file_hash=file_hash,
        version=1,
        ingest_status=status,
        ingest_quality_status="ok",
        ingest_report_json=report,
    )


COMPLETE = {"quality_status": "ok", "page_count": 4, "page_coverage": {"status": "complete", "missing_pages": [], "recovered_pages": []}}


def test_complete_sources_produce_a_complete_manifest():
    manifest = summarize_manifest([_file_entry(_file("a", report=COMPLETE))])
    assert manifest["complete"] is True
    assert manifest["incomplete_files"] == []


def test_unrecovered_missing_page_and_failed_ingest_are_visible():
    lost = {
        "quality_status": "warning",
        "page_coverage": {"status": "incomplete_recovered", "missing_pages": [3, 4], "recovered_pages": [3]},
    }
    manifest = summarize_manifest(
        [
            _file_entry(_file("a", report=lost)),
            _file_entry(_file("b", filename="annex.pdf", status="error", report={"quality_status": "error"})),
        ]
    )
    assert manifest["complete"] is False
    issues = {entry["file_id"]: entry["issues"] for entry in manifest["incomplete_files"]}
    assert "pages_missing:4" in issues["a"]
    assert "ingest_status:error" in issues["b"]
    assert "extraction_error" in issues["b"]


def test_legacy_pdf_without_page_coverage_is_marked_not_recorded():
    manifest = summarize_manifest([_file_entry(_file("a", report={"quality_status": "ok"}))])
    assert manifest["complete"] is False
    assert manifest["files"][0]["page_coverage_status"] == "not_recorded"
    assert "page_coverage_not_recorded" in manifest["files"][0]["issues"]


def test_manifest_hash_changes_with_revision_and_ignores_order():
    first = [_file_entry(_file("a", report=COMPLETE)), _file_entry(_file("b", report=COMPLETE, file_hash="h2"))]
    reordered = list(reversed(first))
    changed = [_file_entry(_file("a", report=COMPLETE, file_hash="h9")), first[1]]
    assert summarize_manifest(first)["manifest_hash"] == summarize_manifest(reordered)["manifest_hash"]
    assert summarize_manifest(first)["manifest_hash"] != summarize_manifest(changed)["manifest_hash"]


def test_empty_manifest_is_not_complete():
    assert summarize_manifest([])["complete"] is False
