from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.orchestrator import _run_drafting_all
from app.core.models import TpOutline
from tests.conftest import _make_project


def _outline_result(outline: TpOutline) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=outline)
    return result


@pytest.mark.asyncio
async def test_run_drafting_all_prefers_latest_outline_even_if_unlocked(mock_db):
    project = _make_project()
    latest_outline = TpOutline(
        id=str(uuid.uuid4()),
        project_id=project.id,
        outline_json={
            "sections": [
                {
                    "uid": str(uuid.uuid4()),
                    "title": "Концепция и подход",
                    "requirements": ["Подробно описание на подхода"],
                    "subsections": [],
                }
            ]
        },
        status_locked=False,
        version=7,
    )
    locked_outline = TpOutline(
        id=str(uuid.uuid4()),
        project_id=project.id,
        outline_json={
            "sections": [
                {
                    "uid": str(uuid.uuid4()),
                    "title": "Общи данни за проекта",
                    "requirements": ["Общи данни"],
                    "subsections": [],
                }
            ]
        },
        status_locked=True,
        version=1,
    )

    async def execute_side_effect(statement):
        sql = str(statement)
        if "FROM tp_outlines" in sql:
            if "status_locked = true" in sql.lower():
                return _outline_result(locked_outline)
            return _outline_result(latest_outline)
        if "FROM generations" in sql:
            return []
        raise AssertionError(f"Unexpected statement: {sql}")

    mock_db.execute = AsyncMock(side_effect=execute_side_effect)

    with (
        patch(
            "app.agents.schedule.run_schedule",
            new=AsyncMock(return_value={"status": "ok", "tp_section_text": "График"}),
        ),
        patch(
            "app.agents.examples.run_examples",
            new=AsyncMock(return_value={"selected_snippets": [], "total_found": 0}),
        ) as run_examples,
        patch(
            "app.agents.legislation.run_legislation",
            new=AsyncMock(return_value={"citations": [], "total_found": 0}),
        ),
        patch(
            "app.agents.drafting.run_drafting",
            new=AsyncMock(return_value={"generation_ids": {"variant_1": str(uuid.uuid4())}}),
        ),
    ):
        result = await _run_drafting_all(project=project, db=mock_db, trace_id=str(uuid.uuid4()))

    assert result["outline_version"] == 7
    assert result["outline_locked"] is False
    assert result["generated_count"] == 1
    assert result["sections"][0]["title"] == "Концепция и подход"
    assert run_examples.await_args_list[0].kwargs["query"] == "Концепция и подход"
