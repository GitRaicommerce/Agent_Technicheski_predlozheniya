from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import pytest

from app.agents.drafting_v2 import (
    MAX_LLM_ASSEMBLY_SOURCE_CHARS,
    assembly_quality,
    run_section_assembly,
)
from app.core.llm_gateway import LLMOutputTruncatedError
from app.agents.generation_structure import build_generation_groups, section_assembly_uid


def test_generation_groups_are_universal_and_stable():
    root = {
        "content_plan_uid": str(uuid.uuid4()),
        "title": "Произволен раздел от нова документация",
        "subsections": [
            {"uid": str(uuid.uuid4()), "title": "Първа подточка", "subsections": []},
            {"uid": str(uuid.uuid4()), "title": "Втора подточка", "subsections": []},
        ],
    }

    groups = build_generation_groups([root])

    assert len(groups) == 1
    assert groups[0]["requires_assembly"] is True
    assert [item["title"] for item in groups[0]["units"]] == [
        "Първа подточка",
        "Втора подточка",
    ]
    assert groups[0]["assembly_uid"] == section_assembly_uid(root)
    uuid.UUID(groups[0]["assembly_uid"])


def test_assembly_quality_rejects_shortened_or_missing_subpoints():
    subpoints = [
        {"title": "Организация", "text": "Организация действия контрол записи"},
        {"title": "Комуникация", "text": "Комуникация срещи доклади координация"},
    ]

    failed = assembly_quality("Организация действия.", subpoints)
    passed = assembly_quality(
        "Организация\nОрганизация действия контрол записи.\n"
        "Комуникация\nКомуникация срещи доклади координация.",
        subpoints,
    )

    assert failed["passed"] is False
    assert "Комуникация" in failed["missing_titles"]
    assert passed["passed"] is True


@pytest.mark.asyncio
async def test_section_assembly_persists_a_selected_hierarchical_generation(mock_db):
    section_uid = str(uuid.uuid4())
    subpoints = [
        {
            "section_uid": str(uuid.uuid4()),
            "generation_id": str(uuid.uuid4()),
            "title": "Организация",
            "text": "Организация на действията, отговорностите и контролните записи.",
        },
        {
            "section_uid": str(uuid.uuid4()),
            "generation_id": str(uuid.uuid4()),
            "title": "Комуникация",
            "text": "Комуникация чрез срещи, доклади и проследима координация.",
        },
    ]
    previous_result = MagicMock()
    previous_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(side_effect=[previous_result, MagicMock()])
    assembled_text = (
        "Организация\nОрганизация на действията, отговорностите и контролните записи.\n"
        "Комуникация\nКомуникация чрез срещи, доклади и проследима координация."
    )

    with patch(
        "app.agents.drafting_v2.llm_gateway.call",
        new=AsyncMock(return_value={"text": assembled_text, "change_summary": "Сглобено."}),
    ):
        result = await run_section_assembly(
            project_id=str(uuid.uuid4()),
            section_uid=section_uid,
            section_title="Управление",
            subpoints=subpoints,
            db=mock_db,
        )

    saved = mock_db.add.call_args.args[0]
    assert saved.generation_kind == "section_assembly"
    assert saved.section_uid == section_uid
    assert saved.selected is True
    assert saved.flags_json["assembly_quality"]["passed"] is True
    assert set(saved.evidence_map_json) == {
        subpoints[0]["section_uid"],
        subpoints[1]["section_uid"],
    }
    assert result["generation_id"] == saved.id


@pytest.mark.asyncio
async def test_large_section_assembly_preserves_text_without_an_llm_echo(mock_db):
    section_uid = str(uuid.uuid4())
    first_text = "Пълно описание на организацията. " * 600
    second_text = "Пълно описание на контрола. " * 600
    assert len(first_text) + len(second_text) > MAX_LLM_ASSEMBLY_SOURCE_CHARS
    subpoints = [
        {
            "section_uid": str(uuid.uuid4()),
            "generation_id": str(uuid.uuid4()),
            "title": "Организация",
            "text": first_text,
        },
        {
            "section_uid": str(uuid.uuid4()),
            "generation_id": str(uuid.uuid4()),
            "title": "Контрол",
            "text": second_text,
        },
    ]
    previous_result = MagicMock()
    previous_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(side_effect=[previous_result, MagicMock()])

    with patch(
        "app.agents.drafting_v2.llm_gateway.call",
        new=AsyncMock(),
    ) as llm_call:
        result = await run_section_assembly(
            project_id=str(uuid.uuid4()),
            section_uid=section_uid,
            section_title="Голям раздел",
            subpoints=subpoints,
            db=mock_db,
        )

    llm_call.assert_not_awaited()
    saved = mock_db.add.call_args.args[0]
    assert first_text.strip() in saved.text
    assert second_text.strip() in saved.text
    assert saved.flags_json["assembly_mode"] == "deterministic_large_section"
    assert result["assembly_mode"] == "deterministic_large_section"


@pytest.mark.asyncio
async def test_truncated_section_assembly_falls_back_without_a_second_llm_call(mock_db):
    section_uid = str(uuid.uuid4())
    subpoints = [
        {
            "section_uid": str(uuid.uuid4()),
            "generation_id": str(uuid.uuid4()),
            "title": "Организация",
            "text": "Организация на дейностите и отговорностите.",
        },
        {
            "section_uid": str(uuid.uuid4()),
            "generation_id": str(uuid.uuid4()),
            "title": "Контрол",
            "text": "Контрол чрез проверки и записи.",
        },
    ]
    previous_result = MagicMock()
    previous_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(side_effect=[previous_result, MagicMock()])
    truncated = LLMOutputTruncatedError(
        "LLM response was truncated by the output token limit."
    )

    with patch(
        "app.agents.drafting_v2.llm_gateway.call",
        new=AsyncMock(side_effect=truncated),
    ) as llm_call:
        result = await run_section_assembly(
            project_id=str(uuid.uuid4()),
            section_uid=section_uid,
            section_title="Раздел",
            subpoints=subpoints,
            db=mock_db,
        )

    llm_call.assert_awaited_once()
    saved = mock_db.add.call_args.args[0]
    assert "Организация" in saved.text
    assert "Контрол" in saved.text
    assert saved.flags_json["assembly_mode"] == "deterministic_after_truncation"
    assert result["assembly_quality"]["passed"] is True


@pytest.mark.asyncio
async def test_section_assembly_rejects_calendar_date_introduced_by_editor(mock_db):
    section_uid = str(uuid.uuid4())
    subpoints = [
        {
            "section_uid": str(uuid.uuid4()),
            "generation_id": str(uuid.uuid4()),
            "title": "Проектиране",
            "text": "Проектирането се изпълнява в срок от 20 дни.",
        }
    ]
    previous_result = MagicMock()
    previous_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(side_effect=[previous_result, MagicMock()])

    with patch(
        "app.agents.drafting_v2.llm_gateway.call",
        new=AsyncMock(return_value={
            "text": "Проектиране\nПроектирането започва на 06.10.2026 г.",
            "change_summary": "Редактирано.",
        }),
    ):
        result = await run_section_assembly(
            project_id=str(uuid.uuid4()),
            section_uid=section_uid,
            section_title="Проектиране",
            subpoints=subpoints,
            db=mock_db,
        )

    saved = mock_db.add.call_args.args[0]
    assert "06.10.2026" not in saved.text
    assert "20 дни" in saved.text
    assert result["assembly_mode"] == "deterministic_calendar_guard"
