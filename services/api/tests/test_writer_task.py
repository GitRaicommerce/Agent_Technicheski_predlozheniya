"""WP-06 acceptance (T-05, T-18, writer part of T-23)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.content_plan import _item_outline_payload
from app.agents.context import build_project_grounding_context_v2, excerpt_around
from app.agents.drafting import run_drafting
from app.agents.writer_task import (
    approved_criteria,
    evidence_quotes,
    select_writer_profile,
)


def _plan_item(criteria):
    return SimpleNamespace(
        id="item-1",
        uid="uid-1",
        number="2.1",
        title="Разпределение на отговорностите",
        acceptance_criteria_json=criteria,
        source_quotes_json=[],
        content_kind="specific",
        linked_wbs_ids=[],
        linked_fact_keys=[],
        generation_uid="gen-1",
        drafting_guidance_json=None,
    )


EDITED = [
    {
        "id": "crit-1",
        "text": "Всяка проектна част има посочен отговорен проектант (редактирано)",
        "kind": "cross_ref",
        "requirement_id": "req-1",
        "requirement_text": "Оригинален текст на изискването",
        "source_quote": "за всяка една част от проекта е наличен съответния специалист",
    },
    {
        "id": "crit-manual",
        "text": "Ръчно добавен критерий без изискване",
        "kind": "content",
    },
]


def test_checklist_uses_edited_criterion_text_and_ids():
    """T-05: editing only the criterion changes what the writer is told."""
    payload = _item_outline_payload(_plan_item(EDITED), [])
    checklist = {entry["id"]: entry["text"] for entry in payload["requirement_checklist_items"]}
    assert checklist == {
        "crit-1": "Всяка проектна част има посочен отговорен проектант (редактирано)",
        "crit-manual": "Ръчно добавен критерий без изискване",
    }
    assert "Оригинален текст на изискването" not in checklist.values()


@pytest.mark.asyncio
async def test_writer_prompt_and_saved_generation_carry_the_approved_task(mock_db):
    unit = {"title": "Разпределение", "acceptance_criteria": EDITED, "source_quotes": []}
    criteria = approved_criteria(unit)
    profile = select_writer_profile(unit, criteria)
    controls = [
        {
            "requirement_id": "req-names",
            "category": "prohibition",
            "kind": "prohibition",
            "text": "Експертите се посочват само като квалификация и брой.",
        }
    ]
    with patch(
        "app.agents.drafting.llm_gateway.call",
        new=AsyncMock(return_value={"variant_1": {"text": "Текст.", "evidence_map": {}}, "flags": []}),
    ) as call:
        await run_drafting(
            project_id=str(uuid.uuid4()),
            section_uid=str(uuid.uuid4()),
            section_title="Разпределение",
            section_requirements=[],
            evidence_snippets=[],
            schedule_summary=None,
            lex_citations=[],
            db=mock_db,
            acceptance_criteria=criteria,
            global_controls=controls,
            writer_profile=profile,
            writer_role=profile["role"],
            use_drafting_blueprint=False,
        )

    prompt = call.await_args.kwargs["user_message"]
    assert "APPROVED ACCEPTANCE CRITERIA" in prompt
    assert "id=crit-1 [cross_ref]: Всяка проектна част има посочен отговорен проектант (редактирано)" in prompt
    assert "id=crit-manual" in prompt
    assert "GLOBAL CONTROLS" in prompt
    assert "само като квалификация и брой" in prompt
    assert call.await_args.kwargs["role_override"] == "drafting_complex"
    saved = mock_db.add.call_args.args[0]
    assert [c["id"] for c in saved.used_sources_json["acceptance_criteria"]] == ["crit-1", "crit-manual"]
    assert saved.used_sources_json["writer_profile"]["role"] == "drafting_complex"
    assert "cross-reference" in saved.used_sources_json["writer_profile"]["reason"]


@pytest.mark.parametrize(
    "unit,role",
    [
        ({"title": "Описание на ресурсите", "content_kind": "specific"}, "drafting_routine"),
        ({"title": "Технология на изпълнение", "content_kind": "specific"}, "drafting_complex"),
        ({"title": "Описание", "content_kind": "reuse"}, "drafting_complex"),
        (
            {"title": "Описание", "drafting_guidance": {"instructions": ["Целева дълбочина: detailed."]}},
            "drafting_complex",
        ),
    ],
)
def test_writer_profile_is_chosen_by_task_not_phase(unit, role):
    profile = select_writer_profile(unit, [])
    assert profile["role"] == role
    assert profile["reason"]


def test_evidence_quotes_come_from_criteria_and_sources_without_duplicates():
    unit = {
        "acceptance_criteria": EDITED,
        "source_quotes": [{"source_quote": "за всяка една част от проекта е наличен съответния специалист"}],
    }
    assert evidence_quotes(unit, approved_criteria(unit)) == [
        "за всяка една част от проекта е наличен съответния специалист"
    ]


def test_excerpt_centres_on_a_late_key_clause():
    text = "Общ текст. " * 400 + "КЛЮЧОВО УТОЧНЕНИЕ за срока." + " край" * 50
    excerpt, offset = excerpt_around(text, ["КЛЮЧОВО УТОЧНЕНИЕ"], 1800)
    assert text.index("КЛЮЧОВО УТОЧНЕНИЕ") > 3000  # beyond the old fixed cut
    assert "КЛЮЧОВО УТОЧНЕНИЕ" in excerpt
    assert offset > 0
    assert len(excerpt) <= 1800 + 2


def _chunk(chunk_id, text="Текст"):
    return SimpleNamespace(id=chunk_id, page=1, section_path=None, text=text)


@pytest.mark.asyncio
async def test_keyword_hit_is_not_pushed_out_by_a_full_semantic_list():
    """T-18: 18 semantic results plus one important keyword result."""
    semantic = [_chunk(f"sem-{index}") for index in range(18)]
    base = {
        "tender_chunks": [
            {"chunk_id": "direct-1", "text": "пряк цитат", "retrieval": "direct"},
            {"chunk_id": "kw-important", "text": "точен ключов резултат"},
            {"chunk_id": "sem-3", "text": "дубликат"},  # already semantic
        ],
        "schedule": {"tasks": []},
    }
    semantic_result = MagicMock()
    semantic_result.scalars.return_value.all.return_value = semantic
    wbs_result = MagicMock()
    wbs_result.scalars.return_value.all.return_value = []
    fact_result = MagicMock()
    fact_result.scalar_one_or_none.return_value = None
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[semantic_result, wbs_result, fact_result])

    with (
        patch("app.agents.context.build_project_grounding_context", new=AsyncMock(return_value=base)),
        patch("app.core.embedding.embed_query", new=AsyncMock(return_value=[0.1] * 3)),
    ):
        context = await build_project_grounding_context_v2("p1", "Раздел", [], db, max_tender_chunks=18)

    ids = [chunk["chunk_id"] for chunk in context["tender_chunks"]]
    assert ids[0] == "direct-1"
    assert "kw-important" in ids
    assert len(ids) == 18 and len(set(ids)) == 18
    assert context["retrieval_counts"]["keyword"] == 1
    assert context["retrieval_mode"] == "semantic_plus_keyword"
