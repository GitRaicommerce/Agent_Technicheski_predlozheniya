"""
Тестове за /api/v1/export endpoints.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import _make_project


# ---------------------------------------------------------------------------
# GET /api/v1/export/{project_id}/docx
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_docx_project_not_found(client, mock_db):
    """404 ако проектът не съществува."""
    mock_db.get = AsyncMock(return_value=None)

    resp = await client.get(f"/api/v1/export/{uuid.uuid4()}/docx")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_export_docx_stale_returns_409(client, mock_db):
    """409 ако има генерации с evidence_status='stale'."""
    project = _make_project()
    mock_db.get = AsyncMock(return_value=project)

    stale_gen = MagicMock()
    stale_gen.section_uid = "s1"
    stale_gen.evidence_status = "stale"

    selected_result = MagicMock()
    selected_result.scalars.return_value.all.return_value = [stale_gen]
    mock_db.execute = AsyncMock(return_value=selected_result)

    resp = await client.get(f"/api/v1/export/{project.id}/docx")

    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert "stale" in detail["message"]
    assert "s1" in detail["stale_sections"]


@pytest.mark.asyncio
async def test_export_docx_duplicate_selected_returns_409(client, mock_db):
    project = _make_project()
    mock_db.get = AsyncMock(return_value=project)

    first = MagicMock()
    first.id = "gen-1"
    first.section_uid = "sec-duplicate"
    first.evidence_status = "ok"
    second = MagicMock()
    second.id = "gen-2"
    second.section_uid = "sec-duplicate"
    second.evidence_status = "ok"

    selected_result = MagicMock()
    selected_result.scalars.return_value.all.return_value = [first, second]
    mock_db.execute = AsyncMock(return_value=selected_result)

    resp = await client.get(f"/api/v1/export/{project.id}/docx")

    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["duplicate_selected_count"] == 1
    assert detail["duplicate_selected_sections"][0]["section_uid"] == "sec-duplicate"
    assert detail["duplicate_selected_sections"][0]["generation_ids"] == [
        "gen-1",
        "gen-2",
    ]


@pytest.mark.asyncio
async def test_export_readiness_aggregates_multiple_blockers(client, mock_db):
    project = _make_project()
    mock_db.get = AsyncMock(return_value=project)

    duplicate_first = MagicMock()
    duplicate_first.id = "gen-duplicate-1"
    duplicate_first.section_uid = "sec-duplicate"
    duplicate_first.evidence_status = "ok"
    duplicate_first.flags_json = {}
    duplicate_first.text = "Duplicate first text."

    duplicate_second = MagicMock()
    duplicate_second.id = "gen-duplicate-2"
    duplicate_second.section_uid = "sec-duplicate"
    duplicate_second.evidence_status = "ok"
    duplicate_second.flags_json = {}
    duplicate_second.text = "Duplicate second text."

    stale_generation = MagicMock()
    stale_generation.id = "gen-stale"
    stale_generation.section_uid = "sec-stale"
    stale_generation.evidence_status = "stale"
    stale_generation.flags_json = {}
    stale_generation.text = "Stale selected text."

    missing_generation = MagicMock()
    missing_generation.id = "gen-missing"
    missing_generation.section_uid = "sec-missing"
    missing_generation.evidence_status = "ok"
    missing_generation.text = "Text with missing requirements."
    missing_generation.flags_json = {
        "requirement_coverage": {
            "missing_ids": ["req-1", "req-2", "req-3"],
            "items": [
                {"id": "req-1", "text": "First missing", "status": "missing"},
                {
                    "id": "req-2",
                    "text": "Second missing",
                    "status": "missing",
                    "missing_terms": ["approval", "handover"],
                    "coherent_matched_terms": ["second"],
                    "required_coherent_match_count": 2,
                    "matched_ratio": 0.8,
                    "coherent_matched_ratio": 0.8,
                    "requires_operational_detail": True,
                    "operational_signals": ["record"],
                    "required_operational_signal_count": 2,
                },
                {
                    "id": "req-3",
                    "text": "Final acceptance and handover controls.",
                    "status": "missing",
                    "distinctive_terms": ["final", "acceptance", "handover"],
                    "distinctive_matches": [],
                    "required_distinctive_count": 1,
                    "matched_terms": ["control", "record", "role"],
                    "required_match_count": 3,
                },
            ],
        }
    }

    shallow_generation = MagicMock()
    shallow_generation.id = "gen-shallow"
    shallow_generation.section_uid = "sec-shallow"
    shallow_generation.evidence_status = "ok"
    shallow_generation.text = "Short covered text."
    shallow_generation.flags_json = {
        "requirement_coverage": {
            "total": 3,
            "covered": 3,
            "missing": 0,
            "missing_ids": [],
            "items": [
                {"id": "req-3", "status": "covered"},
                {"id": "req-4", "status": "covered"},
                {"id": "req-5", "status": "covered"},
            ],
        }
    }

    selected_result = MagicMock()
    selected_result.scalars.return_value.all.return_value = [
        duplicate_first,
        duplicate_second,
        stale_generation,
        missing_generation,
        shallow_generation,
    ]
    outline_result = MagicMock()
    outline_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(side_effect=[selected_result, outline_result])

    resp = await client.get(f"/api/v1/export/{project.id}/readiness")

    assert resp.status_code == 200
    detail = resp.json()
    assert detail["ready"] is False
    assert detail["blocker_count"] == 4
    assert [blocker["code"] for blocker in detail["blockers"]] == [
        "duplicate_selected",
        "stale_evidence",
        "missing_requirements",
        "shallow_sections",
    ]
    assert detail["duplicate_selected_count"] == 1
    assert detail["stale_section_count"] == 1
    assert detail["missing_requirement_count"] == 3
    missing_items = detail["missing_requirement_sections"][0]["missing_items"]
    assert missing_items[0]["reason"] == "missing requirement coverage"
    assert missing_items[1]["reason"] == "needs operational evidence"
    assert missing_items[1]["missing_terms"] == ["approval", "handover"]
    assert "include the missing concepts: approval, handover" in missing_items[1][
        "remediation_guidance"
    ]
    assert "keep the requirement concepts together" in missing_items[1][
        "remediation_guidance"
    ]
    assert "add operational evidence" in missing_items[1]["remediation_guidance"]
    assert missing_items[1]["operational_signals"] == ["record"]
    assert missing_items[1]["required_operational_signal_count"] == 2
    assert missing_items[2]["reason"] == "missing distinctive requirement detail"
    assert missing_items[2]["distinctive_terms"] == [
        "final",
        "acceptance",
        "handover",
    ]
    assert "include distinctive requirement details" in missing_items[2][
        "remediation_guidance"
    ]
    assert detail["quality_section_count"] == 1


@pytest.mark.asyncio
async def test_export_readiness_report_returns_markdown_summary(client, mock_db):
    project = _make_project()
    mock_db.get = AsyncMock(return_value=project)

    shallow_generation = MagicMock()
    shallow_generation.id = "gen-shallow"
    shallow_generation.section_uid = "sec-shallow"
    shallow_generation.evidence_status = "ok"
    shallow_generation.text = "Short covered text."
    shallow_generation.flags_json = {
        "requirement_coverage": {
            "total": 2,
            "covered": 2,
            "missing": 0,
            "missing_ids": [],
            "items": [
                {"id": "req-1", "status": "covered"},
                {"id": "req-2", "status": "covered"},
            ],
        }
    }
    shallow_generation.used_sources_json = {
        "drafting_blueprint": {
            "groups": [
                {
                    "category": f"category-{index}",
                    "label": f"Category {index}",
                    "requirements": [{"id": f"req-{index}"}],
                }
                for index in range(1, 5)
            ]
        }
    }

    selected_result = MagicMock()
    selected_result.scalars.return_value.all.return_value = [shallow_generation]
    outline = MagicMock()
    outline.outline_json = {
        "sections": [
            {
                "uid": "sec-shallow",
                "title": "Blueprint heavy section",
                "requirement_checklist_items": [
                    {"id": "req-1"},
                    {"id": "req-2"},
                ],
            }
        ]
    }
    outline_result = MagicMock()
    outline_result.scalar_one_or_none.return_value = outline
    mock_db.execute = AsyncMock(side_effect=[selected_result, outline_result])

    resp = await client.get(f"/api/v1/export/{project.id}/readiness/report")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/markdown")
    assert "# DOCX export readiness report" in resp.text
    assert "shallow_sections" in resp.text
    assert "sec-shallow" in resp.text
    assert "Blueprint heavy section" in resp.text
    assert "Blueprint groups" in resp.text
    assert "too_short_for_requirements" in resp.text


@pytest.mark.asyncio
async def test_export_docx_missing_requirement_coverage_returns_409(client, mock_db):
    project = _make_project()
    mock_db.get = AsyncMock(return_value=project)

    generation = MagicMock()
    generation.id = "gen-1"
    generation.section_uid = "sec-1"
    generation.evidence_status = "ok"
    generation.flags_json = {
        "requirement_coverage": {
            "missing_ids": ["req-1"],
            "items": [
                {
                    "id": "req-1",
                    "text": "Следва да се представи подробен линеен график.",
                    "importance": "mandatory",
                    "status": "missing",
                }
            ],
        }
    }
    selected_result = MagicMock()
    selected_result.scalars.return_value.all.return_value = [generation]
    mock_db.execute = AsyncMock(return_value=selected_result)

    resp = await client.get(f"/api/v1/export/{project.id}/docx")

    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["missing_requirement_count"] == 1
    assert detail["missing_requirement_sections"][0]["section_uid"] == "sec-1"
    assert detail["missing_requirement_sections"][0]["missing_requirement_ids"] == [
        "req-1"
    ]


@pytest.mark.asyncio
async def test_export_docx_shallow_requirement_text_returns_409(client, mock_db):
    project = _make_project()
    mock_db.get = AsyncMock(return_value=project)

    generation = MagicMock()
    generation.id = "gen-shallow"
    generation.section_uid = "sec-shallow"
    generation.evidence_status = "ok"
    generation.text = "Кратко общо описание."
    generation.flags_json = {
        "requirement_coverage": {
            "total": 3,
            "covered": 3,
            "missing": 0,
            "missing_ids": [],
            "items": [
                {"id": "req-1", "status": "covered"},
                {"id": "req-2", "status": "covered"},
                {"id": "req-3", "status": "covered"},
            ],
        }
    }
    selected_result = MagicMock()
    selected_result.scalars.return_value.all.return_value = [generation]
    outline_result = MagicMock()
    outline_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(side_effect=[selected_result, outline_result])

    resp = await client.get(f"/api/v1/export/{project.id}/docx")

    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["quality_section_count"] == 1
    assert detail["quality_sections"][0]["section_uid"] == "sec-shallow"
    assert detail["quality_sections"][0]["requirement_count"] == 3
    assert detail["quality_sections"][0]["word_count"] < detail["quality_sections"][0]["min_words"]


@pytest.mark.asyncio
async def test_export_docx_uses_drafting_blueprint_for_quality_gate(client, mock_db):
    project = _make_project()
    mock_db.get = AsyncMock(return_value=project)

    generation = MagicMock()
    generation.id = "gen-blueprint-shallow"
    generation.section_uid = "sec-blueprint"
    generation.evidence_status = "ok"
    generation.text = (
        "The text names coordination, quality, risk, environment, schedule, "
        "and reporting in a very short way."
    )
    generation.flags_json = {
        "requirement_coverage": {
            "total": 2,
            "covered": 2,
            "missing": 0,
            "missing_ids": [],
            "items": [
                {"id": "req-1", "status": "covered"},
                {"id": "req-2", "status": "covered"},
            ],
        }
    }
    generation.used_sources_json = {
        "drafting_blueprint": {
            "groups": [
                {
                    "category": "environment",
                    "label": "Environment",
                    "requirements": [
                        {"id": f"req-{topic}"}
                        for topic in [
                            "dust",
                            "waste",
                            "soil",
                            "water",
                            "noise",
                            "transport",
                        ]
                    ],
                    "topic_details": [
                        {
                            "topic": topic,
                            "requirement_ids": [f"req-{topic}"],
                        }
                        for topic in [
                            "dust",
                            "waste",
                            "soil",
                            "water",
                            "noise",
                            "transport",
                        ]
                    ],
                }
            ]
        }
    }

    selected_result = MagicMock()
    selected_result.scalars.return_value.all.return_value = [generation]
    outline_result = MagicMock()
    outline_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(side_effect=[selected_result, outline_result])

    resp = await client.get(f"/api/v1/export/{project.id}/docx")

    assert resp.status_code == 409
    detail = resp.json()["detail"]
    quality_section = detail["quality_sections"][0]
    assert quality_section["section_uid"] == "sec-blueprint"
    assert quality_section["requirement_count"] == 2
    assert quality_section["blueprint_group_count"] == 1
    assert quality_section["blueprint_topic_count"] == 6
    assert quality_section["blueprint_requirement_id_count"] == 6
    assert quality_section["min_words"] >= 1200
    assert "suggested_words_per_structure" in quality_section
    assert quality_section["structure_coverage"]["anchor_count"] == 6


@pytest.mark.asyncio
async def test_export_docx_reports_uneven_blueprint_distribution(client, mock_db):
    project = _make_project()
    mock_db.get = AsyncMock(return_value=project)

    generation = MagicMock()
    generation.id = "gen-uneven-blueprint"
    generation.section_uid = "sec-environment"
    generation.evidence_status = "ok"
    generation.text = (
        "The environmental section develops dust suppression with responsible "
        "roles, monitoring records, corrective actions, control points, "
        "acceptance evidence, reporting sequence, and site coordination. "
    ) * 90
    generation.flags_json = {
        "requirement_coverage": {
            "total": 4,
            "covered": 4,
            "missing": 0,
            "missing_ids": [],
        }
    }
    generation.used_sources_json = {
        "drafting_blueprint": {
            "groups": [
                {
                    "category": "environment",
                    "label": "Environmental protection",
                    "requirements": [
                        {"id": f"req-{topic}"}
                        for topic in ["dust", "waste", "soil", "water"]
                    ],
                    "topics": ["dust", "waste", "soil", "water"],
                    "topic_details": [
                        {"topic": topic, "requirement_ids": [f"req-{topic}"]}
                        for topic in ["dust", "waste", "soil", "water"]
                    ],
                }
            ]
        }
    }

    selected_result = MagicMock()
    selected_result.scalars.return_value.all.return_value = [generation]
    outline_result = MagicMock()
    outline_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(side_effect=[selected_result, outline_result])

    resp = await client.get(f"/api/v1/export/{project.id}/readiness")

    assert resp.status_code == 200
    detail = resp.json()
    quality_section = detail["quality_sections"][0]
    assert detail["quality_section_count"] == 1
    assert "uneven_blueprint_distribution" in {
        issue["code"] for issue in quality_section["issues"]
    }
    assert quality_section["structure_coverage"]["covered_count"] == 1
    assert quality_section["structure_coverage"]["required_count"] == 3
    assert [
        item["label"]
        for item in quality_section["structure_coverage"]["missing"]
    ] == ["waste", "soil", "water"]


@pytest.mark.asyncio
async def test_export_docx_uses_outline_requirements_for_legacy_quality_gate(client, mock_db):
    project = _make_project()
    mock_db.get = AsyncMock(return_value=project)

    generation = MagicMock()
    generation.id = "gen-legacy"
    generation.section_uid = "sec-legacy"
    generation.evidence_status = "ok"
    generation.text = "Кратък legacy текст."
    generation.flags_json = {}

    selected_result = MagicMock()
    selected_result.scalars.return_value.all.return_value = [generation]
    outline = MagicMock()
    outline.outline_json = {
        "sections": [
            {
                "uid": "sec-legacy",
                "title": "Legacy section",
                "requirements": [
                    "Да се опише организацията.",
                    "Да се опише контролът.",
                    "Да се опише приемането.",
                ],
            }
        ]
    }
    outline_result = MagicMock()
    outline_result.scalar_one_or_none.return_value = outline
    mock_db.execute = AsyncMock(side_effect=[selected_result, outline_result])

    resp = await client.get(f"/api/v1/export/{project.id}/docx")

    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["quality_sections"][0]["section_uid"] == "sec-legacy"
    assert detail["quality_sections"][0]["requirement_count"] == 3


@pytest.mark.asyncio
async def test_export_docx_ok(client, mock_db):
    """200 с DOCX bytes при успешен export."""
    project = _make_project(name="Test Project")
    mock_db.get = AsyncMock(return_value=project)

    selected_result = MagicMock()
    selected_result.scalars.return_value.all.return_value = []
    mock_db.execute = AsyncMock(return_value=selected_result)

    fake_docx = b"PK\x03\x04fake-docx-content"

    with patch(
        "app.export.docx_generator.generate_docx",
        new=AsyncMock(return_value=fake_docx),
    ):
        resp = await client.get(f"/api/v1/export/{project.id}/docx")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert resp.content == fake_docx
