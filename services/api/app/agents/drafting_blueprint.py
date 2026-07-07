from __future__ import annotations

from typing import Any


CATEGORY_GUIDANCE: dict[str, list[str]] = {
    "scope": [
        "Start from the exact tender scope and project parts.",
        "Explain what is included, what deliverables are produced, and how scope gaps are controlled.",
    ],
    "methodology": [
        "Explain the execution method as a sequence of concrete actions.",
        "Tie each method step to a tender requirement, schedule task, or deliverable.",
    ],
    "organization": [
        "Describe roles, responsibilities, coordination rhythm, resources, and decision points.",
        "Make interfaces between teams, subcontractors, authority, supervision, and institutions explicit when applicable.",
    ],
    "schedule": [
        "Develop sequence, dependencies, durations, milestones, deliverables, review steps, and acceptance points.",
        "Use available schedule tasks as operational logic instead of generic timing promises.",
    ],
    "quality": [
        "Describe input, in-process, and final quality controls.",
        "Name records, protocols, inspections, responsible roles, nonconformity handling, and acceptance evidence.",
    ],
    "risk": [
        "For each risk, describe trigger, prevention, response action, owner, monitoring signal, and escalation path.",
        "Avoid generic risk promises; connect measures to the tender context and work sequence.",
    ],
    "communication": [
        "Describe communication channels, meeting cadence, reporting, escalation, and approval interfaces.",
        "Include coordination with the contracting authority, supervision, institutions, and internal teams where supported.",
    ],
    "safety": [
        "Describe health and safety, fire-safety, site access, responsibility, controls, and incident response.",
        "Connect safety measures to phases, documents, briefings, and acceptance records.",
    ],
    "environment": [
        "Describe dust, waste, soil, water, noise, transport, storage, and clean-up controls where relevant.",
        "Name records, responsible roles, monitoring points, and corrective actions.",
    ],
    "deliveries": [
        "Describe material approval, procurement, transport, storage, handover, traceability, and rejection controls.",
        "Tie deliveries to schedule dependencies and quality checks.",
    ],
    "documentation": [
        "Describe records, reports, protocols, executive documentation, document flow, and acceptance evidence.",
        "Name who prepares, checks, submits, approves, and archives each document type.",
    ],
    "warranty": [
        "Describe defect reporting, response times, investigation, correction, documentation, and communication.",
        "Tie warranty duties to acceptance records and responsible roles.",
    ],
    "compliance": [
        "Explain how normative, permit, coordination, and institutional requirements are checked and documented.",
        "Do not quote legislation generically; connect obligations to concrete actions and records.",
    ],
    "specific": [
        "Keep each tender-specific requirement as its own developed point.",
        "Do not hide unusual or one-off requirements inside generic methodology text.",
    ],
}

DEFAULT_GUIDANCE = [
    "Develop the requirement as a concrete operational paragraph.",
    "State action, responsible role, control, evidence record, and link to sequence or deliverable when possible.",
]

BLUEPRINT_GLOBAL_INSTRUCTIONS = [
    "Use the groups below as the section's internal structure.",
    "Write Bulgarian subheadings for each relevant group unless the section title already provides a stronger tender-specific structure.",
    "Under every group, cover every listed requirement id explicitly.",
    "Do not merge unrelated requirement ids into one vague paragraph.",
]


def _clean(value: Any, *, limit: int | None = None) -> str:
    text = " ".join(str(value or "").split())
    if limit is not None and len(text) > limit:
        return text[: limit - 3].rstrip() + "..."
    return text


def _group_label(item: dict[str, Any]) -> str:
    return (
        _clean(item.get("category_label"))
        or _clean(item.get("category"))
        or "Specific tender requirements"
    )


def _group_key(item: dict[str, Any]) -> str:
    return _clean(item.get("category")) or _group_label(item).lower()


def _topic_key(item: dict[str, Any]) -> str:
    return _clean(item.get("topic"), limit=120) or _clean(item.get("text"), limit=80)


def _guidance_for_group(category: str) -> list[str]:
    return CATEGORY_GUIDANCE.get(category, DEFAULT_GUIDANCE)


def _context_cues(project_grounding_context: dict[str, Any] | None) -> list[str]:
    if not isinstance(project_grounding_context, dict):
        return []

    cues: list[str] = []
    schedule = project_grounding_context.get("schedule")
    if isinstance(schedule, dict):
        for task in schedule.get("tasks") or []:
            if not isinstance(task, dict):
                continue
            name = _clean(task.get("name"), limit=180)
            if name:
                cues.append(f"schedule task: {name}")
            if len(cues) >= 4:
                break

    tender_chunks = project_grounding_context.get("tender_chunks") or []
    for chunk in tender_chunks:
        if not isinstance(chunk, dict):
            continue
        text = _clean(chunk.get("text"), limit=220)
        if text:
            cues.append(f"tender excerpt: {text}")
        if len(cues) >= 8:
            break

    return cues


def build_drafting_blueprint(
    *,
    section_title: str,
    requirement_items: list[dict[str, Any]],
    project_grounding_context: dict[str, Any] | None = None,
    max_groups: int = 10,
    max_items_per_group: int = 10,
) -> dict[str, Any]:
    groups_by_key: dict[str, dict[str, Any]] = {}

    for item in requirement_items:
        requirement_id = _clean(item.get("id"))
        text = _clean(item.get("text"), limit=320)
        if not requirement_id or not text:
            continue

        key = _group_key(item)
        group = groups_by_key.setdefault(
            key,
            {
                "category": _clean(item.get("category")) or key,
                "label": _group_label(item),
                "requirements": [],
                "topics": [],
                "topic_details": [],
                "guidance": _guidance_for_group(_clean(item.get("category"))),
            },
        )
        topic = _topic_key(item)
        if topic and topic not in group["topics"]:
            group["topics"].append(topic)
            group["topic_details"].append({"topic": topic, "requirement_ids": []})
        if len(group["requirements"]) < max_items_per_group:
            group["requirements"].append(
                {
                    "id": requirement_id,
                    "text": text,
                    "importance": _clean(item.get("importance")) or "mandatory",
                }
            )
        for topic_detail in group["topic_details"]:
            if (
                topic_detail["topic"] == topic
                and requirement_id not in topic_detail["requirement_ids"]
            ):
                topic_detail["requirement_ids"].append(requirement_id)
                break

    groups = list(groups_by_key.values())[:max_groups]
    return {
        "section_title": _clean(section_title),
        "global_instructions": BLUEPRINT_GLOBAL_INSTRUCTIONS,
        "context_cues": _context_cues(project_grounding_context),
        "groups": groups,
    }


def format_drafting_blueprint_for_prompt(blueprint: dict[str, Any]) -> str:
    groups = blueprint.get("groups") if isinstance(blueprint, dict) else None
    context_cues = blueprint.get("context_cues") if isinstance(blueprint, dict) else None
    if not groups and not context_cues:
        return ""

    lines = [
        "DRAFTING BLUEPRINT:",
        "Use this as the internal structure and self-check plan for the section.",
    ]
    for instruction in blueprint.get("global_instructions") or []:
        lines.append(f"- {instruction}")

    if context_cues:
        lines.append("Context cues to weave into the section:")
        for cue in context_cues:
            lines.append(f"- {cue}")

    for index, group in enumerate(groups or [], start=1):
        label = _clean(group.get("label")) or f"Group {index}"
        category = _clean(group.get("category"))
        suffix = f" [{category}]" if category and category != label else ""
        lines.append(f"{index}. Suggested subheading: {label}{suffix}")
        for guidance in group.get("guidance") or []:
            lines.append(f"   - develop: {guidance}")
        topic_details = [
            topic
            for topic in group.get("topic_details") or []
            if isinstance(topic, dict) and topic.get("topic")
        ]
        if topic_details:
            lines.append("   - required topic coverage:")
            for topic in topic_details:
                requirement_ids = ", ".join(
                    str(item)
                    for item in topic.get("requirement_ids") or []
                    if item
                )
                suffix = f" ({requirement_ids})" if requirement_ids else ""
                lines.append(f"     - {topic.get('topic')}{suffix}")
        for item in group.get("requirements") or []:
            lines.append(
                "   - requirement "
                f"{item.get('id')} ({item.get('importance')}): {item.get('text')}"
            )

    return "\n".join(lines)
