from app.agents.requirement_coverage import (
    assess_requirement_coverage,
    normalize_requirement_items,
)


def test_requirement_coverage_rejects_superficial_keyword_mentions():
    items = normalize_requirement_items(
        [
            {
                "id": "req-quality-acceptance",
                "text": (
                    "Describe input control, protocol records, acceptance "
                    "criteria, responsible role, and nonconformity handling."
                ),
                "importance": "scored",
                "category_label": "Quality control",
            }
        ]
    )

    superficial = assess_requirement_coverage(
        "The proposal includes quality control and protocol records.",
        items,
    )
    developed = assess_requirement_coverage(
        (
            "The proposal describes input control, protocol records, "
            "acceptance criteria, the responsible role, and nonconformity "
            "handling for each inspection."
        ),
        items,
    )

    assert superficial["missing_ids"] == ["req-quality-acceptance"]
    assert superficial["items"][0]["matched_ratio"] < 0.6
    assert developed["covered_ids"] == ["req-quality-acceptance"]
    assert developed["items"][0]["matched_ratio"] >= 0.6


def test_requirement_coverage_rejects_scattered_keyword_mentions():
    items = normalize_requirement_items(
        [
            {
                "id": "req-risk-controls",
                "text": (
                    "Describe risk trigger, prevention action, response owner, "
                    "monitoring signal, escalation path, and corrective record."
                ),
                "importance": "mandatory",
                "category_label": "Risk management",
            }
        ]
    )

    scattered = assess_requirement_coverage(
        (
            "The proposal has a risk register. "
            "The schedule includes a trigger milestone. "
            "Prevention is mentioned in the quality plan. "
            "The project manager is the response owner. "
            "Monitoring appears in weekly reports. "
            "Escalation is available through management. "
            "Corrective records are archived."
        ),
        items,
    )
    coherent = assess_requirement_coverage(
        (
            "For each risk, the proposal identifies the trigger, prevention "
            "action, response owner, monitoring signal, escalation path, and "
            "corrective record in one control workflow."
        ),
        items,
    )

    assert scattered["missing_ids"] == ["req-risk-controls"]
    assert scattered["items"][0]["matched_ratio"] >= 0.6
    assert scattered["items"][0]["coherent_matched_ratio"] < 0.6
    assert coherent["covered_ids"] == ["req-risk-controls"]
    assert coherent["items"][0]["coherent_matched_ratio"] >= 0.6


def test_requirement_coverage_requires_operational_evidence_for_operational_categories():
    items = normalize_requirement_items(
        [
            {
                "id": "req-environment-measures",
                "text": (
                    "Describe waste segregation, soil protection, dust "
                    "suppression, and pollution prevention."
                ),
                "importance": "mandatory",
                "category": "environment",
                "category_label": "Environmental protection",
            }
        ]
    )

    keyword_only = assess_requirement_coverage(
        (
            "The proposal describes waste segregation, soil protection, dust "
            "suppression, and pollution prevention."
        ),
        items,
    )
    operational = assess_requirement_coverage(
        (
            "The environmental workflow assigns a responsible role for waste "
            "segregation, soil protection, dust suppression, and pollution "
            "prevention, with monitoring records and corrective actions."
        ),
        items,
    )

    assert keyword_only["missing_ids"] == ["req-environment-measures"]
    assert keyword_only["items"][0]["matched_ratio"] >= 0.6
    assert keyword_only["items"][0]["requires_operational_detail"] is True
    assert keyword_only["items"][0]["operational_signals"] == []
    assert operational["covered_ids"] == ["req-environment-measures"]
    assert len(operational["items"][0]["operational_signals"]) >= 2


def test_requirement_coverage_requires_operational_evidence_from_requirement_text():
    items = normalize_requirement_items(
        [
            {
                "id": "req-legacy-risk",
                "text": (
                    "Describe risk trigger, mitigation approach, likelihood "
                    "threshold, and impact response."
                ),
                "importance": "mandatory",
            }
        ]
    )

    keyword_only = assess_requirement_coverage(
        (
            "The proposal describes risk trigger, mitigation approach, "
            "likelihood threshold, and impact response."
        ),
        items,
    )
    operational = assess_requirement_coverage(
        (
            "For each risk trigger, the responsible role applies the mitigation "
            "approach at the likelihood threshold, records the impact response, "
            "and monitors corrective action evidence."
        ),
        items,
    )

    assert keyword_only["missing_ids"] == ["req-legacy-risk"]
    assert keyword_only["items"][0]["requires_operational_detail"] is True
    assert keyword_only["items"][0]["operational_signals"] == []
    assert operational["covered_ids"] == ["req-legacy-risk"]
    assert len(operational["items"][0]["operational_signals"]) >= 2


def test_requirement_coverage_keeps_similar_operational_requirements_separate():
    items = normalize_requirement_items(
        [
            {
                "id": "req-input-control",
                "text": (
                    "Describe input quality control for delivered materials, "
                    "inspection protocol, responsible role, and rejection record."
                ),
                "importance": "mandatory",
                "category": "quality",
                "category_label": "Quality control",
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
            },
        ]
    )

    only_input_control = assess_requirement_coverage(
        (
            "For delivered materials, the contractor performs input quality "
            "control through an inspection protocol, assigns a responsible "
            "role, keeps a rejection record, and applies corrective actions."
        ),
        items,
    )
    both_controls = assess_requirement_coverage(
        (
            "For delivered materials, the contractor performs input quality "
            "control through an inspection protocol, assigns a responsible "
            "role, keeps a rejection record, and applies corrective actions. "
            "For completed works, the contractor performs final acceptance "
            "control through a handover protocol, assigns a responsible role, "
            "keeps a corrective record, and documents acceptance evidence."
        ),
        items,
    )

    assert only_input_control["covered_ids"] == ["req-input-control"]
    assert only_input_control["missing_ids"] == ["req-final-acceptance"]
    final_item = only_input_control["items"][1]
    assert final_item["required_distinctive_count"] == 1
    assert final_item["distinctive_matches"] == []
    assert {"final", "acceptance", "completed", "works", "handover"} & set(
        final_item["distinctive_terms"]
    )
    assert both_controls["covered_ids"] == [
        "req-input-control",
        "req-final-acceptance",
    ]
