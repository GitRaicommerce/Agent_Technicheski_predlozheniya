"""Immutable job input sets (card K-05, plan §4.2).

A drafting job fixes, at creation, exactly which inputs it works from: the
plan (identity + content hash), the confirmed facts (content), the schedule
version, the project brief (content), the source-manifest fingerprint and the
model-policy version. Every unit of the job — including resume — reads these
recorded inputs, never "whatever is latest now".

A recorded identifier alone is not enough when its JSON can be edited in
place, so the facts and brief *content* is stored in the snapshot, and the
plan is verified by content hash before any paid unit starts.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.core.models import (
    ProjectBrief,
    ProjectFactSheet,
    ScheduleNormalized,
    TpOutline,
)

SNAPSHOT_SCHEMA_VERSION = 1


class JobInputsChangedError(ValueError):
    """The recorded inputs are no longer available or have been altered."""


def content_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def plan_content_hash(outline: TpOutline) -> str:
    outline_json = outline.outline_json if isinstance(outline.outline_json, dict) else {}
    return content_hash(outline_json.get("sections") or [])


async def latest_brief(project_id: str, db) -> ProjectBrief | None:
    result = await db.execute(
        select(ProjectBrief)
        .where(ProjectBrief.project_id == project_id)
        .order_by(ProjectBrief.version.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def capture_job_inputs(project_id: str, outline: TpOutline, db) -> dict[str, Any]:
    from app.agents.source_manifest import build_source_manifest
    from app.core.model_policy import policy_mode, policy_version

    fact_result = await db.execute(
        select(ProjectFactSheet)
        .where(ProjectFactSheet.project_id == project_id)
        .order_by(ProjectFactSheet.version.desc())
        .limit(1)
    )
    fact_sheet = fact_result.scalar_one_or_none()
    facts = (
        fact_sheet.facts_json
        if fact_sheet is not None and isinstance(fact_sheet.facts_json, dict)
        else {}
    )
    schedule_result = await db.execute(
        select(ScheduleNormalized)
        .where(ScheduleNormalized.project_id == project_id)
        .order_by(ScheduleNormalized.version.desc())
        .limit(1)
    )
    schedule = schedule_result.scalar_one_or_none()
    brief = await latest_brief(project_id, db)
    manifest = await build_source_manifest(project_id, db)
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "outline_id": str(outline.id),
        "outline_version": outline.version,
        "plan_content_hash": plan_content_hash(outline),
        "fact_sheet": {
            "id": str(fact_sheet.id) if fact_sheet is not None else None,
            "version": fact_sheet.version if fact_sheet is not None else None,
            "status": fact_sheet.status if fact_sheet is not None else None,
            "content_hash": content_hash(facts),
            "facts": facts,
        },
        "schedule": {
            "id": str(schedule.id) if schedule is not None else None,
            "version": schedule.version if schedule is not None else None,
        },
        "brief": {
            "id": str(brief.id) if brief is not None else None,
            "version": brief.version if brief is not None else None,
            "content_hash": brief.content_hash if brief is not None else None,
            "content": brief.content if brief is not None else "",
        },
        "source_manifest_hash": manifest["manifest_hash"],
        "source_manifest_complete": manifest["complete"],
        "model_policy": {"mode": policy_mode(), "version": policy_version()},
    }


def job_snapshot(job: Any) -> dict[str, Any] | None:
    result = job.result_json if isinstance(getattr(job, "result_json", None), dict) else {}
    snapshot = result.get("input_snapshot")
    return snapshot if isinstance(snapshot, dict) else None


async def load_job_outline(job: Any, db) -> TpOutline:
    """The plan recorded by the job — never silently the latest approved one."""
    snapshot = job_snapshot(job)
    if snapshot is None:
        raise JobInputsChangedError(
            "Задачата е създадена преди фиксирането на входните данни и не може "
            "да започне ново платено писане. Стартирайте нова задача."
        )
    result = await db.execute(
        select(TpOutline).where(TpOutline.id == snapshot["outline_id"]).limit(1)
    )
    outline = result.scalar_one_or_none()
    if outline is None:
        raise JobInputsChangedError(
            f"Планът v{snapshot.get('outline_version')}, записан в задачата, вече не съществува."
        )
    if not outline.status_locked:
        raise JobInputsChangedError(
            f"Планът v{outline.version}, записан в задачата, вече не е одобрен. "
            "Задачата няма да премине към друг план; одобрете плана и стартирайте нова задача."
        )
    if plan_content_hash(outline) != snapshot.get("plan_content_hash"):
        raise JobInputsChangedError(
            f"Съдържанието на плана v{outline.version} е променено след създаването "
            "на задачата. Стартирайте нова задача за текущия план."
        )
    return outline


def frozen_facts(job: Any) -> dict[str, Any] | None:
    snapshot = job_snapshot(job)
    if snapshot is None:
        return None
    facts = (snapshot.get("fact_sheet") or {}).get("facts")
    return facts if isinstance(facts, dict) else {}


def frozen_fact_sheet_meta(job: Any) -> dict[str, Any] | None:
    snapshot = job_snapshot(job)
    if snapshot is None:
        return None
    sheet = snapshot.get("fact_sheet") or {}
    return {"version": sheet.get("version"), "status": sheet.get("status")}


def frozen_schedule_id(job: Any) -> str | None:
    snapshot = job_snapshot(job)
    return ((snapshot or {}).get("schedule") or {}).get("id")


def frozen_brief(job: Any) -> str:
    snapshot = job_snapshot(job)
    return str(((snapshot or {}).get("brief") or {}).get("content") or "")


def validate_target_units(
    requested: list[str] | None, available_units: list[dict[str, Any]]
) -> list[str]:
    """Return requested unit ids that do not exist in the recorded plan."""
    if requested is None:
        return []
    known = {str(unit.get("uid") or unit.get("section_uid")) for unit in available_units}
    return [uid for uid in requested if str(uid) not in known]
