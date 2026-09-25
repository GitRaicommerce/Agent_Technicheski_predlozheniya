"""WP-03 / K-03 acceptance (T-04): every requirement keeps an explicit disposition."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.content_plan import MandatoryHeading, _populate_from_mandatory_headings
from app.agents.requirement_dispositions import (
    compute_dispositions,
    redistribute_parent_criteria,
)


def req(req_id, *, kind="content", scope="proposal_content", path=None, page=2, text=None):
    return SimpleNamespace(
        id=req_id,
        kind=kind,
        scope=scope,
        normalized_text=text or f"Изискване {req_id}",
        source_quote=text or f"Цитат {req_id}",
        source_file_id="file-1",
        source_page=page,
        proposal_path_json=path or [],
        target_section_hint=None,
        acceptance_criteria_json=[],
    )


def item(item_id, *, parent=None, title="Точка", generatable=True, criteria=None, number="1"):
    return SimpleNamespace(
        id=item_id,
        parent_id=parent,
        title=title,
        number=number,
        order_index=0,
        generation_uid=f"gen-{item_id}" if generatable else None,
        acceptance_criteria_json=criteria or [],
        source_quotes_json=[],
    )


def crit(req_id, text="Критерий", crit_id=None):
    return {"id": crit_id or f"c-{req_id}", "text": text, "requirement_id": req_id, "requirement_text": text}


def test_parent_criteria_move_to_the_best_matching_generatable_child():
    parent = item(
        "p",
        generatable=False,
        criteria=[crit("r-parent", "Разпределение на дейностите между експертите")],
    )
    first = item("c1", parent="p", title="Описание на човешките ресурси")
    second = item("c2", parent="p", title="Разпределение на дейностите и отговорностите")

    moved = redistribute_parent_criteria([parent, first, second])

    assert moved == [
        {"criterion_id": "c-r-parent", "requirement_id": "r-parent", "from_item_id": "p", "to_item_id": "c2"}
    ]
    assert parent.acceptance_criteria_json == []
    received = second.acceptance_criteria_json[0]
    assert received["requirement_id"] == "r-parent"
    assert received["inherited_from_item_id"] == "p"


def test_all_five_requirement_kinds_are_accounted_for():
    """T-04: parent, child, prohibition, evaluation and an unmatched requirement."""
    requirements = [
        req("r-parent", kind="cross_ref", scope="proposal_format"),
        req("r-child"),
        req("r-prohibition", kind="prohibition", scope="proposal_format"),
        req("r-evaluation", kind="evaluation", scope="evaluation_rule"),
        req("r-unmatched"),
        req("r-admin", scope="qualification_admin"),
    ]
    items = [
        item("leaf", criteria=[crit("r-parent"), crit("r-child")]),
        item("decor", generatable=False, criteria=[crit("r-unmatched")]),
    ]

    result = compute_dispositions(items, requirements)
    by_id = {entry["requirement_id"]: entry for entry in result["dispositions"]}

    # Administrative requirements are outside the proposal denominator.
    assert set(by_id) == {"r-parent", "r-child", "r-prohibition", "r-evaluation", "r-unmatched"}
    assert by_id["r-parent"]["disposition"] == "target"
    assert by_id["r-child"]["disposition"] == "target"
    assert by_id["r-prohibition"]["disposition"] == "global_control"
    assert by_id["r-evaluation"]["disposition"] == "global_control"
    assert by_id["r-unmatched"]["disposition"] == "unresolved"
    assert by_id["r-unmatched"]["placed_on_non_generatable_items"] == ["decor"]
    assert by_id["r-unmatched"]["source_quote"] == "Цитат r-unmatched"
    summary = result["summary"]
    assert summary["total"] == 5
    assert summary["unresolved"] == 1
    assert summary["unresolved_requirement_ids"] == ["r-unmatched"]
    categories = {entry["requirement_id"]: entry["category"] for entry in result["global_controls"]}
    # A targeted cross-reference constraint is also kept as a global rule.
    assert categories == {
        "r-parent": "cross_reference",
        "r-prohibition": "prohibition",
        "r-evaluation": "evaluation",
    }


def test_human_resolutions_account_for_unresolved_requirements():
    requirements = [req("r-a"), req("r-b")]
    result = compute_dispositions(
        [item("leaf")],
        requirements,
        {
            "r-a": {"action": "exclude", "reason": "Не се отнася за тази обособена позиция."},
            "r-b": {"action": "global_control"},
        },
    )
    by_id = {entry["requirement_id"]: entry["disposition"] for entry in result["dispositions"]}
    assert by_id == {"r-a": "excluded", "r-b": "global_control"}
    assert result["summary"]["unresolved"] == 0


def test_schedule_requirements_are_global_controls_not_losses():
    root = item("sched", generatable=False, title="Линеен график и ресурсни диаграми", criteria=[crit("r-s")])
    result = compute_dispositions([root], [req("r-s")], schedule_item_ids={"sched"})
    assert result["dispositions"][0]["disposition"] == "global_control"
    assert result["global_controls"][0]["category"] == "schedule"


@pytest.mark.asyncio
async def test_mandatory_structure_build_conserves_parent_and_prohibition_requirements():
    """Before K-03 the generatable subpoints received zero original ids."""
    headings = [
        MandatoryHeading("1", "Концепция и подход", 1, "1. Концепция и подход"),
        MandatoryHeading("2", "Организация на изпълнението", 2, "2. Организация на изпълнението"),
        MandatoryHeading("2.1", "Разпределение на отговорностите", 2, "2.1. Разпределение на отговорностите"),
        MandatoryHeading("2.2", "Организационна схема", 2, "2.2. Организационна схема"),
    ]
    requirements = [
        req(
            "r-parent",
            text="Организация на екипа и разпределение на отговорностите между експертите",
            path=["2. Организация на изпълнението"],
        ),
        req(
            "r-prohibition",
            kind="prohibition",
            scope="proposal_format",
            text="Експертите се посочват само като квалификация и брой.",
            path=["2. Организация на изпълнението"],
        ),
        req("r-concept", text="Подход за изпълнение", path=["1. Концепция и подход"], page=1),
        req("r-lost", text="Нещо без съответствие", path=["Приложения към офертата"], page=9),
    ]
    added: list = []
    db = MagicMock()
    db.add = MagicMock(side_effect=added.append)
    db.flush = AsyncMock()

    await _populate_from_mandatory_headings(
        project_id="project-1",
        outline=SimpleNamespace(id="outline-1"),
        headings=headings,
        requirements=requirements,
        wbs_items=[],
        facts={},
        db=db,
    )

    result = compute_dispositions(added, requirements)
    by_id = {entry["requirement_id"]: entry for entry in result["dispositions"]}
    generatable_ids = {node.id for node in added if node.generation_uid}
    for requirement_id in ("r-parent", "r-prohibition", "r-concept"):
        entry = by_id[requirement_id]
        assert entry["disposition"] == "target", requirement_id
        assert {target["item_id"] for target in entry["targets"]} <= generatable_ids
    assert by_id["r-lost"]["disposition"] == "unresolved"
    # The prohibition did not create a decorative subpoint.
    assert not any("само като квалификация" in node.title for node in added)
    # Parent heading 2 is not generatable and holds no orphaned criteria.
    heading_two = next(node for node in added if node.number == "2")
    assert heading_two.generation_uid is None
    assert not [c for c in heading_two.acceptance_criteria_json if c.get("requirement_id")]
