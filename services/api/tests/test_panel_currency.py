"""WP-07 / K-15 (T-19 backend half): panels show only current results."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.consistency import facts_hash
from tests.conftest import _make_project

NOW = datetime(2026, 9, 30, tzinfo=timezone.utc)


@pytest.fixture
def v2_pipeline(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.generation_pipeline", "v2")


def _scalars(values):
    result = MagicMock()
    result.scalars.return_value.all.return_value = values
    return result


def _scalar(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _check(generation_id, verdict):
    return SimpleNamespace(
        id=f"chk-{generation_id}", generation_id=generation_id, section_uid="u-1",
        criterion_id="c-1", criterion_text="Критерий", criterion_kind="content",
        requirement_id=None, source_quote=None, verdict=verdict, evidence=None,
        note=None, created_at=NOW,
    )


@pytest.mark.asyncio
async def test_criteria_verdicts_of_an_old_version_are_marked_stale(client, mock_db, v2_pipeline):
    project = _make_project()
    mock_db.get = AsyncMock(return_value=project)
    selected = SimpleNamespace(id="gen-new", revision_number=3)
    mock_db.execute = AsyncMock(side_effect=[
        _scalars([_check("gen-old", "covered"), _check("gen-new", "missing")]),
        _scalars([selected]),
        _scalar(None),
    ])

    response = await client.get(f"/api/v1/criteria/{project.id}")

    body = response.json()
    by_generation = {check["generation_id"]: check for check in body["checks"]}
    assert by_generation["gen-old"]["is_current"] is False
    assert by_generation["gen-new"]["is_current"] is True
    assert by_generation["gen-new"]["generation_revision"] == 3
    assert body["totals"]["total"] == 1
    assert body["totals"]["stale"] == 1
    assert body["totals"]["covered"] == 0  # the old "covered" does not count
    assert body["totals"]["missing"] == 1


@pytest.mark.asyncio
async def test_consistency_report_is_stale_after_a_regeneration(client, mock_db, v2_pipeline):
    project = _make_project()
    mock_db.get = AsyncMock(return_value=project)
    job = SimpleNamespace(
        id="job-1", project_id=project.id, status="done", total_sections=1,
        completed_sections=1, current_section_title=None, error=None,
        result_json={
            "checked_generation_ids": ["gen-old"],
            "input_fingerprint": {"schedule_id": None, "facts_hash": facts_hash({})},
        },
        created_at=NOW, updated_at=NOW, completed_at=NOW,
    )
    regenerated = SimpleNamespace(id="gen-new", section_uid="u-1", text="Текст", generation_kind="section", parent_section_uid=None)
    mock_db.execute = AsyncMock(side_effect=[
        _scalar(job), _scalars([regenerated]), _scalar(None), _scalar(None),
    ])

    response = await client.get(f"/api/v1/consistency/{project.id}")

    body = response.json()
    assert body["stale"] is True
    assert body["stale_reasons"] == ["generation_set_changed"]
