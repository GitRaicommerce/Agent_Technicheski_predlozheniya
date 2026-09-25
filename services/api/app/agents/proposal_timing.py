"""Timing guardrails for generated technical-proposal text.

Uploaded schedules often contain calendar dates only because planning software
needs an arbitrary project start.  Those dates are not contractual facts and
must not leak into a proposal whose actual start depends on contract signing or
another future instruction from the contracting authority.
"""

from __future__ import annotations

import re
from typing import Any


_MONTHS_BG = (
    "януари|февруари|март|април|май|юни|юли|август|"
    "септември|октомври|ноември|декември"
)

CONCRETE_CALENDAR_DATE_PATTERNS = (
    re.compile(
        r"(?<!\d)(?:0?[1-9]|[12]\d|3[01])[./-]"
        r"(?:0?[1-9]|1[0-2])[./-](?:\d{2}|\d{4})(?!\d)"
    ),
    re.compile(
        r"(?<!\d)(?:19|20)\d{2}-(?:0[1-9]|1[0-2])-"
        r"(?:0[1-9]|[12]\d|3[01])(?!\d)"
    ),
    re.compile(
        rf"(?<!\d)(?:0?[1-9]|[12]\d|3[01])\s+(?:{_MONTHS_BG})\s+"
        r"(?:19|20)\d{2}(?:\s*г\.?)?",
        re.IGNORECASE,
    ),
)

_CALENDAR_DATE_KEYS = {
    "date",
    "start",
    "finish",
    "end",
    "start_date",
    "finish_date",
    "end_date",
    "actual_start",
    "actual_finish",
    "baseline_start",
    "baseline_finish",
    "early_start",
    "early_finish",
    "late_start",
    "late_finish",
}


def find_concrete_calendar_dates(text: str | None) -> list[str]:
    """Return unique concrete day/month dates found in proposal text."""

    matches: list[str] = []
    for pattern in CONCRETE_CALENDAR_DATE_PATTERNS:
        for match in pattern.finditer(str(text or "")):
            value = match.group(0)
            if value not in matches:
                matches.append(value)
    return matches


def schedule_for_proposal(value: Any) -> Any:
    """Copy schedule data without non-contractual calendar anchors.

    Durations, task names, dependencies, resources and ordering are preserved.
    Date-shaped fragments embedded in free text are replaced so the model
    cannot mistake an arbitrary planning anchor for a contractual commitment.
    """

    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = str(key).strip().casefold().replace("-", "_").replace(" ", "_")
            if normalized_key in _CALENDAR_DATE_KEYS:
                continue
            cleaned[key] = schedule_for_proposal(item)
        return cleaned
    if isinstance(value, list):
        return [schedule_for_proposal(item) for item in value]
    if isinstance(value, tuple):
        return tuple(schedule_for_proposal(item) for item in value)
    if isinstance(value, str):
        cleaned = value
        for pattern in CONCRETE_CALENDAR_DATE_PATTERNS:
            cleaned = pattern.sub("[условна календарна дата премахната]", cleaned)
        return cleaned
    return value
