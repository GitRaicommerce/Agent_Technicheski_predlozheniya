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


OPERATIONAL_COVERAGE_CATEGORIES = {
    "communication",
    "documentation",
    "environment",
    "quality",
    "risk",
    "safety",
}

OPERATIONAL_DETAIL_CUES = (
    "acceptance",
    "communication",
    "control",
    "coordination",
    "corrective",
    "documentation",
    "environment",
    "escalation",
    "inspection",
    "monitoring",
    "protocol",
    "quality",
    "record",
    "reporting",
    "risk",
    "safety",
    "\u043a\u0430\u0447\u0435\u0441\u0442\u0432",
    "\u043a\u043e\u043d\u0442\u0440\u043e\u043b",
    "\u0440\u0438\u0441\u043a",
    "\u0431\u0435\u0437\u043e\u043f\u0430\u0441",
    "\u043a\u043e\u043c\u0443\u043d\u0438\u043a\u0430\u0446",
    "\u043a\u043e\u043e\u0440\u0434\u0438\u043d\u0430\u0446",
    "\u043e\u043a\u043e\u043b\u043d\u0430",
    "\u0441\u0440\u0435\u0434\u0430",
    "\u043e\u0442\u043f\u0430\u0434",
    "\u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442",
    "\u043f\u0440\u043e\u0442\u043e\u043a\u043e\u043b",
    "\u0437\u0430\u043f\u0438\u0441",
    "\u043e\u0442\u0447\u0435\u0442",
    "\u043f\u0440\u0438\u0435\u043c",
    "\u043f\u0440\u043e\u0432\u0435\u0440",
    "\u043c\u043e\u043d\u0438\u0442\u043e\u0440",
    "\u0435\u0441\u043a\u0430\u043b\u0430\u0446",
    "\u043a\u043e\u0440\u0435\u043a\u0442",
)

OPERATIONAL_SIGNAL_TERMS = (
    "action",
    "approval",
    "acceptance",
    "control",
    "corrective",
    "document",
    "evidence",
    "escalation",
    "inspection",
    "monitoring",
    "owner",
    "protocol",
    "record",
    "reporting",
    "responsible",
    "role",
    "sequence",
    "\u0434\u0435\u0439\u0441\u0442\u0432",
    "\u043e\u0434\u043e\u0431\u0440",
    "\u043f\u0440\u0438\u0435\u043c",
    "\u043a\u043e\u043d\u0442\u0440\u043e\u043b",
    "\u043a\u043e\u0440\u0435\u043a\u0442",
    "\u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442",
    "\u0434\u043e\u043a\u0430\u0437\u0430\u0442",
    "\u0435\u0441\u043a\u0430\u043b\u0430\u0446",
    "\u043f\u0440\u043e\u0432\u0435\u0440",
    "\u043c\u043e\u043d\u0438\u0442\u043e\u0440",
    "\u043e\u0442\u0433\u043e\u0432\u043e\u0440",
    "\u043f\u0440\u043e\u0442\u043e\u043a\u043e\u043b",
    "\u0437\u0430\u043f\u0438\u0441",
    "\u043e\u0442\u0447\u0435\u0442",
    "\u0440\u043e\u043b",
    "\u043f\u043e\u0441\u043b\u0435\u0434\u043e\u0432",
)

OPERATIONAL_EXECUTION_TERMS = (
    "applies",
    "assigns",
    "attaches",
    "completes",
    "defines",
    "documents",
    "executes",
    "follows",
    "implements",
    "keeps",
    "maintains",
    "monitors",
    "opens",
    "performs",
    "prepares",
    "records",
    "updates",
    "\u0432\u044a\u0437\u043b\u0430\u0433",
    "\u043e\u043f\u0440\u0435\u0434\u0435\u043b",
    "\u0438\u0437\u043f\u044a\u043b\u043d",
    "\u0438\u0437\u0432\u044a\u0440\u0448",
    "\u043f\u0440\u0438\u043b\u0430\u0433",
    "\u043e\u0441\u0438\u0433\u0443\u0440",
    "\u043e\u0440\u0433\u0430\u043d\u0438\u0437\u0438\u0440",
    "\u043f\u043e\u0434\u0433\u043e\u0442\u0432",
    "\u043f\u0440\u043e\u0432\u0435\u0440\u044f\u0432",
    "\u043a\u043e\u043d\u0442\u0440\u043e\u043b\u0438\u0440",
    "\u0441\u044a\u0441\u0442\u0430\u0432",
    "\u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u0438\u0440",
    "\u0437\u0430\u043f\u0438\u0441\u0432",
    "\u0432\u043e\u0434\u0438",
    "\u043f\u043e\u0434\u0434\u044a\u0440\u0436",
    "\u043c\u043e\u043d\u0438\u0442\u043e\u0440",
    "\u043f\u0440\u043e\u0441\u043b\u0435\u0434",
    "\u0430\u043a\u0442\u0443\u0430\u043b\u0438\u0437",
)

GENERIC_COVERAGE_TERMS = {
    "action",
    "actions",
    "control",
    "controls",
    "corrective",
    "describe",
    "evidence",
    "inspection",
    "monitoring",
    "protocol",
    "protocols",
    "quality",
    "record",
    "records",
    "responsible",
    "role",
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


def _operational_signal_terms(text: str) -> list[str]:
    normalized = _normalize(text)
    return sorted(
        {
            signal
            for signal in OPERATIONAL_SIGNAL_TERMS
            if signal in normalized
        }
    )


def _operational_execution_terms(text: str) -> list[str]:
    normalized = _normalize(text)
    return sorted(
        {
            signal
            for signal in OPERATIONAL_EXECUTION_TERMS
            if signal in normalized
        }
    )


def _distinctive_terms(tokens: list[str]) -> list[str]:
    return [
        token
        for token in tokens
        if token not in GENERIC_COVERAGE_TERMS
        and not any(signal == token for signal in OPERATIONAL_SIGNAL_TERMS)
    ]


def _requires_operational_detail(item: dict[str, Any]) -> bool:
    category = _normalize(item.get("category"))
    category_label = _normalize(item.get("category_label"))
    text = _normalize(item.get("text"))
    topic = _normalize(item.get("topic"))
    haystack = f"{category} {category_label} {topic} {text}"
    return any(
        category_name in haystack
        for category_name in OPERATIONAL_COVERAGE_CATEGORIES
    ) or any(
        cue in haystack
        for cue in OPERATIONAL_DETAIL_CUES
    )


def _best_window_matches(
    requirement_tokens: list[str],
    generated_text: str,
) -> tuple[list[str], float, str]:
    if not requirement_tokens:
        return [], 1.0, str(generated_text or "")

    best_matches: list[str] = []
    best_window = ""
    for window in _sentence_windows(generated_text):
        window_tokens = set(_tokens(window))
        matches = sorted(set(requirement_tokens) & window_tokens)
        if len(matches) > len(best_matches):
            best_matches = matches
            best_window = window

    return best_matches, len(best_matches) / len(requirement_tokens), best_window


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
        window_terms, window_ratio, best_window = _best_window_matches(
            requirement_tokens,
            generated_text,
        )
        operational_signals = _operational_signal_terms(best_window)
        operational_execution_signals = _operational_execution_terms(best_window)
        distinctive_terms = _distinctive_terms(requirement_tokens)
        distinctive_matches = sorted(set(distinctive_terms) & set(window_terms))
        requires_operational_detail = _requires_operational_detail(item)
        required_operational_signal_count = 2 if requires_operational_detail else 0
        required_operational_execution_signal_count = (
            1 if requires_operational_detail else 0
        )
        required_distinctive_count = 1 if len(distinctive_terms) >= 3 else 0

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
        operationally_developed = (
            len(operational_signals) >= required_operational_signal_count
            and len(operational_execution_signals)
            >= required_operational_execution_signal_count
        )
        distinctively_matched = (
            len(distinctive_matches) >= required_distinctive_count
        )
        status = (
            "covered"
            if (
                globally_covered
                and locally_coherent
                and operationally_developed
                and distinctively_matched
            )
            else "missing"
        )
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
                "distinctive_terms": distinctive_terms,
                "distinctive_matches": distinctive_matches,
                "required_distinctive_count": required_distinctive_count,
                "matched_ratio": round(matched_ratio, 3),
                "coherent_matched_terms": window_terms,
                "coherent_matched_ratio": round(window_ratio, 3),
                "required_match_count": required_matches,
                "required_coherent_match_count": required_window_matches,
                "operational_signals": operational_signals,
                "operational_execution_signals": operational_execution_signals,
                "requires_operational_detail": requires_operational_detail,
                "required_operational_signal_count": required_operational_signal_count,
                "required_operational_execution_signal_count": (
                    required_operational_execution_signal_count
                ),
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
