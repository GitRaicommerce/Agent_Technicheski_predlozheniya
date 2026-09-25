"""WP-04 / K-05 acceptance (T-06, T-07): a job works from its recorded inputs."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.context import build_project_grounding_context_v2
from app.agents.generation_jobs import create_drafting_job
from app.agents.job_inputs import (
    JobInputsChangedError,
    capture_job_inputs,
    load_job_outline,
    plan_content_hash,
)
from app.core.models import TpOutline
from tests.conftest import _make_project


def _outline(version=1, locked=True, uid="unit-1"):
    return TpOutline(
        id=str(uuid.uuid4()),
        project_id="project-1",
        version=version,
        status_locked=locked,
        outline_json={"sections": [{"uid": uid, "title": "Точка", "subsections": []}]},
    )


def _result(value):
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=value)
    return result


def _job_for(outline):
    return SimpleNamespace(
        result_json={
            "input_snapshot": {
                "outline_id": outline.id,
                "outline_version": outline.version,
                "plan_content_hash": plan_content_hash(outline),
            }
        }
    )


@pytest.mark.asyncio
async def test_job_loads_its_recorded_plan():
    plan_a = _outline(version=1)
    db = MagicMock()
    db.execute = AsyncMock(return_value=_result(plan_a))

    assert await load_job_outline(_job_for(plan_a), db) is plan_a


@pytest.mark.asyncio
async def test_job_never_switches_to_a_newer_approved_plan():
    """T-06: job for A; B approved before start → specific error, not B."""
    plan_a = _outline(version=1)
    job = _job_for(plan_a)
    plan_a.status_locked = False  # approving B unlocked A
    db = MagicMock()
    db.execute = AsyncMock(return_value=_result(plan_a))

    with pytest.raises(JobInputsChangedError, match="няма да премине към друг план"):
        await load_job_outline(job, db)


@pytest.mark.asyncio
async def test_edited_plan_content_is_detected():
    plan_a = _outline(version=1)
    job = _job_for(plan_a)
    plan_a.outline_json = {"sections": [{"uid": "unit-1", "title": "Променено"}]}
    db = MagicMock()
    db.execute = AsyncMock(return_value=_result(plan_a))

    with pytest.raises(JobInputsChangedError, match="променено"):
        await load_job_outline(job, db)


@pytest.mark.asyncio
async def test_job_without_recorded_inputs_cannot_start_paid_drafting():
    db = MagicMock()
    with pytest.raises(JobInputsChangedError, match="преди фиксирането"):
        await load_job_outline(SimpleNamespace(result_json={"outline_id": "x"}), db)


@pytest.mark.asyncio
async def test_unknown_target_units_are_rejected_before_dispatch(mock_db):
    project = _make_project()
    plan_a = _outline(uid="unit-1")
    with (
        patch("app.agents.generation_jobs._approved_outline", new=AsyncMock(return_value=plan_a)),
        patch("app.agents.generation_jobs.capture_job_inputs", new=AsyncMock(return_value={"schema_version": 1})),
        patch("app.agents.generation_jobs._enqueue_generation_job") as enqueue,
    ):
        with pytest.raises(ValueError, match="unit-ghost"):
            await create_drafting_job(
                project,
                mock_db,
                target_section_uids=["unit-1", "unit-ghost"],
            )
    enqueue.assert_not_called()
    mock_db.add.assert_not_called()


@pytest.mark.asyncio
async def test_resume_reuses_the_recorded_snapshot(mock_db):
    project = _make_project()
    plan_a = _outline(uid="unit-2")
    snapshot = _job_for(plan_a).result_json["input_snapshot"]
    mock_db.execute = AsyncMock(return_value=_result(plan_a))
    capture = AsyncMock()

    with (
        patch("app.agents.generation_jobs.capture_job_inputs", new=capture),
        patch("app.agents.generation_jobs._enqueue_generation_job"),
    ):
        job = await create_drafting_job(
            project,
            mock_db,
            target_section_uids=["unit-2"],
            input_snapshot=snapshot,
        )

    capture.assert_not_awaited()
    assert job.result_json["input_snapshot"] is snapshot
    assert job.result_json["outline_id"] == plan_a.id


@pytest.mark.asyncio
async def test_snapshot_stores_fact_and_brief_content_not_just_ids():
    plan_a = _outline()
    fact_sheet = SimpleNamespace(id="facts-3", version=3, status="confirmed", facts_json={"team": ["ВиК инженер"]})
    schedule = SimpleNamespace(id="schedule-7", version=7)
    brief = SimpleNamespace(id="brief-2", version=2, content_hash="h", content="Не включвай част Електро.")
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[_result(fact_sheet), _result(schedule), _result(brief)])

    with patch(
        "app.agents.source_manifest.build_source_manifest",
        new=AsyncMock(return_value={"manifest_hash": "m1", "complete": True}),
    ):
        snapshot = await capture_job_inputs("project-1", plan_a, db)

    assert snapshot["fact_sheet"]["facts"] == {"team": ["ВиК инженер"]}
    assert snapshot["schedule"] == {"id": "schedule-7", "version": 7}
    assert snapshot["brief"]["content"] == "Не включвай част Електро."
    assert snapshot["source_manifest_hash"] == "m1"
    assert snapshot["plan_content_hash"] == plan_content_hash(plan_a)


@pytest.mark.asyncio
async def test_changed_facts_create_a_new_version(client, mock_db, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.generation_pipeline", "v2")
    project = _make_project()
    current = SimpleNamespace(
        id="facts-3", project_id=project.id, version=3, status="confirmed", facts_json={"a": 1}
    )
    mock_db.get = AsyncMock(return_value=project)
    mock_db.execute = AsyncMock(return_value=_result(current))
    added = []
    mock_db.add = MagicMock(side_effect=added.append)

    async def assign_id():
        for item in added:
            item.id = item.id or "facts-4"

    mock_db.flush = AsyncMock(side_effect=assign_id)

    response = await client.put(
        f"/api/v1/understanding/{project.id}/fact-sheet",
        json={"facts_json": {"a": 2}, "status": "draft"},
    )

    assert response.status_code == 200
    assert response.json()["version"] == 4
    assert current.facts_json == {"a": 1}  # the recorded version is untouched
    assert added[0].facts_json == {"a": 2}


@pytest.mark.asyncio
async def test_frozen_facts_are_used_even_after_the_fact_sheet_changed(monkeypatch):
    """T-07: facts edited between two subpoints do not reach the running job."""
    base = {"tender_chunks": [], "schedule": {"tasks": []}}
    db = MagicMock()
    # Only the WBS query may hit the database; facts must not be re-read.
    wbs_result = MagicMock()
    wbs_result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=wbs_result)

    with (
        patch("app.agents.context.build_project_grounding_context", new=AsyncMock(return_value=base)) as base_ctx,
        patch("app.core.embedding.embed_query", new=AsyncMock(return_value=None)),
    ):
        context = await build_project_grounding_context_v2(
            "project-1",
            "Организация",
            [],
            db,
            frozen_facts={"team": ["стара стойност"]},
            frozen_fact_meta={"version": 3, "status": "confirmed"},
            schedule_id="schedule-7",
        )

    assert context["project_fact_sheet"] == {
        "version": 3,
        "status": "confirmed",
        "facts": {"team": ["стара стойност"]},
    }
    assert db.execute.await_count == 1
    assert base_ctx.await_args.kwargs["schedule_id"] == "schedule-7"
