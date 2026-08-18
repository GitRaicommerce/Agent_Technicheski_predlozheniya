from types import SimpleNamespace

from app.agents.examples import _hydrate_selected_snippets


def test_selected_forlage_is_hydrated_from_exact_stored_text():
    candidates = [
        SimpleNamespace(
            id="snippet-1",
            text="Пълно оригинално описание за изпълнение на проект по част ВиК.",
            snippet_kind="generic_boilerplate",
            source_group="design",
        )
    ]

    result = _hydrate_selected_snippets(
        [
            {
                "snippet_id": "snippet-1",
                "relevance_note": "Подходяща методология",
                "text": "Изменен или измислен от модела текст",
            }
        ],
        candidates,
        5,
    )

    assert result == [
        {
            "snippet_id": "snippet-1",
            "relevance_note": "Подходяща методология",
            "text": "Пълно оригинално описание за изпълнение на проект по част ВиК.",
            "snippet_kind": "generic_boilerplate",
            "source_group": "design",
        }
    ]


def test_forlage_hydration_rejects_unknown_and_duplicate_ids():
    candidates = [
        SimpleNamespace(
            id="snippet-1",
            text="Оригинален текст",
            snippet_kind="generic_boilerplate",
            source_group="design",
        )
    ]

    result = _hydrate_selected_snippets(
        [
            {"snippet_id": "missing"},
            {"snippet_id": "snippet-1"},
            {"snippet_id": "snippet-1"},
        ],
        candidates,
        5,
    )

    assert [item["snippet_id"] for item in result] == ["snippet-1"]
