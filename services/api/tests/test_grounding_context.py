from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.sql.dml import Update

from app.agents.context import build_project_grounding_context
from app.agents.drafting import (
    _format_section_drafting_guidance,
    _quality_repair_feedback,
    run_drafting,
)


def _scalar_result(items):
    result = MagicMock()
    result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=items)))
    return result


def _one_result(item):
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=item)
    return result


def _varied_operational_text(topics: list[str], repeats: int = 8) -> str:
    sentences = []
    for cycle in range(repeats):
        for index, topic in enumerate(topics, start=1):
            sentences.append(
                "For "
                f"{topic}, the proposal defines action package {cycle + 1}-{index} "
                "with a responsible role, control record, monitoring evidence, "
                "acceptance criterion, reporting sequence, escalation point, "
                "corrective action, document owner, timing link, and coordination "
                "interface. "
            )
    return "".join(sentences)


def test_quality_repair_feedback_names_missing_distinctive_requirement_details():
    feedback = _quality_repair_feedback(
        requirement_coverage={
            "items": [
                {
                    "id": "req-final-acceptance",
                    "text": "Describe final acceptance and handover controls.",
                    "status": "missing",
                    "distinctive_terms": ["final", "acceptance", "handover"],
                    "distinctive_matches": [],
                    "required_distinctive_count": 1,
                }
            ]
        },
        depth_assessment={"issues": []},
    )

    assert "distinctive detail: 0/1 required" in feedback
    assert "distinctive terms: final, acceptance, handover" in feedback
    assert "make it distinct from similar checklist items" in feedback


def test_section_drafting_guidance_names_distinctive_requirement_diagnostics():
    guidance = _format_section_drafting_guidance(
        {
            "missing_requirement_items": [
                {
                    "id": "req-final-acceptance",
                    "text": "Describe final acceptance and handover controls.",
                    "reason": "missing distinctive requirement detail",
                    "remediation_guidance": (
                        "include distinctive requirement details such as final, "
                        "acceptance, handover"
                    ),
                    "distinctive_terms": ["final", "acceptance", "handover"],
                    "distinctive_matches": [],
                    "required_distinctive_count": 1,
                }
            ]
        }
    )

    assert "id=req-final-acceptance [missing distinctive requirement detail]" in guidance
    assert "repair: include distinctive requirement details" in guidance
    assert "diagnostics: distinctive detail 0/1" in guidance
    assert "distinctive terms: final, acceptance, handover" in guidance


@pytest.mark.asyncio
async def test_grounding_context_includes_design_parts_from_schedule_and_tender(mock_db):
    project_id = str(uuid.uuid4())
    file_id = str(uuid.uuid4())
    schedule = SimpleNamespace(
        schedule_json={
            "tasks": [
                {
                    "uid": "1",
                    "wbs": "2.1",
                    "name": "Разработване на проектна част Геодезия",
                    "duration_days": 3,
                },
                {
                    "uid": "2",
                    "wbs": "2.2",
                    "name": "Разработване на проектна част Конструктивна",
                    "duration_days": 4,
                },
                {
                    "uid": "3",
                    "wbs": "2.3",
                    "name": "Изготвяне на ПБЗ, ПУСО и сметна документация",
                    "duration_days": 2,
                },
            ]
        },
        status_locked=True,
        version=1,
    )
    tender_chunk = SimpleNamespace(
        id=str(uuid.uuid4()),
        page=12,
        section_path="Техническа спецификация",
        text=(
            "Разработване на инвестиционен проект по части Водоснабдяване, "
            "Геодезия, Конструктивна, ПБЗ, ПУСО и Сметна документация."
        ),
    )

    mock_db.execute = AsyncMock(
        side_effect=[
            _one_result(schedule),
            [SimpleNamespace(id=file_id)],
            _scalar_result([tender_chunk]),
        ]
    )

    context = await build_project_grounding_context(
        project_id=project_id,
        section_title="Разработване на инвестиционен проект",
        section_requirements=[],
        db=mock_db,
    )

    task_names = " ".join(task["name"] for task in context["schedule"]["tasks"])
    tender_text = " ".join(chunk["text"] for chunk in context["tender_chunks"])

    assert "Геодезия" in task_names
    assert "Конструктивна" in task_names
    assert "ПУСО" in task_names
    assert "Сметна документация" in tender_text


@pytest.mark.asyncio
async def test_drafting_prompt_and_saved_generation_include_grounding_context(mock_db):
    project_id = str(uuid.uuid4())
    section_uid = str(uuid.uuid4())
    grounding_context = {
        "tender_chunks": [{"text": "Проектни части: Геодезия и Конструктивна"}],
        "schedule": {"tasks": [{"name": "ПБЗ и ПУСО"}]},
    }

    with patch(
        "app.agents.drafting.llm_gateway.call",
        new=AsyncMock(
            return_value={
                "variant_1": {
                    "text": "Подробен текст за проектните части.",
                    "evidence_map": {},
                },
                "flags": [],
            }
        ),
    ) as llm_call:
        result = await run_drafting(
            project_id=project_id,
            section_uid=section_uid,
            section_title="Разработване на инвестиционен проект",
            section_requirements=[],
            evidence_snippets=[],
            schedule_summary=None,
            lex_citations=[],
            db=mock_db,
            trace_id=str(uuid.uuid4()),
            project_grounding_context=grounding_context,
        )

    prompt = llm_call.await_args.kwargs["user_message"]
    saved_generation = mock_db.add.call_args.args[0]

    assert "PROJECT GROUNDING CONTEXT" in prompt
    assert "DRAFTING BLUEPRINT" in prompt
    assert "Геодезия" in prompt
    assert "ПУСО" in prompt
    assert saved_generation.used_sources_json["grounding_context"] == grounding_context
    assert "drafting_blueprint" in saved_generation.used_sources_json
    assert result["generation_ids"]["variant_1"] == saved_generation.id


@pytest.mark.asyncio
async def test_drafting_unselects_existing_section_generations_before_saving(mock_db):
    project_id = str(uuid.uuid4())
    section_uid = str(uuid.uuid4())

    with patch(
        "app.agents.drafting.llm_gateway.call",
        new=AsyncMock(
            return_value={
                "variant_1": {
                    "text": "Подробен нов текст за секцията.",
                    "evidence_map": {},
                },
                "flags": [],
            }
        ),
    ):
        await run_drafting(
            project_id=project_id,
            section_uid=section_uid,
            section_title="Организация",
            section_requirements=[],
            evidence_snippets=[],
            schedule_summary=None,
            lex_citations=[],
            db=mock_db,
            trace_id=str(uuid.uuid4()),
        )

    statement = mock_db.execute.await_args.args[0]
    saved_generation = mock_db.add.call_args.args[0]

    assert isinstance(statement, Update)
    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "UPDATE generations" in compiled
    assert "selected=false" in compiled.replace(" ", "").lower()
    assert saved_generation.selected is True


@pytest.mark.asyncio
async def test_drafting_prompt_and_saved_generation_include_requirement_coverage(mock_db):
    project_id = str(uuid.uuid4())
    section_uid = str(uuid.uuid4())
    requirement_items = [
        {
            "id": "req-schedule",
            "text": "Следва да се представи подробен линеен график за изпълнение.",
            "importance": "mandatory",
            "category": "schedule",
            "category_label": "График и срокове",
            "coverage_question": "Покрит ли е линейният график?",
        }
    ]

    with patch(
        "app.agents.drafting.llm_gateway.call",
        new=AsyncMock(
            return_value={
                "variant_1": {
                    "text": "Представя се подробен линеен график за изпълнение на дейностите.",
                    "evidence_map": {},
                    "requirement_coverage": [
                        {
                            "id": "req-schedule",
                            "status": "covered",
                            "evidence": "линеен график",
                        }
                    ],
                },
                "flags": [],
            }
        ),
    ) as llm_call:
        result = await run_drafting(
            project_id=project_id,
            section_uid=section_uid,
            section_title="Линеен график",
            section_requirements=["Да се представи линеен график."],
            evidence_snippets=[],
            schedule_summary=None,
            lex_citations=[],
            db=mock_db,
            trace_id=str(uuid.uuid4()),
            project_grounding_context=None,
            section_requirement_items=requirement_items,
            section_drafting_guidance={
                "requirement_count": 1,
                "required_subtopics": ["Detailed linear schedule"],
                "source_refs": ["chunk-req-schedule"],
                "instructions": [
                    "Use the required subtopics as explicit subheadings or developed paragraphs."
                ],
                "missing_requirement_items": [
                    {
                        "id": "req-schedule",
                        "text": "Describe the detailed schedule controls.",
                        "reason": "needs operational evidence",
                        "remediation_guidance": (
                            "Add roles, control records, and acceptance evidence."
                        ),
                    }
                ],
            },
        )

    prompt = llm_call.await_args.kwargs["user_message"]
    saved_generation = mock_db.add.call_args.args[0]

    assert "SECTION REQUIREMENT CHECKLIST" in prompt
    assert "SECTION STRUCTURE PLAN" in prompt
    assert "Detailed linear schedule" in prompt
    assert "Missing requirements to repair" in prompt
    assert "id=req-schedule [needs operational evidence]" in prompt
    assert "repair: Add roles, control records, and acceptance evidence." in prompt
    assert "DRAFTING BLUEPRINT" in prompt
    assert "SECTION DEPTH TARGET" in prompt
    assert "response plan:" in prompt
    assert "id=req-schedule" in prompt
    assert saved_generation.flags_json["requirement_coverage"]["missing_ids"] == []
    assert saved_generation.flags_json["requirement_coverage"]["covered_ids"] == [
        "req-schedule"
    ]
    assert (
        saved_generation.used_sources_json["section_requirement_items"][0]["id"]
        == "req-schedule"
    )
    assert (
        saved_generation.used_sources_json["section_drafting_guidance"][
            "required_subtopics"
        ][0]
        == "Detailed linear schedule"
    )
    assert (
        saved_generation.used_sources_json["drafting_blueprint"]["groups"][0][
            "category"
        ]
        == "schedule"
    )
    assert (
        saved_generation.used_sources_json["drafting_blueprint"]["groups"][0][
            "requirements"
        ][0]["response_plan"]["requirement_id"]
        == "req-schedule"
    )
    assert "responsible role" in saved_generation.used_sources_json[
        "drafting_blueprint"
    ]["groups"][0]["requirements"][0]["response_plan"]["expected_response"]
    assert result["generation_ids"]["variant_1"] == saved_generation.id


@pytest.mark.asyncio
async def test_drafting_repairs_short_or_missing_requirement_coverage_before_saving(
    mock_db,
):
    project_id = str(uuid.uuid4())
    section_uid = str(uuid.uuid4())
    requirement_items = [
        {
            "id": "req-communication-workflow",
            "text": (
                "Describe communication channel, meeting cadence, reporting record, "
                "approval interface, escalation path, and responsible role."
            ),
            "importance": "mandatory",
            "category": "communication",
            "category_label": "Communication and coordination",
            "coverage_question": "Is the full communication workflow covered?",
        }
    ]
    repaired_sentence = (
        "The communication workflow defines the communication channel, meeting "
        "cadence, reporting record, approval interface, escalation path, and "
        "responsible role, with a control record, monitoring signal, acceptance "
        "evidence, and corrective action for every coordination point. "
    )

    with patch(
        "app.agents.drafting.llm_gateway.call",
        new=AsyncMock(
            side_effect=[
                {
                    "variant_1": {
                        "text": "The proposal mentions communication.",
                        "evidence_map": {},
                    },
                    "flags": [],
                },
                {
                    "variant_1": {
                        "text": repaired_sentence * 16,
                        "evidence_map": {},
                    },
                    "flags": [],
                },
            ]
        ),
    ) as llm_call:
        await run_drafting(
            project_id=project_id,
            section_uid=section_uid,
            section_title="Communication workflow",
            section_requirements=[],
            evidence_snippets=[],
            schedule_summary=None,
            lex_citations=[],
            db=mock_db,
            trace_id=str(uuid.uuid4()),
            section_requirement_items=requirement_items,
        )

    saved_generation = mock_db.add.call_args.args[0]
    repair_prompt = llm_call.await_args_list[1].kwargs["user_message"]

    assert llm_call.await_count == 2
    assert "QUALITY REPAIR REQUIRED" in repair_prompt
    assert "matched terms:" in repair_prompt
    assert "coherent terms:" in repair_prompt
    assert "operational evidence:" in repair_prompt
    assert "Requirement repair writing plan:" in repair_prompt
    assert "For id=req-communication-workflow" in repair_prompt
    assert "keep those concepts together in one coherent passage" in repair_prompt
    assert "make it operational with responsible roles" in repair_prompt
    assert saved_generation.text == repaired_sentence * 16
    assert saved_generation.flags_json["quality_repair_attempted"] is True
    assert saved_generation.flags_json["quality_repair_attempt_count"] == 1
    assert saved_generation.flags_json["requirement_coverage"]["missing_ids"] == []
    assert saved_generation.flags_json["generation_depth"]["status"] == "ok"


@pytest.mark.asyncio
async def test_drafting_repair_feedback_names_missing_blueprint_topics(mock_db):
    project_id = str(uuid.uuid4())
    section_uid = str(uuid.uuid4())
    requirement_items = [
        {
            "id": requirement_id,
            "text": text,
            "importance": "mandatory",
            "category": "environment",
            "category_label": "Environmental protection",
            "topic": topic,
        }
        for requirement_id, topic, text in [
            ("req-dust", "dust suppression", "Describe dust suppression measures during execution."),
            ("req-waste", "waste segregation", "Describe waste segregation, storage, transport, and handover."),
            ("req-soil", "soil protection", "Describe soil protection and clean-up controls."),
            ("req-water", "water pollution prevention", "Describe water and pollution prevention controls."),
        ]
    ]
    dust_only_sentence = (
        "The environmental section develops dust suppression with responsible "
        "roles, monitoring records, corrective actions, control points, "
        "acceptance evidence, reporting sequence, and site coordination. "
    )
    balanced_sentence = (
        "The environmental section covers dust suppression, waste segregation, "
        "soil protection, and water pollution prevention with responsible "
        "roles, monitoring records, corrective actions, control points, "
        "acceptance evidence, reporting sequence, and site coordination. "
    )
    balanced_text = _varied_operational_text(
        [
            "dust suppression measures during execution",
            "waste segregation storage transport handover",
            "soil protection clean up controls",
            "water pollution prevention controls",
        ],
        repeats=25,
    )

    with patch(
        "app.agents.drafting.llm_gateway.call",
        new=AsyncMock(
            side_effect=[
                {
                    "variant_1": {
                        "text": dust_only_sentence * 90,
                        "evidence_map": {},
                    },
                    "flags": [],
                },
                {
                    "variant_1": {
                        "text": balanced_text,
                        "evidence_map": {},
                    },
                    "flags": [],
                },
            ]
        ),
    ) as llm_call:
        await run_drafting(
            project_id=project_id,
            section_uid=section_uid,
            section_title="Environmental protection",
            section_requirements=[],
            evidence_snippets=[],
            schedule_summary=None,
            lex_citations=[],
            db=mock_db,
            trace_id=str(uuid.uuid4()),
            section_requirement_items=requirement_items,
        )

    repair_prompt = llm_call.await_args_list[1].kwargs["user_message"]
    saved_generation = mock_db.add.call_args.args[0]

    assert llm_call.await_count == 2
    assert "QUALITY REPAIR REQUIRED" in repair_prompt
    assert "missing blueprint groups/topics" in repair_prompt
    assert "waste segregation (0/2 anchor terms matched)" in repair_prompt
    assert "soil protection (0/2 anchor terms matched)" in repair_prompt
    assert "water pollution prevention (0/2 anchor terms matched)" in repair_prompt
    assert saved_generation.text == balanced_text
    assert saved_generation.flags_json["quality_repair_attempted"] is True
    assert saved_generation.flags_json["quality_repair_attempt_count"] == 1
    assert saved_generation.flags_json["generation_depth"]["status"] == "ok"


@pytest.mark.asyncio
async def test_drafting_runs_second_repair_when_first_repair_still_fails_depth(
    mock_db,
):
    project_id = str(uuid.uuid4())
    section_uid = str(uuid.uuid4())
    requirement_items = [
        {
            "id": f"req-{topic}",
            "text": text,
            "importance": "mandatory",
            "category": "environment",
            "category_label": "Environmental protection",
            "topic": topic,
        }
        for topic, text in [
            ("dust", "Describe dust suppression measures during execution."),
            ("waste", "Describe waste segregation, storage, transport, and handover."),
            ("soil", "Describe soil protection and clean-up controls."),
            ("water", "Describe water and pollution prevention controls."),
        ]
    ]
    first_text = "The proposal mentions environmental protection."
    repeated_repair_sentence = (
        "The environmental section covers dust suppression, waste segregation, "
        "soil protection, and water pollution prevention with responsible roles, "
        "monitoring records, corrective actions, control points, acceptance "
        "evidence, reporting sequence, and site coordination. "
    )
    final_text = _varied_operational_text(
        [
            "dust suppression measures during execution",
            "waste segregation storage transport handover",
            "soil protection clean up controls",
            "water pollution prevention controls",
        ],
        repeats=25,
    )

    with patch(
        "app.agents.drafting.llm_gateway.call",
        new=AsyncMock(
            side_effect=[
                {
                    "variant_1": {
                        "text": first_text,
                        "evidence_map": {},
                    },
                    "flags": [],
                },
                {
                    "variant_1": {
                        "text": repeated_repair_sentence * 90,
                        "evidence_map": {},
                    },
                    "flags": [],
                },
                {
                    "variant_1": {
                        "text": final_text,
                        "evidence_map": {},
                    },
                    "flags": [],
                },
            ]
        ),
    ) as llm_call:
        await run_drafting(
            project_id=project_id,
            section_uid=section_uid,
            section_title="Environmental protection",
            section_requirements=[],
            evidence_snippets=[],
            schedule_summary=None,
            lex_citations=[],
            db=mock_db,
            trace_id=str(uuid.uuid4()),
            section_requirement_items=requirement_items,
        )

    second_repair_prompt = llm_call.await_args_list[2].kwargs["user_message"]
    saved_generation = mock_db.add.call_args.args[0]

    assert llm_call.await_count == 3
    assert "QUALITY REPAIR ATTEMPT 2/2" in second_repair_prompt
    assert "repetitive_content" in second_repair_prompt
    assert saved_generation.text == final_text
    assert saved_generation.flags_json["quality_repair_attempted"] is True
    assert saved_generation.flags_json["quality_repair_attempt_count"] == 2
    assert saved_generation.flags_json["quality_repair_max_attempts"] == 2
    assert saved_generation.flags_json["generation_depth"]["status"] == "ok"


@pytest.mark.asyncio
async def test_drafting_saves_initial_generation_when_quality_repair_fails(mock_db):
    project_id = str(uuid.uuid4())
    section_uid = str(uuid.uuid4())
    initial_text = "The proposal mentions communication."
    requirement_items = [
        {
            "id": "req-communication-workflow",
            "text": (
                "Describe communication channel, meeting cadence, reporting record, "
                "approval interface, escalation path, and responsible role."
            ),
            "importance": "mandatory",
            "category": "communication",
            "category_label": "Communication and coordination",
        }
    ]

    with patch(
        "app.agents.drafting.llm_gateway.call",
        new=AsyncMock(
            side_effect=[
                {
                    "variant_1": {
                        "text": initial_text,
                        "evidence_map": {},
                    },
                    "flags": [],
                },
                RuntimeError("temporary LLM failure"),
            ]
        ),
    ) as llm_call:
        await run_drafting(
            project_id=project_id,
            section_uid=section_uid,
            section_title="Communication workflow",
            section_requirements=[],
            evidence_snippets=[],
            schedule_summary=None,
            lex_citations=[],
            db=mock_db,
            trace_id=str(uuid.uuid4()),
            section_requirement_items=requirement_items,
        )

    saved_generation = mock_db.add.call_args.args[0]

    assert llm_call.await_count == 2
    assert saved_generation.text == initial_text
    assert saved_generation.flags_json["quality_repair_attempted"] is True
    assert saved_generation.flags_json["quality_repair_attempt_count"] == 1
    assert saved_generation.flags_json["quality_repair_error"] == "temporary LLM failure"
    assert saved_generation.flags_json["generation_depth"]["status"] == "needs_review"
