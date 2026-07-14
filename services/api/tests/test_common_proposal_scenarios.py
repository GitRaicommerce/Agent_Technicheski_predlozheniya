from __future__ import annotations

from types import SimpleNamespace

from app.agents.drafting_blueprint import (
    build_drafting_blueprint,
    format_drafting_blueprint_for_prompt,
)
from app.agents.drafting import _format_section_drafting_guidance
from app.agents.generation_jobs import (
    _merge_section_drafting_guidance,
    _missing_requirement_target_guidance,
)
from app.agents.proposal_quality import (
    assess_generation_depth,
    build_generation_depth_target,
)
from app.agents.requirements import (
    RequirementItem,
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
from app.routers.export import _missing_requirement_coverage


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


def _requirement_item(
    requirement_id: str,
    text: str,
    *,
    category: str,
    category_label: str,
    topic: str,
    suggested_section: str,
) -> RequirementItem:
    return RequirementItem(
        id=requirement_id,
        text=text,
        category=category,
        category_label=category_label,
        topic=topic,
        importance="mandatory",
        suggested_section=suggested_section,
        coverage_question=f"Is {topic} covered?",
        source_chunk_id=f"chunk-{requirement_id}",
        source_page=1,
        source_section_path="Technical proposal requirements",
        source_file="tender.pdf",
        source_excerpt=text,
        evidence_cues=[],
    )


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
    assert shallow_result["blueprint_topic_count"] == 5
    assert shallow_result["min_words"] >= 1300
    assert shallow_result["suggested_words_per_structure"] >= 250

    developed_sentence = (
        "Предложението описва управление на риска с конкретни действия, "
        "мерки за околна среда с ограничаване на праха и отпад, "
        "контрол на качество с протоколи за приемане, комуникация с "
        "възложителя, строителния надзор и компетентните институции, "
        "както и специален ред за достъп до помещенията и предаване на ключове. "
        "За всяка тема са посочени отговорни роли, срок, доказателства, "
        "мониторинг, ескалация, коригиращи действия и документиране. "
    )
    developed_result = assess_generation_depth(
        (
            "За управление на риска са описани конкретни действия, отговорна роля, "
            "контролен запис, мониторинг, ескалация, коригиращи действия и доказателства. "
            "Минималното съдържание включва мерки за околна среда, ограничаване на праха, "
            "управление на отпад и отпадъци, отговорна роля, контролен запис и приемателно доказателство. "
            "Контролът на качество включва входяща проверка, текущ контрол, окончателно приемане, "
            "протоколи, отговорен изпълнител, коригиращи действия и документиране. "
            "Организацията на комуникация с възложителя, строителния надзор и компетентните "
            "институции определя канал, график, запис, ескалация и отговорна роля. "
            "Минималното съдържание включва специален ред за достъп до помещенията, предаване "
            "на ключове, контролен запис, отговорно лице и доказателство за приемане. "
        )
        * 22,
        _coverage_for(requirement_items),
        drafting_blueprint=blueprint,
    )
    assert developed_result["status"] == "ok", developed_result["structure_coverage"]


def test_common_structure_plan_preserves_subsections_and_checklist_topics():
    construction_uid = "construction-organization"
    explicit_sections = [
        {
            "uid": "concept",
            "title": "Concept and approach",
            "required": True,
            "requirements": ["Describe the approach."],
            "source_refs": ["chunk-concept"],
            "subsections": [],
        },
        {
            "uid": "design",
            "title": "Design development",
            "required": True,
            "requirements": ["Describe design activities."],
            "source_refs": ["chunk-design"],
            "subsections": [],
        },
        {
            "uid": construction_uid,
            "title": "Construction organization",
            "required": True,
            "requirements": ["Describe construction organization."],
            "source_refs": ["chunk-construction"],
            "subsections": [
                {
                    "uid": "stakeholders",
                    "title": "Stakeholders and participants",
                    "required": True,
                    "requirements": ["Identify stakeholders."],
                    "source_refs": ["chunk-stakeholders"],
                    "subsections": [],
                },
                {
                    "uid": "internal-communication",
                    "title": "Internal communication, coordination and control",
                    "required": True,
                    "requirements": ["Describe internal communication."],
                    "source_refs": ["chunk-communication"],
                    "subsections": [],
                },
            ],
        },
        {
            "uid": "quality",
            "title": "Quality control",
            "required": True,
            "requirements": ["Describe quality controls."],
            "source_refs": ["chunk-quality"],
            "subsections": [],
        },
        {
            "uid": "risk",
            "title": "Risk management",
            "required": True,
            "requirements": ["Describe risk management."],
            "source_refs": ["chunk-risk"],
            "subsections": [],
        },
    ]
    requirements = [
        _requirement_item(
            "req-stakeholders",
            "Describe stakeholders, responsibilities and interfaces.",
            category="organization",
            category_label="Construction organization",
            topic="stakeholder responsibilities",
            suggested_section="Construction organization",
        ),
        _requirement_item(
            "req-communication",
            "Describe communication channel, coordination control and escalation.",
            category="communication",
            category_label="Communication",
            topic="communication escalation",
            suggested_section="Construction organization",
        ),
    ]

    outline = _build_deterministic_outline(
        explicit_numbered_sections=explicit_sections,
        domain_outline_sections=[],
        mandatory_sections=[],
        requirement_checklist=requirements,
    )

    construction = next(
        section
        for section in outline["sections"]
        if section["uid"] == construction_uid
    )
    guidance = construction["drafting_guidance"]

    assert construction["requirement_ids"] == [
        "req-stakeholders",
        "req-communication",
    ]
    assert guidance["requirement_count"] == 2
    assert guidance["required_subtopics"][:2] == [
        "Stakeholders and participants",
        "Internal communication, coordination and control",
    ]
    assert "stakeholder responsibilities" in guidance["required_subtopics"]
    assert "communication escalation" in guidance["required_subtopics"]
    assert "Preserve the subsection order" in " ".join(guidance["instructions"])


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


def test_common_topic_rich_section_must_distribute_depth_across_topics():
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
    dust_only_sentence = (
        "The environmental section develops dust suppression with responsible "
        "roles, monitoring records, corrective actions, control points, "
        "acceptance evidence, reporting sequence, and site coordination. "
    )

    result = assess_generation_depth(
        dust_only_sentence * 90,
        _coverage_for(requirement_items),
        drafting_blueprint=blueprint,
    )

    assert result["word_count"] >= result["min_words"]
    assert result["structure_coverage"]["anchor_count"] == 4
    assert result["structure_coverage"]["covered_count"] == 1
    assert "uneven_blueprint_distribution" in {
        issue["code"] for issue in result["issues"]
    }


def test_common_blueprint_creates_response_plan_for_each_requirement():
    requirement_items = [
        {
            "id": "req-organization",
            "text": "Describe team roles, responsibilities, and coordination.",
            "importance": "mandatory",
            "category": "organization",
            "category_label": "Organization",
            "topic": "team roles",
            "source_ref": "chunk-organization",
        },
        {
            "id": "req-quality",
            "text": "Describe inspections, protocols, and acceptance evidence.",
            "importance": "mandatory",
            "category": "quality",
            "category_label": "Quality control",
            "topic": "acceptance evidence",
            "source_ref": "chunk-quality",
        },
        {
            "id": "req-risk",
            "text": "Describe risk trigger, owner, prevention, and escalation.",
            "importance": "mandatory",
            "category": "risk",
            "category_label": "Risk management",
            "topic": "risk response",
            "source_ref": "chunk-risk",
        },
    ]
    blueprint = build_drafting_blueprint(
        section_title="Work programme",
        requirement_items=requirement_items,
    )

    response_plans = [
        requirement["response_plan"]
        for group in blueprint["groups"]
        for requirement in group["requirements"]
    ]

    assert [plan["requirement_id"] for plan in response_plans] == [
        "req-organization",
        "req-quality",
        "req-risk",
    ]
    assert all("responsible role" in plan["expected_response"] for plan in response_plans)
    assert {plan["source_ref"] for plan in response_plans} == {
        "chunk-organization",
        "chunk-quality",
        "chunk-risk",
    }


def test_common_blueprint_keeps_many_specific_requirements_visible():
    requirement_items = [
        {
            "id": f"req-specific-{index}",
            "text": (
                f"Describe tender-specific operational condition {index} "
                "with responsible role, evidence record, and acceptance step."
            ),
            "importance": "mandatory",
            "category": SPECIFIC_REQUIREMENTS_CATEGORY,
            "category_label": "Specific tender requirements",
            "topic": f"specific condition {index}",
        }
        for index in range(1, 15)
    ]

    blueprint = build_drafting_blueprint(
        section_title="Specific tender requirements",
        requirement_items=requirement_items,
        max_items_per_group=10,
    )
    prompt = format_drafting_blueprint_for_prompt(blueprint)

    group = blueprint["groups"][0]
    assert len(group["requirements"]) == 10
    assert [item["id"] for item in group["additional_requirements"]] == [
        "req-specific-11",
        "req-specific-12",
        "req-specific-13",
        "req-specific-14",
    ]
    assert "additional requirements to cover explicitly" in prompt
    assert "req-specific-14 [specific condition 14]" in prompt
    assert "Do not hide unusual or one-off requirements" in prompt
    target = build_generation_depth_target(
        requirement_coverage={"total": len(requirement_items)},
        drafting_blueprint=blueprint,
    )
    assert target["blueprint_requirement_id_count"] == 14
    assert target["min_words"] >= 1400


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
    assert quality_result["min_words"] >= 1300
    assert quality_result["suggested_words_per_structure"] >= 250

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


def test_common_missing_requirement_remediation_flows_into_targeted_drafting_guidance():
    requirement_items = [
        {
            "id": "req-quality-acceptance",
            "text": (
                "Describe material conformity, laboratory testing, calibration "
                "frequency, sampling scope, defect classification, and warranty "
                "traceability."
            ),
            "importance": "mandatory",
            "category": "quality",
            "category_label": "Quality control",
            "topic": "quality acceptance controls",
        }
    ]
    shallow_text = (
        "The proposal describes material conformity, laboratory testing, "
        "calibration frequency, sampling scope, defect classification, and "
        "warranty traceability in general terms."
    )
    coverage = assess_requirement_coverage(shallow_text, requirement_items)

    readiness_section = _missing_requirement_coverage(
        SimpleNamespace(
            id="gen-quality",
            section_uid="sec-quality",
            flags_json={"requirement_coverage": coverage},
        )
    )
    assert readiness_section is not None
    assert readiness_section["missing_requirement_ids"] == [
        "req-quality-acceptance"
    ]
    missing_item = readiness_section["missing_items"][0]
    assert missing_item["reason"] == "needs operational evidence"
    assert "add operational evidence" in missing_item["remediation_guidance"]

    target_guidance = _missing_requirement_target_guidance([readiness_section])
    section_guidance = _merge_section_drafting_guidance(
        {
            "requirement_count": 1,
            "required_subtopics": ["quality acceptance controls"],
            "instructions": ["Develop the quality controls as a separate point."],
        },
        target_guidance["sec-quality"],
    )
    guidance_prompt = _format_section_drafting_guidance(section_guidance)

    assert "SECTION STRUCTURE PLAN" in guidance_prompt
    assert "Develop the quality controls as a separate point." in guidance_prompt
    assert "Regenerate or edit the selected section" in guidance_prompt
    assert "Missing requirements to repair" in guidance_prompt
    assert "id=req-quality-acceptance [needs operational evidence]" in guidance_prompt
    assert "repair:" in guidance_prompt

    repaired_text = (
        "For material conformity, laboratory testing, calibration frequency, "
        "sampling scope, defect classification, and warranty traceability, the "
        "contractor assigns a responsible role, keeps inspection records, "
        "defines escalation, and executes corrective actions with documented "
        "acceptance evidence."
    )
    repaired_coverage = assess_requirement_coverage(repaired_text, requirement_items)
    assert repaired_coverage["missing_ids"] == []
    assert repaired_coverage["covered_ids"] == ["req-quality-acceptance"]


def test_common_similar_operational_requirements_need_distinctive_remediation():
    requirement_items = [
        {
            "id": "req-input-control",
            "text": (
                "Describe input quality control for delivered materials, "
                "inspection protocol, responsible role, and rejection record."
            ),
            "importance": "mandatory",
            "category": "quality",
            "category_label": "Quality control",
            "topic": "input material control",
        },
        {
            "id": "req-final-acceptance",
            "text": (
                "Describe final acceptance control for completed works, "
                "handover protocol, responsible role, and corrective record."
            ),
            "importance": "mandatory",
            "category": "quality",
            "category_label": "Quality control",
            "topic": "final acceptance handover",
        },
    ]
    input_only_text = (
        "For delivered materials, the contractor performs input quality control "
        "through an inspection protocol, assigns a responsible role, keeps a "
        "rejection record, and applies corrective actions."
    )
    coverage = assess_requirement_coverage(input_only_text, requirement_items)

    readiness_section = _missing_requirement_coverage(
        SimpleNamespace(
            id="gen-quality",
            section_uid="sec-quality",
            flags_json={"requirement_coverage": coverage},
        )
    )

    assert coverage["covered_ids"] == ["req-input-control"]
    assert coverage["missing_ids"] == ["req-final-acceptance"]
    assert readiness_section is not None
    missing_item = readiness_section["missing_items"][0]
    assert missing_item["id"] == "req-final-acceptance"
    assert missing_item["reason"] == "missing distinctive requirement detail"
    assert "include distinctive requirement details" in missing_item[
        "remediation_guidance"
    ]

    target_guidance = _missing_requirement_target_guidance([readiness_section])
    target_missing_item = target_guidance["sec-quality"][
        "missing_requirement_items"
    ][0]
    assert target_missing_item["distinctive_terms"]
    assert target_missing_item["distinctive_matches"] == []
    assert target_missing_item["required_distinctive_count"] == 1
    section_guidance = _merge_section_drafting_guidance(
        {
            "requirement_count": 2,
            "required_subtopics": ["input material control", "final acceptance"],
            "instructions": ["Keep each quality-control stage separate."],
        },
        target_guidance["sec-quality"],
    )
    guidance_prompt = _format_section_drafting_guidance(section_guidance)

    assert "id=req-final-acceptance [missing distinctive requirement detail]" in (
        guidance_prompt
    )
    assert "distinctive" in guidance_prompt
    assert "distinctive detail 0/1" in guidance_prompt
    assert "distinctive terms:" in guidance_prompt
    assert "include distinctive requirement details" in guidance_prompt
    assert "final" in guidance_prompt
    assert "handover" in guidance_prompt

    repaired_text = (
        input_only_text
        + " For completed works, the contractor performs final acceptance "
        "control through a handover protocol, assigns a responsible role, "
        "keeps a corrective record, and documents acceptance evidence."
    )
    repaired_coverage = assess_requirement_coverage(repaired_text, requirement_items)
    assert repaired_coverage["covered_ids"] == [
        "req-input-control",
        "req-final-acceptance",
    ]


def test_common_requirement_coverage_rejects_scattered_keyword_coverage():
    requirement_items = [
        {
            "id": "req-communication-workflow",
            "text": (
                "Describe communication channel, meeting cadence, reporting "
                "record, approval interface, escalation path, and responsible role."
            ),
            "importance": "mandatory",
            "category": "communication",
            "category_label": "Communication and coordination",
        }
    ]

    scattered = assess_requirement_coverage(
        (
            "The proposal names the communication channel. "
            "A separate paragraph mentions meeting cadence. "
            "Reporting records are referenced later. "
            "The approval interface is named in another list. "
            "Escalation path appears in the risk chapter. "
            "The responsible role is stated at the end."
        ),
        requirement_items,
    )
    coherent = assess_requirement_coverage(
        (
            "The communication workflow defines the channel, meeting cadence, "
            "reporting record, approval interface, escalation path, and "
            "responsible role for each coordination point."
        ),
        requirement_items,
    )

    assert scattered["missing_ids"] == ["req-communication-workflow"]
    assert scattered["items"][0]["matched_ratio"] >= 0.6
    assert scattered["items"][0]["coherent_matched_ratio"] < 0.6
    assert coherent["covered_ids"] == ["req-communication-workflow"]
