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
            "corrective record in one control workflow, then assigns the owner, "
            "monitors the signal, and documents corrective records."
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
    assert keyword_only["items"][0]["operational_execution_signals"] == []
    assert (
        keyword_only["items"][0]["required_operational_execution_signal_count"]
        == 1
    )
    assert operational["covered_ids"] == ["req-environment-measures"]
    assert len(operational["items"][0]["operational_signals"]) >= 2
    assert len(operational["items"][0]["operational_execution_signals"]) >= 1


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
    assert keyword_only["items"][0]["operational_execution_signals"] == []
    assert operational["covered_ids"] == ["req-legacy-risk"]
    assert len(operational["items"][0]["operational_signals"]) >= 2
    assert len(operational["items"][0]["operational_execution_signals"]) >= 1


def test_requirement_coverage_requires_active_execution_for_operational_details():
    items = normalize_requirement_items(
        [
            {
                "id": "req-quality-actions",
                "text": (
                    "Describe quality control protocol, inspection record, "
                    "acceptance evidence, and corrective action."
                ),
                "importance": "mandatory",
                "category": "quality",
            }
        ]
    )

    keyword_only = assess_requirement_coverage(
        (
            "The proposal describes quality control protocol, inspection "
            "record, acceptance evidence, and corrective action."
        ),
        items,
    )
    active_execution = assess_requirement_coverage(
        (
            "The contractor assigns a responsible role, performs the quality "
            "control protocol, keeps the inspection record, attaches acceptance "
            "evidence, and documents corrective action."
        ),
        items,
    )

    assert keyword_only["missing_ids"] == ["req-quality-actions"]
    assert len(keyword_only["items"][0]["operational_signals"]) >= 2
    assert keyword_only["items"][0]["operational_execution_signals"] == []
    assert (
        keyword_only["items"][0]["required_operational_execution_signal_count"]
        == 1
    )
    assert active_execution["covered_ids"] == ["req-quality-actions"]
    assert len(active_execution["items"][0]["operational_execution_signals"]) >= 1


def test_requirement_coverage_accepts_bulgarian_active_execution_verbs():
    requirement_text = (
        "\u041e\u043f\u0438\u0448\u0435\u0442\u0435 "
        "\u043a\u043e\u043d\u0442\u0440\u043e\u043b \u043d\u0430 "
        "\u043a\u0430\u0447\u0435\u0441\u0442\u0432\u043e\u0442\u043e, "
        "\u043f\u0440\u043e\u0442\u043e\u043a\u043e\u043b "
        "\u0437\u0430 \u043f\u0440\u0438\u0435\u043c\u0430\u043d\u0435, "
        "\u043e\u0442\u0433\u043e\u0432\u043e\u0440\u043d\u0430 "
        "\u0440\u043e\u043b\u044f \u0438 "
        "\u043a\u043e\u0440\u0438\u0433\u0438\u0440\u0430\u0449\u0438 "
        "\u0434\u0435\u0439\u0441\u0442\u0432\u0438\u044f."
    )
    items = normalize_requirement_items(
        [
            {
                "id": "req-bg-quality-actions",
                "text": requirement_text,
                "importance": "mandatory",
                "category": "quality",
                "category_label": "\u041a\u043e\u043d\u0442\u0440\u043e\u043b "
                "\u043d\u0430 \u043a\u0430\u0447\u0435\u0441\u0442\u0432\u043e\u0442\u043e",
            }
        ]
    )

    keyword_only = assess_requirement_coverage(
        (
            "\u041f\u0440\u0435\u0434\u043b\u043e\u0436\u0435\u043d\u0438\u0435\u0442\u043e "
            "\u043e\u043f\u0438\u0441\u0432\u0430 "
            "\u043a\u043e\u043d\u0442\u0440\u043e\u043b \u043d\u0430 "
            "\u043a\u0430\u0447\u0435\u0441\u0442\u0432\u043e\u0442\u043e, "
            "\u043f\u0440\u043e\u0442\u043e\u043a\u043e\u043b "
            "\u0437\u0430 \u043f\u0440\u0438\u0435\u043c\u0430\u043d\u0435, "
            "\u043e\u0442\u0433\u043e\u0432\u043e\u0440\u043d\u0430 "
            "\u0440\u043e\u043b\u044f \u0438 "
            "\u043a\u043e\u0440\u0438\u0433\u0438\u0440\u0430\u0449\u0438 "
            "\u0434\u0435\u0439\u0441\u0442\u0432\u0438\u044f."
        ),
        items,
    )
    active_execution = assess_requirement_coverage(
        (
            "\u0418\u0437\u043f\u044a\u043b\u043d\u0438\u0442\u0435\u043b\u044f\u0442 "
            "\u0432\u044a\u0437\u043b\u0430\u0433\u0430 "
            "\u043e\u0442\u0433\u043e\u0432\u043e\u0440\u043d\u0430 "
            "\u0440\u043e\u043b\u044f, "
            "\u0438\u0437\u043f\u044a\u043b\u043d\u044f\u0432\u0430 "
            "\u043a\u043e\u043d\u0442\u0440\u043e\u043b \u043d\u0430 "
            "\u043a\u0430\u0447\u0435\u0441\u0442\u0432\u043e\u0442\u043e, "
            "\u0432\u043e\u0434\u0438 "
            "\u043f\u0440\u043e\u0442\u043e\u043a\u043e\u043b "
            "\u0437\u0430 \u043f\u0440\u0438\u0435\u043c\u0430\u043d\u0435 "
            "\u0438 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u0438\u0440\u0430 "
            "\u043a\u043e\u0440\u0438\u0433\u0438\u0440\u0430\u0449\u0438\u0442\u0435 "
            "\u0434\u0435\u0439\u0441\u0442\u0432\u0438\u044f."
        ),
        items,
    )

    assert keyword_only["missing_ids"] == ["req-bg-quality-actions"]
    assert len(keyword_only["items"][0]["operational_signals"]) >= 2
    assert keyword_only["items"][0]["operational_execution_signals"] == []
    assert active_execution["covered_ids"] == ["req-bg-quality-actions"]
    assert {
        "\u0432\u044a\u0437\u043b\u0430\u0433",
        "\u0432\u043e\u0434\u0438",
        "\u0438\u0437\u043f\u044a\u043b\u043d",
    } & set(active_execution["items"][0]["operational_execution_signals"])


def test_requirement_coverage_accepts_common_bulgarian_execution_stems():
    requirement_text = (
        "\u041e\u043f\u0438\u0448\u0435\u0442\u0435 "
        "\u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0430, "
        "\u043a\u043e\u043d\u0442\u0440\u043e\u043b, "
        "\u043f\u0440\u043e\u0442\u043e\u043a\u043e\u043b, "
        "\u043c\u0435\u0440\u043a\u0438 \u0437\u0430 "
        "\u0431\u0435\u0437\u043e\u043f\u0430\u0441\u043d\u043e\u0441\u0442 "
        "\u0438 \u0434\u043e\u043a\u0430\u0437\u0430\u0442\u0435\u043b\u0441\u0442\u0432\u0430."
    )
    items = normalize_requirement_items(
        [
            {
                "id": "req-bg-safety-checks",
                "text": requirement_text,
                "importance": "mandatory",
                "category": "safety",
                "category_label": "\u0411\u0435\u0437\u043e\u043f\u0430\u0441\u043d\u043e\u0441\u0442",
            }
        ]
    )

    keyword_only = assess_requirement_coverage(
        (
            "\u0422\u0435\u043a\u0441\u0442\u044a\u0442 "
            "\u0441\u044a\u0434\u044a\u0440\u0436\u0430 "
            "\u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0430, "
            "\u043a\u043e\u043d\u0442\u0440\u043e\u043b, "
            "\u043f\u0440\u043e\u0442\u043e\u043a\u043e\u043b, "
            "\u043c\u0435\u0440\u043a\u0438 \u0437\u0430 "
            "\u0431\u0435\u0437\u043e\u043f\u0430\u0441\u043d\u043e\u0441\u0442 "
            "\u0438 \u0434\u043e\u043a\u0430\u0437\u0430\u0442\u0435\u043b\u0441\u0442\u0432\u0430."
        ),
        items,
    )
    active_execution = assess_requirement_coverage(
        (
            "\u0415\u043a\u0438\u043f\u044a\u0442 "
            "\u0438\u0437\u0432\u044a\u0440\u0448\u0432\u0430 "
            "\u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0430, "
            "\u043e\u0441\u0438\u0433\u0443\u0440\u044f\u0432\u0430 "
            "\u043c\u0435\u0440\u043a\u0438 \u0437\u0430 "
            "\u0431\u0435\u0437\u043e\u043f\u0430\u0441\u043d\u043e\u0441\u0442, "
            "\u043e\u0440\u0433\u0430\u043d\u0438\u0437\u0438\u0440\u0430 "
            "\u043a\u043e\u043d\u0442\u0440\u043e\u043b, "
            "\u043f\u0440\u043e\u0432\u0435\u0440\u044f\u0432\u0430 "
            "\u0434\u043e\u043a\u0430\u0437\u0430\u0442\u0435\u043b\u0441\u0442\u0432\u0430 "
            "\u0438 \u0441\u044a\u0441\u0442\u0430\u0432\u044f "
            "\u043f\u0440\u043e\u0442\u043e\u043a\u043e\u043b."
        ),
        items,
    )

    assert keyword_only["missing_ids"] == ["req-bg-safety-checks"]
    assert keyword_only["items"][0]["operational_execution_signals"] == []
    assert active_execution["covered_ids"] == ["req-bg-safety-checks"]
    assert {
        "\u0438\u0437\u0432\u044a\u0440\u0448",
        "\u043e\u0441\u0438\u0433\u0443\u0440",
        "\u043e\u0440\u0433\u0430\u043d\u0438\u0437\u0438\u0440",
        "\u043f\u0440\u043e\u0432\u0435\u0440\u044f\u0432",
        "\u0441\u044a\u0441\u0442\u0430\u0432",
    } & set(active_execution["items"][0]["operational_execution_signals"])


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
