from app.agents.proposal_quality import (
    assess_generation_depth,
    build_generation_depth_target,
    format_generation_depth_target_for_prompt,
)


def _drafting_blueprint(group_count: int) -> dict:
    return {
        "groups": [
            {
                "category": f"category-{index}",
                "label": f"Category {index}",
                "requirements": [{"id": f"req-{index}"}],
            }
            for index in range(1, group_count + 1)
        ]
    }


def _topic_rich_blueprint(topic_count: int) -> dict:
    return {
        "groups": [
            {
                "category": "environment",
                "label": "Environment",
                "requirements": [
                    {"id": f"req-topic-{index}"}
                    for index in range(1, topic_count + 1)
                ],
                "topics": [f"topic-{index}" for index in range(1, topic_count + 1)],
                "topic_details": [
                    {
                        "topic": f"topic-{index}",
                        "requirement_ids": [f"req-topic-{index}"],
                    }
                    for index in range(1, topic_count + 1)
                ],
            }
        ]
    }


def _environment_topic_blueprint() -> dict:
    topics = ["dust", "waste", "soil", "water"]
    return {
        "groups": [
            {
                "category": "environment",
                "label": "Environmental protection",
                "requirements": [
                    {"id": f"req-{topic}"}
                    for topic in topics
                ],
                "topics": topics,
                "topic_details": [
                    {"topic": topic, "requirement_ids": [f"req-{topic}"]}
                    for topic in topics
                ],
            }
        ]
    }


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


def test_generation_depth_flags_short_text_with_multiple_requirements():
    coverage = {
        "total": 3,
        "covered": 3,
        "missing": 0,
        "missing_ids": [],
        "items": [
            {"id": "req-1", "status": "covered"},
            {"id": "req-2", "status": "covered"},
            {"id": "req-3", "status": "covered"},
        ],
    }

    result = assess_generation_depth("Кратко общо описание.", coverage)

    assert result["status"] == "needs_review"
    assert result["requirement_count"] == 3
    assert result["word_count"] < result["min_words"]
    assert {issue["code"] for issue in result["issues"]} == {
        "too_short_for_requirements",
        "too_few_developed_sentences",
    }


def test_generation_depth_accepts_developed_text_with_requirements():
    coverage = {
        "total": 2,
        "covered": 2,
        "missing": 0,
        "missing_ids": [],
    }
    sentence = (
        "Разделът описва конкретната организация на изпълнение, отговорните "
        "лица, последователността на дейностите, контролните точки и начина "
        "на документиране на всяко действие съгласно изискванията на възложителя. "
    )

    result = assess_generation_depth(
        _varied_operational_text(["organization", "sequence", "control"], repeats=6),
        coverage,
    )

    assert result["status"] == "ok"
    assert result["word_count"] >= result["min_words"]
    assert result["sentence_count"] >= result["min_sentences"]
    assert result["unique_sentence_count"] >= 3


def test_generation_depth_uses_blueprint_groups_for_complex_sections():
    coverage = {
        "total": 2,
        "covered": 2,
        "missing": 0,
        "missing_ids": [],
    }
    text = (
        "The section describes coordination, quality control, risk monitoring, "
        "environmental measures, reporting, and acceptance records. "
    ) * 20

    result = assess_generation_depth(
        text,
        coverage,
        drafting_blueprint=_drafting_blueprint(6),
    )

    assert result["status"] == "needs_review"
    assert result["requirement_count"] == 2
    assert result["blueprint_group_count"] == 6
    assert result["min_words"] >= 1500
    assert result["word_count"] < result["min_words"]
    assert "too_short_for_requirements" in {
        issue["code"] for issue in result["issues"]
    }


def test_generation_depth_uses_blueprint_topics_for_complex_single_category_sections():
    coverage = {
        "total": 3,
        "covered": 3,
        "missing": 0,
        "missing_ids": [],
    }
    text = (
        "The section describes environmental measures with roles, monitoring, "
        "records, corrective actions, and acceptance evidence. "
    ) * 25

    result = assess_generation_depth(
        text,
        coverage,
        drafting_blueprint=_topic_rich_blueprint(6),
    )

    assert result["status"] == "needs_review"
    assert result["blueprint_group_count"] == 1
    assert result["blueprint_topic_count"] == 6
    assert result["min_words"] >= 1500
    assert "too_short_for_requirements" in {
        issue["code"] for issue in result["issues"]
    }


def test_generation_depth_accepts_developed_blueprint_structured_text():
    coverage = {
        "total": 2,
        "covered": 2,
        "missing": 0,
        "missing_ids": [],
    }
    sentence = (
        "The proposal explains a concrete action, responsible role, control "
        "record, evidence source, timing, coordination point, escalation path, "
        "acceptance criterion, document flow, and corrective action. "
    )

    result = assess_generation_depth(
        _varied_operational_text(
            [
                "organization",
                "quality",
                "risk",
                "environment",
                "communication",
                "documentation",
            ],
            repeats=10,
        ),
        coverage,
        drafting_blueprint=_drafting_blueprint(6),
    )

    assert result["status"] == "ok"
    assert result["blueprint_group_count"] == 6
    assert result["word_count"] >= result["min_words"]
    assert result["sentence_count"] >= result["min_sentences"]


def test_generation_depth_rejects_repetitive_padding():
    coverage = {
        "total": 2,
        "covered": 2,
        "missing": 0,
        "missing_ids": [],
    }
    repeated_sentence = (
        "The proposal explains a concrete action, responsible role, control "
        "record, evidence source, timing, coordination point, escalation path, "
        "acceptance criterion, document flow, and corrective action. "
    )

    result = assess_generation_depth(
        repeated_sentence * 90,
        coverage,
        drafting_blueprint=_drafting_blueprint(6),
    )

    assert result["word_count"] >= result["min_words"]
    assert result["sentence_count"] >= result["min_sentences"]
    assert result["unique_sentence_count"] == 1
    assert "repetitive_content" in {issue["code"] for issue in result["issues"]}


def test_generation_depth_rejects_long_text_with_uneven_blueprint_distribution():
    coverage = {
        "total": 4,
        "covered": 4,
        "missing": 0,
        "missing_ids": [],
    }
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

    dust_only = assess_generation_depth(
        dust_only_sentence * 90,
        coverage,
        drafting_blueprint=_environment_topic_blueprint(),
    )
    balanced = assess_generation_depth(
        _varied_operational_text(["dust", "waste", "soil", "water"], repeats=25),
        coverage,
        drafting_blueprint=_environment_topic_blueprint(),
    )

    assert dust_only["word_count"] >= dust_only["min_words"]
    assert "uneven_blueprint_distribution" in {
        issue["code"] for issue in dust_only["issues"]
    }
    assert dust_only["structure_coverage"]["covered_count"] == 1
    assert dust_only["structure_coverage"]["required_count"] == 3
    assert balanced["status"] == "ok"
    assert balanced["structure_coverage"]["covered_count"] == 4


def test_generation_depth_requires_enough_terms_for_multi_word_blueprint_anchors():
    coverage = {
        "total": 4,
        "covered": 4,
        "missing": 0,
        "missing_ids": [],
    }
    blueprint = {
        "groups": [
            {
                "category": "environment",
                "label": "Environmental protection",
                "requirements": [
                    {"id": "req-dust"},
                    {"id": "req-waste"},
                    {"id": "req-soil"},
                    {"id": "req-water"},
                ],
                "topics": [
                    "dust suppression",
                    "waste segregation",
                    "soil protection",
                    "water pollution prevention",
                ],
                "topic_details": [
                    {"topic": "dust suppression", "requirement_ids": ["req-dust"]},
                    {"topic": "waste segregation", "requirement_ids": ["req-waste"]},
                    {"topic": "soil protection", "requirement_ids": ["req-soil"]},
                    {
                        "topic": "water pollution prevention",
                        "requirement_ids": ["req-water"],
                    },
                ],
            }
        ]
    }
    partial_anchor_text = (
        "The environmental section repeats monitoring control and protection "
        "with responsible roles, records, corrective actions, acceptance "
        "evidence, reporting sequence, and site coordination. "
    )
    developed_topic_text = _varied_operational_text(
        [
            "dust suppression",
            "waste segregation",
            "soil protection",
            "water pollution prevention",
        ],
        repeats=25,
    )

    partial = assess_generation_depth(
        partial_anchor_text * 90,
        coverage,
        drafting_blueprint=blueprint,
    )
    developed = assess_generation_depth(
        developed_topic_text,
        coverage,
        drafting_blueprint=blueprint,
    )

    assert partial["word_count"] >= partial["min_words"]
    assert partial["structure_coverage"]["covered_count"] < partial[
        "structure_coverage"
    ]["required_count"]
    assert {
        item["label"] for item in partial["structure_coverage"]["missing"]
    } == {
        "dust suppression",
        "waste segregation",
        "soil protection",
        "water pollution prevention",
    }
    assert "uneven_blueprint_distribution" in {
        issue["code"] for issue in partial["issues"]
    }
    assert developed["status"] == "ok"


def test_generation_depth_target_prompt_matches_export_gate_thresholds():
    coverage = {
        "total": 2,
        "covered": 2,
        "missing": 0,
        "missing_ids": [],
    }

    target = build_generation_depth_target(
        requirement_coverage=coverage,
        drafting_blueprint=_drafting_blueprint(6),
    )
    prompt = format_generation_depth_target_for_prompt(target)

    assert target["required"] is True
    assert target["min_words"] >= 1500
    assert target["min_sentences"] >= 10
    assert target["blueprint_topic_count"] == 0
    assert target["blueprint_structure_count"] == 6
    assert target["suggested_words_per_structure"] >= 250
    assert "SECTION DEPTH TARGET" in prompt
    assert "2 mapped checklist requirements" in prompt
    assert "6 drafting blueprint groups with 0 required topics" in prompt
    assert "Distribute the depth across the blueprint structure" in prompt
    assert "for each major group/topic" in prompt
    assert str(target["min_words"]) in prompt


def test_generation_depth_target_prompt_reports_topic_rich_blueprint():
    target = build_generation_depth_target(
        requirement_coverage={"total": 3},
        drafting_blueprint=_topic_rich_blueprint(6),
    )
    prompt = format_generation_depth_target_for_prompt(target)

    assert target["blueprint_group_count"] == 1
    assert target["blueprint_topic_count"] == 6
    assert target["min_words"] >= 1500
    assert target["suggested_words_per_structure"] >= 250
    assert "1 drafting blueprint groups with 6 required topics" in prompt
    assert "for each major group/topic" in prompt


def test_generation_depth_target_counts_overflow_blueprint_requirement_ids():
    blueprint = {
        "groups": [
            {
                "category": "specific",
                "label": "Specific tender requirements",
                "requirement_ids": [
                    f"req-specific-{index}" for index in range(1, 14)
                ],
                "requirements": [
                    {"id": f"req-specific-{index}"}
                    for index in range(1, 11)
                ],
                "additional_requirements": [
                    {"id": "req-specific-11"},
                    {"id": "req-specific-12"},
                    {"id": "req-specific-13"},
                ],
                "topics": ["specific conditions"],
                "topic_details": [
                    {
                        "topic": "specific conditions",
                        "requirement_ids": [
                            f"req-specific-{index}" for index in range(1, 14)
                        ],
                    }
                ],
            }
        ]
    }

    target = build_generation_depth_target(
        requirement_coverage={"total": 13},
        drafting_blueprint=blueprint,
    )
    prompt = format_generation_depth_target_for_prompt(target)

    assert target["blueprint_group_count"] == 1
    assert target["blueprint_topic_count"] == 1
    assert target["blueprint_requirement_id_count"] == 13
    assert target["min_words"] >= 1400
    assert "13 blueprint requirement ids" in prompt


def test_generation_depth_target_prompt_omits_zero_sentence_target():
    target = build_generation_depth_target(
        requirement_coverage={"total": 1, "items": [{"id": "req-1"}]},
        drafting_blueprint=_drafting_blueprint(1),
    )
    prompt = format_generation_depth_target_for_prompt(target)

    assert target["min_sentences"] == 0
    assert "0 developed sentences" not in prompt
    assert f"{target['min_words']} words" in prompt
    assert "one developed operational paragraph" in prompt
