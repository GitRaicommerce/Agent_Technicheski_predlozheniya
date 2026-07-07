from __future__ import annotations

import math
import re
from typing import Any


STOP_WORDS = {
    "and",
    "for",
    "the",
    "with",
    "без",
    "във",
    "или",
    "като",
    "към",
    "при",
    "със",
    "това",
    "тези",
    "този",
    "чрез",
    "следва",
    "трябва",
    "изисква",
    "изискване",
    "изискването",
    "участник",
    "участникът",
    "оферта",
    "офертата",
    "техническо",
    "техническото",
    "предложение",
    "предложението",
    "съдържа",
    "представи",
    "представяне",
    "опише",
    "описание",
    "подробно",
    "изпълнение",
    "изпълнението",
}


def _normalize(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").lower()).strip()


def _tokens(value: str) -> list[str]:
    return [
        token
        for token in re.findall(
            r"[0-9a-zа-я]+",
            _normalize(value),
            flags=re.IGNORECASE,
        )
        if len(token) >= 4 and token not in STOP_WORDS
    ]


def _sentence_windows(text: str, *, window_size: int = 2) -> list[str]:
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", str(text or ""))
        if sentence.strip()
    ]
    if not sentences:
        return [str(text or "")]

    windows: list[str] = []
    for index in range(len(sentences)):
        windows.append(" ".join(sentences[index : index + window_size]))
    return windows


def _best_window_matches(
    requirement_tokens: list[str],
    generated_text: str,
) -> tuple[list[str], float]:
    if not requirement_tokens:
        return [], 1.0

    best_matches: list[str] = []
    for window in _sentence_windows(generated_text):
        window_tokens = set(_tokens(window))
        matches = sorted(set(requirement_tokens) & window_tokens)
        if len(matches) > len(best_matches):
            best_matches = matches

    return best_matches, len(best_matches) / len(requirement_tokens)


def normalize_requirement_items(
    items: list[dict[str, Any]] | None,
    *,
    fallback_requirements: list[str] | None = None,
    fallback_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()

    for index, item in enumerate(items or [], start=1):
        text = str(item.get("text") or "").strip()
        requirement_id = str(item.get("id") or "").strip()
        if not text or not requirement_id or requirement_id in seen:
            continue
        seen.add(requirement_id)
        normalized.append(
            {
                "id": requirement_id,
                "text": text,
                "importance": item.get("importance") or "mandatory",
                "category": item.get("category") or "",
                "category_label": item.get("category_label") or "",
                "topic": item.get("topic") or "",
                "coverage_question": item.get("coverage_question") or "",
                "source_chunk_id": item.get("source_chunk_id") or "",
            }
        )

    if normalized:
        return normalized

    fallback_requirements = fallback_requirements or []
    fallback_ids = fallback_ids or []
    for index, text in enumerate(fallback_requirements, start=1):
        cleaned = str(text or "").strip()
        if not cleaned:
            continue
        requirement_id = (
            str(fallback_ids[index - 1])
            if index - 1 < len(fallback_ids) and fallback_ids[index - 1]
            else f"section_requirement_{index}"
        )
        if requirement_id in seen:
            continue
        seen.add(requirement_id)
        normalized.append(
            {
                "id": requirement_id,
                "text": cleaned,
                "importance": "mandatory",
                "category": "",
                "category_label": "",
                "topic": "",
                "coverage_question": "",
                "source_chunk_id": "",
            }
        )

    return normalized


def format_requirement_items_for_prompt(
    items: list[dict[str, Any]],
    *,
    limit: int = 80,
) -> str:
    if not items:
        return ""

    lines = [
        "SECTION REQUIREMENT CHECKLIST:",
        "Cover each item explicitly. Keep the id in mind when self-checking coverage.",
    ]
    for index, item in enumerate(items[:limit], start=1):
        meta = " / ".join(
            str(part)
            for part in (item.get("importance"), item.get("category_label"))
            if part
        )
        suffix = f" ({meta})" if meta else ""
        lines.append(f"{index}. id={item['id']}{suffix}: {item['text']}")
        if item.get("coverage_question"):
            lines.append(f"   check: {item['coverage_question']}")
    if len(items) > limit:
        lines.append(f"... plus {len(items) - limit} more checklist items.")
    return "\n".join(lines)


def assess_requirement_coverage(
    generated_text: str,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    generated_tokens = set(_tokens(generated_text))
    coverage_items: list[dict[str, Any]] = []
    covered_ids: list[str] = []
    missing_ids: list[str] = []
    critical_missing_ids: list[str] = []

    for item in items:
        requirement_tokens = list(dict.fromkeys(_tokens(str(item.get("text") or ""))))
        matched_terms = sorted(set(requirement_tokens) & generated_tokens)
        missing_terms = [token for token in requirement_tokens if token not in matched_terms]
        window_terms, window_ratio = _best_window_matches(
            requirement_tokens,
            generated_text,
        )

        if not requirement_tokens:
            required_matches = 0
        elif len(requirement_tokens) <= 2:
            required_matches = 1
        elif len(requirement_tokens) <= 5:
            required_matches = max(2, math.ceil(len(requirement_tokens) * 0.6))
        else:
            required_matches = max(3, math.ceil(len(requirement_tokens) * 0.4))

        matched_ratio = (
            len(matched_terms) / len(requirement_tokens)
            if requirement_tokens
            else 1.0
        )
        required_window_matches = (
            0
            if required_matches <= 1
            else max(2, math.ceil(required_matches * 0.7))
        )
        globally_covered = len(matched_terms) >= required_matches
        locally_coherent = len(window_terms) >= required_window_matches
        status = "covered" if globally_covered and locally_coherent else "missing"
        requirement_id = str(item.get("id"))
        if status == "covered":
            covered_ids.append(requirement_id)
        else:
            missing_ids.append(requirement_id)
            if (
                not matched_terms
                and item.get("importance") in {"mandatory", "scored", "scope"}
            ):
                critical_missing_ids.append(requirement_id)

        coverage_items.append(
            {
                "id": requirement_id,
                "text": item.get("text"),
                "importance": item.get("importance"),
                "status": status,
                "matched_terms": matched_terms,
                "missing_terms": missing_terms,
                "matched_ratio": round(matched_ratio, 3),
                "coherent_matched_terms": window_terms,
                "coherent_matched_ratio": round(window_ratio, 3),
                "required_match_count": required_matches,
                "required_coherent_match_count": required_window_matches,
            }
        )

    return {
        "total": len(items),
        "covered": len(covered_ids),
        "missing": len(missing_ids),
        "covered_ids": covered_ids,
        "missing_ids": missing_ids,
        "critical_missing_ids": critical_missing_ids,
        "items": coverage_items,
    }
