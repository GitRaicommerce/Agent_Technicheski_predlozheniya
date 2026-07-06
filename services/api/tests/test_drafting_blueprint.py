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
    assert any("trigger" in item for item in groups[0]["guidance"])
    assert any("records" in item for item in groups[1]["guidance"])
    assert any("tender-specific" in item for item in groups[2]["guidance"])


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
    assert "Mobilization and design review" in prompt
    assert "phases, dependencies, and acceptance points" in prompt
