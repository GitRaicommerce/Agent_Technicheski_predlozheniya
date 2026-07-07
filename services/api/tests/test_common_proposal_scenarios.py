from __future__ import annotations

from types import SimpleNamespace

from app.agents.drafting_blueprint import build_drafting_blueprint
from app.agents.proposal_quality import assess_generation_depth
from app.agents.requirements import (
    SPECIFIC_REQUIREMENTS_CATEGORY,
    SUGGESTED_SECTIONS,
    extract_requirement_checklist,
)
from app.agents.requirement_coverage import assess_requirement_coverage
from app.agents.tender_struct import (
    _build_deterministic_outline,
    _extract_explicit_numbered_outline,
)
from app.export.readiness_report import render_export_readiness_report


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
        source_file="documentation.pdf",
        chunk_type=chunk_type,
    )


def _walk_sections(sections: list[dict]):
    for section in sections:
        yield section
        yield from _walk_sections(section.get("subsections") or [])


def _coverage_for(requirement_items: list[dict]) -> dict:
    return {
        "total": len(requirement_items),
        "covered": len(requirement_items),
        "missing": 0,
        "missing_ids": [],
        "items": [
            {"id": item["id"], "status": "covered"}
            for item in requirement_items
        ],
    }


def test_no_outline_complex_tender_gets_checklist_outline_blueprint_and_depth_gate():
    chunks = [
        make_chunk(
            "complex-common-scenario",
            (
                "Минималното съдържание на техническото предложение включва:\n"
                "1. мерки за управление на риска, включително идентифициране\n"
                "на конкретни рискове и действия при непредвидени обстоятелства;\n"
                "2. мерки за опазване на околната среда, ограничаване на праха\n"
                "и управление на строителните отпадъци;\n"
                "3. входящ, текущ и окончателен контрол на качеството\n"
                "с протоколи за приемане;\n"
                "4. организация на комуникацията с Възложителя, строителния надзор\n"
                "и компетентните институции;\n"
                "5. специален ред за достъп до помещенията и предаване на ключове."
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
    assert len(requirements) == 5
    assert {item.category for item in requirements} == {
        "risk",
        "environment",
        "quality",
        "communication",
        SPECIFIC_REQUIREMENTS_CATEGORY,
    }
    titles = {section["title"] for section in _walk_sections(outline["sections"])}
    assert SUGGESTED_SECTIONS["risk"] in titles
    assert SUGGESTED_SECTIONS["environment"] in titles
    assert SUGGESTED_SECTIONS["quality"] in titles
    assert SUGGESTED_SECTIONS["communication"] in titles
    assert SUGGESTED_SECTIONS[SPECIFIC_REQUIREMENTS_CATEGORY] in titles
    assert outline["coverage_summary"]["covered_requirements"] == 5

    requirement_items = [item.as_dict() for item in requirements]
    blueprint = build_drafting_blueprint(
        section_title="Работна програма за изпълнение",
        requirement_items=requirement_items,
        project_grounding_context={
            "schedule": {
                "tasks": [
                    {"name": "Подготовка на обекта"},
                    {"name": "Изпълнение и контрол"},
                ]
            },
            "tender_chunks": [
                {
                    "text": (
                        "Поръчката изисква работна програма с конкретни мерки, "
                        "контроли, отговорности и документиране."
                    )
                }
            ],
        },
    )

    assert {group["category"] for group in blueprint["groups"]} == {
        "risk",
        "environment",
        "quality",
        "communication",
        SPECIFIC_REQUIREMENTS_CATEGORY,
    }
    shallow_result = assess_generation_depth(
        "Generic execution narrative with brief controls and responsibilities. " * 35,
        _coverage_for(requirement_items),
        drafting_blueprint=blueprint,
    )
    assert shallow_result["status"] == "needs_review"
    assert shallow_result["blueprint_group_count"] == 5
    assert shallow_result["min_words"] >= 1000

    developed_sentence = (
        "The proposal identifies the concrete action, responsible role, "
        "coordination point, control record, timing, acceptance evidence, "
        "monitoring signal, escalation path, corrective action, and document "
        "flow for each mapped tender requirement. "
    )
    developed_result = assess_generation_depth(
        developed_sentence * 90,
        _coverage_for(requirement_items),
        drafting_blueprint=blueprint,
    )
    assert developed_result["status"] == "ok"


def test_explicit_outline_keeps_sections_and_attaches_matching_checklist_items():
    outline_chunks = [
        make_chunk(
            "explicit-outline",
            (
                "1.Концепция и подход.\n"
                "Участникът следва да предложи кратко подхода за изпълнение.\n"
                "2.Линеен график.\n"
                "Следва да се представи график за изпълнение.\n"
                "3.Мерки за осигуряване на качеството.\n"
                "Следва да се опишат мерките за контрол.\n"
                "4.Организация на комуникацията.\n"
                "Следва да се опишат механизмите за комуникация.\n"
                "5.Управление на риска.\n"
                "Следва да се посочат мерки при непредвидени обстоятелства."
            ),
            section_path="Съдържание на техническото предложение",
        )
    ]
    requirement_chunks = [
        make_chunk(
            "explicit-requirements",
            (
                "Техническото предложение следва да съдържа:\n"
                "1. подробен линеен график с последователност и срокове;\n"
                "2. мерки за контрол на качеството и приемане на работите;\n"
                "3. начин на комуникация с Възложителя и надзора."
            ),
            page=12,
            section_path="Изисквания към техническото предложение",
        )
    ]

    explicit_sections = _extract_explicit_numbered_outline(outline_chunks)
    requirements = extract_requirement_checklist(requirement_chunks)
    outline = _build_deterministic_outline(
        explicit_numbered_sections=explicit_sections,
        domain_outline_sections=[],
        mandatory_sections=[],
        requirement_checklist=requirements,
    )

    assert outline is not None
    top_level_titles = [section["title"] for section in outline["sections"]]
    assert top_level_titles == [
        "Концепция и подход",
        "Линеен график",
        "Мерки за осигуряване на качеството",
        "Организация на комуникацията",
        "Управление на риска",
    ]
    sections_by_title = {section["title"]: section for section in outline["sections"]}
    assert sections_by_title["Линеен график"]["requirement_checklist_items"][0][
        "category"
    ] == "schedule"
    assert sections_by_title["Мерки за осигуряване на качеството"][
        "requirement_checklist_items"
    ][0]["category"] == "quality"
    assert sections_by_title["Организация на комуникацията"][
        "requirement_checklist_items"
    ][0]["category"] == "communication"
    assert outline["coverage_summary"]["missing_requirement_ids"] == []


def test_narrow_specific_requirement_keeps_moderate_depth_threshold():
    chunks = [
        make_chunk(
            "specific-only",
            (
                "Техническото предложение следва да съдържа:\n"
                "1. описание на специалния ред за достъп до помещенията и "
                "предаване на ключове."
            ),
            page=31,
            section_path="Изисквания към техническото предложение",
        )
    ]

    requirements = extract_requirement_checklist(chunks)
    requirement_items = [item.as_dict() for item in requirements]
    blueprint = build_drafting_blueprint(
        section_title="Други специфични изисквания",
        requirement_items=requirement_items,
    )

    assert len(requirements) == 1
    assert requirements[0].category == SPECIFIC_REQUIREMENTS_CATEGORY
    assert len(blueprint["groups"]) == 1

    sentence = (
        "The proposal describes the access procedure, responsible contact, "
        "handover record, verification step, communication channel, timing, "
        "and corrective action when the room cannot be accessed. "
    )
    result = assess_generation_depth(
        sentence * 16,
        _coverage_for(requirement_items),
        drafting_blueprint=blueprint,
    )

    assert result["status"] == "ok"
    assert result["blueprint_group_count"] == 1
    assert result["min_words"] <= 300


def test_noisy_pdf_rows_do_not_inflate_common_scenario_blueprint():
    chunks = [
        make_chunk(
            "catch-all-noise",
            (
                "Техническото предложение следва да съдържа декларация, че "
                "участникът приема и ще спазва всички изисквания и условия, "
                "посочени в документацията за обществената поръчка."
            ),
            page=8,
            section_path="Методика / Техническо предложение",
        ),
        make_chunk(
            "pdf-table",
            (
                "Минималното съдържание на техническото предложение включва:\n"
                "№ Показател Максимален брой точки\n"
                "1 Организация на изпълнение 20\n"
                "2 Линеен график 10\n"
                "3 Мерки за качество 15\n"
                "Общо 45 точки"
            ),
            page=9,
            section_path="Методика / Техническо предложение",
        ),
    ]

    requirements = extract_requirement_checklist(chunks)
    requirement_items = [item.as_dict() for item in requirements]
    blueprint = build_drafting_blueprint(
        section_title="Работна програма за изпълнение",
        requirement_items=requirement_items,
    )

    assert len(requirements) == 3
    assert all("всички изисквания" not in item.text for item in requirements)
    assert all("Показател" not in item.text for item in requirements)
    assert all("Общо" not in item.text for item in requirements)
    assert {item.category for item in requirements} == {
        "organization",
        "schedule",
        "quality",
    }
    assert {group["category"] for group in blueprint["groups"]} == {
        "organization",
        "schedule",
        "quality",
    }

    result = assess_generation_depth(
        (
            "Generic work programme with basic organization, schedule and "
            "quality controls. "
        )
        * 30,
        _coverage_for(requirement_items),
        drafting_blueprint=blueprint,
    )

    assert result["blueprint_group_count"] == 3
    assert result["status"] == "needs_review"


def test_common_single_category_with_many_topics_still_requires_developed_depth():
    requirement_items = [
        {
            "id": "req-dust",
            "text": "Describe dust suppression measures during execution.",
            "importance": "mandatory",
            "category": "environment",
            "category_label": "Environmental protection",
            "topic": "dust",
        },
        {
            "id": "req-waste",
            "text": "Describe waste segregation, storage, transport, and handover.",
            "importance": "mandatory",
            "category": "environment",
            "category_label": "Environmental protection",
            "topic": "waste",
        },
        {
            "id": "req-soil",
            "text": "Describe soil protection and clean-up controls.",
            "importance": "mandatory",
            "category": "environment",
            "category_label": "Environmental protection",
            "topic": "soil",
        },
        {
            "id": "req-water",
            "text": "Describe water and pollution prevention controls.",
            "importance": "mandatory",
            "category": "environment",
            "category_label": "Environmental protection",
            "topic": "water",
        },
    ]
    blueprint = build_drafting_blueprint(
        section_title="Environmental protection",
        requirement_items=requirement_items,
    )
    shallow_result = assess_generation_depth(
        (
            "The proposal includes environmental protection with responsible "
            "roles, monitoring, records, and corrective actions. "
        )
        * 25,
        _coverage_for(requirement_items),
        drafting_blueprint=blueprint,
    )

    assert len(blueprint["groups"]) == 1
    assert blueprint["groups"][0]["topics"] == ["dust", "waste", "soil", "water"]
    assert shallow_result["blueprint_group_count"] == 1
    assert shallow_result["blueprint_topic_count"] == 4
    assert shallow_result["status"] == "needs_review"
    assert shallow_result["min_words"] >= 800


def test_common_readiness_report_guides_mixed_blocker_remediation():
    chunks = [
        make_chunk(
            "mixed-readiness-requirements",
            (
                "Техническото предложение следва да съдържа:\n"
                "1. организация на изпълнението с екип, отговорности и ресурси;\n"
                "2. линеен график с етапи, последователност и срокове;\n"
                "3. мерки за качество, контрол и приемане на работите;\n"
                "4. комуникация с възложителя, надзора и компетентните институции;\n"
                "5. управление на риска при непредвидени обстоятелства."
            ),
            page=19,
            section_path="Изисквания към техническото предложение",
        )
    ]

    requirements = extract_requirement_checklist(chunks)
    requirement_items = [item.as_dict() for item in requirements]
    blueprint = build_drafting_blueprint(
        section_title="Работна програма за изпълнение",
        requirement_items=requirement_items,
    )
    quality_result = assess_generation_depth(
        (
            "Short work programme with basic organization, schedule, quality, "
            "communication and risk notes. "
        )
        * 20,
        _coverage_for(requirement_items),
        drafting_blueprint=blueprint,
    )

    assert len(requirements) == 5
    assert quality_result["status"] == "needs_review"
    assert quality_result["blueprint_group_count"] == 5

    missing_item = requirement_items[0]
    report = render_export_readiness_report(
        {
            "project_id": "common-mixed-readiness",
            "ready": False,
            "status": "blocked",
            "selected_generation_count": 5,
            "selected_section_count": 4,
            "blocker_count": 4,
            "message": "Pre-export check failed.",
            "blockers": [
                {"code": "duplicate_selected", "count": 1, "message": "Duplicates"},
                {"code": "stale_evidence", "count": 1, "message": "Stale"},
                {"code": "missing_requirements", "count": 1, "message": "Missing"},
                {"code": "shallow_sections", "count": 1, "message": "Shallow"},
            ],
            "duplicate_selected_sections": [
                {
                    "section_uid": "sec-organization",
                    "section_title": "Организация на изпълнението",
                    "selected_count": 2,
                    "generation_ids": ["gen-old", "gen-new"],
                }
            ],
            "stale_section_details": [
                {
                    "section_uid": "sec-schedule",
                    "section_title": "Линеен график и организация във времето",
                }
            ],
            "missing_requirement_sections": [
                {
                    "section_uid": "sec-quality",
                    "section_title": "Мерки за осигуряване на качеството",
                    "missing_count": 1,
                    "missing_requirement_ids": [missing_item["id"]],
                    "missing_items": [
                        {"id": missing_item["id"], "text": missing_item["text"]}
                    ],
                }
            ],
            "quality_sections": [
                {
                    "section_uid": "sec-work-program",
                    "section_title": "Работна програма за изпълнение",
                    **quality_result,
                }
            ],
        }
    )

    action_lines = [
        line
        for line in report.splitlines()
        if line.startswith(("1. ", "2. ", "3. ", "4. "))
    ]
    assert "Остави най-новите" in action_lines[0]
    assert "stale секции" in action_lines[1]
    assert "непокрити checklist изисквания" in action_lines[2]
    assert "плитките секции" in action_lines[3]
    assert "Организация на изпълнението (`sec-organization`)" in report
    assert "Работна програма за изпълнение (`sec-work-program`)" in report


def test_common_requirement_coverage_requires_developed_operational_detail():
    requirement_items = [
        {
            "id": "req-environment-controls",
            "text": (
                "Describe dust control, waste segregation, soil protection, "
                "responsible role, monitoring records, and corrective actions."
            ),
            "importance": "scored",
            "category": "environment",
            "category_label": "Environmental protection",
        }
    ]

    superficial = assess_requirement_coverage(
        "The work programme includes environmental protection and dust control.",
        requirement_items,
    )
    developed = assess_requirement_coverage(
        (
            "The work programme describes dust control, waste segregation, "
            "soil protection, the responsible role, monitoring records, and "
            "corrective actions during execution."
        ),
        requirement_items,
    )

    assert superficial["missing_ids"] == ["req-environment-controls"]
    assert developed["covered_ids"] == ["req-environment-controls"]
