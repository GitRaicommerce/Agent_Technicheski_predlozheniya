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


def _two_page_audit(page_one: str, page_two: str):
    return (
        [
            {"page": 1, "method": "pypdf", "text_chars": len(page_one), "issues": []},
            {"page": 2, "method": "pypdf", "text_chars": len(page_two), "issues": []},
        ],
        [(1, page_one), (2, page_two)],
        ["pypdf"],
        [],
    )


PAGE_ONE = (
    "Организация на изпълнението. Участникът следва да посочи организацията "
    "на екипа и разпределението на дейностите между експертите. " * 6
)
PAGE_TWO = (
    "Заключителни изисквания. Участникът следва да опише мерките за проверка "
    "на сертификатите на влаганите материали."
)


def test_short_requirement_lines_are_kept_in_markdown_and_page_text():
    markdown_chunks = parsers._chunks_from_markdown(
        "# Срокове\n\nСрок: 30 дни.\n\nНе се допуска.\n\n12\n\n—\n"
    )
    texts = [chunk["text"] for chunk in markdown_chunks]
    assert "Срок: 30 дни." in texts
    assert "Не се допуска." in texts
    # Bare page numbers and separators are still dropped.
    assert "12" not in texts and "—" not in texts

    page_paragraphs = parsers._split_paragraphs("Срок: 30 дни.\n\n7\n\nПозиция 4.2.")
    assert page_paragraphs == ["Срок: 30 дни.", "Позиция 4.2."]


def test_missing_page_is_reported_and_recovered_despite_good_total_ratio(monkeypatch):
    """T-02: one lost page must not get quality_status=ok."""
    monkeypatch.setattr(
        parsers,
        "_extract_pdf_via_opendataloader_markdown",
        lambda *_args: (PAGE_ONE, []),
    )
    monkeypatch.setattr(parsers, "_to_markdown_via_markitdown", lambda *_args: "")
    monkeypatch.setattr(
        parsers, "_audit_pdf_pages", lambda *_args: _two_page_audit(PAGE_ONE, PAGE_TWO)
    )

    chunks, report = parsers.extract_chunks_with_audit(b"%PDF", "tender.pdf")

    # The document-wide ratio alone would have accepted this extraction.
    assert report["markdown_chars"] >= 0.75 * report["reference_chars"]
    assert report["primary_method"] == "opendataloader_pdf"
    assert report["quality_status"] == "warning"
    assert "page_text_missing_from_extraction:2" in report["warnings"]
    assert report["page_coverage"]["missing_pages"] == [2]
    assert report["page_coverage"]["recovered_pages"] == [2]
    recovered = [chunk for chunk in chunks if chunk.get("page") == 2]
    assert recovered and "сертификатите" in recovered[0]["text"]
    assert recovered[0]["meta"]["recovered_missing_page"] is True


def test_empty_page_is_not_reported_as_lost(monkeypatch):
    monkeypatch.setattr(
        parsers,
        "_extract_pdf_via_opendataloader_markdown",
        lambda *_args: (PAGE_ONE, []),
    )
    monkeypatch.setattr(parsers, "_to_markdown_via_markitdown", lambda *_args: "")
    monkeypatch.setattr(
        parsers, "_audit_pdf_pages", lambda *_args: _two_page_audit(PAGE_ONE, "")
    )

    _chunks, report = parsers.extract_chunks_with_audit(b"%PDF", "tender.pdf")

    assert report["page_coverage"]["missing_pages"] == []
    assert report["page_coverage"]["empty_pages"] == [2]
    assert report["page_coverage"]["status"] == "complete"
    assert not any(
        warning.startswith("page_text_missing_from_extraction")
        for warning in report["warnings"]
    )


def test_unreadable_page_layer_marks_coverage_unknown(monkeypatch):
    monkeypatch.setattr(
        parsers,
        "_extract_pdf_via_opendataloader_markdown",
        lambda *_args: (PAGE_ONE, []),
    )
    monkeypatch.setattr(parsers, "_to_markdown_via_markitdown", lambda *_args: "")
    monkeypatch.setattr(
        parsers,
        "_audit_pdf_pages",
        lambda *_args: ([], [], ["pypdf"], ["pdf_reader_failed:ValueError"]),
    )

    _chunks, report = parsers.extract_chunks_with_audit(b"%PDF", "tender.pdf")

    assert report["page_coverage"]["status"] == "unknown"
    assert "page_coverage_unknown" in report["warnings"]
    assert report["quality_status"] == "warning"


def test_classify_opendataloader_error_detects_old_java_runtime():
    exc = subprocess.CalledProcessError(
        1,
        ["java", "-jar", "opendataloader-pdf-cli.jar"],
        stderr="java.lang.UnsupportedClassVersionError",
    )

    assert parsers._classify_opendataloader_error(exc) == "opendataloader_java_too_old"
