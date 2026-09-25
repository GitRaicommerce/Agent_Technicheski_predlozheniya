"""WP-03 / K-26 acceptance (T-24): the plan author cannot break the protected plan."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.plan_author import (
    PlanAuthorValidationError,
    apply_author_proposal,
    run_plan_author,
    validate_author_proposal,
)
from app.agents.requirement_dispositions import (
    compute_dispositions,
    redistribute_parent_criteria,
)


def req(req_id, *, kind="content", scope="proposal_content", text=None):
    return SimpleNamespace(
        id=req_id,
        kind=kind,
        scope=scope,
        normalized_text=text or f"Изискване {req_id}",
        source_quote=f"Цитат {req_id}",
        source_page=2,
        source_file_id="file-1",
        acceptance_criteria_json=[],
    )


def plan_item(item_id, *, number, title, parent=None, generatable=True, mandatory=True, criteria=None):
    return SimpleNamespace(
        id=item_id,
        project_id="project-1",
        parent_id=parent,
        number=number,
        title=title,
        order_index=int(number.split(".")[-1]),
        generation_uid=f"gen-{item_id}" if generatable else None,
        acceptance_criteria_json=criteria or [],
        source_quotes_json=[{"source_kind": "mandatory_heading"}] if mandatory else [],
        drafting_guidance_json=None,
    )


REQUIREMENTS = [
    req("r-team", text="Описание на предвидените човешки ресурси"),
    req("r-split", text="Разпределение на дейностите между експертите"),
    req("r-names", kind="prohibition", scope="proposal_format"),
]


def base_items():
    return [
        plan_item("i1", number="1", title="Концепция и подход", criteria=[{"id": "c0", "requirement_id": "", "text": "x"}]),
        plan_item("i2", number="2", title="Организация на изпълнението"),
    ]


def valid_proposal():
    return {
        "subpoints": [
            {
                "temp_id": "n1",
                "parent_item_id": "i2",
                "title": "Описание на предвидените човешки ресурси",
                "origin": "source_requirement",
                "requirement_ids": ["r-team"],
                "criteria": [{"requirement_id": "r-team", "text": "Посочени са квалификация и брой"}],
                "target_depth": "detailed",
                "instructions": ["Опиши всяка роля с конкретни задължения"],
                "content_kind": "specific",
            },
            {
                "temp_id": "n2",
                "parent_item_id": "i2",
                "title": "Разпределение на дейностите и отговорностите",
                "origin": "source_requirement",
                "requirement_ids": ["r-split"],
                "criteria": [{"requirement_id": "r-split", "text": "Всяка дейност има отговорен експерт"}],
            },
            {
                "temp_id": "n3",
                "parent_item_id": "i1",
                "title": "Предложение за вътрешен контрол на изпълнителя",
                "origin": "contractor_method",
                "requirement_ids": [],
                "criteria": [{"text": "Описан е вътрешният контрол"}],
            },
        ],
        "assignments": [],
        "item_guidance": [{"item_id": "i1", "target_depth": "standard", "instructions": ["Кратко"]}],
        "unresolved": [],
    }


def test_valid_proposal_passes_validation():
    proposal = validate_author_proposal(valid_proposal(), base_items(), REQUIREMENTS)
    assert len(proposal["subpoints"]) == 3
    assert proposal["subpoints"][2]["origin"] == "contractor_method"


@pytest.mark.parametrize(
    "mutate,message",
    [
        (lambda p: p.update(renames=[{"item_id": "i2", "title": "Ново"}]), "промени съществуващи точки"),
        (lambda p: p["subpoints"][0].update(parent_item_id="ghost"), "непозната точка"),
        (lambda p: p["subpoints"][0].update(requirement_ids=["r-team", "r-foreign"]), "чужди идентификатори"),
        (lambda p: p["subpoints"][1].update(requirement_ids=[]), "мълчаливо"),
        (lambda p: p["subpoints"][0].update(requirement_ids=[]), "няма източник"),
        (lambda p: p["subpoints"][2].update(requirement_ids=["r-team"]), "не може да се представя"),
        (lambda p: p["subpoints"][0].update(criteria=[]), "няма критерии"),
    ],
)
def test_invalid_proposals_are_rejected(mutate, message):
    proposal = valid_proposal()
    mutate(proposal)
    with pytest.raises(PlanAuthorValidationError) as caught:
        validate_author_proposal(proposal, base_items(), REQUIREMENTS)
    assert any(message in error for error in caught.value.errors), caught.value.errors


def test_explicitly_unresolved_requirement_is_allowed_and_kept_visible():
    proposal = valid_proposal()
    proposal["subpoints"].pop(1)
    proposal["unresolved"] = [{"requirement_id": "r-split", "reason": "Неясно към коя точка"}]
    validated = validate_author_proposal(proposal, base_items(), REQUIREMENTS)
    assert validated["unresolved"] == [{"requirement_id": "r-split", "reason": "Неясно към коя точка"}]


def test_applied_proposal_keeps_mandatory_titles_and_accounts_for_requirements():
    items = base_items()
    outline = SimpleNamespace(id="outline-1")
    db = MagicMock()
    proposal = validate_author_proposal(valid_proposal(), items, REQUIREMENTS)

    created = apply_author_proposal(proposal, outline=outline, items=items, requirements=REQUIREMENTS, db=db)
    all_items = [*items, *created]
    redistribute_parent_criteria(all_items)

    assert [item.title for item in items] == ["Концепция и подход", "Организация на изпълнението"]
    # Parent points with new children stop being drafted themselves.
    assert items[1].generation_uid is None and items[0].generation_uid is None
    numbers = sorted(item.number for item in created)
    assert numbers == ["1.1", "2.1", "2.2"]
    contractor = next(item for item in created if item.title.startswith("Предложение"))
    assert contractor.drafting_guidance_json["origin"] == "contractor_method"
    assert contractor.acceptance_criteria_json[0]["requirement_id"] == ""
    result = compute_dispositions(all_items, REQUIREMENTS)
    by_id = {entry["requirement_id"]: entry["disposition"] for entry in result["dispositions"]}
    assert by_id == {"r-team": "target", "r-split": "target", "r-names": "global_control"}


@pytest.mark.asyncio
async def test_invalid_model_plan_is_not_saved(monkeypatch):
    """T-24: an invalid draft never replaces the plan (no sync, error raised)."""
    monkeypatch.setattr("app.core.config.settings.generation_pipeline", "v2")
    outline = SimpleNamespace(id="outline-9", version=9, outline_json={})
    items = base_items()
    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: items)),
            SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: REQUIREMENTS)),
        ]
    )
    db.flush = AsyncMock()
    bad = valid_proposal()
    bad["renames"] = [{"item_id": "i2", "title": "Преименувано"}]
    sync = AsyncMock()

    with (
        patch("app.agents.content_plan.build_content_plan", new=AsyncMock(return_value=outline)),
        patch("app.agents.content_plan.sync_outline_from_content_plan", new=sync),
        patch("app.agents.plan_author.llm_gateway.call", new=AsyncMock(return_value=bad)) as call,
    ):
        with pytest.raises(PlanAuthorValidationError):
            await run_plan_author("project-1", db)

    assert call.await_args.kwargs["agent"] == "content_plan_author"
    sync.assert_not_awaited()
    assert "plan_author" not in outline.outline_json
    assert items[1].title == "Организация на изпълнението"
