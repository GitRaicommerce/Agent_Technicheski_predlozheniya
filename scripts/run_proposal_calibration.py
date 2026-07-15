from __future__ import annotations

import argparse
import asyncio
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

from compare_calibration_manifests import (
    load_manifest as load_comparison_manifest,
    render_comparison as render_manifest_comparison,
)
from export_selected_proposal_markdown import (
    GenerationSnapshot,
    load_snapshot,
    newest_generation_per_section,
    render_selected_proposal_markdown,
)
from proposal_gap_analysis import (
    extract_text,
    render_report,
    split_sections,
)


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "services" / "api"
GAP_FOCUS_PRIORITY = {
    "outline mapping": 0,
    "drafting depth": 1,
    "grounding and checklist coverage": 2,
    "monitor": 3,
}
READINESS_ACTION_KEYS = {
    "duplicate_selected": "resolve_duplicate_selected",
    "stale_evidence": "regenerate_stale",
    "missing_requirements": "regenerate_missing_requirements",
    "shallow_sections": "regenerate_quality_depth",
}
GAP_FOCUS_ACTION_KEYS = {
    "drafting depth": READINESS_ACTION_KEYS["shallow_sections"],
    "grounding and checklist coverage": READINESS_ACTION_KEYS[
        "missing_requirements"
    ],
}
GAP_FOCUS_UI_ACTIONS = {
    "drafting depth": "Регенерирай подробно",
    "grounding and checklist coverage": "Регенерирай покритието",
    "outline mapping": "Прегледай outline mapping",
}


def _remediation_api_path(project_id: str | None, action_key: str) -> str:
    project_part = project_id or "{project_id}"
    return f"/api/v1/agents/{project_part}/remediation-actions/{action_key}"


def _display_path(path: Path) -> str:
    return path.as_posix()


def load_action_execution_reports(paths: list[Path]) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Action execution report {path} must be a JSON object")
        reports.append(payload)
    return reports


def action_execution_summary(reports: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    missing_reason_counts: dict[str, int] = {}
    operational_signal_counts: dict[str, int] = {}
    section_label_counts: dict[str, int] = {}
    total_actions = 0
    executed_actions = 0
    ready_report_count = 0
    failure_report_count = 0
    unexecuted_report_count = 0
    unverified_report_count = 0
    for report in reports:
        total_actions += int(report.get("total_actions") or 0)
        executed_actions += int(report.get("executed_actions") or 0)
        raw_counts = report.get("status_counts") or {}
        if not isinstance(raw_counts, dict):
            raw_counts = {}
        if "executed_actions" not in report:
            executed_actions += sum(
                int(count or 0)
                for status, count in raw_counts.items()
                if str(status) != "planned"
            )
        report_has_failures = bool(report.get("has_failures"))
        if "has_failures" not in report:
            report_has_failures = any(
                str(status)
                not in {"done", "executed", "planned", "executed_unverified"}
                and int(count or 0) > 0
                for status, count in raw_counts.items()
            )
        report_has_unexecuted = bool(report.get("has_unexecuted_actions"))
        if "has_unexecuted_actions" not in report:
            report_has_unexecuted = int(raw_counts.get("planned") or 0) > 0
        report_has_unverified = bool(report.get("has_unverified_actions"))
        if "has_unverified_actions" not in report:
            report_has_unverified = int(raw_counts.get("executed_unverified") or 0) > 0
        if bool(report.get("ready_for_bundle")):
            ready_report_count += 1
        if report_has_failures:
            failure_report_count += 1
        if report_has_unexecuted:
            unexecuted_report_count += 1
        if report_has_unverified:
            unverified_report_count += 1
        for action in report.get("actions") or []:
            if not isinstance(action, dict):
                continue
            for label in action.get("section_labels") or []:
                label_text = str(label).strip()
                if label_text:
                    section_label_counts[label_text] = (
                        section_label_counts.get(label_text, 0) + 1
                    )
            raw_reason_counts = action.get("missing_reason_counts") or {}
            if isinstance(raw_reason_counts, dict):
                for reason, count in raw_reason_counts.items():
                    reason_label = str(reason).strip()
                    if not reason_label:
                        continue
                    try:
                        reason_count = int(count)
                    except (TypeError, ValueError):
                        reason_count = 0
                    missing_reason_counts[reason_label] = (
                        missing_reason_counts.get(reason_label, 0) + reason_count
                    )
            for signal in action.get("operational_detail_missing_signals") or []:
                signal_label = str(signal).strip()
                if signal_label:
                    operational_signal_counts[signal_label] = (
                        operational_signal_counts.get(signal_label, 0) + 1
                    )
        if not raw_counts:
            continue
        for status, count in raw_counts.items():
            status_key = str(status or "unknown")
            try:
                status_count = int(count)
            except (TypeError, ValueError):
                status_count = 0
            status_counts[status_key] = status_counts.get(status_key, 0) + status_count
    has_failures = failure_report_count > 0
    has_unexecuted_actions = unexecuted_report_count > 0
    has_unverified_actions = unverified_report_count > 0
    ready_for_bundle = (
        bool(reports)
        and ready_report_count == len(reports)
        and failure_report_count == 0
        and unexecuted_report_count == 0
        and unverified_report_count == 0
    )
    if not reports:
        evidence_level = "none"
    elif has_failures:
        evidence_level = "failed"
    elif has_unverified_actions:
        evidence_level = "unverified"
    elif has_unexecuted_actions:
        evidence_level = "planned"
    elif ready_for_bundle:
        evidence_level = "proof"
    else:
        evidence_level = "insufficient"
    return {
        "report_count": len(reports),
        "total_actions": total_actions,
        "executed_actions": executed_actions,
        "status_counts": status_counts,
        "missing_reason_counts": dict(
            sorted(missing_reason_counts.items(), key=lambda item: (-item[1], item[0]))
        ),
        "operational_detail_missing_signal_counts": dict(
            sorted(
                operational_signal_counts.items(),
                key=lambda item: (-item[1], item[0]),
            )
        ),
        "section_label_counts": dict(
            sorted(section_label_counts.items(), key=lambda item: (-item[1], item[0]))
        ),
        "ready_report_count": ready_report_count,
        "failure_report_count": failure_report_count,
        "unexecuted_report_count": unexecuted_report_count,
        "unverified_report_count": unverified_report_count,
        "has_failures": has_failures,
        "has_unexecuted_actions": has_unexecuted_actions,
        "has_unverified_actions": has_unverified_actions,
        "ready_for_bundle": ready_for_bundle,
        "evidence_level": evidence_level,
    }


def snapshot_warning_count(markdown: str) -> int:
    in_warnings = False
    count = 0
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped == "## Snapshot Warnings":
            in_warnings = True
            continue
        if in_warnings and stripped.startswith("## "):
            break
        if in_warnings and stripped.startswith("- "):
            count += 1
    return count


def _split_markdown_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|"):
        return []
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for char in stripped.strip("|"):
        if char == "|" and not escaped:
            cells.append("".join(current).strip().replace("\\|", "|"))
            current = []
            escaped = False
            continue
        current.append(char)
        escaped = char == "\\" and not escaped
        if char != "\\":
            escaped = False
    cells.append("".join(current).strip().replace("\\|", "|"))
    return cells


def gap_calibration_focus_counts(markdown: str) -> dict[str, int]:
    in_diagnostics = False
    counts: dict[str, int] = {}
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped == "## Section Gap Diagnostics":
            in_diagnostics = True
            continue
        if in_diagnostics and stripped.startswith("## "):
            break
        if not in_diagnostics or not stripped.startswith("|"):
            continue
        cells = _split_markdown_table_row(stripped)
        if len(cells) < 6 or cells[0] in {"Reference section", "---"}:
            continue
        focus = cells[5]
        if focus:
            counts[focus] = counts.get(focus, 0) + 1
    return counts


def _signal_list(value: str) -> list[str]:
    if value.strip().lower() in {"", "n/a"}:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def gap_summary_metrics(markdown: str) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    line_patterns = {
        "raw_reference_sections": r"Raw recognized sections in reference TP:\s*`(\d+)`",
        "raw_generated_sections": r"Raw recognized sections in generated TP:\s*`(\d+)`",
        "content_reference_sections": r"Content sections compared in reference TP:\s*`(\d+)`",
        "content_generated_sections": r"Content sections compared in generated TP:\s*`(\d+)`",
        "reference_word_tokens": r"Word-like tokens .*?референтното ТП:\s*`(\d+)`",
        "generated_word_tokens": r"Word-like tokens .*?генерираното ТП:\s*`(\d+)`",
    }
    for line in markdown.splitlines():
        for key, pattern in line_patterns.items():
            match = re.search(pattern, line)
            if match:
                metrics[key] = int(match.group(1))
        if line.startswith("| ") and " | " in line:
            cells = _split_markdown_table_row(line)
            if len(cells) >= 5 and cells[0] in {"covered", "partial", "weak", "n/a"}:
                try:
                    ratio = float(cells[1])
                except ValueError:
                    continue
                metrics["operational_detail_status"] = cells[0]
                metrics["operational_detail_ratio"] = ratio
                metrics["operational_detail_reference_signals"] = _signal_list(
                    cells[2]
                )
                metrics["operational_detail_generated_signals"] = _signal_list(
                    cells[3]
                )
                missing_signals = _signal_list(cells[4])
                metrics["operational_detail_missing_signals"] = missing_signals
                metrics["operational_detail_missing_signal_count"] = len(
                    missing_signals
                )

    reference_words = metrics.get("reference_word_tokens")
    generated_words = metrics.get("generated_word_tokens")
    if isinstance(reference_words, int) and isinstance(generated_words, int):
        metrics["generated_reference_volume_ratio"] = (
            generated_words / reference_words if reference_words else 0.0
        )

    return metrics


def gap_regeneration_priority_rows(
    markdown: str,
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    in_diagnostics = False
    rows: list[dict[str, Any]] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped == "## Section Gap Diagnostics":
            in_diagnostics = True
            continue
        if in_diagnostics and stripped.startswith("## "):
            break
        if not in_diagnostics or not stripped.startswith("|"):
            continue
        cells = _split_markdown_table_row(stripped)
        if len(cells) < 6 or cells[0] in {"Reference section", "---"}:
            continue
        focus = cells[5]
        if not focus or focus == "monitor":
            continue
        try:
            coverage = float(cells[2])
        except ValueError:
            coverage = 1.0
        try:
            volume = float(cells[3])
        except ValueError:
            volume = 1.0
        rows.append(
            {
                "reference_section": cells[0],
                "generated_section": cells[1],
                "coverage": coverage,
                "volume": volume,
                "reasons": cells[4],
                "focus": focus,
            }
        )
    rows.sort(
        key=lambda row: (
            GAP_FOCUS_PRIORITY.get(str(row["focus"]), 9),
            float(row["coverage"]),
            float(row["volume"]),
            str(row["reference_section"]),
        )
    )
    return rows[:limit]


def _normalize_section_title(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def generated_section_uid_map(markdown: str) -> dict[str, str]:
    section_uids: dict[str, str] = {}
    current_title = ""
    for line in markdown.splitlines():
        stripped = line.strip()
        heading = re.match(r"^#{2,6}\s+(.+)$", stripped)
        if heading:
            current_title = heading.group(1).strip()
            continue
        if not current_title:
            continue
        meta_match = re.search(r"\bsection_uid=([^;\s]+)", stripped)
        if meta_match:
            section_uids[current_title] = meta_match.group(1).strip()
    return section_uids


def _section_uid_for_generated_title(
    generated_title: str,
    section_uid_by_generated_title: dict[str, str],
) -> str:
    normalized_generated = _normalize_section_title(generated_title)
    if not normalized_generated:
        return ""
    normalized_map = {
        _normalize_section_title(title): uid
        for title, uid in section_uid_by_generated_title.items()
        if title and uid
    }
    direct = normalized_map.get(normalized_generated)
    if direct:
        return direct
    for title, uid in normalized_map.items():
        if normalized_generated in title or title in normalized_generated:
            return uid
    return ""


def enrich_gap_priority_rows(
    rows: list[dict[str, Any]],
    *,
    project_id: str | None = None,
    section_uid_by_generated_title: dict[str, str] | None = None,
    operational_detail_missing_signals: list[str] | None = None,
) -> list[dict[str, Any]]:
    section_uid_by_generated_title = section_uid_by_generated_title or {}
    operational_detail_missing_signals = operational_detail_missing_signals or []
    enriched: list[dict[str, Any]] = []
    for row in rows:
        focus = str(row.get("focus") or "")
        action_key = GAP_FOCUS_ACTION_KEYS.get(focus)
        item = dict(row)
        ui_action = GAP_FOCUS_UI_ACTIONS.get(focus)
        if ui_action:
            item["ui_action"] = ui_action
        if action_key:
            item["action_key"] = action_key
            item["api_method"] = "POST"
            item["api_path"] = _remediation_api_path(project_id, action_key)
            generated_section = str(item.get("generated_section") or "").strip()
            section_uid = _section_uid_for_generated_title(
                generated_section,
                section_uid_by_generated_title,
            )
            if section_uid:
                item["request_json"] = {
                    "section_uids": [section_uid],
                    "section_title_hints": [generated_section],
                }
            elif generated_section:
                item["request_json"] = {
                    "section_title_hints": [generated_section],
                }
            request_json = item.get("request_json")
            if isinstance(request_json, dict) and action_key == READINESS_ACTION_KEYS["shallow_sections"]:
                reasons = [
                    reason.strip()
                    for reason in str(item.get("reasons") or "").split(",")
                    if reason.strip()
                ]
                if reasons:
                    request_json["gap_reasons"] = reasons
                reference_section = str(item.get("reference_section") or "").strip()
                if reference_section:
                    request_json["reference_section"] = reference_section
                if generated_section:
                    request_json["generated_section"] = generated_section
                if operational_detail_missing_signals:
                    request_json["operational_detail_missing_signals"] = (
                        operational_detail_missing_signals
                    )
        enriched.append(item)
    return enriched


def _section_label(section: dict[str, Any]) -> str:
    for key in ("section_title", "title", "section_uid"):
        value = section.get(key)
        if value:
            return str(value)
    return "unknown section"


def _section_target_request(sections: list[dict[str, Any]]) -> dict[str, list[str]]:
    section_uids: list[str] = []
    title_hints: list[str] = []
    for section in sections:
        section_uid = str(
            section.get("section_uid")
            or section.get("uid")
            or ""
        ).strip()
        if section_uid:
            section_uids.append(section_uid)
        title = str(section.get("section_title") or section.get("title") or "").strip()
        if title:
            title_hints.append(title)

    request_json: dict[str, list[str]] = {}
    unique_uids = list(dict.fromkeys(section_uids))
    unique_titles = list(dict.fromkeys(title_hints))
    if unique_uids:
        request_json["section_uids"] = unique_uids
    if unique_titles:
        request_json["section_title_hints"] = unique_titles
    return request_json


def _request_target_label(request_json: dict[str, Any] | None) -> str:
    if not isinstance(request_json, dict):
        return ""
    section_uids = [
        str(item).strip()
        for item in request_json.get("section_uids") or []
        if str(item).strip()
    ]
    title_hints = [
        str(item).strip()
        for item in request_json.get("section_title_hints") or []
        if str(item).strip()
    ]
    parts: list[str] = []
    if section_uids:
        parts.append("uids=" + ", ".join(section_uids[:6]))
        if len(section_uids) > 6:
            parts.append(f"+{len(section_uids) - 6} more uids")
    if title_hints:
        parts.append("titles=" + ", ".join(title_hints[:6]))
        if len(title_hints) > 6:
            parts.append(f"+{len(title_hints) - 6} more titles")
    return "; ".join(parts)


def _summarize_labels(labels: list[str], limit: int = 6) -> str:
    visible = labels[:limit]
    suffix = f" (+{len(labels) - limit} more)" if len(labels) > limit else ""
    return "; ".join(visible) + suffix


def _missing_requirement_label(section: dict[str, Any]) -> str:
    missing_count = int(section.get("missing_count") or 0)
    reasons: list[str] = []
    for item in section.get("missing_items") or []:
        if not isinstance(item, dict):
            continue
        item_reasons = item.get("reasons")
        if not isinstance(item_reasons, list):
            item_reasons = [item.get("reason")]
        for raw_reason in item_reasons:
            reason = str(raw_reason or "").strip()
            if reason and reason not in reasons:
                reasons.append(reason)

    reason_summary = ""
    if reasons:
        visible = reasons[:3]
        suffix = f", +{len(reasons) - 3} more" if len(reasons) > 3 else ""
        reason_summary = "; " + ", ".join(visible) + suffix
    return f"{_section_label(section)} ({missing_count} missing{reason_summary})"


def _quality_issue_summary(section: dict[str, Any]) -> str:
    issue_codes: list[str] = []
    for issue in section.get("issues") or []:
        if not isinstance(issue, dict):
            continue
        code = str(issue.get("code") or "").strip()
        if code and code not in issue_codes:
            issue_codes.append(code)
    if not issue_codes:
        return ""

    visible = issue_codes[:3]
    suffix = f", +{len(issue_codes) - 3} more" if len(issue_codes) > 3 else ""
    return "issues: " + ", ".join(visible) + suffix


def _quality_section_label(section: dict[str, Any]) -> str:
    word_count = int(section.get("word_count") or 0)
    min_words = int(section.get("min_words") or 0)
    diagnostics = [f"{word_count}/{min_words} words"]

    blueprint_groups = int(section.get("blueprint_group_count") or 0)
    blueprint_topics = int(section.get("blueprint_topic_count") or 0)
    blueprint_requirement_ids = int(
        section.get("blueprint_requirement_id_count") or 0
    )
    suggested_words = int(section.get("suggested_words_per_structure") or 0)
    if blueprint_groups:
        diagnostics.append(f"{blueprint_groups} groups")
    if blueprint_topics:
        diagnostics.append(f"{blueprint_topics} topics")
    if blueprint_requirement_ids:
        diagnostics.append(f"{blueprint_requirement_ids} checklist ids")
    if suggested_words:
        diagnostics.append(f"{suggested_words} words/group-topic")
    issue_summary = _quality_issue_summary(section)
    if issue_summary:
        diagnostics.append(issue_summary)

    return f"{_section_label(section)} ({', '.join(diagnostics)})"


def _missing_requirement_reason_counts(
    sections: list[dict[str, Any]],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for section in sections:
        for item in section.get("missing_items") or []:
            if not isinstance(item, dict):
                continue
            item_reasons = item.get("reasons")
            if not isinstance(item_reasons, list):
                item_reasons = [item.get("reason")]
            for raw_reason in item_reasons:
                reason = str(raw_reason or "").strip()
                if reason:
                    counts[reason] = counts.get(reason, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _blocker_count(readiness: dict[str, Any], code: str) -> int:
    for blocker in readiness.get("blockers") or []:
        if isinstance(blocker, dict) and blocker.get("code") == code:
            try:
                return int(blocker.get("count") or 0)
            except (TypeError, ValueError):
                return 0
    return 0


def readiness_priority_actions(readiness: dict[str, Any] | None) -> list[str]:
    readiness = readiness or {}
    actions: list[str] = []
    duplicate_sections = [
        item
        for item in readiness.get("duplicate_selected_sections") or []
        if isinstance(item, dict)
    ]
    duplicate_count = len(duplicate_sections) or _blocker_count(
        readiness,
        "duplicate_selected",
    )
    if duplicate_count:
        labels = [_section_label(item) for item in duplicate_sections] or [
            f"{duplicate_count} duplicate selected sections"
        ]
        actions.append(
            "`duplicate_selected` action_key=`resolve_duplicate_selected`: use Generations attention action "
            "`Остави най-новите` or manually keep one selected variant before "
            "regeneration - "
            + _summarize_labels(labels)
        )

    stale_sections = [
        item
        for item in readiness.get("stale_section_details") or []
        if isinstance(item, dict)
    ]
    if not stale_sections:
        stale_sections = [
            {"section_uid": str(item)}
            for item in readiness.get("stale_sections") or []
            if item is not None
        ]
    stale_count = len(stale_sections) or _blocker_count(readiness, "stale_evidence")
    if stale_count:
        labels = [_section_label(item) for item in stale_sections] or [
            f"{stale_count} stale selected sections"
        ]
        actions.append(
            "`stale_evidence` action_key=`regenerate_stale`: използвайте Generations bulk `Регенерирай` за избраните "
            "stale секции с обновени доказателства - "
            + _summarize_labels(labels)
        )

    missing_sections = [
        item
        for item in readiness.get("missing_requirement_sections") or []
        if isinstance(item, dict)
    ]
    missing_count = len(missing_sections) or _blocker_count(
        readiness,
        "missing_requirements",
    )
    if missing_count:
        missing_sections.sort(
            key=lambda item: int(item.get("missing_count") or 0),
            reverse=True,
        )
        labels = [_missing_requirement_label(item) for item in missing_sections] or [
            f"{missing_count} sections with missing requirements"
        ]
        actions.append(
            "`missing_requirements` action_key=`regenerate_missing_requirements`: използвайте Generations bulk `Регенерирай покритието` "
            "за пренаписване на избраните секции с явно checklist покритие - "
            + _summarize_labels(labels)
        )

    quality_sections = [
        item
        for item in readiness.get("quality_sections") or []
        if isinstance(item, dict)
    ]
    quality_count = len(quality_sections) or _blocker_count(
        readiness,
        "shallow_sections",
    )
    if quality_count:
        quality_sections.sort(
            key=lambda item: (
                int(item.get("requirement_count") or 0),
                int(item.get("blueprint_topic_count") or 0),
            ),
            reverse=True,
        )
        labels = [_quality_section_label(item) for item in quality_sections] or [
            f"{quality_count} shallow/quality sections"
        ]
        actions.append(
            "`shallow_sections` action_key=`regenerate_quality_depth`: използвайте Generations bulk `Регенерирай подробно` "
            "за по-развит разказ, контроли, записи, роли и последователност - "
            + _summarize_labels(labels)
        )

    return actions


def structured_readiness_priority_actions(
    readiness: dict[str, Any] | None,
    *,
    project_id: str | None = None,
) -> list[dict[str, Any]]:
    readiness = readiness or {}
    actions: list[dict[str, Any]] = []

    duplicate_sections = [
        item
        for item in readiness.get("duplicate_selected_sections") or []
        if isinstance(item, dict)
    ]
    duplicate_count = len(duplicate_sections) or _blocker_count(
        readiness,
        "duplicate_selected",
    )
    if duplicate_count:
        labels = [_section_label(item) for item in duplicate_sections] or [
            f"{duplicate_count} duplicate selected sections"
        ]
        actions.append(
            {
                "blocker_code": "duplicate_selected",
                "action_key": READINESS_ACTION_KEYS["duplicate_selected"],
                "api_method": "POST",
                "api_path": _remediation_api_path(
                    project_id,
                    READINESS_ACTION_KEYS["duplicate_selected"],
                ),
                "ui_action": "Остави най-новите",
                "section_count": duplicate_count,
                "section_labels": labels,
                "summary": _summarize_labels(labels),
            }
        )

    stale_sections = [
        item
        for item in readiness.get("stale_section_details") or []
        if isinstance(item, dict)
    ]
    if not stale_sections:
        stale_sections = [
            {"section_uid": str(item)}
            for item in readiness.get("stale_sections") or []
            if item is not None
        ]
    stale_count = len(stale_sections) or _blocker_count(readiness, "stale_evidence")
    if stale_count:
        labels = [_section_label(item) for item in stale_sections] or [
            f"{stale_count} stale selected sections"
        ]
        actions.append(
            {
                "blocker_code": "stale_evidence",
                "action_key": READINESS_ACTION_KEYS["stale_evidence"],
                "api_method": "POST",
                "api_path": _remediation_api_path(
                    project_id,
                    READINESS_ACTION_KEYS["stale_evidence"],
                ),
                "ui_action": "Регенерирай",
                "section_count": stale_count,
                "section_labels": labels,
                "summary": _summarize_labels(labels),
            }
        )

    missing_sections = [
        item
        for item in readiness.get("missing_requirement_sections") or []
        if isinstance(item, dict)
    ]
    missing_count = len(missing_sections) or _blocker_count(
        readiness,
        "missing_requirements",
    )
    if missing_count:
        missing_sections.sort(
            key=lambda item: int(item.get("missing_count") or 0),
            reverse=True,
        )
        labels = [_missing_requirement_label(item) for item in missing_sections] or [
            f"{missing_count} sections with missing requirements"
        ]
        action = {
            "blocker_code": "missing_requirements",
            "action_key": READINESS_ACTION_KEYS["missing_requirements"],
            "api_method": "POST",
            "api_path": _remediation_api_path(
                project_id,
                READINESS_ACTION_KEYS["missing_requirements"],
            ),
            "ui_action": "Регенерирай покритието",
            "section_count": missing_count,
            "section_labels": labels,
            "summary": _summarize_labels(labels),
        }
        reason_counts = _missing_requirement_reason_counts(missing_sections)
        if reason_counts:
            action["missing_reason_counts"] = reason_counts
        request_json = _section_target_request(missing_sections)
        if request_json:
            action["request_json"] = request_json
        actions.append(action)

    quality_sections = [
        item
        for item in readiness.get("quality_sections") or []
        if isinstance(item, dict)
    ]
    quality_count = len(quality_sections) or _blocker_count(
        readiness,
        "shallow_sections",
    )
    if quality_count:
        quality_sections.sort(
            key=lambda item: (
                int(item.get("requirement_count") or 0),
                int(item.get("blueprint_topic_count") or 0),
            ),
            reverse=True,
        )
        labels = [_quality_section_label(item) for item in quality_sections] or [
            f"{quality_count} shallow/depth-blocked sections"
        ]
        action = {
            "blocker_code": "shallow_sections",
            "action_key": READINESS_ACTION_KEYS["shallow_sections"],
            "api_method": "POST",
            "api_path": _remediation_api_path(
                project_id,
                READINESS_ACTION_KEYS["shallow_sections"],
            ),
            "ui_action": "Регенерирай подробно",
            "section_count": quality_count,
            "section_labels": labels,
            "summary": _summarize_labels(labels),
        }
        request_json = _section_target_request(quality_sections)
        if request_json:
            action["request_json"] = request_json
        actions.append(action)

    return actions


def calibration_output_paths(out_dir: Path) -> dict[str, Path]:
    return {
        "selected_snapshot": out_dir / "selected_proposal_snapshot.md",
        "effective_snapshot": out_dir / "effective_proposal_snapshot.md",
        "readiness_report": out_dir / "docx_readiness_report.md",
        "gap_report": out_dir / "proposal_gap_report.md",
        "manifest": out_dir / "calibration_manifest.md",
        "manifest_json": out_dir / "calibration_manifest.json",
        "comparison": out_dir / "calibration_manifest_comparison.md",
    }


def render_manifest(
    *,
    project_id: str,
    reference: Path,
    selected_snapshot: Path,
    effective_snapshot: Path,
    readiness_report: Path,
    gap_report: Path,
    tenders: list[Path],
    readiness: dict[str, Any] | None = None,
    snapshot_warnings: int = 0,
    gap_summary: dict[str, Any] | None = None,
    gap_focus_counts: dict[str, int] | None = None,
    gap_priority_rows: list[dict[str, Any]] | None = None,
    section_uid_by_generated_title: dict[str, str] | None = None,
    action_report_paths: list[Path] | None = None,
    action_execution_reports: list[dict[str, Any]] | None = None,
) -> str:
    readiness = readiness or {}
    blockers = [
        item
        for item in readiness.get("blockers") or []
        if isinstance(item, dict)
    ]
    gap_focus_counts = gap_focus_counts or {}
    gap_summary = gap_summary or {}
    gap_priority_rows = enrich_gap_priority_rows(
        gap_priority_rows or [],
        project_id=project_id,
        section_uid_by_generated_title=section_uid_by_generated_title,
        operational_detail_missing_signals=gap_summary.get(
            "operational_detail_missing_signals"
        )
        if isinstance(gap_summary.get("operational_detail_missing_signals"), list)
        else None,
    )
    readiness_actions = readiness_priority_actions(readiness)
    structured_readiness_actions = structured_readiness_priority_actions(
        readiness,
        project_id=project_id,
    )
    action_report_paths = action_report_paths or []
    action_execution_reports = action_execution_reports or []
    action_summary = action_execution_summary(action_execution_reports)
    lines = [
        "# Proposal calibration bundle",
        "",
        f"- Project ID: `{project_id}`",
        f"- Reference proposal: `{_display_path(reference)}`",
        f"- Raw selected proposal snapshot: `{_display_path(selected_snapshot)}`",
        f"- Effective proposal snapshot: `{_display_path(effective_snapshot)}`",
        f"- DOCX readiness report: `{_display_path(readiness_report)}`",
        f"- Gap report: `{_display_path(gap_report)}`",
        "- Mode: `non-mutating`",
        "",
        "## Calibration gates",
        "",
        f"- Snapshot warnings: `{snapshot_warnings}`",
        f"- DOCX readiness status: `{readiness.get('status', 'unknown')}`",
        f"- DOCX readiness blockers: `{len(blockers)}`",
        "- Gap input snapshot: `effective_proposal_snapshot.md`",
    ]
    if blockers:
        lines.extend(
            f"  - `{blocker.get('code', 'unknown')}`: `{blocker.get('count', 0)}`"
            for blocker in blockers
        )
        lines.append(
            "- Gap report interpretation: resolve readiness blockers before treating "
            "reference-gap findings as final generation-quality evidence."
        )
    else:
        lines.append(
            "- Gap report interpretation: readiness is clear enough for calibration review."
        )
    lines.extend(["", "## Gap quality scorecard", ""])
    if gap_summary:
        content_reference = gap_summary.get("content_reference_sections", "n/a")
        content_generated = gap_summary.get("content_generated_sections", "n/a")
        reference_words = gap_summary.get("reference_word_tokens", "n/a")
        generated_words = gap_summary.get("generated_word_tokens", "n/a")
        volume_ratio = gap_summary.get("generated_reference_volume_ratio")
        lines.extend(
            [
                (
                    "- Content sections compared: "
                    f"`{content_generated}` generated / `{content_reference}` reference"
                ),
                (
                    "- Word-like tokens compared: "
                    f"`{generated_words}` generated / `{reference_words}` reference"
                ),
            ]
        )
        if isinstance(volume_ratio, float):
            lines.append(f"- Generated/reference volume ratio: `{volume_ratio:.2f}`")
        operational_ratio = gap_summary.get("operational_detail_ratio")
        operational_status = gap_summary.get("operational_detail_status")
        if isinstance(operational_ratio, float):
            lines.append(
                "- Operational detail coverage: "
                f"`{operational_ratio:.2f}`"
                + (
                    f" (`{operational_status}`)"
                    if isinstance(operational_status, str)
                    else ""
                )
            )
            operational_missing = gap_summary.get(
                "operational_detail_missing_signals"
            )
            if isinstance(operational_missing, list) and operational_missing:
                visible_signals = [
                    str(signal) for signal in operational_missing[:10]
                ]
                suffix = (
                    f" (+{len(operational_missing) - 10} more)"
                    if len(operational_missing) > 10
                    else ""
                )
                lines.append(
                    "- Missing operational signals: `"
                    + "`, `".join(visible_signals)
                    + f"`{suffix}"
                )
    else:
        lines.append("- `n/a`: Gap summary metrics were not found in the report.")
    lines.extend(["", "## Remediation action execution evidence", ""])
    if action_report_paths:
        lines.append(
            (
                "- Action execution reports: "
                f"`{action_summary['report_count']}` files, "
                f"`{action_summary['total_actions']}` actions"
            )
        )
        lines.append(
            "- Action evidence level: "
            f"`{action_summary['evidence_level']}`"
        )
        lines.append(
            "- Action evidence ready for next bundle: "
            f"`{'yes' if action_summary['ready_for_bundle'] else 'no'}`"
        )
        if action_summary["has_failures"]:
            lines.append(
                "- Action evidence warning: failed remediation actions are present."
            )
        if action_summary["has_unexecuted_actions"]:
            lines.append(
                "- Action evidence warning: some remediation actions were only planned."
            )
        if action_summary["has_unverified_actions"]:
            lines.append(
                "- Action evidence warning: some executed generation actions were not waited to completion."
            )
        for path in action_report_paths:
            lines.append(f"  - `{_display_path(path)}`")
        status_counts = action_summary.get("status_counts") or {}
        if status_counts:
            lines.append("- Final action/job statuses:")
            for status, count in sorted(status_counts.items()):
                lines.append(f"  - `{status}`: `{count}`")
        missing_reason_counts = action_summary.get("missing_reason_counts") or {}
        if missing_reason_counts:
            lines.append("- Missing requirement reasons addressed:")
            for reason, count in missing_reason_counts.items():
                lines.append(f"  - `{reason}`: `{count}`")
        operational_signal_counts = action_summary.get(
            "operational_detail_missing_signal_counts"
        ) or {}
        if operational_signal_counts:
            lines.append("- Operational detail signals targeted:")
            for signal, count in operational_signal_counts.items():
                lines.append(f"  - `{signal}`: `{count}`")
        section_label_counts = action_summary.get("section_label_counts") or {}
        if section_label_counts:
            lines.append("- Remediation section labels targeted:")
            for index, (label, count) in enumerate(section_label_counts.items()):
                if index >= 8:
                    remaining = len(section_label_counts) - index
                    lines.append(f"  - `+{remaining} more`: `...`")
                    break
                lines.append(f"  - `{label}`: `{count}`")
    else:
        lines.append(
            "- `none`: No remediation action execution report was attached to this bundle."
        )
    executable_action_count = len(structured_readiness_actions) + sum(
        1 for row in gap_priority_rows if row.get("action_key")
    )
    if executable_action_count:
        manifest_json_path = gap_report.parent / "calibration_manifest.json"
        action_json_path = gap_report.parent / "calibration_action_execution.json"
        action_md_path = gap_report.parent / "calibration_action_execution.md"
        dry_run_command = (
            "py -3 scripts/run_calibration_manifest_actions.py "
            f"--manifest {_display_path(manifest_json_path)} --all "
            f"--out-json {_display_path(action_json_path)} "
            f"--out-md {_display_path(action_md_path)}"
        )
        execute_command = dry_run_command + " --execute --wait"
        lines.extend(
            [
                "",
                "## Executable remediation commands",
                "",
                (
                    f"- Executable actions found: `{executable_action_count}`. "
                    "Run dry-run first, then execute against a live API stack."
                ),
                "- Dry-run all manifest actions:",
                "",
                "```powershell",
                dry_run_command,
                "```",
                "",
                "- Execute all manifest actions and wait for generation jobs:",
                "",
                "```powershell",
                execute_command,
                "```",
            ]
        )
    lines.extend(["", "## Gap calibration focus summary", ""])
    if gap_focus_counts:
        for focus, count in sorted(
            gap_focus_counts.items(),
            key=lambda item: (-item[1], item[0]),
        ):
            lines.append(f"- `{focus}`: `{count}` sections")
    else:
        lines.append("- `none`: Section Gap Diagnostics not found or no section rows.")
    lines.extend(["", "## Regeneration priority shortlist", ""])
    if readiness_actions:
        lines.append(
            "- Readiness blockers come first because they affect exportability and "
            "can distort reference-gap interpretation."
        )
        for index, action in enumerate(readiness_actions, start=1):
            target_label = ""
            structured_index = index - 1
            if structured_index < len(structured_readiness_actions):
                target_label = _request_target_label(
                    structured_readiness_actions[structured_index].get("request_json")
                )
            suffix = f" (targets: {target_label})" if target_label else ""
            lines.append(f"{index}. {action}{suffix}")
        next_index = len(readiness_actions) + 1
    else:
        lines.append(
            "- No readiness blockers found; use the gap diagnostics to choose the "
            "first regeneration targets."
        )
        next_index = 1
    if gap_priority_rows:
        for row in gap_priority_rows:
            action_suffix = (
                f" action_key=`{row['action_key']}`"
                if row.get("action_key")
                else f" ui_action=`{row.get('ui_action')}`"
                if row.get("ui_action")
                else ""
            )
            lines.append(
                f"{next_index}. Gap `{row['focus']}`{action_suffix}: "
                "regenerate/reference-align "
                f"`{row['reference_section']}` using generated section "
                f"`{row['generated_section']}` as the nearest current base "
                f"(coverage `{row['coverage']:.2f}`, volume `{row['volume']:.2f}`, "
                f"reasons: {row['reasons']})."
            )
            next_index += 1
    elif not readiness_actions:
        lines.append(
            "1. No concrete regeneration targets were found in readiness or gap diagnostics."
        )
    lines.extend(
        [
            "",
            "## Tender/source documents",
            "",
        ]
    )
    if tenders:
        lines.extend(f"- `{_display_path(path)}`" for path in tenders)
    else:
        lines.append("- `none`")
    lines.extend(
        [
            "",
            "## Recommended review order",
            "",
            "1. Open the selected proposal snapshot and check Snapshot Warnings.",
            "2. Open the DOCX readiness report and resolve export blockers.",
            "3. Open the effective proposal snapshot to see the in-memory newest-per-section view.",
            "4. Open the gap report and review Universal Topic Coverage.",
            "5. Follow Calibration Recommendations before regenerating sections.",
            "6. Rerun this calibration bundle after regeneration.",
            "",
        ]
    )
    return "\n".join(lines)


def render_manifest_json(
    *,
    project_id: str,
    reference: Path,
    selected_snapshot: Path,
    effective_snapshot: Path,
    readiness_report: Path,
    gap_report: Path,
    tenders: list[Path],
    readiness: dict[str, Any] | None = None,
    snapshot_warnings: int = 0,
    gap_summary: dict[str, Any] | None = None,
    gap_focus_counts: dict[str, int] | None = None,
    gap_priority_rows: list[dict[str, Any]] | None = None,
    section_uid_by_generated_title: dict[str, str] | None = None,
    action_report_paths: list[Path] | None = None,
    action_execution_reports: list[dict[str, Any]] | None = None,
) -> str:
    readiness = readiness or {}
    blockers = [
        item
        for item in readiness.get("blockers") or []
        if isinstance(item, dict)
    ]
    action_report_paths = action_report_paths or []
    action_execution_reports = action_execution_reports or []
    payload = {
        "schema_version": "calibration_manifest.v1",
        "project_id": project_id,
        "mode": "non-mutating",
        "paths": {
            "reference": _display_path(reference),
            "selected_snapshot": _display_path(selected_snapshot),
            "effective_snapshot": _display_path(effective_snapshot),
            "readiness_report": _display_path(readiness_report),
            "gap_report": _display_path(gap_report),
            "tenders": [_display_path(path) for path in tenders],
            "action_execution_reports": [
                _display_path(path) for path in action_report_paths
            ],
        },
        "calibration_gates": {
            "snapshot_warnings": snapshot_warnings,
            "docx_readiness_status": readiness.get("status", "unknown"),
            "docx_readiness_blockers": len(blockers),
            "blockers": blockers,
            "gap_input_snapshot": "effective_proposal_snapshot.md",
        },
        "gap_quality_scorecard": gap_summary or {},
        "gap_calibration_focus_counts": gap_focus_counts or {},
        "action_execution_summary": action_execution_summary(
            action_execution_reports
        ),
        "action_execution_reports": action_execution_reports,
        "readiness_actions": structured_readiness_priority_actions(
            readiness,
            project_id=project_id,
        ),
        "gap_priority_rows": enrich_gap_priority_rows(
            gap_priority_rows or [],
            project_id=project_id,
            section_uid_by_generated_title=section_uid_by_generated_title,
            operational_detail_missing_signals=(gap_summary or {}).get(
                "operational_detail_missing_signals"
            )
            if isinstance(
                (gap_summary or {}).get("operational_detail_missing_signals"),
                list,
            )
            else None,
        ),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _api_imports() -> None:
    api_path = str(API_ROOT)
    if api_path not in sys.path:
        sys.path.insert(0, api_path)


async def export_readiness_report_markdown(
    project_id: str,
    out_path: Path,
) -> dict[str, Any]:
    _api_imports()
    from app.core.database import AsyncSessionLocal
    from app.core.models import Project
    from app.export.readiness_report import render_export_readiness_report
    from app.routers.export import _build_export_readiness, _load_selected_generations

    async with AsyncSessionLocal() as db:
        project = await db.get(Project, project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")

        selected_generations = await _load_selected_generations(project_id, db)
        readiness = await _build_export_readiness(project_id, selected_generations, db)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(render_export_readiness_report(readiness), encoding="utf-8")
        return readiness


def load_offline_readiness(manifest_path: Path | None) -> dict[str, Any]:
    if not manifest_path:
        return {
            "status": "unknown",
            "blockers": [],
            "offline_source": "snapshot_inputs_without_readiness_manifest",
        }

    manifest = load_comparison_manifest(manifest_path)
    gates = manifest.get("calibration_gates")
    if not isinstance(gates, dict):
        return {
            "status": "unknown",
            "blockers": [],
            "offline_source": str(manifest_path),
        }

    blockers = [
        item
        for item in gates.get("blockers") or []
        if isinstance(item, dict)
    ]
    return {
        "status": str(gates.get("docx_readiness_status") or "unknown"),
        "blockers": blockers,
        "offline_source": str(manifest_path),
    }


async def run_calibration_bundle(
    *,
    project_id: str,
    reference: Path,
    out_dir: Path,
    tenders: list[Path],
    previous_manifest: Path | None = None,
    action_reports: list[Path] | None = None,
    selected_snapshot: Path | None = None,
    effective_snapshot: Path | None = None,
    readiness_report: Path | None = None,
    offline_readiness_manifest: Path | None = None,
) -> dict[str, Path]:
    paths = calibration_output_paths(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    offline_inputs = [selected_snapshot, effective_snapshot, readiness_report]
    if any(offline_inputs) and not all(offline_inputs):
        raise ValueError(
            "Offline calibration requires --selected-snapshot, "
            "--effective-snapshot, and --readiness-report together."
        )

    if selected_snapshot and effective_snapshot and readiness_report:
        shutil.copyfile(selected_snapshot, paths["selected_snapshot"])
        shutil.copyfile(effective_snapshot, paths["effective_snapshot"])
        shutil.copyfile(readiness_report, paths["readiness_report"])
        readiness = load_offline_readiness(
            offline_readiness_manifest or previous_manifest
        )
    else:
        project_name, outline_sections, selected_generations = await load_snapshot(
            project_id
        )
        paths["selected_snapshot"].write_text(
            render_selected_proposal_markdown(
                project_name=project_name,
                project_id=project_id,
                outline_sections=outline_sections,
                selected_generations=selected_generations,
            ),
            encoding="utf-8",
        )
        effective_generations = newest_generation_per_section(selected_generations)
        paths["effective_snapshot"].write_text(
            render_selected_proposal_markdown(
                project_name=project_name,
                project_id=project_id,
                outline_sections=outline_sections,
                selected_generations=effective_generations,
                snapshot_mode="effective-newest-selected-per-section",
            ),
            encoding="utf-8",
        )
        readiness = await export_readiness_report_markdown(
            project_id,
            paths["readiness_report"],
        )

    reference_text = extract_text(reference)
    selected_text = extract_text(paths["selected_snapshot"])
    effective_text = extract_text(paths["effective_snapshot"])
    warning_count = snapshot_warning_count(selected_text)
    tender_text = "\n\n".join(extract_text(path) for path in tenders)
    report = render_report(
        tender_text=tender_text,
        reference_sections=split_sections(reference_text),
        generated_sections=split_sections(effective_text),
        reference_path=reference,
        generated_path=paths["effective_snapshot"],
        tender_paths=tenders,
    )
    paths["gap_report"].write_text(report, encoding="utf-8")
    gap_summary = gap_summary_metrics(report)
    gap_focus_counts = gap_calibration_focus_counts(report)
    gap_priority_rows = gap_regeneration_priority_rows(report)
    section_uid_by_generated_title = generated_section_uid_map(effective_text)
    action_report_paths = action_reports or []
    action_execution_reports = load_action_execution_reports(action_report_paths)
    paths["manifest"].write_text(
        render_manifest(
            project_id=project_id,
            reference=reference,
            selected_snapshot=paths["selected_snapshot"],
            effective_snapshot=paths["effective_snapshot"],
            readiness_report=paths["readiness_report"],
            gap_report=paths["gap_report"],
            tenders=tenders,
            readiness=readiness,
            snapshot_warnings=warning_count,
            gap_summary=gap_summary,
            gap_focus_counts=gap_focus_counts,
            gap_priority_rows=gap_priority_rows,
            section_uid_by_generated_title=section_uid_by_generated_title,
            action_report_paths=action_report_paths,
            action_execution_reports=action_execution_reports,
        ),
        encoding="utf-8",
    )
    manifest_json_text = render_manifest_json(
        project_id=project_id,
        reference=reference,
        selected_snapshot=paths["selected_snapshot"],
        effective_snapshot=paths["effective_snapshot"],
        readiness_report=paths["readiness_report"],
        gap_report=paths["gap_report"],
        tenders=tenders,
        readiness=readiness,
        snapshot_warnings=warning_count,
        gap_summary=gap_summary,
        gap_focus_counts=gap_focus_counts,
        gap_priority_rows=gap_priority_rows,
        section_uid_by_generated_title=section_uid_by_generated_title,
        action_report_paths=action_report_paths,
        action_execution_reports=action_execution_reports,
    )
    paths["manifest_json"].write_text(
        manifest_json_text,
        encoding="utf-8",
    )
    if previous_manifest:
        paths["comparison"].write_text(
            render_manifest_comparison(
                load_comparison_manifest(previous_manifest),
                json.loads(manifest_json_text),
            ),
            encoding="utf-8",
        )
    return paths


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a non-mutating calibration bundle: selected proposal "
            "snapshot plus gap analysis against a reference proposal."
        )
    )
    parser.add_argument("--project-id", required=True, help="Project UUID")
    parser.add_argument(
        "--reference",
        required=True,
        type=Path,
        help="Winning/reference proposal DOCX/PDF/TXT/MD",
    )
    parser.add_argument(
        "--tender",
        action="append",
        default=[],
        type=Path,
        help="Tender/source document. Can be passed multiple times.",
    )
    parser.add_argument(
        "--out-dir",
        required=True,
        type=Path,
        help="Bundle output directory",
    )
    parser.add_argument(
        "--previous-manifest",
        type=Path,
        help=(
            "Optional previous calibration_manifest.json. When set, writes a "
            "before/after calibration_manifest_comparison.md report."
        ),
    )
    parser.add_argument(
        "--action-report",
        action="append",
        default=[],
        type=Path,
        help=(
            "JSON report from run_calibration_manifest_actions.py --out-json. "
            "Can be passed multiple times."
        ),
    )
    parser.add_argument(
        "--selected-snapshot",
        type=Path,
        help=(
            "Existing selected_proposal_snapshot.md to reuse in offline mode. "
            "Requires --effective-snapshot and --readiness-report."
        ),
    )
    parser.add_argument(
        "--effective-snapshot",
        type=Path,
        help=(
            "Existing effective_proposal_snapshot.md to reuse in offline mode. "
            "Requires --selected-snapshot and --readiness-report."
        ),
    )
    parser.add_argument(
        "--readiness-report",
        type=Path,
        help=(
            "Existing docx_readiness_report.md to reuse in offline mode. "
            "Requires --selected-snapshot and --effective-snapshot."
        ),
    )
    parser.add_argument(
        "--offline-readiness-manifest",
        type=Path,
        help=(
            "Optional calibration_manifest.json whose readiness gates should be "
            "used when running with offline snapshot inputs."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    paths = asyncio.run(
        run_calibration_bundle(
            project_id=args.project_id,
            reference=args.reference,
            out_dir=args.out_dir,
            tenders=args.tender,
            previous_manifest=args.previous_manifest,
            action_reports=args.action_report,
            selected_snapshot=args.selected_snapshot,
            effective_snapshot=args.effective_snapshot,
            readiness_report=args.readiness_report,
            offline_readiness_manifest=args.offline_readiness_manifest,
        )
    )
    print(f"Wrote {paths['manifest']}")
    print(f"Wrote {paths['manifest_json']}")
    print(f"Wrote {paths['selected_snapshot']}")
    print(f"Wrote {paths['effective_snapshot']}")
    print(f"Wrote {paths['readiness_report']}")
    print(f"Wrote {paths['gap_report']}")
    if args.previous_manifest:
        print(f"Wrote {paths['comparison']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
