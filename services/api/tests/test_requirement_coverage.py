from app.agents.requirement_coverage import (
    assess_requirement_coverage,
    format_requirement_items_for_prompt,
    normalize_requirement_items,
)


def test_requirement_coverage_marks_covered_and_missing_items():
    items = normalize_requirement_items(
        [
            {
                "id": "req-schedule",
                "text": "Следва да се представи подробен линеен график за изпълнение.",
                "importance": "mandatory",
                "category_label": "График и срокове",
            },
            {
                "id": "req-access",
                "text": "Следва да се опише специален ред за достъп до помещенията и предаване на ключове.",
                "importance": "mandatory",
                "category_label": "Специфични изисквания",
            },
        ]
    )

    coverage = assess_requirement_coverage(
        "Предвижда се подробен линеен график с последователност на дейностите.",
        items,
    )

    assert coverage["covered_ids"] == ["req-schedule"]
    assert coverage["missing_ids"] == ["req-access"]
    assert coverage["critical_missing_ids"] == ["req-access"]


def test_requirement_items_prompt_keeps_ids_and_questions():
    items = normalize_requirement_items(
        [
            {
                "id": "req-quality",
                "text": "Да се опишат мерките за входящ контрол на материалите.",
                "importance": "scored",
                "category_label": "Качество и контрол",
                "coverage_question": "Покрит ли е входящият контрол?",
            }
        ]
    )

    prompt = format_requirement_items_for_prompt(items)

    assert "id=req-quality" in prompt
    assert "Покрит ли е входящият контрол?" in prompt
