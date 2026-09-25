"""Requirement conservation for the content plan (card K-03).

Every confirmed, applicable proposal requirement must end in exactly one
explicit disposition; nothing may silently drop out of the denominator:

- ``target``          at least one generatable plan point carries its criteria;
- ``global_control``  a rule applied across the proposal (prohibitions, format
                      and cross-reference constraints, evaluation rules, the
                      human-supplied schedule), not a decorative chapter;
- ``excluded``        a human decision with a recorded reason;
- ``unresolved``      no receiver yet — visible, and it blocks approval.

Parent requirements that land on a point with children are redistributed to
an explicit receiver among the generatable descendants (only leaves are
drafted), so a parent obligation reaches a concrete writer and verifier.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Iterable

PROPOSAL_SCOPES = {"proposal_content", "proposal_format", "evaluation_rule"}
RULE_KINDS = {"prohibition", "format"}
DISPOSITIONS = ("target", "global_control", "excluded", "unresolved")
RESOLUTION_ACTIONS = {"assign", "exclude", "global_control"}

_TOKEN_RE = re.compile(r"[а-яa-z0-9]{3,}", re.UNICODE)
_STOP = {
    "за", "на", "по", "при", "към", "като", "или", "със", "във", "участникът",
    "следва", "трябва", "техническото", "предложение", "изпълнение", "поръчката",
}


def _tokens(*values: Any) -> set[str]:
    text = " ".join(str(value or "") for value in values).casefold()
    return {token for token in _TOKEN_RE.findall(text) if token not in _STOP}


def _criteria(item: Any) -> list[dict[str, Any]]:
    return [
        entry
        for entry in (getattr(item, "acceptance_criteria_json", None) or [])
        if isinstance(entry, dict)
    ]


def _children_by_parent(items: Iterable[Any]) -> dict[str | None, list[Any]]:
    grouped: dict[str | None, list[Any]] = defaultdict(list)
    for item in items:
        grouped[getattr(item, "parent_id", None)].append(item)
    for children in grouped.values():
        children.sort(key=lambda node: (getattr(node, "order_index", 0) or 0, str(node.id)))
    return grouped


def _generatable_descendants(item: Any, children: dict[str | None, list[Any]]) -> list[Any]:
    found: list[Any] = []
    stack = list(reversed(children.get(item.id, [])))
    while stack:
        node = stack.pop()
        if getattr(node, "generation_uid", None):
            found.append(node)
        stack.extend(reversed(children.get(node.id, [])))
    return found


def _best_receiver(criterion: dict[str, Any], candidates: list[Any]) -> Any:
    wanted = _tokens(criterion.get("text"), criterion.get("requirement_text"))
    best = candidates[0]
    best_score = -1.0
    for candidate in candidates:
        offered = _tokens(
            getattr(candidate, "title", ""),
            *(entry.get("text") for entry in _criteria(candidate)),
        )
        score = len(wanted & offered) / max(1, len(wanted))
        if score > best_score:
            best, best_score = candidate, score
    return best


def redistribute_parent_criteria(items: list[Any]) -> list[dict[str, Any]]:
    """Move criteria off non-generatable parents onto a generatable receiver.

    Returns one record per moved criterion (for tests and diagnostics).
    """
    children = _children_by_parent(items)
    moved: list[dict[str, Any]] = []
    for item in items:
        if getattr(item, "generation_uid", None):
            continue
        criteria = _criteria(item)
        if not criteria:
            continue
        receivers = _generatable_descendants(item, children)
        if not receivers:
            continue
        kept: list[dict[str, Any]] = []
        for criterion in criteria:
            if not criterion.get("requirement_id"):
                # Synthetic "heading was developed" criteria stay with the parent.
                kept.append(criterion)
                continue
            receiver = _best_receiver(criterion, receivers)
            inherited = {
                **criterion,
                "inherited_from_item_id": item.id,
                "receiver_rule": "parent_to_best_child",
            }
            existing_ids = {entry.get("id") for entry in _criteria(receiver)}
            if inherited.get("id") not in existing_ids:
                receiver.acceptance_criteria_json = [*_criteria(receiver), inherited]
            source = {
                "requirement_id": criterion.get("requirement_id"),
                "source_quote": criterion.get("source_quote"),
                "inherited_from_item_id": item.id,
            }
            quotes = list(getattr(receiver, "source_quotes_json", None) or [])
            if source not in quotes:
                receiver.source_quotes_json = [*quotes, source]
            moved.append(
                {
                    "criterion_id": criterion.get("id"),
                    "requirement_id": criterion.get("requirement_id"),
                    "from_item_id": item.id,
                    "to_item_id": receiver.id,
                }
            )
        item.acceptance_criteria_json = kept
    return moved


def _requirement_record(requirement: Any) -> dict[str, Any]:
    return {
        "requirement_id": str(requirement.id),
        "kind": getattr(requirement, "kind", None),
        "scope": getattr(requirement, "scope", None),
        "text": getattr(requirement, "normalized_text", None),
        "source_quote": getattr(requirement, "source_quote", None),
        "source_file_id": getattr(requirement, "source_file_id", None),
        "source_page": getattr(requirement, "source_page", None),
        "acceptance_criteria": list(getattr(requirement, "acceptance_criteria_json", None) or []),
    }


def _is_rule(requirement: Any) -> bool:
    return (
        getattr(requirement, "kind", None) in RULE_KINDS
        or getattr(requirement, "scope", None) in {"proposal_format", "evaluation_rule"}
    )


def _rule_category(requirement: Any) -> str:
    if getattr(requirement, "scope", None) == "evaluation_rule" or getattr(
        requirement, "kind", None
    ) == "evaluation":
        return "evaluation"
    if getattr(requirement, "kind", None) == "prohibition":
        return "prohibition"
    if getattr(requirement, "kind", None) == "cross_ref":
        return "cross_reference"
    return "format"


def compute_dispositions(
    items: list[Any],
    requirements: list[Any],
    resolutions: dict[str, dict[str, Any]] | None = None,
    *,
    schedule_item_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Account for every confirmed applicable requirement exactly once."""
    resolutions = resolutions or {}
    schedule_item_ids = schedule_item_ids or set()
    targets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    placed_elsewhere: dict[str, list[str]] = defaultdict(list)
    for item in items:
        for criterion in _criteria(item):
            requirement_id = str(criterion.get("requirement_id") or "")
            if not requirement_id:
                continue
            if getattr(item, "generation_uid", None):
                entry = {
                    "item_id": item.id,
                    "number": getattr(item, "number", ""),
                    "title": getattr(item, "title", ""),
                    "criterion_id": criterion.get("id"),
                }
                if entry not in targets[requirement_id]:
                    targets[requirement_id].append(entry)
            else:
                placed_elsewhere[requirement_id].append(item.id)

    dispositions: list[dict[str, Any]] = []
    global_controls: list[dict[str, Any]] = []
    for requirement in requirements:
        if getattr(requirement, "scope", None) not in PROPOSAL_SCOPES:
            continue
        record = _requirement_record(requirement)
        requirement_id = record["requirement_id"]
        resolution = resolutions.get(requirement_id) or {}
        action = resolution.get("action")
        is_rule = _is_rule(requirement)
        on_schedule = any(
            item_id in schedule_item_ids for item_id in placed_elsewhere.get(requirement_id, [])
        )
        if action == "exclude":
            disposition = "excluded"
        elif targets.get(requirement_id):
            disposition = "target"
        elif action == "global_control" or is_rule or on_schedule:
            disposition = "global_control"
        else:
            disposition = "unresolved"
        entry = {
            **record,
            "disposition": disposition,
            "targets": targets.get(requirement_id, []),
            "placed_on_non_generatable_items": placed_elsewhere.get(requirement_id, []),
            "resolution": resolution or None,
        }
        dispositions.append(entry)
        if disposition == "global_control" or (disposition == "target" and is_rule):
            global_controls.append(
                {
                    **record,
                    "category": "schedule" if on_schedule and not is_rule else _rule_category(requirement),
                    "also_targeted": bool(targets.get(requirement_id)),
                }
            )

    counts = {name: 0 for name in DISPOSITIONS}
    for entry in dispositions:
        counts[entry["disposition"]] += 1
    return {
        "dispositions": dispositions,
        "global_controls": global_controls,
        "summary": {
            "total": len(dispositions),
            **counts,
            "unresolved_requirement_ids": [
                entry["requirement_id"]
                for entry in dispositions
                if entry["disposition"] == "unresolved"
            ],
        },
    }
