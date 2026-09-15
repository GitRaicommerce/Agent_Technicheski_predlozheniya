"""Тестове за Фаза 5.1 — LLM верификация по критерии."""

from __future__ import annotations

from app.agents.criteria_verifier import (
    _normalize_criterion,
    _sanitize_checks,
    _walk_sections,
    summarize_checks,
)


def _criteria() -> list[dict]:
    return [
        {
            "id": "crit-1",
            "text": "Посочено е разпределение на дейностите по експерти.",
            "kind": "content",
            "source_quote": "Участникът следва да направи предложение...",
            "requirement_id": "req-1",
        },
        {
            "id": "crit-2",
            "text": "Експертите са посочени само като квалификация и брой.",
            "kind": "prohibition",
            "source_quote": "само като квалификация и брой",
            "requirement_id": "req-2",
        },
        {
            "id": "crit-3",
            "text": "За всяка проектна част е посочен съответният специалист.",
            "kind": "cross_ref",
            "source_quote": "за всяка една част от проекта",
            "requirement_id": "req-3",
        },
    ]


def test_sanitize_checks_maps_valid_verdicts():
    raw = {
        "checks": [
            {
                "criterion_id": "crit-1",
                "verdict": "covered",
                "evidence": "Ръководителят на екипа разпределя...",
                "note": "Конкретно разпределение по роли.",
            },
            {
                "criterion_id": "crit-2",
                "verdict": "violated",
                "evidence": "инж. Иван Иванов",
                "note": "Посочено е име на експерт.",
            },
            {
                "criterion_id": "crit-3",
                "verdict": "partial",
                "evidence": "",
                "note": "Липсва специалист за част Геодезия.",
            },
        ]
    }
    checks = _sanitize_checks(raw, _criteria())

    by_id = {check["criterion"]["id"]: check for check in checks}
    assert by_id["crit-1"]["verdict"] == "covered"
    assert by_id["crit-2"]["verdict"] == "violated"
    assert by_id["crit-3"]["verdict"] == "partial"
    assert by_id["crit-3"]["evidence"] is None


def test_sanitize_checks_downgrades_violated_for_content_criteria():
    raw = {
        "checks": [
            {"criterion_id": "crit-1", "verdict": "violated", "note": "x"},
        ]
    }
    checks = _sanitize_checks(raw, _criteria())
    by_id = {check["criterion"]["id"]: check for check in checks}
    # Content критерий не може да е "violated" — става "missing".
    assert by_id["crit-1"]["verdict"] == "missing"


def test_sanitize_checks_marks_unanswered_criteria_as_unchecked():
    raw = {
        "checks": [
            {"criterion_id": "crit-1", "verdict": "covered"},
            {"criterion_id": "unknown-id", "verdict": "covered"},
            {"criterion_id": "crit-2", "verdict": "not-a-verdict"},
        ]
    }
    checks = _sanitize_checks(raw, _criteria())
    by_id = {check["criterion"]["id"]: check for check in checks}
    assert by_id["crit-1"]["verdict"] == "covered"
    assert by_id["crit-2"]["verdict"] == "unchecked"
    assert by_id["crit-3"]["verdict"] == "unchecked"
    # Непознат criterion_id не създава запис.
    assert len(checks) == 3


def test_summarize_checks_counts_all_verdicts():
    checks = _sanitize_checks(
        {
            "checks": [
                {"criterion_id": "crit-1", "verdict": "covered"},
                {"criterion_id": "crit-2", "verdict": "violated"},
            ]
        },
        _criteria(),
    )
    summary = summarize_checks(checks)
    assert summary == {
        "total": 3,
        "covered": 1,
        "partial": 0,
        "missing": 0,
        "violated": 1,
        "unchecked": 1,
    }


def test_normalize_criterion_requires_id_and_text():
    assert _normalize_criterion({"id": "", "text": "x"}) is None
    assert _normalize_criterion({"id": "a", "text": "  "}) is None
    assert _normalize_criterion("not-a-dict") is None
    normalized = _normalize_criterion(
        {"id": "a", "text": "  Разпределение   на   екипа  ", "kind": ""}
    )
    assert normalized == {
        "id": "a",
        "text": "Разпределение на екипа",
        "kind": "content",
        "source_quote": None,
        "requirement_id": None,
    }


def test_walk_sections_traverses_subsections():
    sections = [
        {
            "uid": "root",
            "subsections": [
                {"uid": "child", "subsections": [{"uid": "grandchild"}]},
            ],
        }
    ]
    uids = [section.get("uid") for section in _walk_sections(sections)]
    assert uids == ["root", "child", "grandchild"]
