from types import SimpleNamespace

from app.agents.requirements import (
    extract_requirement_checklist,
    format_requirements_for_prompt,
    render_requirements_markdown,
)


def make_chunk(chunk_id: str, text: str, *, page: int | None = None):
    return SimpleNamespace(
        id=chunk_id,
        text=text,
        page=page,
        section_path="Методика / Техническо предложение",
        source_file="Документация.pdf",
    )


def test_extract_requirement_checklist_splits_tp_list_items():
    chunks = [
        make_chunk(
            "c1",
            (
                "Техническото предложение следва да съдържа:\n"
                "1. описание на организацията за изпълнение;\n"
                "2. линеен график с последователност на дейностите;\n"
                "3. мерки за контрол на качеството."
            ),
            page=42,
        )
    ]

    items = extract_requirement_checklist(chunks)

    assert len(items) == 3
    assert any("описание на организацията" in item.text for item in items)
    assert any(item.category == "schedule" for item in items)
    assert any(item.category == "quality" for item in items)
    assert all(item.source_page == 42 for item in items)


def test_extract_requirement_checklist_keeps_scored_requirements():
    chunks = [
        make_chunk(
            "c2",
            "Ще се оценява предложената методология за управление на риска и мерките при непредвидени обстоятелства.",
            page=55,
        )
    ]

    items = extract_requirement_checklist(chunks)

    assert len(items) == 1
    assert items[0].importance == "scored"
    assert items[0].category == "risk"
    assert "Управление на риска" in items[0].suggested_section


def test_extract_requirement_checklist_ignores_clear_admin_noise_without_tp_context():
    chunks = [
        make_chunk(
            "c3",
            "Участникът следва да представи ЕЕДОП и декларация за лично състояние.",
            page=12,
        )
    ]

    assert extract_requirement_checklist(chunks) == []


def test_requirement_checklist_renderers_include_actionable_fields():
    items = extract_requirement_checklist(
        [
            make_chunk(
                "c4",
                "Участникът следва да опише комуникацията с Възложителя и строителния надзор.",
                page=61,
            )
        ]
    )

    prompt = format_requirements_for_prompt(items)
    markdown = render_requirements_markdown(items, title="Тестов чеклист")

    assert "УНИВЕРСАЛЕН ЧЕКЛИСТ" in prompt
    assert "Комуникация" in prompt
    assert "Контролен въпрос" in markdown
    assert "[ ]" in markdown
