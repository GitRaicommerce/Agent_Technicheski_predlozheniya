from __future__ import annotations

from app.agents.drafting_blueprint import (
    build_drafting_blueprint,
    format_drafting_blueprint_for_prompt,
)


def test_drafting_blueprint_groups_requirements_by_category():
    blueprint = build_drafting_blueprint(
        section_title="Work programme",
        requirement_items=[
            {
                "id": "req-risk",
                "text": "Describe risk prevention and response measures.",
                "importance": "mandatory",
                "category": "risk",
                "category_label": "Risk management",
                "topic": "risk",
            },
            {
                "id": "req-quality",
                "text": "Describe input and final quality controls.",
                "importance": "scored",
                "category": "quality",
                "category_label": "Quality control",
                "topic": "quality",
            },
            {
                "id": "req-specific",
                "text": "Describe the tender-specific handover meeting.",
                "importance": "mandatory",
                "category": "specific",
                "category_label": "Specific requirements",
                "topic": "handover",
            },
        ],
    )

    groups = blueprint["groups"]
    assert [group["category"] for group in groups] == [
        "risk",
        "quality",
        "specific",
    ]
    assert groups[0]["requirements"][0]["id"] == "req-risk"
    assert groups[0]["topic_details"] == [
        {"topic": "risk", "requirement_ids": ["req-risk"]}
    ]
    assert any("trigger" in item for item in groups[0]["guidance"])
    assert any("records" in item for item in groups[1]["guidance"])
    assert any("tender-specific" in item for item in groups[2]["guidance"])
    assert (
        groups[0]["requirements"][0]["response_plan"]["requirement_id"]
        == "req-risk"
    )
    assert "responsible role" in groups[0]["requirements"][0]["response_plan"][
        "expected_response"
    ]


def test_drafting_blueprint_prompt_includes_context_cues_and_ids():
    blueprint = build_drafting_blueprint(
        section_title="Schedule",
        requirement_items=[
            {
                "id": "req-schedule",
                "text": "Describe phases, dependencies, and acceptance points.",
                "importance": "mandatory",
                "category": "schedule",
                "category_label": "Schedule",
                "topic": "phases",
            }
        ],
        project_grounding_context={
            "schedule": {"tasks": [{"name": "Mobilization and design review"}]},
            "tender_chunks": [{"text": "The tender requires phased execution."}],
        },
    )

    prompt = format_drafting_blueprint_for_prompt(blueprint)

    assert "DRAFTING BLUEPRINT" in prompt
    assert "Suggested subheading: Schedule" in prompt
    assert "req-schedule" in prompt
    assert "required topic coverage" in prompt
    assert "phases (req-schedule)" in prompt
    assert "response plan:" in prompt
    assert "responsible role" in prompt
    assert "category focus: schedule" in prompt
    assert "Mobilization and design review" in prompt
    assert "phases, dependencies, and acceptance points" in prompt


def test_drafting_blueprint_keeps_distinct_topics_inside_one_category():
    blueprint = build_drafting_blueprint(
        section_title="Environmental measures",
        requirement_items=[
            {
                "id": "req-dust",
                "text": "Describe dust limitation measures.",
                "importance": "mandatory",
                "category": "environment",
                "category_label": "Environment",
                "topic": "dust",
            },
            {
                "id": "req-waste",
                "text": "Describe construction waste management.",
                "importance": "mandatory",
                "category": "environment",
                "category_label": "Environment",
                "topic": "waste",
            },
            {
                "id": "req-soil",
                "text": "Describe soil protection and clean-up.",
                "importance": "mandatory",
                "category": "environment",
                "category_label": "Environment",
                "topic": "soil",
            },
        ],
    )

    groups = blueprint["groups"]
    assert len(groups) == 1
    assert groups[0]["category"] == "environment"
    assert groups[0]["topics"] == ["dust", "waste", "soil"]
    assert groups[0]["topic_details"] == [
        {"topic": "dust", "requirement_ids": ["req-dust"]},
        {"topic": "waste", "requirement_ids": ["req-waste"]},
        {"topic": "soil", "requirement_ids": ["req-soil"]},
    ]


def test_drafting_blueprint_keeps_overflow_requirements_visible_in_prompt():
    requirement_items = [
        {
            "id": f"req-quality-{index}",
            "text": f"Describe quality control measure {index}.",
            "importance": "mandatory",
            "category": "quality",
            "category_label": "Quality control",
            "topic": f"quality topic {index}",
        }
        for index in range(1, 14)
    ]

    blueprint = build_drafting_blueprint(
        section_title="Quality control",
        requirement_items=requirement_items,
        max_items_per_group=10,
    )
    prompt = format_drafting_blueprint_for_prompt(blueprint)

    group = blueprint["groups"][0]
    assert group["requirement_ids"] == [
        f"req-quality-{index}" for index in range(1, 14)
    ]
    assert [item["id"] for item in group["requirements"]] == [
        f"req-quality-{index}" for index in range(1, 11)
    ]
    assert [item["id"] for item in group["additional_requirements"]] == [
        "req-quality-11",
        "req-quality-12",
        "req-quality-13",
    ]
    assert "additional requirements to cover explicitly" in prompt
    assert "req-quality-11 [quality topic 11]" in prompt
    assert "req-quality-13 [quality topic 13]" in prompt
