from types import SimpleNamespace

from app.agents.requirements import (
    SPECIFIC_REQUIREMENTS_CATEGORY,
    SPECIFIC_REQUIREMENTS_LABEL,
    SUGGESTED_SECTIONS,
    RequirementItem,
    extract_requirement_checklist,
)
from app.agents.tender_struct import (
    _attach_requirement_checklist_to_outline_sections,
    _build_domain_outline,
    _build_deterministic_outline,
    _build_outline_coverage_summary,
    _ensure_mandatory_sections,
    _extract_explicit_numbered_outline,
    _extract_mandatory_sections,
    _is_tp_requirement_chunk,
    _score_chunk,
    _select_tender_struct_chunks,
)


def make_chunk(
    chunk_id: str,
    text: str,
    *,
    page: int | None = None,
    section_path: str | None = None,
    chunk_type: str = "text",
):
    return SimpleNamespace(
        id=chunk_id,
        text=text,
        page=page,
        section_path=section_path,
        chunk_type=chunk_type,
    )


def make_requirement(
    requirement_id: str,
    text: str,
    *,
    category: str = "schedule",
    category_label: str = "График и срокове",
    suggested_section: str | None = None,
):
    return RequirementItem(
        id=requirement_id,
        text=text,
        category=category,
        category_label=category_label,
        topic=text,
        importance="mandatory",
        suggested_section=suggested_section or SUGGESTED_SECTIONS[category],
        coverage_question=f"Покрито ли е: {text}?",
        source_chunk_id=f"chunk-{requirement_id}",
        source_page=1,
        source_section_path="Изисквания към техническото предложение",
        source_file="docs.pdf",
        source_excerpt=text,
        evidence_cues=[],
    )


def test_score_chunk_prioritizes_explicit_tp_requirements():
    generic_chunk = make_chunk(
        "generic",
        "Общи данни за поръчката и административна информация.",
        page=2,
    )
    requirement_chunk = make_chunk(
        "requirement",
        (
            "Техническото предложение следва да съдържа раздели "
            "\"Концепция и подход\" и \"Разработване на работен проект\"."
        ),
        page=14,
    )

    assert _score_chunk(requirement_chunk) > _score_chunk(generic_chunk)


def test_select_tender_struct_chunks_keeps_priority_chunks_even_if_late_in_document():
    leading_chunks = [
        make_chunk(
            f"lead-{index}",
            f"Въведение и обща информация {index}",
            page=index + 1,
        )
        for index in range(90)
    ]
    late_requirement = make_chunk(
        "late-requirement",
        "Участникът следва да опише Концепция и подход, Разработване на работен проект и организация на изпълнението.",
        page=48,
        section_path="Изисквания към техническото предложение",
    )

    selected, priority = _select_tender_struct_chunks(
        [*leading_chunks, late_requirement],
        max_priority_chunks=10,
        max_context_chunks=25,
    )

    assert any(chunk.id == "late-requirement" for chunk in selected)
    assert any(chunk.id == "late-requirement" for chunk in priority)


def test_extract_mandatory_sections_reads_explicit_numbered_titles():
    chunks = [
        make_chunk(
            "chunk-1",
            (
                "1.Концепция и подход.\n"
                "Участникът следва да предложи кратко подхода за изпълнение на предмета на поръчката."
            ),
            page=10,
        )
    ]

    mandatory = _extract_mandatory_sections(chunks)

    assert len(mandatory) == 1
    assert mandatory[0]["title"] == "Концепция и подход"
    assert "Участникът следва да предложи" in mandatory[0]["requirement"]


def test_ensure_mandatory_sections_inserts_missing_explicit_titles():
    mandatory = [
        {
            "title": "Концепция и подход",
            "source_ref": "chunk-1",
            "requirement": "Участникът следва да предложи кратко подхода за изпълнение.",
        }
    ]
    outline_sections = [
        {
            "uid": "existing",
            "title": "Организация на изпълнението",
            "required": True,
            "requirements": ["Описание на организацията."],
            "source_refs": [],
            "subsections": [],
        }
    ]

    result = _ensure_mandatory_sections(outline_sections, mandatory)

    assert result[0]["title"] == "Концепция и подход"
    assert result[0]["source_refs"] == ["chunk-1"]
    assert result[1]["title"] == "Организация на изпълнението"


def test_build_deterministic_outline_uses_extracted_sections_when_llm_omits_outline():
    explicit_sections = [
        {
            "uid": f"section-{index}",
            "title": title,
            "required": True,
            "requirements": [f"РР·РёСЃРєРІР°РЅРµ Р·Р° {title}"],
            "source_refs": [f"chunk-{index}"],
            "subsections": [],
        }
        for index, title in enumerate(
            [
                "РљРѕРЅС†РµРїС†РёСЏ Рё РїРѕРґС…РѕРґ",
                "Р Р°Р·СЂР°Р±РѕС‚РІР°РЅРµ РЅР° РёРЅРІРµСЃС‚РёС†РёРѕРЅРµРЅ РїСЂРѕРµРєС‚",
                "Р›РёРЅРµРµРЅ РіСЂР°С„РёРє",
                "РњРµСЂРєРё Р·Р° РѕСЃРёРіСѓСЂСЏРІР°РЅРµ РЅР° РєР°С‡РµСЃС‚РІРѕС‚Рѕ",
                "РћСЂРіР°РЅРёР·Р°С†РёСЏ РЅР° РєРѕРјСѓРЅРёРєР°С†РёСЏС‚Р°",
            ]
        )
    ]

    outline = _build_deterministic_outline(
        explicit_numbered_sections=explicit_sections,
        domain_outline_sections=[],
        mandatory_sections=[],
    )

    assert outline is not None
    assert [section["title"] for section in outline["sections"]] == [
        section["title"] for section in explicit_sections
    ]


def test_requirement_checklist_is_attached_to_matching_outline_sections():
    sections = [
        {
            "uid": "schedule-section",
            "title": SUGGESTED_SECTIONS["schedule"],
            "required": True,
            "requirements": [],
            "source_refs": [],
            "subsections": [],
        }
    ]
    schedule_requirement = make_requirement(
        "req-schedule",
        "Следва да се представи подробен линеен график за изпълнение.",
    )
    specific_requirement = make_requirement(
        "req-specific",
        "Следва да се опише специален ред за достъп до помещенията.",
        category=SPECIFIC_REQUIREMENTS_CATEGORY,
        category_label=SPECIFIC_REQUIREMENTS_LABEL,
        suggested_section=SUGGESTED_SECTIONS[SPECIFIC_REQUIREMENTS_CATEGORY],
    )

    enriched = _attach_requirement_checklist_to_outline_sections(
        sections,
        [schedule_requirement, specific_requirement],
    )
    summary = _build_outline_coverage_summary(
        enriched,
        [schedule_requirement, specific_requirement],
    )

    schedule_section = next(section for section in enriched if section["uid"] == "schedule-section")
    specific_section = next(
        section
        for section in enriched
        if section["title"] == SUGGESTED_SECTIONS[SPECIFIC_REQUIREMENTS_CATEGORY]
    )

    assert schedule_section["requirement_ids"] == ["req-schedule"]
    assert schedule_section["requirement_checklist_items"][0]["id"] == "req-schedule"
    assert schedule_section["drafting_guidance"]["requirement_count"] == 1
    assert schedule_section["drafting_guidance"]["required_subtopics"] == [
        schedule_requirement.topic
    ]
    assert specific_section["requirement_ids"] == ["req-specific"]
    assert specific_section["requirement_checklist_items"][0]["id"] == "req-specific"
    assert specific_section["drafting_guidance"]["requirement_count"] == 1
    assert summary["total_requirements"] == 2
    assert summary["covered_requirements"] == 2
    assert summary["missing_requirement_ids"] == []


def test_build_deterministic_outline_can_start_from_requirement_checklist():
    requirement = make_requirement(
        "req-specific-only",
        "Следва да се опише специален ред за достъп до помещенията.",
        category=SPECIFIC_REQUIREMENTS_CATEGORY,
        category_label=SPECIFIC_REQUIREMENTS_LABEL,
        suggested_section=SUGGESTED_SECTIONS[SPECIFIC_REQUIREMENTS_CATEGORY],
    )

    outline = _build_deterministic_outline(
        explicit_numbered_sections=[],
        domain_outline_sections=[],
        mandatory_sections=[],
        requirement_checklist=[requirement],
    )

    assert outline is not None
    assert outline["sections"][0]["title"] == SUGGESTED_SECTIONS[SPECIFIC_REQUIREMENTS_CATEGORY]
    assert outline["sections"][0]["requirement_ids"] == ["req-specific-only"]
    assert outline["sections"][0]["requirement_checklist_items"][0]["id"] == "req-specific-only"
    assert outline["sections"][0]["drafting_guidance"]["requirement_count"] == 1
    assert outline["coverage_summary"]["covered_requirements"] == 1


def test_common_noisy_requirement_scenario_builds_outline_from_checklist():
    chunks = [
        make_chunk(
            "common-scenario",
            (
                "Минималното съдържание на техническото предложение включва:\n"
                "1. мерки за управление на риска, включително идентифициране\n"
                "на конкретни рискове и действия при непредвидени обстоятелства;\n"
                "2. мерки за опазване на околната среда, ограничаване на праха\n"
                "и управление на строителните отпадъци;\n"
                "3. входящ, текущ и окончателен контрол на качеството\n"
                "с протоколи за приемане;\n"
                "4. специален ред за достъп до помещенията и\n"
                "предаване на ключове."
            ),
            page=18,
            section_path="Изисквания към техническото предложение",
        )
    ]

    requirements = extract_requirement_checklist(chunks)
    outline = _build_deterministic_outline(
        explicit_numbered_sections=[],
        domain_outline_sections=[],
        mandatory_sections=[],
        requirement_checklist=requirements,
    )

    assert outline is not None
    assert len(requirements) == 4
    titles = [section["title"] for section in outline["sections"]]
    assert SUGGESTED_SECTIONS["risk"] in titles
    assert SUGGESTED_SECTIONS["environment"] in titles
    assert SUGGESTED_SECTIONS["quality"] in titles
    assert SUGGESTED_SECTIONS[SPECIFIC_REQUIREMENTS_CATEGORY] in titles
    assert outline["coverage_summary"]["total_requirements"] == 4
    assert outline["coverage_summary"]["covered_requirements"] == 4
    assert outline["coverage_summary"]["missing_requirement_ids"] == []


def test_extract_mandatory_sections_ignores_numbered_lines_without_tp_context():
    chunks = [
        make_chunk(
            "chunk-2",
            "8.13. Възможността по предходната точка се прилага и за подизпълнителите.",
            page=20,
        )
    ]

    mandatory = _extract_mandatory_sections(chunks)

    assert mandatory == []


def test_extract_explicit_numbered_outline_reads_top_level_sections_without_space_after_number():
    chunks = [
        make_chunk(
            "chunk-1",
            (
                "1.Концепция и подход.\n"
                "Участникът следва да предложи кратко подхода за изпълнение.\n"
                "2.Разработване на инвестиционен проект.\n"
                "Участникът следва да опише обхвата и дейностите по проектирането.\n"
                "3.Линеен график.\n"
                "Следва да се представи график за изпълнение.\n"
                "4.Мерки за осигуряване на качеството.\n"
                "Следва да се опишат мерките за контрол.\n"
                "5.Организация на комуникацията.\n"
                "Следва да се опишат механизмите за комуникация."
            )
        )
    ]

    outline = _extract_explicit_numbered_outline(chunks)

    assert [section["title"] for section in outline] == [
        "Концепция и подход",
        "Разработване на инвестиционен проект",
        "Линеен график",
        "Мерки за осигуряване на качеството",
        "Организация на комуникацията",
    ]


def test_is_tp_requirement_chunk_rejects_administrative_table_of_contents_noise():
    toc_chunk = make_chunk(
        "toc",
        "4.1. ИЗИСКВАНИЯ КЪМ ЛИЧНОТО СЪСТОЯНИЕ НА УЧАСТНИЦИТЕ: ........ 12",
        chunk_type="heading",
    )
    requirement_chunk = make_chunk(
        "req",
        "1.Концепция и подход.\nУчастникът следва да предложи кратко подхода за изпълнение.",
    )

    assert _is_tp_requirement_chunk(toc_chunk) is False
    assert _is_tp_requirement_chunk(requirement_chunk) is True


def test_build_domain_outline_prefers_tp_domain_sections_over_document_noise():
    chunks = [
        make_chunk("c1", "1.Концепция и подход.\nУчастникът следва да предложи кратко подхода за изпълнение."),
        make_chunk("c2", "2.Разработване на инвестиционен проект:\n2.1. Обхват и дейности:"),
        make_chunk("c3", "2.2. Организация при изпълнение на проектирането"),
        make_chunk("c4", "2.3. Комуникация\nУчастникът следва да представи начините на комуникация."),
        make_chunk("c5", "3. Осъществяване на авторски надзор по време на изпълнение на СМР"),
        make_chunk("c6", "4.2. Организация на ресурсите"),
        make_chunk("c7", "4.3. Комуникация\n... екипа за изпълнение на строителството ..."),
        make_chunk("c8", "4.4. Организация за доставка на материали"),
        make_chunk("c9", "ПОДРОБЕН ЛИНЕЕН ГРАФИК ЗА ИЗПЪЛНЕНИЕ НА ПРЕДВИДЕНИТЕ ДЕЙНОСТИ", chunk_type="heading"),
        make_chunk("c10", "5. Управление на риска"),
        make_chunk("c11", "6. Ограничаване и предотвратяване на негативното въздействие върху околната среда"),
        make_chunk("c12", "7. Мерки за осигуряване на качеството."),
        make_chunk("c13", "8. Организация на дейностите по отстраняване на гаранционни дефекти"),
        make_chunk("noise", "4.1. ИЗИСКВАНИЯ КЪМ ЛИЧНОТО СЪСТОЯНИЕ НА УЧАСТНИЦИТЕ: ........ 12", chunk_type="heading"),
    ]

    outline = _build_domain_outline(chunks)

    assert [section["title"] for section in outline] == [
        "Концепция и подход",
        "Разработване на инвестиционен проект",
        "Осъществяване на авторски надзор по време на изпълнение на СМР",
        "Организация при изпълнение на строителството",
        "Линеен график",
        "Управление на риска",
        "Ограничаване и предотвратяване на негативното въздействие върху околната среда",
        "Мерки за осигуряване на качеството",
        "Организация на дейностите по отстраняване на гаранционни дефекти",
    ]


def test_build_domain_outline_adds_detailed_work_program_subtopics_when_present():
    chunks = [
        make_chunk("c1", "1.Концепция и подход."),
        make_chunk("c2", "2.Разработване на инвестиционен проект."),
        make_chunk("c3", "3. Осъществяване на авторски надзор по време на изпълнение на СМР"),
        make_chunk("c4", "4.2. Организация на ресурсите"),
        make_chunk("c5", "Заинтересовани страни и участници в изпълнението на поръчката."),
        make_chunk("c6", "Вътрешнофирмена комуникация, координация, контрол и субординация."),
        make_chunk("c7", "Комуникация с Възложителя, строителния надзор и компетентните институции."),
        make_chunk("c8", "Пожарна безопасност и здравословни и безопасни условия при изпълнение."),
        make_chunk("c9", "Линеен график за изпълнение."),
        make_chunk("c10", "5. Управление на риска."),
        make_chunk("c11", "Идентификация на риска, конкретни рискове и мерки за ограничаване на риска."),
        make_chunk("c12", "Мониторинг на риска, отговорности при риск и ескалация."),
        make_chunk("c13", "6. Опазване на околната среда."),
        make_chunk("c14", "Мерки срещу запрашаване, прах и замърсяване на въздуха."),
        make_chunk("c15", "Опазване на почвите, водите и прилежащи терени."),
        make_chunk("c16", "Управление на строителни отпадъци и ПУСО."),
        make_chunk("c17", "7. Мерки за осигуряване на качеството."),
        make_chunk("c18", "Входящ контрол, текущ контрол и окончателен контрол."),
        make_chunk("c19", "Документиране, протоколи и приемане на изпълнените работи."),
        make_chunk("c20", "8. Организация на дейностите по отстраняване на гаранционни дефекти."),
    ]

    outline = _build_domain_outline(chunks)

    construction = next(section for section in outline if section["title"].startswith("Организация при"))
    risk = next(section for section in outline if section["title"] == "Управление на риска")
    environment = next(section for section in outline if section["title"].startswith("Ограничаване"))
    quality = next(section for section in outline if section["title"] == "Мерки за осигуряване на качеството")

    construction_titles = [section["title"] for section in construction["subsections"]]
    risk_titles = [section["title"] for section in risk["subsections"]]
    environment_titles = [section["title"] for section in environment["subsections"]]
    quality_titles = [section["title"] for section in quality["subsections"]]

    assert "Заинтересовани страни и участници в изпълнението" in construction_titles
    assert "Вътрешнофирмена комуникация, координация, контрол и субординация" in construction_titles
    assert "Комуникация с Възложителя, строителния надзор и институциите" in construction_titles
    assert "Пожарна безопасност и безопасност при изпълнение на СМР" in construction_titles
    assert "Идентификация, оценка и мерки за конкретните рискове" in risk_titles
    assert "Мониторинг, отговорности и ескалация при риск" in risk_titles
    assert "Мерки срещу запрашаване и замърсяване на въздуха" in environment_titles
    assert "Опазване на почви, води и прилежащи терени" in environment_titles
    assert "Управление на строителните отпадъци" in environment_titles
    assert "Входящ, текущ и окончателен контрол на качеството" in quality_titles
    assert "Документиране, проверки и приемане на изпълнените работи" in quality_titles
