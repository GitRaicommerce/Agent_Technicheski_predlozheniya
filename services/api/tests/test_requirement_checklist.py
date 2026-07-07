from types import SimpleNamespace

from app.agents.requirements import (
    SPECIFIC_REQUIREMENTS_CATEGORY,
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


def test_extract_requirement_checklist_reconstructs_wrapped_pdf_list_items():
    chunks = [
        make_chunk(
            "c-wrapped-list",
            (
                "Техническото предложение следва да съдържа:\n"
                "1. описание на организацията за\n"
                "изпълнение, включително отговорности и ресурси;\n"
                "2. мерки за контрол на\n"
                "качеството и приемане на изпълнените работи;\n"
                "3. организация на комуникацията\n"
                "с Възложителя и строителния надзор."
            ),
            page=43,
        )
    ]

    items = extract_requirement_checklist(chunks)

    assert len(items) == 3
    assert any("отговорности и ресурси" in item.text for item in items)
    assert any("качеството и приемане" in item.text for item in items)
    assert any("Възложителя и строителния надзор" in item.text for item in items)
    assert any(item.category == "organization" for item in items)
    assert any(item.category == "quality" for item in items)
    assert any(item.category == "communication" for item in items)


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


def test_extract_requirement_checklist_reconstructs_wrapped_scored_sentence():
    chunks = [
        make_chunk(
            "c-wrapped-scored",
            (
                "Ще се оценява предложената методология за управление на\n"
                "риска, идентифициране на конкретни рискове и мерки при\n"
                "непредвидени обстоятелства."
            ),
            page=56,
        )
    ]

    items = extract_requirement_checklist(chunks)

    assert len(items) == 1
    assert items[0].importance == "scored"
    assert items[0].category == "risk"
    assert "идентифициране на конкретни рискове" in items[0].text
    assert "непредвидени обстоятелства" in items[0].text


def test_extract_requirement_checklist_ignores_clear_admin_noise_without_tp_context():
    chunks = [
        make_chunk(
            "c3",
            "Участникът следва да представи ЕЕДОП и декларация за лично състояние.",
            page=12,
        )
    ]

    assert extract_requirement_checklist(chunks) == []


def test_extract_requirement_checklist_ignores_procurement_only_noise_with_tp_words():
    chunks = [
        make_chunk(
            "c-procurement-noise",
            (
                "Техническо предложение - включващо документите по чл. 39, ал. 3 от ЗОП.\n"
                "Физическите лица по пълномощие, когато участникът се представлява от "
                "физическо лице по пълномощие, следва да представят документите."
            ),
            page=14,
        ),
        make_chunk(
            "c-experience-noise",
            (
                "Списък на строителството, идентично или сходно с предмета на поръчката, "
                "изпълнено през последните 5 години, с удостоверения за добро изпълнение, "
                "които да съдържат стойността и мястото на изпълнение."
            ),
            page=19,
        ),
        make_chunk(
            "c-offer-submission-noise",
            (
                "Подаването на офертата задължава участниците да приемат напълно всички "
                "изисквания и условия, посочени в документацията."
            ),
            page=9,
        ),
        make_chunk(
            "c-professional-law-noise",
            (
                "6 ЗКАИИП следва да са изпълнени от избрания за изпълнител участник "
                "при сключването на договора."
            ),
            page=21,
        ),
    ]

    assert extract_requirement_checklist(chunks) == []


def test_extract_requirement_checklist_ignores_generic_offer_ranking_noise():
    chunks = [
        make_chunk(
            "c-ranking-noise",
            (
                "Класирането на офертите се извършва на база комплексна оценка на "
                "офертите, като избраният критерий е оптимално съотношение качество/цена "
                "и показателите и относителната им тежест са посочени в методиката."
            ),
            page=22,
        )
    ]

    assert extract_requirement_checklist(chunks) == []


def test_extract_requirement_checklist_ignores_broad_catch_all_clauses():
    chunks = [
        make_chunk(
            "c-broad-all",
            (
                "Техническото предложение следва да съдържа декларация, че "
                "участникът приема и ще спазва всички изисквания и условия, "
                "посочени в документацията за обществената поръчка."
            ),
            page=23,
        ),
        make_chunk(
            "c-broad-docs",
            (
                "Участникът следва да спазва всички приложими нормативни актове "
                "и всички указания на Възложителя при изпълнение на договора."
            ),
            page=24,
        ),
        make_chunk(
            "c-concrete-compliance",
            (
                "Техническото предложение следва да опише конкретни мерки за "
                "спазване на нормативните изисквания за безопасност, контрол "
                "на качеството и опазване на околната среда при изпълнение на СМР."
            ),
            page=25,
        ),
    ]

    items = extract_requirement_checklist(chunks)

    assert len(items) == 1
    assert items[0].category == "quality"
    assert "конкретни мерки" in items[0].text


def test_extract_requirement_checklist_splits_pdf_table_rows_without_header_noise():
    chunks = [
        make_chunk(
            "c-table-rows",
            (
                "Минималното съдържание на техническото предложение включва:\n"
                "№ Показател Максимален брой точки\n"
                "1 Организация на изпълнение 20\n"
                "2 Линеен график 10\n"
                "3 Мерки за качество 15\n"
                "Общо 45 точки"
            ),
            page=26,
        )
    ]

    items = extract_requirement_checklist(chunks)

    assert len(items) == 3
    assert all("Показател" not in item.text for item in items)
    assert all("Общо" not in item.text for item in items)
    assert any("Организация на изпълнение" in item.text for item in items)
    assert any("Линеен график" in item.text for item in items)
    assert any("Мерки за качество" in item.text for item in items)


def test_extract_requirement_checklist_keeps_unmapped_specific_requirements():
    chunks = [
        make_chunk(
            "c-specific",
            (
                "Техническото предложение следва да съдържа:\n"
                "1. описание на специалния ред за достъп до помещенията и предаване на ключове."
            ),
            page=31,
        )
    ]

    items = extract_requirement_checklist(chunks)

    assert len(items) == 1
    assert items[0].category == SPECIFIC_REQUIREMENTS_CATEGORY
    assert "специфични изисквания" in items[0].category_label.lower()


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
