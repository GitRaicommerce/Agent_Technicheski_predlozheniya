"""Тестове за Фаза 5.2 — кръстосана съгласуваност."""

from __future__ import annotations

from app.agents.consistency import (
    _sanitize_claims,
    _sanitize_conflicts,
    render_consistency_report,
)


def test_sanitize_claims_requires_verbatim_quote():
    text = "Проектирането се изпълнява за 30 календарни дни от възлагането."
    raw = {
        "claims": [
            {
                "kind": "deadline",
                "value": "проектиране: 30 к.д.",
                "quote": "Проектирането се изпълнява за 30 календарни дни",
            },
            {
                "kind": "deadline",
                "value": "измислен срок",
                "quote": "срок от 45 дни",  # няма го в текста
            },
            {"kind": "not-a-kind", "value": "x", "quote": text},
            {"kind": "team", "value": "", "quote": text},
        ]
    }
    claims = _sanitize_claims(raw, text)
    assert len(claims) == 1
    assert claims[0]["kind"] == "deadline"
    assert claims[0]["value"] == "проектиране: 30 к.д."


def test_sanitize_conflicts_filters_invalid_entries():
    quotes_by_section = {
        "sec-1": {"Екипът включва двама инженери ВиК"},
        "sec-2": {"Предвиден е един инженер ВиК"},
    }
    raw = {
        "conflicts": [
            {
                "kind": "cross_section",
                "topic": "Брой инженери ВиК",
                "severity": "critical",
                "explanation": "Разделите посочват различен брой инженери.",
                "statements": [
                    {
                        "section_uid": "sec-1",
                        "quote": "Екипът включва двама инженери ВиК",
                    },
                    {
                        "section_uid": "sec-2",
                        "quote": "Предвиден е един инженер ВиК",
                    },
                ],
            },
            {
                # cross_section с една декларация — отпада
                "kind": "cross_section",
                "topic": "Непълно",
                "severity": "critical",
                "explanation": "x",
                "statements": [
                    {"section_uid": "sec-1", "quote": "Екипът включва двама инженери ВиК"}
                ],
            },
            {
                # непознат раздел — statement отпада, конфликтът остава без statements → отпада
                "kind": "schedule",
                "topic": "Непознат раздел",
                "severity": "warning",
                "explanation": "x",
                "statements": [
                    {"section_uid": "sec-unknown", "quote": "нещо"}
                ],
            },
            {
                "kind": "invalid-kind",
                "topic": "x",
                "severity": "critical",
                "explanation": "x",
                "statements": [],
            },
        ]
    }
    conflicts = _sanitize_conflicts(raw, quotes_by_section)
    assert len(conflicts) == 1
    conflict = conflicts[0]
    assert conflict["kind"] == "cross_section"
    assert conflict["severity"] == "critical"
    assert len(conflict["statements"]) == 2
    assert all(statement["anchored"] for statement in conflict["statements"])


def test_sanitize_conflicts_marks_unanchored_quotes():
    quotes_by_section = {"sec-1": {"точен цитат от твърдение"}}
    raw = {
        "conflicts": [
            {
                "kind": "schedule",
                "topic": "Срок за етап 1",
                "severity": "critical",
                "explanation": "Срокът противоречи на графика.",
                "statements": [
                    {"section_uid": "sec-1", "quote": "свободен преразказ"}
                ],
            }
        ]
    }
    conflicts = _sanitize_conflicts(raw, quotes_by_section)
    assert len(conflicts) == 1
    assert conflicts[0]["statements"][0]["anchored"] is False


def test_render_consistency_report_lists_conflicts():
    report = {
        "checked_section_count": 3,
        "claim_count": 12,
        "critical_count": 1,
        "warning_count": 0,
        "conflicts": [
            {
                "kind": "cross_section",
                "topic": "Брой инженери",
                "severity": "critical",
                "explanation": "Различен брой инженери в два раздела.",
                "statements": [
                    {
                        "section_uid": "sec-1",
                        "section_title": "2.1 Организация",
                        "quote": "двама инженери",
                        "anchored": True,
                    }
                ],
            }
        ],
    }
    rendered = render_consistency_report(report)
    assert "Брой инженери" in rendered
    assert "2.1 Организация" in rendered
    assert "критично" in rendered


def test_render_consistency_report_without_conflicts():
    rendered = render_consistency_report(
        {
            "checked_section_count": 2,
            "claim_count": 5,
            "critical_count": 0,
            "warning_count": 0,
            "conflicts": [],
        }
    )
    assert "Не са открити противоречия" in rendered
