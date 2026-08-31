from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import pytest

from app.agents.drafting_v2 import assembly_quality, run_section_assembly
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
