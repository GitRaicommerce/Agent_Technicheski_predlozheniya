from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.generation_jobs import (
    _run_drafting_all_job,
    _sections_pending_generation,
    create_drafting_quality_job,
    create_drafting_requirements_job,
    create_drafting_stale_job,
)
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


@pytest.mark.asyncio
async def test_generation_job_targets_requested_sections(mock_db):
    project = _make_project()
    skipped_uid = str(uuid.uuid4())
    target_uid = str(uuid.uuid4())
    outline = TpOutline(
        id=str(uuid.uuid4()),
        project_id=project.id,
        outline_json={
            "sections": [
                {
                    "uid": skipped_uid,
                    "title": "Already fresh",
                    "requirements": [],
                    "subsections": [],
                },
                {
                    "uid": target_uid,
                    "title": "Selected stale",
                    "requirements": [],
                    "drafting_guidance": {
                        "requirement_count": 2,
                        "required_subtopics": ["organization", "controls"],
                    },
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
        job_type="drafting_stale",
        status="queued",
        total_sections=0,
        completed_sections=0,
        skipped_sections=0,
        current_section_uid=None,
        current_section_title=None,
        result_json={
            "target_section_uids": [target_uid],
            "target_reason": "stale_selected",
            "target_guidance": {
                target_uid: {
                    "instructions": [
                        "Regenerate this section with the missing control record."
                    ],
                    "missing_requirement_ids": ["req-control"],
                    "missing_requirement_items": [
                        {
                            "id": "req-control",
                            "text": "Describe the control record.",
                            "reason": "needs operational evidence",
                            "remediation_guidance": (
                                "Add operational evidence for the control record."
                            ),
                        }
                    ],
                }
            },
        },
        error=None,
        completed_at=None,
        updated_at=None,
    )

    generation_rows = [
        SimpleNamespace(section_uid=skipped_uid, evidence_status="ok"),
        SimpleNamespace(section_uid=target_uid, evidence_status="ok"),
    ]
    mock_db.get = AsyncMock(side_effect=[project])
    mock_db.execute = AsyncMock(side_effect=[_outline_result(outline), generation_rows])

    with (
        patch(
            "app.agents.schedule.run_schedule",
            new=AsyncMock(return_value={"status": "ok", "tp_section_text": "Schedule"}),
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
    assert job.total_sections == 1
    assert job.skipped_sections == 0
    assert job.completed_sections == 1
    assert run_drafting.await_count == 1
    assert run_drafting.await_args.kwargs["section_uid"] == target_uid
    assert run_drafting.await_args.kwargs["section_drafting_guidance"] == {
        "requirement_count": 2,
        "required_subtopics": ["organization", "controls"],
        "instructions": [
            "Regenerate this section with the missing control record."
        ],
        "missing_requirement_ids": ["req-control"],
        "missing_requirement_items": [
            {
                "id": "req-control",
                "text": "Describe the control record.",
                "reason": "needs operational evidence",
                "remediation_guidance": (
                    "Add operational evidence for the control record."
                ),
            }
        ],
    }
    assert job.result_json["target_section_uids"] == [target_uid]
    assert job.result_json["target_reason"] == "stale_selected"
    assert job.result_json["target_guidance"][target_uid]["missing_requirement_ids"] == [
        "req-control"
    ]


@pytest.mark.asyncio
async def test_create_drafting_stale_job_targets_selected_stale_sections(mock_db):
    project = _make_project()
    stale_uid = str(uuid.uuid4())
    stale_result = [(stale_uid,)]
    mock_db.execute = AsyncMock(return_value=stale_result)
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()

    with patch("app.agents.generation_jobs._enqueue_generation_job") as enqueue:
        job = await create_drafting_stale_job(project, mock_db)

    assert job.job_type == "drafting_stale"
    assert job.result_json == {
        "target_section_uids": [stale_uid],
        "target_reason": "stale_selected",
    }
    mock_db.add.assert_called_once_with(job)
    enqueue.assert_called_once_with(job.id)


@pytest.mark.asyncio
async def test_create_drafting_quality_job_targets_quality_sections(mock_db):
    project = _make_project()
    selected_generations = [SimpleNamespace(section_uid="sec-quality")]
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()

    with (
        patch("app.agents.generation_jobs._enqueue_generation_job") as enqueue,
        patch(
            "app.routers.export._load_selected_generations",
            new=AsyncMock(return_value=selected_generations),
        ) as load_selected,
        patch(
            "app.routers.export._build_export_readiness",
            new=AsyncMock(
                return_value={
                    "quality_sections": [
                        {"section_uid": "sec-quality"},
                        {"section_uid": "sec-quality"},
                    ]
                }
            ),
        ) as build_readiness,
    ):
        job = await create_drafting_quality_job(project, mock_db)

    assert job.job_type == "drafting_quality"
    assert job.result_json == {
        "target_section_uids": ["sec-quality"],
        "target_reason": "quality_review",
    }
    load_selected.assert_awaited_once_with(project.id, mock_db)
    build_readiness.assert_awaited_once_with(
        project.id,
        selected_generations,
        mock_db,
    )
    mock_db.add.assert_called_once_with(job)
    enqueue.assert_called_once_with(job.id)


@pytest.mark.asyncio
async def test_create_drafting_requirements_job_filters_requested_missing_sections(
    mock_db,
):
    project = _make_project()
    selected_generations = [
        SimpleNamespace(section_uid="sec-quality"),
        SimpleNamespace(section_uid="sec-risk"),
    ]
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()

    with (
        patch("app.agents.generation_jobs._enqueue_generation_job") as enqueue,
        patch(
            "app.routers.export._load_selected_generations",
            new=AsyncMock(return_value=selected_generations),
        ),
        patch(
            "app.routers.export._build_export_readiness",
            new=AsyncMock(
                return_value={
                    "missing_requirement_sections": [
                        {
                            "section_uid": "sec-quality",
                            "missing_requirement_ids": ["req-quality"],
                            "missing_items": [
                                {
                                    "id": "req-quality",
                                    "text": "Describe quality evidence.",
                                    "reason": "needs operational evidence",
                                    "remediation_guidance": (
                                        "Regenerate quality with records."
                                    ),
                                }
                            ],
                        },
                        {
                            "section_uid": "sec-risk",
                            "missing_requirement_ids": ["req-risk"],
                            "missing_items": [
                                {
                                    "id": "req-risk",
                                    "text": "Describe risk controls.",
                                    "reason": "missing key terms",
                                    "remediation_guidance": (
                                        "Regenerate risk with controls."
                                    ),
                                }
                            ],
                        },
                    ]
                }
            ),
        ),
    ):
        job = await create_drafting_requirements_job(
            project,
            mock_db,
            target_section_uids=["sec-quality"],
            target_reason="calibration_gap:regenerate_missing_requirements",
        )

    assert job.job_type == "drafting_requirements"
    assert job.result_json["target_section_uids"] == ["sec-quality"]
    assert job.result_json["target_reason"] == (
        "calibration_gap:regenerate_missing_requirements"
    )
    assert job.result_json["target_guidance"] == {
        "sec-quality": {
            "instructions": ["Regenerate quality with records."],
            "missing_requirement_ids": ["req-quality"],
            "missing_requirement_items": [
                {
                    "id": "req-quality",
                    "text": "Describe quality evidence.",
                    "reason": "needs operational evidence",
                    "remediation_guidance": "Regenerate quality with records.",
                    "missing_terms": [],
                    "required_match_count": None,
                    "required_coherent_match_count": None,
                    "required_operational_signal_count": None,
                }
            ],
        }
    }
    mock_db.add.assert_called_once_with(job)
    enqueue.assert_called_once_with(job.id)


@pytest.mark.asyncio
async def test_create_drafting_requirements_job_targets_missing_requirement_sections(
    mock_db,
):
    project = _make_project()
    selected_generations = [SimpleNamespace(section_uid="sec-missing")]
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()

    with (
        patch("app.agents.generation_jobs._enqueue_generation_job") as enqueue,
        patch(
            "app.routers.export._load_selected_generations",
            new=AsyncMock(return_value=selected_generations),
        ) as load_selected,
        patch(
            "app.routers.export._build_export_readiness",
            new=AsyncMock(
                return_value={
                    "missing_requirement_sections": [
                        {
                            "section_uid": "sec-missing",
                            "missing_requirement_ids": ["req-1"],
                            "missing_items": [
                                {
                                    "id": "req-1",
                                    "text": "Describe missing control.",
                                    "reason": "needs operational evidence",
                                    "remediation_guidance": (
                                        "Regenerate with a control record and owner."
                                    ),
                                    "missing_terms": ["control", "owner"],
                                    "required_match_count": 2,
                                    "required_coherent_match_count": 2,
                                    "required_operational_signal_count": 2,
                                }
                            ],
                        },
                        {
                            "section_uid": "sec-missing",
                            "missing_requirement_ids": ["req-2"],
                            "missing_items": [
                                {
                                    "id": "req-2",
                                    "text": "Describe missing acceptance.",
                                    "reason": "missing key terms",
                                    "remediation_guidance": (
                                        "Regenerate with acceptance evidence."
                                    ),
                                }
                            ],
                        },
                    ]
                }
            ),
        ) as build_readiness,
    ):
        job = await create_drafting_requirements_job(project, mock_db)

    assert job.job_type == "drafting_requirements"
    assert job.result_json == {
        "target_section_uids": ["sec-missing"],
        "target_reason": "missing_requirements",
        "target_guidance": {
            "sec-missing": {
                "instructions": [
                    "Regenerate with a control record and owner.",
                    "Regenerate with acceptance evidence.",
                ],
                "missing_requirement_ids": ["req-1", "req-2"],
                "missing_requirement_items": [
                    {
                        "id": "req-1",
                        "text": "Describe missing control.",
                        "reason": "needs operational evidence",
                        "remediation_guidance": (
                            "Regenerate with a control record and owner."
                        ),
                        "missing_terms": ["control", "owner"],
                        "required_match_count": 2,
                        "required_coherent_match_count": 2,
                        "required_operational_signal_count": 2,
                    },
                    {
                        "id": "req-2",
                        "text": "Describe missing acceptance.",
                        "reason": "missing key terms",
                        "remediation_guidance": (
                            "Regenerate with acceptance evidence."
                        ),
                        "missing_terms": [],
                        "required_match_count": None,
                        "required_coherent_match_count": None,
                        "required_operational_signal_count": None,
                    },
                ],
            }
        },
    }
    load_selected.assert_awaited_once_with(project.id, mock_db)
    build_readiness.assert_awaited_once_with(
        project.id,
        selected_generations,
        mock_db,
    )
    mock_db.add.assert_called_once_with(job)
    enqueue.assert_called_once_with(job.id)
