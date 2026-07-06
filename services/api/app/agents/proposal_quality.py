from __future__ import annotations

import re
from typing import Any


BASE_MIN_WORDS = 120
MIN_WORDS_PER_REQUIREMENT = 80
MIN_WORDS_WITH_REQUIREMENTS = 220
MAX_MIN_WORDS = 900


def _word_count(text: str) -> int:
    return len(re.findall(r"[0-9A-Za-zА-Яа-я]+", text or ""))


def _sentence_count(text: str) -> int:
    pieces = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    return sum(1 for piece in pieces if _word_count(piece) >= 6)


def _coverage_total(requirement_coverage: dict[str, Any] | None) -> int:
    if not isinstance(requirement_coverage, dict):
        return 0

    total = requirement_coverage.get("total")
    if isinstance(total, int) and total > 0:
        return total

    items = requirement_coverage.get("items")
    if isinstance(items, list):
        return len(items)

    covered_ids = requirement_coverage.get("covered_ids")
    missing_ids = requirement_coverage.get("missing_ids")
    covered_count = len(covered_ids) if isinstance(covered_ids, list) else 0
    missing_count = len(missing_ids) if isinstance(missing_ids, list) else 0
    return covered_count + missing_count


def _min_words_for_requirements(requirement_count: int) -> int:
    if requirement_count <= 0:
        return 0
    return min(
        MAX_MIN_WORDS,
        max(
            MIN_WORDS_WITH_REQUIREMENTS,
            BASE_MIN_WORDS + requirement_count * MIN_WORDS_PER_REQUIREMENT,
        ),
    )


def _min_sentences_for_requirements(requirement_count: int) -> int:
    if requirement_count <= 1:
        return 0
    return min(8, max(3, requirement_count))


def assess_generation_depth(
    text: str,
    requirement_coverage: dict[str, Any] | None,
) -> dict[str, Any]:
    requirement_count = _coverage_total(requirement_coverage)
    word_count = _word_count(text)
    sentence_count = _sentence_count(text)
    min_words = _min_words_for_requirements(requirement_count)
    min_sentences = _min_sentences_for_requirements(requirement_count)
    issues: list[dict[str, Any]] = []

    if requirement_count > 0 and word_count < min_words:
        issues.append(
            {
                "code": "too_short_for_requirements",
                "message": "Generated text is too short for the mapped tender requirements.",
                "word_count": word_count,
                "min_words": min_words,
            }
        )

    if requirement_count > 1 and sentence_count < min_sentences:
        issues.append(
            {
                "code": "too_few_developed_sentences",
                "message": "Generated text has too few developed sentences for the mapped tender requirements.",
                "sentence_count": sentence_count,
                "min_sentences": min_sentences,
            }
        )

    return {
        "status": "needs_review" if issues else "ok",
        "word_count": word_count,
        "sentence_count": sentence_count,
        "requirement_count": requirement_count,
        "min_words": min_words,
        "min_sentences": min_sentences,
        "issues": issues,
    }
