from __future__ import annotations

from typing import Any


def _as_int(value: Any, default: int = 0) -> int:
    return value if isinstance(value, int) else default


def _truncate(value: Any, *, limit: int = 180) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _list(values: list[str], *, empty: str = "няма") -> str:
    return ", ".join(values) if values else empty


def _table_cell(value: Any) -> str:
    return str(value or "").replace("|", "\\|")


def _section_label(section: dict[str, Any]) -> str:
    section_uid = str(section.get("section_uid") or "n/a")
    title = _truncate(section.get("section_title"), limit=90)
    if title:
        return f"{title} (`{section_uid}`)"
    return f"`{section_uid}`"


def _blocker_actions(readiness: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    blocker_codes = {
        str(blocker.get("code"))
        for blocker in readiness.get("blockers") or []
        if isinstance(blocker, dict)
    }
    if "duplicate_selected" in blocker_codes:
        actions.append(
            "Изберете точно една генерирана версия за всяка секция с дублирани selected варианти."
        )
    if "stale_evidence" in blocker_codes:
        actions.append(
            "Регенерирайте избраните stale секции след разрешаване на дублираните selected варианти."
        )
    if "missing_requirements" in blocker_codes:
        actions.append(
            "Регенерирайте или редактирайте секциите с непокрити checklist изисквания."
        )
    if "shallow_sections" in blocker_codes:
        actions.append(
            "Регенерирайте плитките секции с по-развита структура, роли, контроли, документи и последователност."
        )
    return actions


def render_export_readiness_report(readiness: dict[str, Any]) -> str:
    lines = [
        "# DOCX export readiness report",
        "",
        "## Summary",
        "",
        f"- Project ID: `{readiness.get('project_id', 'n/a')}`",
        f"- Status: `{readiness.get('status', 'unknown')}`",
        f"- Ready: `{bool(readiness.get('ready'))}`",
        f"- Selected generations: `{_as_int(readiness.get('selected_generation_count'))}`",
        f"- Selected sections: `{_as_int(readiness.get('selected_section_count'))}`",
        f"- Blockers: `{_as_int(readiness.get('blocker_count'))}`",
        f"- Message: {_truncate(readiness.get('message') or '')}",
        "",
        "## Blockers",
        "",
    ]

    blockers = [item for item in readiness.get("blockers") or [] if isinstance(item, dict)]
    if not blockers:
        lines.append("- Няма readiness блокери.")
    else:
        lines.extend(
            [
                "| Code | Count | Message |",
                "| --- | ---: | --- |",
            ]
        )
        for blocker in blockers:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _table_cell(blocker.get("code", "")),
                        str(_as_int(blocker.get("count"))),
                        _table_cell(_truncate(blocker.get("message"))),
                    ]
                )
                + " |"
            )

    duplicate_sections = [
        item
        for item in readiness.get("duplicate_selected_sections") or []
        if isinstance(item, dict)
    ]
    if duplicate_sections:
        lines.extend(["", "## Duplicate Selected Sections", ""])
        for section in duplicate_sections:
            generation_ids = [
                str(item)
                for item in section.get("generation_ids") or []
                if item is not None
            ]
            lines.append(
                "- "
                f"{_section_label(section)}: "
                f"{_as_int(section.get('selected_count'))} selected variants "
                f"({_list(generation_ids)})"
            )

    stale_section_details = [
        item
        for item in readiness.get("stale_section_details") or []
        if isinstance(item, dict)
    ]
    if not stale_section_details:
        stale_section_details = [
            {"section_uid": str(item)}
            for item in readiness.get("stale_sections") or []
            if item is not None
        ]
    if stale_section_details:
        lines.extend(["", "## Stale Evidence Sections", ""])
        for section in stale_section_details:
            lines.append(f"- {_section_label(section)}")

    missing_sections = [
        item
        for item in readiness.get("missing_requirement_sections") or []
        if isinstance(item, dict)
    ]
    if missing_sections:
        lines.extend(["", "## Missing Requirement Coverage", ""])
        for section in missing_sections:
            missing_ids = [
                str(item)
                for item in section.get("missing_requirement_ids") or []
                if item is not None
            ]
            lines.append(
                "- "
                f"{_section_label(section)}: "
                f"{_as_int(section.get('missing_count'))} missing "
                f"({_list(missing_ids)})"
            )
            for item in section.get("missing_items") or []:
                if isinstance(item, dict):
                    lines.append(f"  - `{item.get('id', 'n/a')}`: {_truncate(item.get('text'))}")

    quality_sections = [
        item
        for item in readiness.get("quality_sections") or []
        if isinstance(item, dict)
    ]
    if quality_sections:
        lines.extend(["", "## Shallow Or Underdeveloped Sections", ""])
        lines.extend(
            [
                "| Section | Words | Min words | Sentences | Min sentences | Requirements | Blueprint groups | Issues |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
            ]
        )
        for section in quality_sections:
            issue_codes = [
                str(issue.get("code"))
                for issue in section.get("issues") or []
                if isinstance(issue, dict) and issue.get("code")
            ]
            lines.append(
                "| "
                + " | ".join(
                    [
                        _table_cell(_section_label(section)),
                        str(_as_int(section.get("word_count"))),
                        str(_as_int(section.get("min_words"))),
                        str(_as_int(section.get("sentence_count"))),
                        str(_as_int(section.get("min_sentences"))),
                        str(_as_int(section.get("requirement_count"))),
                        str(_as_int(section.get("blueprint_group_count"))),
                        _table_cell(_list(issue_codes)),
                    ]
                )
                + " |"
            )

    actions = _blocker_actions(readiness)
    lines.extend(["", "## Recommended Next Actions", ""])
    if actions:
        lines.extend(f"{index}. {action}" for index, action in enumerate(actions, start=1))
    else:
        lines.append("1. Proposal is ready for DOCX export.")

    lines.append("")
    return "\n".join(lines)
