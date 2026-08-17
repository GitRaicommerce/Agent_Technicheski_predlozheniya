"""Phase 2: deterministic, reviewable content plan from Understanding artifacts."""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import func, select, update

from app.core.models import (
    ContentPlanItem,
    ProjectFactSheet,
    RequirementRegister,
    TpOutline,
    WbsItem,
)


PROPOSAL_SCOPES = {"proposal_content", "proposal_format", "evaluation_rule"}
GENERIC_ROOTS = (
    "техническо предложение",
    "предложение за изпълнение на поръчката",
    "оценка на техническото предложение",
)
EXCLUDED_ROOTS = (
    "ценово предложение",
    "доказателства за технически и професионални способности",
    "оценка и класиране",
)
PROGRAM_ROOT = "Програма за организация и изпълнение на поръчката"
SCHEDULE_ROOT = "Линеен график и ресурсни диаграми"
FORMAL_ROOT = "Формални изисквания и приложения"
CONTROL_ROOT = "Контролни критерии за допустимост и оценяване"
STOPWORDS = {
    "за", "на", "по", "и", "в", "с", "от", "до", "при", "към", "се",
    "да", "е", "са", "или", "като", "този", "тази", "това", "всички",
    "техническо", "предложение", "поръчката", "програма", "изпълнение",
}

CATEGORY_LABELS = {
    "scope": "Обхват",
    "methodology": "Методология",
    "organization": "Организация и отговорности",
    "schedule": "График и срокове",
    "quality": "Контрол на качеството",
    "risk": "Управление на риска",
    "communication": "Комуникация и координация",
    "safety": "Безопасност и здраве",
    "environment": "Околна среда",
    "deliveries": "Доставки",
    "documentation": "Документация и приемане",
    "compliance": "Съответствие",
    "specific": "Специфично изискване",
}


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()


def _normalized(value: Any) -> str:
    return _clean(value).casefold()


def _title(value: Any) -> str:
    return re.sub(r"^\d+(?:\.\d+)*[.)]?\s*", "", _clean(value)).strip(" .:-")


def _tokens(value: Any) -> set[str]:
    return {
        token
        for token in re.findall(r"[а-яa-z0-9]{3,}", _normalized(value))
        if token not in STOPWORDS
    }


def _requirement_path(item: RequirementRegister) -> list[str]:
    raw_path = [
        _clean(part)
        for part in (item.proposal_path_json or [])
        if _clean(part)
    ]
    if not raw_path and item.target_section_hint:
        raw_path = [_clean(item.target_section_hint)]
    if not raw_path:
        raw_path = ["Други задължителни изисквания"]

    first = _normalized(raw_path[0])
    if any(marker in first for marker in EXCLUDED_ROOTS):
        return []
    while raw_path and any(marker == _normalized(raw_path[0]) for marker in GENERIC_ROOTS):
        raw_path.pop(0)
    path = [_title(part) for part in raw_path if _title(part)]
    if not path:
        path = ["Основен документ"]

    first = _normalized(path[0])
    if first == _normalized(PROGRAM_ROOT):
        return [PROGRAM_ROOT, *path[1:]]
    if item.scope == "evaluation_rule" or any(
        marker in first
        for marker in ("оценяване", "допустимост", "програма и график", "оценка")
    ):
        return [CONTROL_ROOT, *path]
    if any(
        marker in first
        for marker in ("линеен график", "линеен календарен", "подробен линеен")
    ):
        return [SCHEDULE_ROOT, *path[1:]]
    if any(
        marker in first
        for marker in (
            "организация", "управление на риска", "риск", "доставка",
            "качеств", "околна среда", "мерки", "методи и дейности",
            "технически решения", "срокове за изпълнение",
        )
    ):
        return [PROGRAM_ROOT, *path]
    return [FORMAL_ROOT, *path]


def _section_order(item: ContentPlanItem) -> tuple[int, int, str]:
    title = _normalized(item.title)
    root_priorities = {
        _normalized(PROGRAM_ROOT): 1,
        _normalized(SCHEDULE_ROOT): 2,
        _normalized(FORMAL_ROOT): 3,
        _normalized(CONTROL_ROOT): 4,
    }
    if title in root_priorities:
        return root_priorities[title], item.order_index, title
    priorities = (
        (1, "концепция"),
        (2, "разработване на инвестиционен проект"),
        (3, "авторски надзор"),
        (4, "строително-монтаж"),
        (5, "организация на ресурсите"),
        (6, "доставка"),
        (7, "управление на риска"),
        (8, "околна среда"),
        (9, "качеств"),
        (10, "срок"),
        (11, "график"),
        (12, "прилож"),
    )
    priority = next((value for value, marker in priorities if marker in title), 50)
    return priority, item.order_index, title


def _category(title: str, text: str) -> str:
    haystack = _normalized(f"{title} {text}")
    rules = (
        ("risk", ("риск",)),
        ("quality", ("качеств", "контрол")),
        ("schedule", ("график", "срок", "последователност", "етапност")),
        ("organization", ("организац", "екип", "експерт", "персонал", "отговорност")),
        ("communication", ("комуникац", "координац", "субординац")),
        ("safety", ("безопасност", "здраве", "пожар")),
        ("environment", ("околна среда", "отпад", "прах", "шум", "замърс")),
        ("deliveries", ("достав", "материал", "складиране")),
        ("documentation", ("документ", "протокол", "отчет", "приемане")),
        ("methodology", ("технолог", "метод", "подход", "дейност")),
        ("scope", ("обхват", "предмет")),
        ("compliance", ("съответств", "норматив", "изискван")),
    )
    for category, markers in rules:
        if any(marker in haystack for marker in markers):
            return category
    return "specific"


def _content_kind(item: RequirementRegister, path: list[str]) -> str:
    classification_path = path[1:] if path and path[0] in {
        PROGRAM_ROOT, SCHEDULE_ROOT, FORMAL_ROOT, CONTROL_ROOT,
    } else path
    text = _normalized(f"{' '.join(classification_path)} {item.normalized_text}")
    if item.kind in {"format", "prohibition", "cross_ref"}:
        return "mixed"
    has_specific_fact = bool(re.search(r"\b\d+(?:[.,]\d+)?\b", text)) or any(
        marker in text
        for marker in ("обекта", "проектна част", "линеен график", "възложителя")
    )
    has_reusable_method = any(
        marker in text
        for marker in (
            "метод", "подход", "организац", "комуникац", "координац",
            "контрол", "качеств", "риск", "безопасност", "околна среда",
            "достав", "технолог", "гаранцион",
        )
    )
    if has_specific_fact and has_reusable_method:
        return "mixed"
    if has_specific_fact:
        return "specific"
    if has_reusable_method:
        return "reuse"
    return "mixed"


def _fact_links(title: str, criteria: list[dict[str, Any]], facts: dict[str, Any]) -> list[str]:
    text = _normalized(" ".join([title, *[str(item.get("text") or "") for item in criteria]]))
    candidates = {
        "team": ("екип", "експерт", "персонал", "проектант", "ръководител"),
        "deadlines": ("срок", "график", "продължителност"),
        "stages": ("етап", "последователност", "фаза"),
        "project_parts": ("проектна част", "проектиране", "проектант"),
        "key_parameters": ("парамет", "количеств", "размер", "дължина"),
        "subject": ("предмет", "обект", "обхват"),
    }
    return [
        key
        for key, markers in candidates.items()
        if key in facts and any(marker in text for marker in markers)
    ]


def _wbs_links(title: str, criteria: list[dict[str, Any]], wbs_items: list[WbsItem]) -> list[str]:
    plan_tokens = _tokens(" ".join([title, *[str(item.get("text") or "") for item in criteria]]))
    scored: list[tuple[int, str]] = []
    for item in wbs_items:
        if item.status == "rejected":
            continue
        overlap = len(plan_tokens & _tokens(f"{item.title} {item.description or ''}"))
        if overlap:
            scored.append((overlap, item.id))
    return [item_id for _, item_id in sorted(scored, key=lambda pair: (-pair[0], pair[1]))[:8]]


def _item_outline_payload(item: ContentPlanItem, children: list[dict[str, Any]]) -> dict[str, Any]:
    criteria = [entry for entry in (item.acceptance_criteria_json or []) if isinstance(entry, dict)]
    requirement_map: dict[str, str] = {}
    for entry in criteria:
        requirement_id = str(entry.get("requirement_id") or "").strip()
        requirement_text = _clean(entry.get("requirement_text"))
        if requirement_id and requirement_text:
            requirement_map.setdefault(requirement_id, requirement_text)
    requirement_ids = list(requirement_map)
    requirements = list(requirement_map.values())
    checklist = []
    for requirement_id, requirement_text in requirement_map.items():
        category = _category(item.title, requirement_text)
        checklist.append({
            "id": requirement_id,
            "text": requirement_text,
            "importance": "mandatory",
            "category": category,
            "category_label": CATEGORY_LABELS[category],
            "topic": item.title,
            "coverage_question": f"Описано ли е изпълнението на: {requirement_text}",
            "source_chunk_id": "",
        })
    payload: dict[str, Any] = {
        "content_plan_uid": item.uid,
        "number": item.number,
        "title": item.title,
        "required": bool(criteria),
        "requirements": requirements,
        "requirement_ids": requirement_ids,
        "requirement_checklist_items": checklist,
        "acceptance_criteria": criteria,
        "source_quotes": item.source_quotes_json or [],
        "content_kind": item.content_kind,
        "linked_wbs_ids": item.linked_wbs_ids or [],
        "linked_fact_keys": item.linked_fact_keys or [],
        "subsections": children,
        "include_in_document": bool(
            item.generation_uid
            or any(child.get("include_in_document") for child in children)
        ),
    }
    if item.generation_uid:
        payload["uid"] = item.generation_uid
    return payload


async def sync_outline_from_content_plan(outline_id: str, db) -> TpOutline:
    outline = await db.get(TpOutline, outline_id)
    if not outline:
        raise ValueError("Content plan outline not found")
    result = await db.execute(
        select(ContentPlanItem)
        .where(ContentPlanItem.outline_id == outline_id)
        .order_by(ContentPlanItem.order_index, ContentPlanItem.id)
    )
    items = list(result.scalars().all())
    children_by_parent: dict[str | None, list[ContentPlanItem]] = defaultdict(list)
    for item in items:
        children_by_parent[item.parent_id].append(item)

    def build(parent_id: str | None) -> list[dict[str, Any]]:
        return [
            _item_outline_payload(item, build(item.id))
            for item in children_by_parent.get(parent_id, [])
        ]

    generatable = sum(1 for item in items if item.generation_uid)
    outline.outline_json = {
        "source": "understanding_content_plan",
        "content_plan_version": 1,
        "understanding_status": (outline.outline_json or {}).get("understanding_status", {}),
        "sections": build(None),
        "coverage_summary": {
            "content_plan_items": len(items),
            "generatable_items": generatable,
            "requirement_ids": sorted({
                str(entry.get("requirement_id"))
                for item in items
                for entry in (item.acceptance_criteria_json or [])
                if isinstance(entry, dict) and entry.get("requirement_id")
            }),
        },
    }
    await db.flush()
    return outline


async def build_content_plan(project_id: str, db) -> TpOutline:
    requirement_result = await db.execute(
        select(RequirementRegister)
        .where(
            RequirementRegister.project_id == project_id,
            RequirementRegister.status == "confirmed",
            RequirementRegister.scope.in_(PROPOSAL_SCOPES),
        )
        .order_by(RequirementRegister.source_page, RequirementRegister.created_at, RequirementRegister.id)
    )
    requirements = list(requirement_result.scalars().all())
    if not requirements:
        raise ValueError("Потвърдете изискванията към ТП преди създаване на плана.")

    wbs_result = await db.execute(
        select(WbsItem)
        .where(WbsItem.project_id == project_id, WbsItem.status != "rejected")
        .order_by(WbsItem.order_index, WbsItem.id)
    )
    wbs_items = list(wbs_result.scalars().all())
    fact_result = await db.execute(
        select(ProjectFactSheet)
        .where(ProjectFactSheet.project_id == project_id)
        .order_by(ProjectFactSheet.version.desc())
        .limit(1)
    )
    fact_sheet = fact_result.scalar_one_or_none()
    facts = fact_sheet.facts_json if fact_sheet and isinstance(fact_sheet.facts_json, dict) else {}
    understanding_status = {
        "requirements_confirmed": True,
        "wbs_confirmed": bool(wbs_items) and all(item.status == "confirmed" for item in wbs_items),
        "fact_sheet_confirmed": bool(fact_sheet and fact_sheet.status == "confirmed"),
    }

    version_result = await db.execute(
        select(func.max(TpOutline.version)).where(TpOutline.project_id == project_id)
    )
    version = int(version_result.scalar_one_or_none() or 0) + 1
    await db.execute(
        update(TpOutline)
        .where(TpOutline.project_id == project_id, TpOutline.status_locked.is_(True))
        .values(status_locked=False, approved_at=None)
    )
    outline = TpOutline(
        project_id=project_id,
        outline_json={"source": "understanding_content_plan", "sections": []},
        status_locked=False,
        version=version,
    )
    db.add(outline)
    await db.flush()

    nodes: dict[tuple[str | None, str], ContentPlanItem] = {}
    insertion = 0
    for requirement in requirements:
        path = _requirement_path(requirement)
        if not path:
            continue
        parent_id: str | None = None
        for depth, path_title in enumerate(path):
            key = (parent_id, _normalized(path_title))
            item = nodes.get(key)
            if item is None:
                insertion += 1
                item = ContentPlanItem(
                    id=str(uuid.uuid4()),
                    project_id=project_id,
                    outline_id=outline.id,
                    parent_id=parent_id,
                    uid=str(uuid.uuid4()),
                    number="",
                    title=path_title,
                    source_quotes_json=[],
                    acceptance_criteria_json=[],
                    content_kind="mixed",
                    linked_wbs_ids=[],
                    linked_fact_keys=[],
                    order_index=insertion,
                    status="draft",
                    generation_uid=None,
                )
                db.add(item)
                nodes[key] = item
            parent_id = item.id

        leaf = item
        source_entry = {
            "requirement_id": requirement.id,
            "source_file_id": requirement.source_file_id,
            "source_page": requirement.source_page,
            "source_quote": requirement.source_quote,
        }
        if source_entry not in leaf.source_quotes_json:
            leaf.source_quotes_json = [*leaf.source_quotes_json, source_entry]
        criteria_texts = [
            _clean(value)
            for value in (requirement.acceptance_criteria_json or [])
            if _clean(value)
        ] or [_clean(requirement.normalized_text)]
        criteria = list(leaf.acceptance_criteria_json)
        for index, text in enumerate(criteria_texts, start=1):
            criterion = {
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{requirement.id}:{index}:{text}")),
                "text": text,
                "kind": requirement.kind,
                "source_quote": requirement.source_quote,
                "requirement_id": requirement.id,
                "requirement_text": requirement.normalized_text,
                "scope": requirement.scope,
            }
            if not any(existing.get("id") == criterion["id"] for existing in criteria):
                criteria.append(criterion)
        leaf.acceptance_criteria_json = criteria
        leaf.content_kind = _content_kind(requirement, path)
        is_program_text = (
            requirement.scope == "proposal_content"
            and path[0] == PROGRAM_ROOT
            and _normalized(leaf.title) not in {
                "основен документ", "структура", "раздел", "подраздел",
            }
        )
        if is_program_text and not leaf.generation_uid:
            leaf.generation_uid = str(uuid.uuid4())

    if not nodes:
        raise ValueError("Няма приложими потвърдени изисквания към техническото предложение.")

    children_by_parent: dict[str | None, list[ContentPlanItem]] = defaultdict(list)
    for item in nodes.values():
        children_by_parent[item.parent_id].append(item)

    def assign_numbers(parent_id: str | None, prefix: str = "") -> None:
        children = sorted(children_by_parent.get(parent_id, []), key=_section_order)
        for index, item in enumerate(children, start=1):
            item.order_index = index
            item.number = f"{prefix}.{index}" if prefix else str(index)
            criteria = [entry for entry in item.acceptance_criteria_json if isinstance(entry, dict)]
            item.linked_wbs_ids = _wbs_links(item.title, criteria, wbs_items)
            item.linked_fact_keys = _fact_links(item.title, criteria, facts)
            assign_numbers(item.id, item.number)

    assign_numbers(None)
    await db.flush()
    await sync_outline_from_content_plan(outline.id, db)
    outline.outline_json = {
        **outline.outline_json,
        "understanding_status": understanding_status,
    }
    await db.flush()
    return outline
