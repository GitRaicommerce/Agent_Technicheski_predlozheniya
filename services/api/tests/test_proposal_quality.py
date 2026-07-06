from app.agents.proposal_quality import assess_generation_depth


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
