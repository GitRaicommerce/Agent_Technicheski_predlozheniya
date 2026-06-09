from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.context import build_project_grounding_context
from app.agents.drafting import run_drafting


def _scalar_result(items):
    result = MagicMock()
    result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=items)))
    return result


def _one_result(item):
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=item)
    return result


@pytest.mark.asyncio
async def test_grounding_context_includes_design_parts_from_schedule_and_tender(mock_db):
    project_id = str(uuid.uuid4())
    file_id = str(uuid.uuid4())
    schedule = SimpleNamespace(
        schedule_json={
            "tasks": [
                {
                    "uid": "1",
                    "wbs": "2.1",
                    "name": "Разработване на проектна част Геодезия",
                    "duration_days": 3,
                },
                {
                    "uid": "2",
                    "wbs": "2.2",
                    "name": "Разработване на проектна част Конструктивна",
                    "duration_days": 4,
                },
                {
                    "uid": "3",
                    "wbs": "2.3",
                    "name": "Изготвяне на ПБЗ, ПУСО и сметна документация",
                    "duration_days": 2,
                },
            ]
        },
        status_locked=True,
        version=1,
    )
    tender_chunk = SimpleNamespace(
        id=str(uuid.uuid4()),
        page=12,
        section_path="Техническа спецификация",
        text=(
            "Разработване на инвестиционен проект по части Водоснабдяване, "
            "Геодезия, Конструктивна, ПБЗ, ПУСО и Сметна документация."
        ),
    )

    mock_db.execute = AsyncMock(
        side_effect=[
            _one_result(schedule),
            [SimpleNamespace(id=file_id)],
            _scalar_result([tender_chunk]),
        ]
    )

    context = await build_project_grounding_context(
        project_id=project_id,
        section_title="Разработване на инвестиционен проект",
        section_requirements=[],
        db=mock_db,
    )

    task_names = " ".join(task["name"] for task in context["schedule"]["tasks"])
    tender_text = " ".join(chunk["text"] for chunk in context["tender_chunks"])

    assert "Геодезия" in task_names
    assert "Конструктивна" in task_names
    assert "ПУСО" in task_names
    assert "Сметна документация" in tender_text


@pytest.mark.asyncio
async def test_drafting_prompt_and_saved_generation_include_grounding_context(mock_db):
    project_id = str(uuid.uuid4())
    section_uid = str(uuid.uuid4())
    grounding_context = {
        "tender_chunks": [{"text": "Проектни части: Геодезия и Конструктивна"}],
        "schedule": {"tasks": [{"name": "ПБЗ и ПУСО"}]},
    }

    with patch(
        "app.agents.drafting.llm_gateway.call",
        new=AsyncMock(
            return_value={
                "variant_1": {
                    "text": "Подробен текст за проектните части.",
                    "evidence_map": {},
                },
                "flags": [],
            }
        ),
    ) as llm_call:
        result = await run_drafting(
            project_id=project_id,
            section_uid=section_uid,
            section_title="Разработване на инвестиционен проект",
            section_requirements=[],
            evidence_snippets=[],
            schedule_summary=None,
            lex_citations=[],
            db=mock_db,
            trace_id=str(uuid.uuid4()),
            project_grounding_context=grounding_context,
        )

    prompt = llm_call.await_args.kwargs["user_message"]
    saved_generation = mock_db.add.call_args.args[0]

    assert "PROJECT GROUNDING CONTEXT" in prompt
    assert "Геодезия" in prompt
    assert "ПУСО" in prompt
    assert saved_generation.used_sources_json == {
        "grounding_context": grounding_context
    }
    assert result["generation_ids"]["variant_1"] == saved_generation.id
