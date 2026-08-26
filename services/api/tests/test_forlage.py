from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.examples import run_examples
from app.agents.forlage import (
    candidate_matches,
    confirmed_forlage_for_item,
    extract_forlage_sections,
    score_forlage_match,
)


def test_extract_forlage_sections_preserves_numbered_hierarchy_and_content():
    chunks = [
        {"type": "text", "text": "**1. Концепция и подход**", "page": 1},
        {"type": "text", "text": "Общо описание на изпълнението.", "page": 1},
        {"type": "text", "text": "1.1 Организация на екипа", "page": 2},
        {"type": "text", "text": "Ръководителят организира и контролира работата.", "page": 2},
        {"type": "text", "text": "2. Контрол на качеството", "page": 3},
        {"type": "text", "text": "Проверки, протоколи и записи за качество.", "page": 3},
    ]

    sections = extract_forlage_sections(chunks)

    assert [(section["number"], section["title"]) for section in sections] == [
        ("1", "Концепция и подход"),
        ("1.1", "Организация на екипа"),
        ("2", "Контрол на качеството"),
    ]
    assert sections[1]["path"] == ["Концепция и подход", "Организация на екипа"]
    assert "организира и контролира" in sections[1]["text"]
    assert sections[2]["page_start"] == 3


def test_forlage_matching_prefers_relevant_methodology_section():
    item = SimpleNamespace(
        id="item-quality",
        title="Мерки за осигуряване на качеството",
        acceptance_criteria_json=[
            {"text": "Описват се проверки, контролни точки, протоколи и записи за качество."}
        ],
    )
    quality = SimpleNamespace(
        id="section-quality",
        text="Контролът на качеството включва проверки, протоколи и записи.",
        topics_json={
            "section_title": "Контрол на качеството",
            "section_path": ["Работна програма", "Контрол на качеството"],
        },
    )
    finance = SimpleNamespace(
        id="section-finance",
        text="Финансов оборот и банкови документи на участника.",
        topics_json={"section_title": "Финансови възможности", "section_path": []},
    )

    quality_score, _ = score_forlage_match(item, quality)
    finance_score, _ = score_forlage_match(item, finance)
    candidates = candidate_matches(item, [finance, quality])

    assert quality_score > finance_score
    assert candidates[0]["section_id"] == "section-quality"


@pytest.mark.asyncio
async def test_pending_forlage_review_is_not_used_for_drafting():
    project_id = "11111111-1111-1111-1111-111111111111"
    item = SimpleNamespace(
        project_id=project_id,
        outline_id="22222222-2222-2222-2222-222222222222",
        forlage_section_id="33333333-3333-3333-3333-333333333333",
    )
    outline = SimpleNamespace(outline_json={"forlage_review": {"status": "pending"}})
    db = AsyncMock()
    db.get = AsyncMock(side_effect=[item, outline])

    result = await confirmed_forlage_for_item(
        project_id=project_id,
        content_plan_item_id="44444444-4444-4444-4444-444444444444",
        db=db,
    )

    assert result is None


@pytest.mark.asyncio
async def test_examples_agent_uses_confirmed_phase3_section_without_llm():
    project_id = "11111111-1111-1111-1111-111111111111"
    item = SimpleNamespace(
        id="22222222-2222-2222-2222-222222222222",
        project_id=project_id,
        outline_id="44444444-4444-4444-4444-444444444444",
        forlage_section_id="33333333-3333-3333-3333-333333333333",
    )
    snippet = SimpleNamespace(
        id=item.forlage_section_id,
        project_id=project_id,
        text="Пълна методология за контрол на качеството.",
        snippet_kind="forlage_section",
        source_group="hierarchical_section",
        topics_json={
            "section_title": "Контрол на качеството",
            "section_path": ["Работна програма", "Контрол на качеството"],
        },
    )
    outline = SimpleNamespace(
        outline_json={"forlage_review": {"status": "confirmed"}},
    )
    db = AsyncMock()
    db.get = AsyncMock(side_effect=[item, outline, snippet])

    with patch("app.agents.examples.llm_gateway.call", new=AsyncMock()) as llm_call:
        result = await run_examples(
            project_id=project_id,
            query="Качество",
            db=db,
            content_plan_item_id=item.id,
        )

    llm_call.assert_not_awaited()
    assert result["selection_mode"] == "confirmed_phase3_match"
    assert result["selected_snippets"][0]["text"] == snippet.text


@pytest.mark.asyncio
async def test_confirmed_no_forlage_choice_does_not_fall_back_to_llm_search():
    project_id = "11111111-1111-1111-1111-111111111111"
    item = SimpleNamespace(
        project_id=project_id,
        outline_id="22222222-2222-2222-2222-222222222222",
        forlage_section_id=None,
    )
    outline = SimpleNamespace(
        outline_json={"forlage_review": {"status": "confirmed"}},
    )
    db = AsyncMock()
    db.get = AsyncMock(side_effect=[item, outline])

    with patch("app.agents.examples.llm_gateway.call", new=AsyncMock()) as llm_call:
        result = await run_examples(
            project_id=project_id,
            query="Риск",
            db=db,
            content_plan_item_id="33333333-3333-3333-3333-333333333333",
        )

    llm_call.assert_not_awaited()
    assert result["selection_mode"] == "confirmed_phase3_no_match"
    assert result["selected_snippets"] == []
