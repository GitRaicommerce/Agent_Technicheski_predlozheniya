from __future__ import annotations

import re
from math import ceil
from typing import Any


BASE_MIN_WORDS = 120
MIN_WORDS_PER_REQUIREMENT = 100
MIN_WORDS_WITH_REQUIREMENTS = 220
MAX_MIN_WORDS = 1400
BLUEPRINT_BASE_MIN_WORDS = 260
MIN_WORDS_PER_BLUEPRINT_GROUP = 220
MAX_BLUEPRINT_MIN_WORDS = 2400
MIN_UNIQUE_SENTENCE_RATIO = 0.45
STRUCTURE_ANCHOR_STOP_WORDS = {
    "category",
    "group",
    "requirement",
    "requirements",
    "specific",
    "tender",
    "topic",
}


def _word_count(text: str) -> int:
    return len(re.findall(r"[0-9A-Za-zА-Яа-я]+", text or ""))


def _tokens(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[0-9A-Za-z\u0400-\u04FF]+", str(text or "").lower())
        if len(token) >= 4 and token not in STRUCTURE_ANCHOR_STOP_WORDS
    ]


def _sentence_count(text: str) -> int:
    pieces = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    return sum(1 for piece in pieces if _word_count(piece) >= 6)


def _developed_sentence_fingerprints(text: str) -> list[str]:
    pieces = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    fingerprints: list[str] = []
    for piece in pieces:
        if _word_count(piece) < 6:
            continue
        tokens = [
            token
            for token in _tokens(piece)
            if not token.isdigit()
        ]
        if tokens:
            fingerprints.append(" ".join(tokens))
    return fingerprints


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


def _blueprint_group_count(drafting_blueprint: dict[str, Any] | None) -> int:
    if not isinstance(drafting_blueprint, dict):
        return 0

    groups = drafting_blueprint.get("groups")
    if not isinstance(groups, list):
        return 0

    count = 0
    for group in groups:
        if not isinstance(group, dict):
            continue
        requirements = group.get("requirements")
        has_requirements = isinstance(requirements, list) and len(requirements) > 0
        has_label = bool(group.get("label") or group.get("category"))
        if has_requirements or has_label:
            count += 1
    return count


def _blueprint_topic_count(drafting_blueprint: dict[str, Any] | None) -> int:
    if not isinstance(drafting_blueprint, dict):
        return 0

    groups = drafting_blueprint.get("groups")
    if not isinstance(groups, list):
        return 0

    count = 0
    for group in groups:
        if not isinstance(group, dict):
            continue
        topic_details = group.get("topic_details")
        if isinstance(topic_details, list):
            count += sum(
                1
                for topic in topic_details
                if isinstance(topic, dict)
                and (topic.get("topic") or topic.get("requirement_ids"))
            )
            continue
        topics = group.get("topics")
        if isinstance(topics, list):
            count += sum(1 for topic in topics if topic)
    return count


def _blueprint_structure_anchors(
    drafting_blueprint: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not isinstance(drafting_blueprint, dict):
        return []

    groups = drafting_blueprint.get("groups")
    if not isinstance(groups, list):
        return []

    anchors: list[dict[str, Any]] = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        for topic in group.get("topic_details") or []:
            if not isinstance(topic, dict) or not topic.get("topic"):
                continue
            terms = _tokens(str(topic.get("topic") or ""))
            if terms:
                anchors.append(
                    {
                        "label": str(topic.get("topic") or ""),
                        "terms": terms,
                        "kind": "topic",
                    }
                )

    if len(anchors) > 1:
        return anchors

    anchors = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        label = str(group.get("label") or group.get("category") or "")
        topics = " ".join(str(topic) for topic in group.get("topics") or [] if topic)
        terms = list(dict.fromkeys(_tokens(f"{label} {topics}")))
        if terms:
            anchors.append(
                {
                    "label": label or str(group.get("category") or "group"),
                    "terms": terms,
                    "kind": "group",
                }
            )
    return anchors


def _blueprint_structure_coverage(
    text: str,
    drafting_blueprint: dict[str, Any] | None,
) -> dict[str, Any]:
    anchors = _blueprint_structure_anchors(drafting_blueprint)
    generated_tokens = set(_tokens(text))
    covered: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for anchor in anchors:
        matched_terms = sorted(set(anchor["terms"]) & generated_tokens)
        required_terms = min(
            len(anchor["terms"]),
            max(1, ceil(len(anchor["terms"]) * 0.6)),
        )
        if len(anchor["terms"]) >= 2:
            required_terms = max(2, required_terms)
        target = {
            "label": anchor["label"],
            "kind": anchor["kind"],
            "matched_terms": matched_terms,
            "terms": anchor["terms"],
            "required_terms": required_terms,
        }
        if len(matched_terms) >= required_terms:
            covered.append(target)
        else:
            missing.append(target)

    required = ceil(len(anchors) * 0.7) if len(anchors) > 1 else 0
    return {
        "anchor_count": len(anchors),
        "covered_count": len(covered),
        "required_count": required,
        "covered": covered,
        "missing": missing,
    }


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


def _min_words_for_blueprint_groups(group_count: int) -> int:
    if group_count <= 1:
        return 0
    return min(
        MAX_BLUEPRINT_MIN_WORDS,
        max(
            MIN_WORDS_WITH_REQUIREMENTS,
            BLUEPRINT_BASE_MIN_WORDS
            + group_count * MIN_WORDS_PER_BLUEPRINT_GROUP,
        ),
    )


def _min_sentences_for_requirements(requirement_count: int) -> int:
    if requirement_count <= 1:
        return 0
    return min(8, max(3, requirement_count))


def _min_sentences_for_blueprint_groups(group_count: int) -> int:
    if group_count <= 1:
        return 0
    return min(14, max(4, group_count * 2))


def assess_generation_depth(
    text: str,
    requirement_coverage: dict[str, Any] | None,
    drafting_blueprint: dict[str, Any] | None = None,
) -> dict[str, Any]:
    target = build_generation_depth_target(
        requirement_coverage=requirement_coverage,
        drafting_blueprint=drafting_blueprint,
    )
    requirement_count = target["requirement_count"]
    blueprint_group_count = target["blueprint_group_count"]
    blueprint_topic_count = target["blueprint_topic_count"]
    blueprint_structure_count = max(blueprint_group_count, blueprint_topic_count)
    word_count = _word_count(text)
    sentence_count = _sentence_count(text)
    sentence_fingerprints = _developed_sentence_fingerprints(text)
    unique_sentence_count = len(set(sentence_fingerprints))
    min_words = target["min_words"]
    min_sentences = target["min_sentences"]
    structure_coverage = _blueprint_structure_coverage(text, drafting_blueprint)
    issues: list[dict[str, Any]] = []

    if (requirement_count > 0 or blueprint_structure_count > 1) and word_count < min_words:
        issues.append(
            {
                "code": "too_short_for_requirements",
                "message": (
                    "Generated text is too short for the mapped tender "
                    "requirements and drafting structure."
                ),
                "word_count": word_count,
                "min_words": min_words,
                "blueprint_group_count": blueprint_group_count,
                "blueprint_topic_count": blueprint_topic_count,
            }
        )

    if (
        (requirement_count > 1 or blueprint_structure_count > 1)
        and sentence_count < min_sentences
    ):
        issues.append(
            {
                "code": "too_few_developed_sentences",
                "message": (
                    "Generated text has too few developed sentences for the "
                    "mapped tender requirements and drafting structure."
                ),
                "sentence_count": sentence_count,
                "min_sentences": min_sentences,
                "blueprint_group_count": blueprint_group_count,
                "blueprint_topic_count": blueprint_topic_count,
            }
        )

    if (
        (requirement_count > 1 or blueprint_structure_count > 1)
        and sentence_count >= max(6, min_sentences)
        and unique_sentence_count < max(3, ceil(min_sentences * MIN_UNIQUE_SENTENCE_RATIO))
    ):
        issues.append(
            {
                "code": "repetitive_content",
                "message": (
                    "Generated text appears to meet the length target by repeating "
                    "the same developed sentence patterns instead of adding distinct "
                    "operational detail."
                ),
                "sentence_count": sentence_count,
                "unique_sentence_count": unique_sentence_count,
                "min_unique_sentence_count": max(
                    3,
                    ceil(min_sentences * MIN_UNIQUE_SENTENCE_RATIO),
                ),
            }
        )

    if (
        structure_coverage["anchor_count"] > 1
        and structure_coverage["covered_count"] < structure_coverage["required_count"]
    ):
        issues.append(
            {
                "code": "uneven_blueprint_distribution",
                "message": (
                    "Generated text does not visibly distribute developed "
                    "coverage across the drafting blueprint groups/topics."
                ),
                "covered_structure_count": structure_coverage["covered_count"],
                "required_structure_count": structure_coverage["required_count"],
                "blueprint_anchor_count": structure_coverage["anchor_count"],
                "missing_structure_labels": [
                    item["label"] for item in structure_coverage["missing"]
                ],
            }
        )

    return {
        "status": "needs_review" if issues else "ok",
        "word_count": word_count,
        "sentence_count": sentence_count,
        "unique_sentence_count": unique_sentence_count,
        "requirement_count": requirement_count,
        "blueprint_group_count": blueprint_group_count,
        "blueprint_topic_count": blueprint_topic_count,
        "blueprint_structure_count": target["blueprint_structure_count"],
        "min_words": min_words,
        "min_sentences": min_sentences,
        "suggested_words_per_structure": target["suggested_words_per_structure"],
        "structure_coverage": structure_coverage,
        "issues": issues,
    }


def build_generation_depth_target(
    *,
    requirement_coverage: dict[str, Any] | None,
    drafting_blueprint: dict[str, Any] | None = None,
) -> dict[str, Any]:
    requirement_count = _coverage_total(requirement_coverage)
    blueprint_group_count = _blueprint_group_count(drafting_blueprint)
    blueprint_topic_count = _blueprint_topic_count(drafting_blueprint)
    blueprint_structure_count = max(blueprint_group_count, blueprint_topic_count)
    min_words = max(
        _min_words_for_requirements(requirement_count),
        _min_words_for_blueprint_groups(blueprint_structure_count),
    )
    min_sentences = max(
        _min_sentences_for_requirements(requirement_count),
        _min_sentences_for_blueprint_groups(blueprint_structure_count),
    )
    return {
        "requirement_count": requirement_count,
        "blueprint_group_count": blueprint_group_count,
        "blueprint_topic_count": blueprint_topic_count,
        "blueprint_structure_count": blueprint_structure_count,
        "min_words": min_words,
        "min_sentences": min_sentences,
        "suggested_words_per_structure": (
            ceil(min_words / blueprint_structure_count)
            if blueprint_structure_count > 1 and min_words > 0
            else 0
        ),
        "required": requirement_count > 0 or blueprint_structure_count > 1,
    }


def format_generation_depth_target_for_prompt(target: dict[str, Any]) -> str:
    if not isinstance(target, dict) or not target.get("required"):
        return ""

    requirement_count = int(target.get("requirement_count") or 0)
    blueprint_group_count = int(target.get("blueprint_group_count") or 0)
    blueprint_topic_count = int(target.get("blueprint_topic_count") or 0)
    blueprint_structure_count = int(target.get("blueprint_structure_count") or 0)
    min_words = int(target.get("min_words") or 0)
    min_sentences = int(target.get("min_sentences") or 0)
    suggested_words_per_structure = int(
        target.get("suggested_words_per_structure") or 0
    )
    sentence_target = (
        f" and {min_sentences} developed sentences" if min_sentences > 0 else ""
    )
    distribution_hint = (
        (
            "- Distribute the depth across the blueprint structure: write roughly "
            f"{suggested_words_per_structure}+ words for each major group/topic "
            "when the sources support it, instead of spending the whole section "
            "on introductory text."
        )
        if blueprint_structure_count > 1 and suggested_words_per_structure > 0
        else (
            "- Write at least one developed operational paragraph for each mapped "
            "checklist requirement."
        )
    )

    return "\n".join(
        [
            "SECTION DEPTH TARGET:",
            (
                "- Draft at least "
                f"{min_words} words{sentence_target} "
                "for this section unless the provided tender sources are "
                "genuinely narrower."
            ),
            (
                "- The target is derived from "
                f"{requirement_count} mapped checklist requirements and "
                f"{blueprint_group_count} drafting blueprint groups "
                f"with {blueprint_topic_count} required topics."
            ),
            distribution_hint,
            (
                "- Meet the target through concrete actions, roles, controls, "
                "documents, sequence, acceptance evidence, and tender-specific "
                "details; do not pad the section with repetition."
            ),
        ]
    )
