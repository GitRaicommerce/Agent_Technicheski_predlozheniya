"""K-07: reanalysis preserves human review decisions.

A new understanding run no longer deletes and recreates the machine register.
It reconciles the new extraction with the existing records by a stable
identity — the source file plus the normalized verbatim quote:

- same statement → the record keeps its id (approved plans stay resolvable),
  its human status (confirmed/rejected) and every field the human edited;
  machine fields the human never touched are refreshed. If the machine's
  interpretation of an unedited, already-confirmed record changed (kind or
  scope), the approval is not carried over silently — it returns to review;
- new statement → a new ``extracted`` record;
- statement no longer produced (changed/removed source) → a reviewed record
  becomes ``superseded`` (kept for old plans, excluded from the active
  register); an unreviewed one is deleted. A changed source never inherits
  an old approval.

WBS items are reconciled by (normalized title, kind) with the same id/status
preservation; unmatched confirmed items become ``superseded``.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timezone
from typing import Any

MACHINE_ORIGINS = ("map", "audit", "proposal_audit")
REVIEW_FIELDS = (
    "normalized_text",
    "kind",
    "scope",
    "target_section_hint",
    "proposal_path_json",
    "acceptance_criteria_json",
    "source_page",
)


def _normalize_quote(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().casefold()


def requirement_identity(source_file_id: Any, source_quote: Any) -> str:
    raw = f"{source_file_id}|{_normalize_quote(source_quote)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def record_human_decision(record: Any, *, status: str | None = None, edited_fields: list[str] | None = None) -> None:
    """Store the reviewer's decision so reanalysis can preserve it."""
    decision = dict(getattr(record, "human_decision_json", None) or {})
    if status:
        decision["status"] = status
    if edited_fields:
        decision["edited_fields"] = sorted(
            set(decision.get("edited_fields") or []) | set(edited_fields)
        )
    decision["decided_at"] = datetime.now(timezone.utc).isoformat()
    record.human_decision_json = decision
    if getattr(record, "identity_key", None) is None:
        record.identity_key = requirement_identity(record.source_file_id, record.source_quote)


def _new_fields(item: dict[str, Any]) -> dict[str, Any]:
    ref = item["source_ref"]
    return {
        "source_file_id": ref["file_id"],
        "source_page": ref.get("page"),
        "source_quote": item["source_quote"],
        "normalized_text": item["normalized_text"],
        "kind": item["kind"],
        "scope": item.get("scope", "execution_constraint"),
        "target_section_hint": item.get("target_section_hint"),
        "proposal_path_json": item.get("proposal_path") or [],
        "acceptance_criteria_json": item.get("acceptance_criteria") or [],
        "origin": item.get("origin", "map"),
    }


def reconcile_requirements(
    existing: list[Any],
    extracted: list[dict[str, Any]],
    *,
    project_id: str,
    model_factory,
) -> dict[str, list[Any]]:
    """Return {"kept", "created", "superseded", "deleted", "needs_review"}."""
    by_key: dict[str, Any] = {}
    for record in existing:
        if getattr(record, "origin", None) not in MACHINE_ORIGINS:
            continue
        key = record.identity_key or requirement_identity(record.source_file_id, record.source_quote)
        record.identity_key = key
        # Keep the reviewed record if duplicates exist for the same statement.
        if key not in by_key or getattr(record, "human_decision_json", None):
            by_key[key] = record

    kept: list[Any] = []
    created: list[Any] = []
    needs_review: list[Any] = []
    seen: set[str] = set()
    for item in extracted:
        fields = _new_fields(item)
        key = requirement_identity(fields["source_file_id"], fields["source_quote"])
        if key in seen:
            continue
        seen.add(key)
        old = by_key.pop(key, None)
        if old is None:
            record = model_factory(
                id=str(uuid.uuid4()),
                project_id=project_id,
                status="extracted",
                identity_key=key,
                **fields,
            )
            created.append(record)
            continue
        decision = dict(getattr(old, "human_decision_json", None) or {})
        edited = set(decision.get("edited_fields") or [])
        reinterpreted = (
            ("kind" not in edited and old.kind != fields["kind"])
            or ("scope" not in edited and old.scope != fields["scope"])
        )
        for field, value in fields.items():
            if field in edited or field in {"source_file_id", "source_quote"}:
                continue
            setattr(old, field, value)
        if old.status == "superseded":
            old.status = decision.get("status") or "extracted"
        if old.status == "confirmed" and reinterpreted and not edited:
            # The machine now reads the same statement differently; do not
            # carry the approval over silently.
            old.status = "extracted"
            decision["needs_review"] = "reinterpreted"
            old.human_decision_json = decision
            needs_review.append(old)
        kept.append(old)

    superseded: list[Any] = []
    deleted: list[Any] = []
    for old in by_key.values():
        reviewed = bool(getattr(old, "human_decision_json", None)) or old.status in {
            "confirmed",
            "rejected",
        }
        if reviewed:
            old.status = "superseded"
            superseded.append(old)
        else:
            deleted.append(old)
    return {
        "kept": kept,
        "created": created,
        "superseded": superseded,
        "deleted": deleted,
        "needs_review": needs_review,
    }


def _wbs_key(title: Any, kind: Any) -> tuple[str, str]:
    return (re.sub(r"\s+", " ", str(title or "")).strip().casefold(), str(kind or ""))


def reconcile_wbs(
    existing: list[Any],
    extracted: list[dict[str, Any]],
    *,
    project_id: str,
    model_factory,
) -> dict[str, Any]:
    by_key = {_wbs_key(item.title, item.kind): item for item in existing}
    models: dict[str, Any] = {}
    created: list[Any] = []
    for item in extracted:
        key = _wbs_key(item["title"], item["kind"])
        old = by_key.pop(key, None)
        if old is not None:
            old.level = item["level"]
            old.description = item.get("description") if old.status != "confirmed" else old.description
            old.source_refs_json = item.get("source_refs") or []
            old.schedule_task_uid = item.get("schedule_task_uid") or old.schedule_task_uid
            old.order_index = item["order_index"]
            if old.status == "superseded":
                old.status = "extracted"
            models[item["key"]] = old
            continue
        model = model_factory(
            id=str(uuid.uuid4()),
            project_id=project_id,
            parent_id=None,
            level=item["level"],
            kind=item["kind"],
            title=item["title"],
            description=item.get("description"),
            source_refs_json=item.get("source_refs") or [],
            schedule_task_uid=item.get("schedule_task_uid"),
            order_index=item["order_index"],
            status="extracted",
        )
        models[item["key"]] = model
        created.append(model)
    superseded: list[Any] = []
    deleted: list[Any] = []
    for old in by_key.values():
        if old.status in {"confirmed", "rejected"}:
            old.status = "superseded" if old.status == "confirmed" else old.status
            superseded.append(old)
        else:
            deleted.append(old)
    return {"models": models, "created": created, "superseded": superseded, "deleted": deleted}
