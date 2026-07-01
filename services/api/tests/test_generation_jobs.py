from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.generation_jobs import _run_drafting_all_job, _sections_pending_generation
from app.core.models import TpOutline
from tests.conftest import _make_project


def _outline_result(outline: TpOutline) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=outline)
    return result


def test_sections_pending_generation_retries_stale_sections():
    sections = [
        {"uid": "fresh", "title": "Fresh"},
        {"uid": "stale", "title": "Stale"},
        {"uid": "missing", "title": "Missing"},
        {"uid": "mixed", "title": "Mixed"},
    ]
    generation_statuses = {
        "fresh": {"ok"},
        "stale": {"stale"},
        "mixed": {"stale", "ok"},
    }

    pending = _sections_pending_generation(sections, generation_statuses)

    assert [section["uid"] for section in pending] == ["stale", "missing"]


@pytest.mark.asyncio
async def test_generation_job_records_failed_section_and_keeps_progress(mock_db):
    project = _make_project()
    section_ok = str(uuid.uuid4())
    section_failed = str(uuid.uuid4())
    outline = TpOutline(
        id=str(uuid.uuid4()),
        project_id=project.id,
        outline_json={
            "sections": [
                {
                    "uid": section_ok,
                    "title": "Концепция и подход",
                    "requirements": [],
                    "subsections": [],
                },
                {
                    "uid": section_failed,
                    "title": "Разработване на инвестиционен проект",
                    "requirements": [],
                    "subsections": [],
                },
            ]
        },
        status_locked=True,
        version=1,
    )
    job = SimpleNamespace(
        id=str(uuid.uuid4()),
        project_id=project.id,
        trace_id=str(uuid.uuid4()),
        status="queued",
        total_sections=0,
        completed_sections=0,
        skipped_sections=0,
        current_section_uid=None,
        current_section_title=None,
        result_json=None,
        error=None,
        completed_at=None,
        updated_at=None,
    )

    mock_db.get = AsyncMock(side_effect=[project, job])
    mock_db.execute = AsyncMock(side_effect=[_outline_result(outline), []])

    with (
        patch(
            "app.agents.schedule.run_schedule",
            new=AsyncMock(return_value={"status": "ok", "tp_section_text": "График"}),
        ),
        patch(
            "app.agents.examples.run_examples",
            new=AsyncMock(return_value={"selected_snippets": []}),
        ),
        patch(
            "app.agents.legislation.run_legislation",
            new=AsyncMock(return_value={"citations": []}),
        ),
        patch(
            "app.agents.context.build_project_grounding_context",
            new=AsyncMock(return_value={"schedule": {"tasks": []}}),
        ),
        patch(
            "app.agents.drafting.run_drafting",
            new=AsyncMock(
                side_effect=[
                    {"generation_ids": {"variant_1": str(uuid.uuid4())}},
                    RuntimeError("Connection error."),
                ]
            ),
        ),
    ):
        await _run_drafting_all_job(job, mock_db)

    assert job.status == "error"
    assert job.completed_sections == 1
    assert job.skipped_sections == 1
    assert len(job.result_json["sections"]) == 1
    assert job.result_json["sections"][0]["section_uid"] == section_ok
    assert len(job.result_json["failed_sections"]) == 1
    assert job.result_json["failed_sections"][0]["section_uid"] == section_failed
    assert "Run generation again" in job.error


@pytest.mark.asyncio
async def test_generation_job_continues_when_schedule_summary_fails(mock_db):
    project = _make_project()
    section_uid = str(uuid.uuid4())
    outline = TpOutline(
        id=str(uuid.uuid4()),
        project_id=project.id,
        outline_json={
            "sections": [
                {
                    "uid": section_uid,
                    "title": "Линеен график",
                    "requirements": [],
                    "subsections": [],
                }
            ]
        },
        status_locked=True,
        version=1,
    )
    job = SimpleNamespace(
        id=str(uuid.uuid4()),
        project_id=project.id,
        trace_id=str(uuid.uuid4()),
        status="queued",
        total_sections=0,
        completed_sections=0,
        skipped_sections=0,
        current_section_uid=None,
        current_section_title=None,
        result_json=None,
        error=None,
        completed_at=None,
        updated_at=None,
    )

    mock_db.get = AsyncMock(side_effect=[project, job])
    mock_db.execute = AsyncMock(side_effect=[_outline_result(outline), []])

    with (
        patch(
            "app.agents.schedule.run_schedule",
            new=AsyncMock(side_effect=RuntimeError("Connection error.")),
        ),
        patch(
            "app.agents.examples.run_examples",
            new=AsyncMock(return_value={"selected_snippets": []}),
        ),
        patch(
            "app.agents.legislation.run_legislation",
            new=AsyncMock(return_value={"citations": []}),
        ),
        patch(
            "app.agents.context.build_project_grounding_context",
            new=AsyncMock(return_value={"schedule": {"tasks": []}}),
        ),
        patch(
            "app.agents.drafting.run_drafting",
            new=AsyncMock(return_value={"generation_ids": {"variant_1": str(uuid.uuid4())}}),
        ) as run_drafting,
    ):
        await _run_drafting_all_job(job, mock_db)

    assert job.status == "done"
    assert job.completed_sections == 1
    assert job.result_json["failed_sections"] == []
    assert run_drafting.await_args.kwargs["schedule_summary"] is None


@pytest.mark.asyncio
async def test_generation_job_continues_when_legislation_fails(mock_db):
    project = _make_project()
    section_uid = str(uuid.uuid4())
    outline = TpOutline(
        id=str(uuid.uuid4()),
        project_id=project.id,
        outline_json={
            "sections": [
                {
                    "uid": section_uid,
                    "title": "РџСЂРѕРµРєС‚РёСЂР°РЅРµ",
                    "requirements": [],
                    "subsections": [],
                }
            ]
        },
        status_locked=True,
        version=1,
    )
    job = SimpleNamespace(
        id=str(uuid.uuid4()),
        project_id=project.id,
        trace_id=str(uuid.uuid4()),
        status="queued",
        total_sections=0,
        completed_sections=0,
        skipped_sections=0,
        current_section_uid=None,
        current_section_title=None,
        result_json=None,
        error=None,
        completed_at=None,
        updated_at=None,
    )

    mock_db.get = AsyncMock(side_effect=[project, job])
    mock_db.execute = AsyncMock(side_effect=[_outline_result(outline), []])

    with (
        patch(
            "app.agents.schedule.run_schedule",
            new=AsyncMock(return_value={"status": "ok", "tp_section_text": "Р“СЂР°С„РёРє"}),
        ),
        patch(
            "app.agents.examples.run_examples",
            new=AsyncMock(return_value={"selected_snippets": []}),
        ),
        patch(
            "app.agents.legislation.run_legislation",
            new=AsyncMock(side_effect=RuntimeError("Lex.bg unavailable")),
        ),
        patch(
            "app.agents.context.build_project_grounding_context",
            new=AsyncMock(return_value={"schedule": {"tasks": []}}),
        ),
        patch(
            "app.agents.drafting.run_drafting",
            new=AsyncMock(return_value={"generation_ids": {"variant_1": str(uuid.uuid4())}}),
        ) as run_drafting,
    ):
        await _run_drafting_all_job(job, mock_db)

    assert job.status == "done"
    assert job.completed_sections == 1
    assert job.result_json["failed_sections"] == []
    assert run_drafting.await_args.kwargs["lex_citations"] == []
