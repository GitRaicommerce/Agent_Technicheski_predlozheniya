"""WP-04 / K-07 acceptance (T-08): reanalysis preserves human review decisions."""

from __future__ import annotations

from types import SimpleNamespace

from app.agents.review_preservation import (
    reconcile_requirements,
    reconcile_wbs,
    record_human_decision,
    requirement_identity,
)


def record(rec_id, quote, *, status="extracted", kind="content", scope="proposal_content", text=None, decision=None):
    item = SimpleNamespace(
        id=rec_id,
        project_id="p1",
        source_file_id="file-1",
        source_quote=quote,
        source_page=2,
        normalized_text=text or quote,
        kind=kind,
        scope=scope,
        target_section_hint=None,
        proposal_path_json=[],
        acceptance_criteria_json=[],
        status=status,
        origin="map",
        identity_key=None,
        human_decision_json=decision,
    )
    return item


def extracted(quote, *, kind="content", scope="proposal_content", text=None):
    return {
        "source_ref": {"file_id": "file-1", "page": 3},
        "source_quote": quote,
        "normalized_text": text or f"машинно: {quote}",
        "kind": kind,
        "scope": scope,
        "target_section_hint": None,
        "proposal_path": [],
        "acceptance_criteria": [],
        "origin": "map",
    }


def factory(**fields):
    return SimpleNamespace(human_decision_json=None, **fields)


def test_confirmation_edit_and_rejection_survive_reanalysis():
    """T-08: unchanged statements keep ids, statuses and human edits."""
    confirmed = record("r-conf", "Участникът описва екипа.")
    record_human_decision(confirmed, status="confirmed")
    confirmed.status = "confirmed"
    edited = record("r-edit", "Участникът описва контрола.", text="Човешка редакция")
    record_human_decision(edited, edited_fields=["normalized_text"])
    rejected = record("r-rej", "Шум от документа.")
    record_human_decision(rejected, status="rejected")
    rejected.status = "rejected"

    changes = reconcile_requirements(
        [confirmed, edited, rejected],
        [
            extracted("Участникът описва екипа."),
            extracted("Участникът   описва контрола."),  # whitespace-only difference
            extracted("Шум от документа."),
        ],
        project_id="p1",
        model_factory=factory,
    )

    assert {item.id for item in changes["kept"]} == {"r-conf", "r-edit", "r-rej"}
    assert changes["created"] == []
    assert confirmed.status == "confirmed"
    assert rejected.status == "rejected"
    assert edited.normalized_text == "Човешка редакция"  # human edit kept
    assert confirmed.normalized_text == "машинно: Участникът описва екипа."  # unedited refreshed
    assert confirmed.source_page == 3


def test_changed_source_never_inherits_an_old_approval():
    old = record("r-old", "Срок за проектиране 30 дни.", status="confirmed")
    record_human_decision(old, status="confirmed")
    unreviewed = record("r-noise", "Нещо непрегледано.")

    changes = reconcile_requirements(
        [old, unreviewed],
        [extracted("Срок за проектиране 45 дни.")],
        project_id="p1",
        model_factory=factory,
    )

    assert old.status == "superseded"  # kept for old plans, out of the active register
    assert changes["superseded"] == [old]
    assert changes["deleted"] == [unreviewed]
    new = changes["created"][0]
    assert new.status == "extracted"
    assert new.id != "r-old"


def test_reinterpreted_confirmed_requirement_returns_to_review():
    confirmed = record("r-1", "Участникът прилага сертификатите.", status="confirmed")
    record_human_decision(confirmed, status="confirmed")

    changes = reconcile_requirements(
        [confirmed],
        [extracted("Участникът прилага сертификатите.", scope="qualification_admin")],
        project_id="p1",
        model_factory=factory,
    )

    assert confirmed.status == "extracted"
    assert confirmed.human_decision_json["needs_review"] == "reinterpreted"
    assert changes["needs_review"] == [confirmed]


def test_identity_is_file_plus_normalized_quote():
    assert requirement_identity("f", "A  b") == requirement_identity("f", "a b")
    assert requirement_identity("f", "a b") != requirement_identity("g", "a b")


def test_wbs_ids_and_statuses_are_preserved():
    kept = SimpleNamespace(id="w1", title="Проектиране", kind="activity", status="confirmed", level=0, description="d", source_refs_json=[], schedule_task_uid="7", order_index=0)
    stale_confirmed = SimpleNamespace(id="w2", title="Стара дейност", kind="task", status="confirmed", level=1, description=None, source_refs_json=[], schedule_task_uid=None, order_index=1)
    stale_draft = SimpleNamespace(id="w3", title="Чернова", kind="task", status="extracted", level=1, description=None, source_refs_json=[], schedule_task_uid=None, order_index=2)

    changes = reconcile_wbs(
        [kept, stale_confirmed, stale_draft],
        [{"key": "k1", "title": "проектиране", "kind": "activity", "level": 0, "order_index": 0, "source_refs": [{"chunk_id": "c"}]}],
        project_id="p1",
        model_factory=factory,
    )

    assert changes["models"]["k1"] is kept
    assert kept.status == "confirmed"
    assert stale_confirmed.status == "superseded"
    assert changes["deleted"] == [stale_draft]
