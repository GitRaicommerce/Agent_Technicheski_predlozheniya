from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.examples import run_examples
from app.agents.forlage import (
    extract_forlage_sections,
    rank_forlage_for_query,
    score_forlage_query,
)


def _snippet(snippet_id: str, title: str, text: str):
    return SimpleNamespace(
        id=snippet_id,
        text=text,
        snippet_kind="forlage_section",
        source_group="hierarchical_section",
        topics_json={
            "section_title": title,
            "section_path": ["Работна програма", title],
        },
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


def test_automatic_retrieval_uses_full_section_context():
    quality = _snippet(
        "section-quality",
        "Контрол на качеството",
        "Контролът включва проверки, контролни точки, протоколи и записи.",
    )
    finance = _snippet(
        "section-finance",
        "Финансови възможности",
        "Финансов оборот и банкови документи на участника.",
    )
    duplicate = _snippet("section-quality-copy", quality.topics_json["section_title"], quality.text)
    query = (
        "Мерки за осигуряване на качеството\n"
        "Изискват се проверки, контролни точки, протоколи и записи."
    )

    quality_score, _ = score_forlage_query(query, quality)
    finance_score, _ = score_forlage_query(query, finance)
    ranked = rank_forlage_for_query(query, [finance, quality, duplicate])

    assert quality_score > finance_score
    assert [snippet.id for snippet in ranked] == ["section-quality"]


@pytest.mark.asyncio
async def test_examples_agent_searches_and_selects_forlage_automatically():
    project_id = "11111111-1111-1111-1111-111111111111"
    quality = _snippet(
        "section-quality",
        "Контрол на качеството",
        "Пълна методология с проверки, контролни точки, протоколи и записи.",
    )
    finance = _snippet(
        "section-finance",
        "Финансови възможности",
        "Финансов оборот и банкови документи.",
    )
    rows = SimpleNamespace(
        scalars=lambda: SimpleNamespace(all=lambda: [finance, quality])
    )
    db = AsyncMock()
    db.execute = AsyncMock(return_value=rows)
    llm_result = {
        "selected_snippets": [{
            "snippet_id": quality.id,
            "relevance_note": "Подходяща методология за адаптиране.",
        }]
    }

    with (
        patch("app.core.embedding.embed_query", new=AsyncMock(return_value=None)),
        patch("app.agents.examples.llm_gateway.call", new=AsyncMock(return_value=llm_result)) as llm_call,
    ):
        result = await run_examples(
            project_id=project_id,
            query="Мерки за осигуряване на качеството",
            section_requirements=["Да се опишат проверки и контролни точки."],
            section_requirement_items=[{"text": "Да се водят протоколи и записи."}],
            section_drafting_guidance={
                "required_subtopics": ["Входящ контрол"],
                "instructions": ["Текстът да следва текущата техническа спецификация."],
            },
            db=db,
        )

    prompt = llm_call.await_args.kwargs["user_message"]
    assert "проверки и контролни точки" in prompt
    assert "протоколи и записи" in prompt
    assert "Входящ контрол" in prompt
    assert "Пълна методология" in prompt
    assert "Финансов оборот" not in prompt
    assert result["selected_snippets"][0]["text"] == quality.text
    assert result["total_found"] == 1
    assert result["selection_mode"] == "automatic_drafting_search"
