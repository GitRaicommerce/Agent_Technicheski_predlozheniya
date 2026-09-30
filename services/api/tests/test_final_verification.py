"""WP-08 acceptance (T-10, T-12): absent or partial verification is never success."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.criteria_verifier import (
    _sanitize_checks,
    split_text_batches,
    verify_unit,
)
from tests.scope_fixture import late_violation_text, load_scope_fixture

CRITERIA = [
    {"id": "c-content", "text": "Описано е разпределението", "kind": "content", "source_quote": None, "requirement_id": "r1"},
    {"id": "c-names", "text": "Експертите само като квалификация и брой", "kind": "prohibition", "source_quote": None, "requirement_id": "r2"},
]
TEXT = "Ръководителят разпределя дейностите между експертите по части. Друг текст."


def test_missing_verdict_and_invented_evidence_are_not_verified():
    """T-10: no verdict, or a quote absent from the text, is not coverage."""
    checks = _sanitize_checks(
        {
            "checks": [
                {"criterion_id": "c-content", "verdict": "covered", "evidence": "цитат, който го няма в текста"},
            ]
        },
        CRITERIA,
        text=TEXT,
    )
    by_id = {check["criterion"]["id"]: check for check in checks}
    assert by_id["c-content"]["verdict"] == "unchecked"
    assert "не е намерено" in by_id["c-content"]["note"]
    assert by_id["c-names"]["verdict"] == "unchecked"  # no verdict returned

    ok = _sanitize_checks(
        {"checks": [{"criterion_id": "c-content", "verdict": "covered", "evidence": "разпределя дейностите между експертите"}]},
        CRITERIA,
        text=TEXT,
    )
    assert ok[0]["verdict"] == "covered"


@pytest.mark.asyncio
async def test_late_violation_beyond_60000_chars_is_inspected():
    """T-12: a violation after the old cut-off is checked, not skipped."""
    text = late_violation_text()
    violation = load_scope_fixture()["late_text_violation"]["violation_sentence"]
    assert text.index(violation) > 60000
    batches = split_text_batches(text, 60000)
    assert len(batches) >= 2 and sum(len(b) for b in batches) == len(text)

    async def verifier(**kwargs):
        batch = kwargs["user_message"]
        if violation in batch:
            return {"checks": [
                {"criterion_id": "c-names", "verdict": "violated", "evidence": "инж. Иван Иванов"},
                {"criterion_id": "c-content", "verdict": "covered", "evidence": "организира дейностите последователно"},
            ]}
        return {"checks": [
            {"criterion_id": "c-names", "verdict": "covered", "evidence": "организира дейностите последователно"},
            {"criterion_id": "c-content", "verdict": "covered", "evidence": "организира дейностите последователно"},
        ]}

    unit = {"number": "2.1", "title": "Организация", "criteria": CRITERIA, "text": text}
    with patch("app.agents.criteria_verifier.llm_gateway.call", new=verifier):
        checks = await verify_unit(unit, "trace")

    by_id = {check["criterion"]["id"]: check["verdict"] for check in checks}
    assert by_id["c-names"] == "violated"
    assert by_id["c-content"] == "covered"
    assert unit["checked_chars"] == unit["total_chars"] == len(text)
    assert unit["batch_count"] >= 2


@pytest.mark.asyncio
async def test_unsupported_commitment_becomes_a_violated_check():
    text = "Изпълнителят осигурява безплатна поддръжка 10 години след приемането."
    unit = {"number": "3", "title": "Гаранции", "criteria": CRITERIA[:1], "text": text}
    output = {
        "checks": [{"criterion_id": "c-content", "verdict": "missing"}],
        "unsupported_commitments": [
            {"quote": "безплатна поддръжка 10 години", "reason": "Няма такова изискване"},
            {"quote": "измислен цитат извън текста", "reason": "x"},
        ],
    }
    with patch("app.agents.criteria_verifier.llm_gateway.call", new=AsyncMock(return_value=output)):
        checks = await verify_unit(unit, "trace")

    commitments = [c for c in checks if c["criterion"]["kind"] == "unsupported_commitment"]
    assert len(commitments) == 1
    assert commitments[0]["verdict"] == "violated"
    assert commitments[0]["criterion"]["id"].startswith("commitment:")


@pytest.mark.asyncio
async def test_new_unverified_version_is_reported_as_a_verification_gap(client, mock_db):
    """T-10: a new selected version with no checks is not 'verified'."""
    from tests.conftest import _make_project

    project = _make_project()
    mock_db.get = AsyncMock(return_value=project)
    generation = MagicMock()
    generation.id = "gen-new"
    generation.section_uid = "unit-1"
    generation.evidence_status = "ok"
    generation.text = "Текст."
    generation.flags_json = {}
    generation.generation_kind = "subpoint"
    generation.parent_section_uid = None
    selected = MagicMock()
    selected.scalars.return_value.all.return_value = [generation]
    outline = SimpleNamespace(
        outline_json={
            "sections": [
                {"uid": "unit-1", "title": "2.1 Организация", "acceptance_criteria": [{"id": "c-1"}, {"id": "c-2"}]}
            ]
        }
    )
    outline_result = MagicMock()
    outline_result.scalar_one_or_none.return_value = outline
    old_check = SimpleNamespace(generation_id="gen-old", section_uid="unit-1", criterion_id="c-1", verdict="covered")
    checks_result = MagicMock()
    checks_result.scalars.return_value.all.return_value = [old_check]
    no_consistency = MagicMock()
    no_consistency.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(side_effect=[selected, outline_result, checks_result, no_consistency])

    response = await client.get(f"/api/v1/export/{project.id}/readiness")

    body = response.json()
    assert body["criteria_unverified_count"] == 2
    gap = body["criteria_verification_gaps"][0]
    assert gap["never_checked_ids"] == ["c-1", "c-2"]  # old version's check does not count
    assert "criteria_unverified" in {b["code"] for b in body["blockers"]}
    assert body["can_export_current_draft"] is True  # working draft still allowed
