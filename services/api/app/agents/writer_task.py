"""WP-06: the exact accepted task for the selected writer (K-04, K-24 drafting).

One place builds what a writer receives for a plan unit — the approved
criteria (id, text, kind, source quote), the plan's global controls and the
evidence quotes used for retrieval — and selects the writer profile
(routine Sol / complex Astra) before dispatch, with a recorded reason.
"""

from __future__ import annotations

import re
from typing import Any

COMPLEX_TITLE_MARKERS = (
    "методолог",
    "технолог",
    "организац",
    "управление на риска",
    "контрол на качеството",
    "последователност",
    "етап",
    "мерки",
    "план за",
)
COMPLEX_CRITERIA_THRESHOLD = 6


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def approved_criteria(unit: dict[str, Any]) -> list[dict[str, Any]]:
    """The approved criteria of a plan unit exactly as stored in the plan."""
    criteria: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in unit.get("acceptance_criteria") or []:
        if not isinstance(entry, dict):
            continue
        criterion_id = _clean(entry.get("id"))
        text = _clean(entry.get("text"))
        if not criterion_id or not text or criterion_id in seen:
            continue
        seen.add(criterion_id)
        criteria.append(
            {
                "id": criterion_id,
                "text": text,
                "kind": entry.get("kind") or "content",
                "source_quote": entry.get("source_quote"),
                "requirement_id": entry.get("requirement_id") or None,
                "synthetic": bool(entry.get("synthetic")),
            }
        )
    return criteria


def evidence_quotes(unit: dict[str, Any], criteria: list[dict[str, Any]]) -> list[str]:
    quotes = [c["source_quote"] for c in criteria if c.get("source_quote")]
    for source in unit.get("source_quotes") or []:
        if isinstance(source, dict) and source.get("source_quote"):
            quotes.append(source["source_quote"])
    seen: set[str] = set()
    unique = []
    for quote in quotes:
        key = _clean(quote).casefold()
        if key and key not in seen:
            seen.add(key)
            unique.append(quote)
    return unique


def compact_global_controls(controls: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    compact = []
    for entry in controls or []:
        if not isinstance(entry, dict) or not entry.get("requirement_id"):
            continue
        compact.append(
            {
                "requirement_id": entry.get("requirement_id"),
                "category": entry.get("category"),
                "kind": entry.get("kind"),
                "text": _clean(entry.get("text")),
                "source_quote": entry.get("source_quote"),
            }
        )
    return compact


def select_writer_profile(unit: dict[str, Any], criteria: list[dict[str, Any]]) -> dict[str, str]:
    """Routine (Sol) or complex (Astra) writer, decided before dispatch.

    Complex: reusable technical methodology, a detailed target depth, many
    or cross-referencing criteria, or a methodology/organisation title. The
    choice depends on the task, never on the job phase.
    """
    guidance = unit.get("drafting_guidance") or {}
    title = _clean(unit.get("title")).casefold()
    reasons: list[str] = []
    if unit.get("content_kind") == "reuse":
        reasons.append("reusable technical methodology")
    instructions = " ".join(str(value) for value in guidance.get("instructions") or [])
    if "Целева дълбочина: detailed" in instructions:
        reasons.append("detailed target depth")
    real = [c for c in criteria if not c.get("synthetic")]
    if len(real) >= COMPLEX_CRITERIA_THRESHOLD:
        reasons.append(f"{len(real)} acceptance criteria")
    if any(c.get("kind") == "cross_ref" for c in real):
        reasons.append("cross-reference criterion")
    if any(marker in title for marker in COMPLEX_TITLE_MARKERS):
        reasons.append("methodology/organisation subject")
    if reasons:
        return {"role": "drafting_complex", "reason": "; ".join(reasons)}
    return {"role": "drafting_routine", "reason": "explicit task with few criteria"}


def format_criteria_for_prompt(criteria: list[dict[str, Any]]) -> str:
    if not criteria:
        return ""
    lines = [
        "APPROVED ACCEPTANCE CRITERIA (binding — the text is verified criterion by "
        "criterion after drafting, using these ids; a prohibition must never be "
        "violated):",
    ]
    for index, criterion in enumerate(criteria, start=1):
        quote = f' | source: "{_clean(criterion["source_quote"])[:400]}"' if criterion.get("source_quote") else ""
        lines.append(f"{index}. id={criterion['id']} [{criterion['kind']}]: {criterion['text']}{quote}")
    return "\n".join(lines)


def format_global_controls_for_prompt(controls: list[dict[str, Any]]) -> str:
    if not controls:
        return ""
    lines = [
        "GLOBAL CONTROLS (rules that apply to the whole proposal, including this text):",
    ]
    for control in controls:
        lines.append(f"- [{control.get('category') or control.get('kind')}] {control['text']}")
    return "\n".join(lines)
