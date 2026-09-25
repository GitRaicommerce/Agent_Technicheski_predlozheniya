"""WP-05 / K-25 acceptance (T-25, T-26, T-27): independent plan audit and gate."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents import plan_audit
from app.agents.plan_audit import (
    DraftingNotEligibleError,
    apply_resolution,
    compare_inventory,
    drafting_eligibility,
    ensure_drafting_eligible,
    overall_status,
    sanitize_inventory,
)
from tests.scope_fixture import fixture_chunks, load_scope_fixture


@pytest.fixture
def v2(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.generation_pipeline", "v2")
    monkeypatch.setattr("app.core.config.settings.plan_audit_required", True)


def _plan_item(item_id, number, title, criteria, *, origin=None):
    return SimpleNamespace(
        id=item_id,
        parent_id=None,
        number=number,
        title=title,
        generation_uid=f"gen-{item_id}",
        acceptance_criteria_json=[{"text": text} for text in criteria],
        drafting_guidance_json={"origin": origin} if origin else None,
    )


def _complete_inventory(obligations):
    return {
        "obligations": obligations,
        "uncertainties": [],
        "coverage": {"complete": True, "missing_or_partial_locations": []},
    }


# ── Stage A ─────────────────────────────────────────────────────────────────


def test_inventory_keeps_only_verbatim_quotes():
    chunks = {chunk["chunk_id"]: chunk for chunk in fixture_chunks()}
    last_page = next(c for c in chunks.values() if c["page"] == 4)
    raw = {
        "obligations": [
            {
                "source_chunk_id": last_page["chunk_id"],
                "quote": "да опише мерките за проверка на сертификатите",
                "kind": "obligation",
                "text": "Мерки за проверка на сертификатите",
            },
            {
                "source_chunk_id": last_page["chunk_id"],
                "quote": "измислен цитат, който го няма",
                "kind": "obligation",
                "text": "Измислено",
            },
        ]
    }
    inventory = sanitize_inventory(raw, chunks)
    assert [o["text"] for o in inventory["obligations"]] == ["Мерки за проверка на сертификатите"]
    assert inventory["rejected_quotes"] == 1


@pytest.mark.asyncio
async def test_auditor_reads_sources_without_the_plan_and_finds_a_registry_gap(monkeypatch):
    """T-25: an obligation missing from the first registry is found from the source."""
    monkeypatch.setattr("app.core.config.settings.understanding_max_concurrency", 2)
    chunks = fixture_chunks()
    db = MagicMock()
    db.execute = AsyncMock(
        return_value=SimpleNamespace(
            all=lambda: [
                (
                    SimpleNamespace(id=c["chunk_id"], page=c["page"], text=c["text"]),
                    SimpleNamespace(id=c["file_id"], filename=c["filename"]),
                )
                for c in chunks
            ]
        )
    )
    certificates = load_scope_fixture()["expected_requirements"][-1]
    seen_prompts: list[str] = []

    async def extract(**kwargs):
        seen_prompts.append(kwargs["user_message"])
        assert kwargs["agent"] == "plan_audit_extract"
        return {
            "obligations": [
                {
                    "source_chunk_id": "fx-file-tender-p4",
                    "quote": certificates["quote"],
                    "kind": "obligation",
                    "text": "Мерки за проверка на сертификатите",
                }
            ]
        }

    manifest = {
        "files": [{"file_id": "fx-file-tender"}, {"file_id": "fx-file-qualification"}],
        "incomplete_files": [],
    }
    with patch("app.agents.plan_audit.llm_gateway.call", new=extract):
        inventory = await plan_audit.build_inventory("p1", manifest, db, "trace")

    assert inventory["coverage"]["complete"] is True
    assert inventory["obligations"][0]["page"] == 4
    # Independence: the extraction prompt contains the sources, never a plan.
    joined = "\n".join(seen_prompts)
    assert certificates["quote"] in joined
    assert "PLAN" not in joined and "plan_item" not in joined

    plan = [_plan_item("i1", "1", "Концепция и подход", ["Описан е подходът"])]
    comparison_output = {
        "findings": [
            {"inventory_id": "A1", "plan_item_ids": [], "verdict": "missing", "rationale": "Няма получател", "required_correction": "Добави подточка"}
        ]
    }
    with patch("app.agents.plan_audit.llm_gateway.call", new=AsyncMock(return_value=comparison_output)) as compare:
        comparison = await compare_inventory(inventory, plan, "", "trace")
    assert compare.await_args.kwargs["agent"] == "plan_audit_compare"
    report = {**comparison, "coverage": inventory["coverage"], "inventory": inventory, "resolutions": {}}
    assert overall_status(report) == "changes_required"
    assert comparison["findings"][0]["verdict"] == "missing"


# ── Stage B verdicts (T-26) ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_heading_without_depth_and_invented_obligation_block_the_plan():
    inventory = _complete_inventory(
        [{"id": "A1", "quote": "разпределение на дейностите", "text": "Разпределение", "kind": "obligation"}]
    )
    plan = [
        _plan_item("i1", "2.1", "Разпределение на отговорностите", []),
        _plan_item("i2", "3", "Безплатна поддръжка 10 години", ["Гарантирана поддръжка"]),
    ]
    output = {
        "findings": [
            {"inventory_id": "A1", "plan_item_ids": ["i1"], "verdict": "partial", "rationale": "Само заглавие без критерии"}
        ],
        "plan_additions": [
            {"plan_item_id": "i2", "verdict": "unsupported_addition", "rationale": "Няма източник"}
        ],
    }
    with patch("app.agents.plan_audit.llm_gateway.call", new=AsyncMock(return_value=output)):
        comparison = await compare_inventory(inventory, plan, "", "t")
    report = {**comparison, "coverage": inventory["coverage"], "inventory": inventory, "resolutions": {}}
    assert overall_status(report) == "changes_required"

    # Resolving only the heading still leaves the invented obligation blocking.
    resolved = apply_resolution(report, "finding:A1", interpretation="Детайлност по т. 2.1 е достатъчна", reason="Документацията иска само общо описание")
    assert resolved["overall"] == "changes_required"


@pytest.mark.asyncio
async def test_covered_without_receiver_is_not_coverage_and_missing_verdict_is_partial():
    inventory = _complete_inventory(
        [
            {"id": "A1", "quote": "q1", "text": "t1", "kind": "obligation"},
            {"id": "A2", "quote": "q2", "text": "t2", "kind": "obligation"},
        ]
    )
    plan = [_plan_item("i1", "1", "Точка", ["к"])]
    output = {"findings": [{"inventory_id": "A1", "plan_item_ids": ["ghost"], "verdict": "covered"}]}
    with patch("app.agents.plan_audit.llm_gateway.call", new=AsyncMock(return_value=output)):
        comparison = await compare_inventory(inventory, plan, "", "t")
    assert comparison["findings"][0]["verdict"] == "missing"
    assert comparison["unanswered_inventory_ids"] == ["A2"]
    report = {**comparison, "coverage": inventory["coverage"], "inventory": inventory}
    assert overall_status(report) == "partial"


def test_unread_final_page_makes_the_audit_partial_even_if_all_covered():
    report = {
        "coverage": {"complete": False, "missing_or_partial_locations": [{"issues": ["pages_missing:4"]}]},
        "findings": [{"inventory_id": "A1", "verdict": "covered", "plan_item_ids": ["i1"]}],
        "plan_additions": [],
        "unanswered_inventory_ids": [],
    }
    assert overall_status(report) == "partial"
    with pytest.raises(ValueError):
        apply_resolution(report, "finding:A1", interpretation="ок ок", reason="няма какво да се реши")


def test_resolution_requires_a_reason_and_a_blocking_verdict():
    report = {
        "coverage": {"complete": True},
        "findings": [{"inventory_id": "A1", "verdict": "ambiguous", "plan_item_ids": []}],
        "plan_additions": [],
        "unanswered_inventory_ids": [],
    }
    with pytest.raises(ValueError, match="обосновка"):
        apply_resolution(report, "finding:A1", interpretation="кратко", reason="")
    resolved = apply_resolution(
        report,
        "finding:A1",
        interpretation="Не се отнася за позиция 1",
        reason="Разяснение №3 изключва позиция 1 от обхвата",
    )
    assert resolved["overall"] == "passed"
    assert resolved["findings"][0]["verdict"] == "ambiguous"  # auditor verdict untouched


# ── Gate (T-27) ─────────────────────────────────────────────────────────────


def _audit_job(fingerprint, overall_report=None, status="done"):
    report = {
        "input_fingerprint": fingerprint,
        "coverage": {"complete": True},
        "findings": [],
        "plan_additions": [],
        "unanswered_inventory_ids": [],
        "resolutions": {},
        **(overall_report or {}),
    }
    return SimpleNamespace(id="audit-1", status=status, result_json=report)


FP = {
    "source_manifest_hash": "m1",
    "plan_id": "plan-A",
    "plan_content_hash": "h1",
    "project_brief_hash": "b1",
}


@pytest.mark.asyncio
async def test_gate_is_inactive_under_v1(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.generation_pipeline", "v1")
    result = await drafting_eligibility("p1", MagicMock(), SimpleNamespace(id="plan-A"))
    assert result["eligible"] is True
    assert result["reason"] == "gate_inactive_v1_legacy_unaudited"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "job,current,reason",
    [
        (None, FP, "no_audit"),
        (_audit_job(FP, status="error"), FP, "audit_error"),
        (_audit_job(FP), {**FP, "plan_content_hash": "h2"}, "stale"),
        (_audit_job(FP), {**FP, "source_manifest_hash": "m2"}, "stale"),
        (_audit_job(FP), {**FP, "project_brief_hash": "b2"}, "stale"),
        (_audit_job(FP, {"coverage": {"complete": False}}), FP, "partial"),
        (_audit_job(FP, {"findings": [{"inventory_id": "A1", "verdict": "missing", "plan_item_ids": []}]}), FP, "changes_required"),
        (_audit_job(FP), FP, "passed"),
    ],
)
async def test_gate_requires_a_current_passed_audit_of_the_exact_inputs(v2, job, current, reason):
    outline = SimpleNamespace(id="plan-A")
    with (
        patch("app.agents.plan_audit.latest_audit_for_plan", new=AsyncMock(return_value=job)),
        patch("app.agents.plan_audit.current_fingerprint", new=AsyncMock(return_value=current)),
    ):
        result = await drafting_eligibility("p1", MagicMock(), outline)
    assert result["reason"] == reason
    assert result["eligible"] is (reason == "passed")


@pytest.mark.asyncio
async def test_new_job_is_refused_without_acceptance_and_nothing_is_enqueued(v2, mock_db):
    from app.agents.generation_jobs import create_drafting_job
    from tests.conftest import _make_project

    with (
        patch("app.agents.generation_jobs._approved_outline", new=AsyncMock(return_value=SimpleNamespace(id="plan-A", version=1, outline_json={"sections": []}))),
        patch("app.agents.generation_jobs.capture_job_inputs", new=AsyncMock(return_value={"schema_version": 1})),
        patch("app.agents.plan_audit.latest_audit_for_plan", new=AsyncMock(return_value=None)),
        patch("app.agents.generation_jobs._enqueue_generation_job") as enqueue,
    ):
        with pytest.raises(DraftingNotEligibleError, match="независим одит"):
            await create_drafting_job(_make_project(), mock_db)
    enqueue.assert_not_called()
    mock_db.add.assert_not_called()


@pytest.mark.asyncio
async def test_direct_single_section_regeneration_cannot_bypass_the_gate(v2, client, mock_db):
    from tests.conftest import _make_project

    project = _make_project()
    mock_db.get = AsyncMock(return_value=project)
    with patch(
        "app.agents.plan_audit.drafting_eligibility",
        new=AsyncMock(return_value={"eligible": False, "reason": "stale", "audit_id": "a1", "message": "Одитът е остарял."}),
    ):
        response = await client.post(f"/api/v1/agents/{project.id}/sections/sec-1/regenerate")
    assert response.status_code == 409
    assert response.json()["detail"]["reason"] == "stale"


@pytest.mark.asyncio
async def test_chat_drafting_explains_the_gate(v2, client, mock_db):
    from tests.conftest import _make_project

    project = _make_project()
    mock_db.get = AsyncMock(return_value=project)
    with patch(
        "app.agents.orchestrator.run_orchestrator",
        new=AsyncMock(side_effect=DraftingNotEligibleError("Планът няма независим одит.", reason="no_audit")),
    ):
        response = await client.post(
            "/api/v1/agents/chat",
            json={"project_id": project.id, "message": "Генерирай всичко", "history": []},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "needs_user_action"
    assert body["drafting_gate"]["reason"] == "no_audit"


@pytest.mark.asyncio
async def test_running_job_stops_at_the_next_unit_when_acceptance_is_lost(v2):
    from app.agents.generation_jobs import _stop_if_no_longer_eligible

    job = SimpleNamespace(status="processing", error=None, current_section_uid="u", current_section_title="t", completed_at=None, updated_at=None)
    db = MagicMock()
    db.commit = AsyncMock()
    with patch(
        "app.agents.generation_jobs.drafting_eligibility",
        new=AsyncMock(return_value={"eligible": False, "reason": "stale", "message": "Документацията е променена."}),
    ):
        stopped = await _stop_if_no_longer_eligible(job, "p1", SimpleNamespace(id="plan-A"), db)
    assert stopped is True
    assert job.status == "error"
    assert "Завършените подточки са запазени" in job.error


@pytest.mark.asyncio
async def test_correction_cycles_are_bounded(v2, monkeypatch):
    from app.agents.plan_author import _correction_request

    monkeypatch.setattr("app.core.config.settings.plan_audit_max_correction_cycles", 2)
    report = {
        "input_fingerprint": {"plan_id": "plan-A"},
        "coverage": {"complete": True},
        "findings": [{"inventory_id": "A1", "verdict": "missing", "plan_item_ids": [], "required_correction": "Добави"}],
        "plan_additions": [],
        "unanswered_inventory_ids": [],
        "inventory": {"obligations": [{"id": "A1", "quote": "цитат", "page": 2}]},
    }
    audit = SimpleNamespace(project_id="p1", job_type="plan_audit", status="done", result_json=report)
    plan_after_two = SimpleNamespace(outline_json={"plan_author": {"correction_cycle": 2}})
    db = MagicMock()
    db.get = AsyncMock(side_effect=[audit, plan_after_two])

    with pytest.raises(ValueError, match="лимитът от 2"):
        await _correction_request("p1", "audit-1", db)

    plan_after_one = SimpleNamespace(outline_json={"plan_author": {"correction_cycle": 1}})
    db.get = AsyncMock(side_effect=[audit, plan_after_one])
    request = await _correction_request("p1", "audit-1", db)
    assert request["cycle"] == 2
    assert "„цитат“" in request["findings_text"]


def test_json_findings_payload_shape_is_documented():
    # The persisted report keeps the auditor's verdict vocabulary distinct.
    assert plan_audit.FINDING_VERDICTS == {"covered", "partial", "missing", "contradiction", "ambiguous"}
    assert plan_audit.ADDITION_VERDICTS == {"supported", "unsupported_addition"}
    assert json.dumps(sorted(plan_audit.OVERALL_STATES)) == json.dumps(
        sorted(["passed", "changes_required", "partial", "error", "stale"])
    )
