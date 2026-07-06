from app.agents.proposal_quality import assess_generation_depth


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

    result = assess_generation_depth(sentence * 18, coverage)

    assert result["status"] == "ok"
    assert result["word_count"] >= result["min_words"]
    assert result["sentence_count"] >= result["min_sentences"]


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
    assert result["min_words"] >= 1200
    assert result["word_count"] < result["min_words"]
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
        sentence * 90,
        coverage,
        drafting_blueprint=_drafting_blueprint(6),
    )

    assert result["status"] == "ok"
    assert result["blueprint_group_count"] == 6
    assert result["word_count"] >= result["min_words"]
    assert result["sentence_count"] >= result["min_sentences"]
