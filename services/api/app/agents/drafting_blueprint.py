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

RESPONSE_COVERAGE_CONTRACT = [
    "action: what will be done in concrete operational terms",
    "responsible role: who prepares, performs, checks, approves, or reports it",
    "control point: how compliance or quality is checked during execution",
    "evidence record: what protocol, report, log, schedule entry, approval, or deliverable proves execution",
    "sequence link: where the response sits in the work phases, dependencies, handover, or acceptance flow",
    "source-specific detail: which tender phrase, project part, risk, measure, institution, or deliverable makes this requirement unique",
]

BLUEPRINT_GLOBAL_INSTRUCTIONS = [
    "Use the groups below as the section's internal structure.",
    "Write Bulgarian subheadings for each relevant group unless the section title already provides a stronger tender-specific structure.",
    "Under every group, cover every listed requirement id explicitly.",
    "Do not merge unrelated requirement ids into one vague paragraph.",
    "For every requirement response, state the action, responsible role, control or evidence record, and sequence/deliverable link when supported by sources.",
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


def _response_plan_for_item(item: dict[str, Any]) -> dict[str, Any]:
    category = _clean(item.get("category"))
    topic = _topic_key(item)
    source_ref = _clean(item.get("source_ref")) or _clean(item.get("source_chunk_id"))
    plan = {
        "requirement_id": _clean(item.get("id")),
        "topic": topic,
        "expected_response": (
            "Write a developed Bulgarian passage that names the concrete action, "
            "responsible role, control point, evidence record, and link to the "
            "work sequence or deliverable when the sources support it."
        ),
        "coverage_contract": RESPONSE_COVERAGE_CONTRACT,
    }
    if category in CATEGORY_GUIDANCE:
        plan["category_focus"] = category
    if source_ref:
        plan["source_ref"] = source_ref
    return plan


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
                "requirement_ids": [],
                "requirements": [],
                "additional_requirements": [],
                "topics": [],
                "topic_details": [],
                "guidance": _guidance_for_group(_clean(item.get("category"))),
            },
        )
        topic = _topic_key(item)
        if topic and topic not in group["topics"]:
            group["topics"].append(topic)
            group["topic_details"].append({"topic": topic, "requirement_ids": []})
        if requirement_id not in group["requirement_ids"]:
            group["requirement_ids"].append(requirement_id)
        if len(group["requirements"]) < max_items_per_group:
            group["requirements"].append(
                {
                    "id": requirement_id,
                    "text": text,
                    "importance": _clean(item.get("importance")) or "mandatory",
                    "response_plan": _response_plan_for_item(item),
                }
            )
        else:
            group["additional_requirements"].append(
                {
                    "id": requirement_id,
                    "topic": topic,
                    "text": _clean(item.get("text"), limit=180),
                }
            )
        for topic_detail in group["topic_details"]:
            if (
                topic_detail["topic"] == topic
                and requirement_id not in topic_detail["requirement_ids"]
            ):
                topic_detail["requirement_ids"].append(requirement_id)
                break

    all_groups = list(groups_by_key.values())
    groups = all_groups[:max_groups]
    additional_groups = [
        {
            "category": group.get("category"),
            "label": group.get("label"),
            "requirement_ids": group.get("requirement_ids") or [],
            "topics": group.get("topics") or [],
            "requirements": [
                {
                    "id": item.get("id"),
                    "text": _clean(item.get("text"), limit=180),
                    "importance": item.get("importance"),
                }
                for item in (group.get("requirements") or [])
                if isinstance(item, dict) and item.get("id")
            ],
            "additional_requirements": group.get("additional_requirements") or [],
        }
        for group in all_groups[max_groups:]
    ]
    return {
        "section_title": _clean(section_title),
        "global_instructions": BLUEPRINT_GLOBAL_INSTRUCTIONS,
        "context_cues": _context_cues(project_grounding_context),
        "groups": groups,
        "additional_groups": additional_groups,
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
            response_plan = item.get("response_plan")
            if isinstance(response_plan, dict):
                expected_response = _clean(response_plan.get("expected_response"))
                if expected_response:
                    lines.append(f"     response plan: {expected_response}")
                coverage_contract = [
                    _clean(item)
                    for item in response_plan.get("coverage_contract") or []
                    if _clean(item)
                ]
                if coverage_contract:
                    lines.append("     coverage contract:")
                    for contract_item in coverage_contract:
                        lines.append(f"       - {contract_item}")
                category_focus = _clean(response_plan.get("category_focus"))
                if category_focus:
                    lines.append(f"     category focus: {category_focus}")
                source_ref = _clean(response_plan.get("source_ref"))
                if source_ref:
                    lines.append(f"     source reference: {source_ref}")
        additional_requirements = [
            item
            for item in group.get("additional_requirements") or []
            if isinstance(item, dict) and item.get("id")
        ]
        if additional_requirements:
            lines.append(
                "   - additional requirements to cover explicitly "
                "(compact list beyond the detailed response-plan limit):"
            )
            for item in additional_requirements:
                topic = _clean(item.get("topic"))
                suffix = f" [{topic}]" if topic else ""
                text = _clean(item.get("text"), limit=180)
                lines.append(f"     - {item.get('id')}{suffix}: {text}")

    additional_groups = [
        group
        for group in blueprint.get("additional_groups") or []
        if isinstance(group, dict) and group.get("requirement_ids")
    ]
    if additional_groups:
        lines.append("Additional blueprint groups to cover explicitly:")
        for group in additional_groups:
            label = _clean(group.get("label")) or _clean(group.get("category"))
            requirement_ids = ", ".join(
                str(item)
                for item in group.get("requirement_ids") or []
                if item
            )
            suffix = f" ({requirement_ids})" if requirement_ids else ""
            lines.append(f"- {label}{suffix}")
            topics = [
                _clean(topic)
                for topic in group.get("topics") or []
                if _clean(topic)
            ]
            if topics:
                lines.append(f"  topics: {', '.join(topics[:8])}")
            for item in group.get("requirements") or []:
                if not isinstance(item, dict) or not item.get("id"):
                    continue
                lines.append(
                    "  - requirement "
                    f"{item.get('id')} ({item.get('importance')}): "
                    f"{_clean(item.get('text'), limit=180)}"
                )
            extra = [
                item
                for item in group.get("additional_requirements") or []
                if isinstance(item, dict) and item.get("id")
            ]
            if extra:
                lines.append(
                    "  - plus compact requirements: "
                    + ", ".join(str(item.get("id")) for item in extra[:10])
                )

    return "\n".join(lines)
