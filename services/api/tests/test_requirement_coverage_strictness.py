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
