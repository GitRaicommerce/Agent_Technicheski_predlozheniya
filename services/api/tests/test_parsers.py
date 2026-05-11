from __future__ import annotations

import subprocess

from app.ingestion import parsers


def _fake_pdf_audit(reference_text: str = "A" * 120):
    return (
        [{"page": 1, "method": "pypdf", "text_chars": len(reference_text), "issues": []}],
        [(1, reference_text)],
        ["pypdf"],
        [],
    )


def test_extract_pdf_prefers_opendataloader_when_coverage_is_good(monkeypatch):
    monkeypatch.setattr(
        parsers,
        "_extract_pdf_via_opendataloader_markdown",
        lambda *_args: (
            "# Концепция и подход\n\n" + ("Подробно описание. " * 8),
            [],
        ),
    )
    monkeypatch.setattr(
        parsers,
        "_to_markdown_via_markitdown",
        lambda *_args: "# Fallback\n\n" + ("Кратко. " * 4),
    )
    monkeypatch.setattr(parsers, "_audit_pdf_pages", lambda *_args: _fake_pdf_audit())

    chunks, report = parsers.extract_chunks_with_audit(b"%PDF", "sample.pdf")

    assert report["primary_method"] == "opendataloader_pdf"
    assert report["markdown_chars"] >= 90
    assert any(chunk.get("parser_method") == "opendataloader_pdf" for chunk in chunks)


def test_extract_pdf_falls_back_to_markitdown_when_opendataloader_is_empty(monkeypatch):
    monkeypatch.setattr(
        parsers,
        "_extract_pdf_via_opendataloader_markdown",
        lambda *_args: ("", []),
    )
    monkeypatch.setattr(
        parsers,
        "_to_markdown_via_markitdown",
        lambda *_args: "# Раздел\n\n" + ("Достатъчно съдържание. " * 8),
    )
    monkeypatch.setattr(parsers, "_audit_pdf_pages", lambda *_args: _fake_pdf_audit())

    chunks, report = parsers.extract_chunks_with_audit(b"%PDF", "sample.pdf")

    assert report["primary_method"] == "markitdown"
    assert "opendataloader_returned_no_text" in report["warnings"]
    assert any(chunk.get("parser_method") == "markitdown" for chunk in chunks)


def test_extract_pdf_uses_page_text_when_both_markdown_paths_have_low_coverage(monkeypatch):
    monkeypatch.setattr(
        parsers,
        "_extract_pdf_via_opendataloader_markdown",
        lambda *_args: ("Твърде кратко.", []),
    )
    monkeypatch.setattr(
        parsers,
        "_to_markdown_via_markitdown",
        lambda *_args: "Също кратко.",
    )
    monkeypatch.setattr(
        parsers,
        "_audit_pdf_pages",
        lambda *_args: _fake_pdf_audit(reference_text="A" * 300),
    )

    chunks, report = parsers.extract_chunks_with_audit(b"%PDF", "sample.pdf")

    assert report["primary_method"] == "pdf_page_text"
    assert "used_page_text_fallback_low_markdown_coverage" in report["warnings"]
    assert chunks
    assert all(chunk.get("parser_method") is None for chunk in chunks)


def test_classify_opendataloader_error_detects_old_java_runtime():
    exc = subprocess.CalledProcessError(
        1,
        ["java", "-jar", "opendataloader-pdf-cli.jar"],
        stderr="java.lang.UnsupportedClassVersionError",
    )

    assert parsers._classify_opendataloader_error(exc) == "opendataloader_java_too_old"
