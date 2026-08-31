"""Deterministic Phase 4 generation units derived from an approved outline."""

from __future__ import annotations

import uuid
from typing import Any


def section_assembly_uid(section: dict[str, Any]) -> str:
    """Return a stable UUID for the assembled form of one top-level section."""
    identity = (
        section.get("content_plan_uid")
        or section.get("uid")
        or section.get("section_uid")
        or f"{section.get('number', '')}:{section.get('title', '')}"
    )
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"tp-ai:section-assembly:{identity}"))


def _collect_units(
    section: dict[str, Any],
    result: list[dict[str, Any]],
) -> None:
    uid = section.get("uid") or section.get("section_uid")
    if uid:
        result.append(section)
    for child in section.get("subsections") or section.get("children") or []:
        if isinstance(child, dict):
            _collect_units(child, result)


def build_generation_groups(
    sections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Group generatable subpoints by their top-level proposal section."""
    groups: list[dict[str, Any]] = []
    for root in sections:
        if not isinstance(root, dict):
            continue
        units: list[dict[str, Any]] = []
        _collect_units(root, units)
        if not units:
            continue
        has_children = bool(root.get("subsections") or root.get("children"))
        groups.append(
            {
                "root": root,
                "assembly_uid": section_assembly_uid(root),
                "requires_assembly": has_children or len(units) > 1,
                "units": units,
            }
        )
    return groups
