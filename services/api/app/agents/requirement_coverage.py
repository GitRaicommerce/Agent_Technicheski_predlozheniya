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
                "category_label": item.get("category_label") or "",
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
                "category_label": "",
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

        if not requirement_tokens:
            required_matches = 0
        elif len(requirement_tokens) <= 2:
            required_matches = 1
        else:
            required_matches = max(2, math.ceil(len(requirement_tokens) * 0.35))

        status = "covered" if len(matched_terms) >= required_matches else "missing"
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
                "required_match_count": required_matches,
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
