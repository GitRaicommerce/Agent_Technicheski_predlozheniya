from __future__ import annotations

from types import SimpleNamespace

from app.agents.drafting_blueprint import build_drafting_blueprint
from app.agents.proposal_quality import assess_generation_depth
from app.agents.requirements import (
    SPECIFIC_REQUIREMENTS_CATEGORY,
    SUGGESTED_SECTIONS,
    extract_requirement_checklist,
)
from app.agents.tender_struct import (
    _build_deterministic_outline,
    _extract_explicit_numbered_outline,
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
