"""WP-07 / K-13 (T-19 backend half): criteria are edited as stable-id records."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.routers.content_plan import validate_item_criteria

EXISTING = [
    {"id": "c-a", "text": "Първи", "kind": "content", "source_quote": "цитат А", "requirement_id": "r-a"},
    {"id": "c-b", "text": "Втори", "kind": "content", "source_quote": "цитат Б", "requirement_id": "r-b"},
]


def test_reorder_and_delete_keep_each_record_with_its_own_quote():
    result = validate_item_criteria(
        [{"id": "c-b", "text": "Втори (редактиран)", "kind": "content"}],
        EXISTING,
        set(),
    )
    assert result == [
        {"id": "c-b", "text": "Втори (редактиран)", "kind": "content", "source_quote": "цитат Б", "requirement_id": "r-b"}
    ]


def test_client_cannot_move_a_quote_between_records():
    result = validate_item_criteria(
        [{"id": "c-a", "text": "Първи", "kind": "content", "source_quote": "цитат Б", "requirement_id": "r-b"}],
        EXISTING,
        set(),
    )
    assert result[0]["source_quote"] == "цитат А"
    assert result[0]["requirement_id"] == "r-a"


def test_new_criterion_gets_no_inherited_quote():
    result = validate_item_criteria(
        [*EXISTING, {"id": "manual-new", "text": "Нов", "kind": "content"}],
        EXISTING,
        set(),
    )
    assert result[-1] == {"id": "manual-new", "text": "Нов", "kind": "content"}


@pytest.mark.parametrize(
    ("submitted", "elsewhere", "fragment"),
    [
        ([{"id": "c-a", "text": "x"}, {"id": "c-a", "text": "y"}], set(), "Повторен"),
        ([{"id": "", "text": "x"}], set(), "идентификатор"),
        ([{"id": "c-a", "text": "   "}], set(), "празен"),
        ([{"id": "c-other", "text": "x"}], {"c-other"}, "друга точка"),
        ([{"id": "manual-1", "text": "x", "source_quote": "чужд цитат"}], set(), "цитат"),
    ],
)
def test_invalid_or_duplicate_ids_are_rejected(submitted, elsewhere, fragment):
    with pytest.raises(HTTPException) as caught:
        validate_item_criteria(submitted, EXISTING, elsewhere)
    assert caught.value.status_code == 422
    assert fragment in caught.value.detail
