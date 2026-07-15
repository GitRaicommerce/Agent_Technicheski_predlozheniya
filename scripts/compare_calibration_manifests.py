"""Compare two calibration manifest JSON files after remediation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _int_value(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        return int(float(value))
    return 0


def _float_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        return float(value)
    return None


def _action_counts(rows: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        action_key = str(row.get("action_key") or "").strip()
        if action_key:
            counts[action_key] = counts.get(action_key, 0) + 1
    return counts


def _string_items(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _string_list_value(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        if value.strip().lower() == "n/a":
            return []
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _request_target_summary(request_json: Any) -> str:
    if not isinstance(request_json, dict):
        return ""
    section_uids = _string_items(request_json.get("section_uids"))
    title_hints = _string_items(request_json.get("section_title_hints"))
    parts: list[str] = []
    if section_uids:
        parts.append("uids=" + ", ".join(section_uids[:6]))
        if len(section_uids) > 6:
            parts.append(f"+{len(section_uids) - 6} more uids")
    if title_hints:
        parts.append("titles=" + ", ".join(title_hints[:4]))
        if len(title_hints) > 4:
            parts.append(f"+{len(title_hints) - 4} more titles")
    return "; ".join(parts)


def _action_target_summary(row: dict[str, Any]) -> str:
    parts: list[str] = []
    target_summary = _request_target_summary(row.get("request_json"))
    if target_summary:
        parts.append(target_summary)
    summary = str(row.get("summary") or "").strip()
    if not parts and summary and _int_value(row.get("section_count")):
        parts.append("sections=" + summary)
    section_labels = _section_label_summary(row.get("section_labels"))
    if section_labels:
        parts.append("labels=" + section_labels)
    return "; ".join(parts)


def _section_label_summary(value: Any) -> str:
    section_labels = _string_items(value)
    if not section_labels:
        return ""
    parts = section_labels[:4]
    if len(section_labels) > 4:
        parts.append(f"+{len(section_labels) - 4} more")
    return "; ".join(parts)


def _action_target_counts(rows: list[Any]) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        action_key = str(row.get("action_key") or "").strip()
        target_summary = _action_target_summary(row)
        if action_key and target_summary:
            key = (action_key, target_summary)
            counts[key] = counts.get(key, 0) + 1
    return counts


def _missing_reason_counts(rows: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("action_key") != "regenerate_missing_requirements":
            continue
        reason_counts = row.get("missing_reason_counts") or {}
        if not isinstance(reason_counts, dict):
            continue
        for reason, count in reason_counts.items():
            reason_label = str(reason).strip()
            if reason_label:
                counts[reason_label] = counts.get(reason_label, 0) + _int_value(count)
    return counts


def _summary_count_map(summary: Any, key: str) -> dict[str, int]:
    if not isinstance(summary, dict):
        return {}
    raw_counts = summary.get(key) or {}
    if not isinstance(raw_counts, dict):
        return {}
    return {
        str(label): _int_value(count)
        for label, count in raw_counts.items()
        if str(label).strip()
    }


def _status_counts(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    raw_counts = value.get("status_counts") or {}
    if not isinstance(raw_counts, dict):
        return {}
    return {
        str(status): _int_value(count)
        for status, count in raw_counts.items()
        if str(status)
    }


def _executed_action_count(summary: dict[str, Any]) -> int:
    if "executed_actions" in summary:
        return _int_value(summary.get("executed_actions"))
    status_counts = _status_counts(summary)
    if status_counts:
        return sum(
            count
            for status, count in status_counts.items()
            if status != "planned"
        )
    return _int_value(summary.get("total_actions"))


def _action_evidence_level(summary: dict[str, Any]) -> str:
    explicit = str(summary.get("evidence_level") or "").strip()
    if explicit:
        return explicit
    if bool(summary.get("ready_for_bundle")):
        return "proof"
    failure_count = _int_value(summary.get("failure_report_count"))
    unexecuted_count = _int_value(summary.get("unexecuted_report_count"))
    status_counts = _status_counts(summary)
    if failure_count or any(
        status not in {"done", "executed", "planned"}
        and count > 0
        for status, count in status_counts.items()
    ):
        return "failed"
    if unexecuted_count or status_counts.get("planned", 0) > 0:
        return "planned"
    if status_counts or _int_value(summary.get("report_count")):
        return "insufficient"
    return "none"


def summarize_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    gates = manifest.get("calibration_gates") or {}
    scorecard = manifest.get("gap_quality_scorecard") or {}
    focus_counts = manifest.get("gap_calibration_focus_counts") or {}
    readiness_actions = manifest.get("readiness_actions") or []
    gap_rows = manifest.get("gap_priority_rows") or []
    action_execution_summary = manifest.get("action_execution_summary") or {}
    if not isinstance(gates, dict):
        gates = {}
    if not isinstance(scorecard, dict):
        scorecard = {}
    if not isinstance(focus_counts, dict):
        focus_counts = {}
    if not isinstance(readiness_actions, list):
        readiness_actions = []
    if not isinstance(gap_rows, list):
        gap_rows = []

    return {
        "project_id": str(manifest.get("project_id") or ""),
        "readiness_status": str(gates.get("docx_readiness_status") or "unknown"),
        "readiness_blockers": _int_value(gates.get("docx_readiness_blockers")),
        "snapshot_warnings": _int_value(gates.get("snapshot_warnings")),
        "volume_ratio": _float_value(
            scorecard.get("generated_reference_volume_ratio")
        ),
        "operational_detail_ratio": _float_value(
            scorecard.get("operational_detail_ratio")
        ),
        "operational_detail_status": str(
            scorecard.get("operational_detail_status") or "unknown"
        ),
        "operational_detail_missing_signals": _string_list_value(
            scorecard.get("operational_detail_missing_signals")
        ),
        "operational_detail_missing_signal_count": _int_value(
            scorecard.get("operational_detail_missing_signal_count")
        ),
        "content_generated_sections": _int_value(
            scorecard.get("content_generated_sections")
        ),
        "content_reference_sections": _int_value(
            scorecard.get("content_reference_sections")
        ),
        "gap_focus_counts": {
            str(key): _int_value(value) for key, value in focus_counts.items()
        },
        "readiness_action_counts": _action_counts(readiness_actions),
        "gap_action_counts": _action_counts(gap_rows),
        "readiness_action_target_counts": _action_target_counts(readiness_actions),
        "gap_action_target_counts": _action_target_counts(gap_rows),
        "missing_requirement_reason_counts": _missing_reason_counts(
            readiness_actions
        ),
        "action_execution_section_label_counts": _summary_count_map(
            action_execution_summary,
            "section_label_counts",
        ),
        "action_execution_operational_signal_counts": _summary_count_map(
            action_execution_summary,
            "operational_detail_missing_signal_counts",
        ),
        "executed_action_count": _int_value(
            _executed_action_count(action_execution_summary)
            if isinstance(action_execution_summary, dict)
            else 0,
        ),
        "action_evidence_ready": bool(
            action_execution_summary.get("ready_for_bundle")
            if isinstance(action_execution_summary, dict)
            else False
        ),
        "action_evidence_level": (
            _action_evidence_level(action_execution_summary)
            if isinstance(action_execution_summary, dict)
            else "none"
        ),
        "action_evidence_failures": _int_value(
            action_execution_summary.get("failure_report_count")
            if isinstance(action_execution_summary, dict)
            else 0
        ),
        "action_evidence_unexecuted": _int_value(
            action_execution_summary.get("unexecuted_report_count")
            if isinstance(action_execution_summary, dict)
            else 0
        ),
        "execution_report_count": _int_value(
            action_execution_summary.get("report_count")
            if isinstance(action_execution_summary, dict)
            else 0
        ),
        "execution_status_counts": _status_counts(action_execution_summary),
    }


def _format_number(value: int | float | None) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _format_delta(before: int | float | None, after: int | float | None) -> str:
    if before is None or after is None:
        return "n/a"
    delta = after - before
    if isinstance(delta, float):
        return f"{delta:+.2f}"
    return f"{delta:+d}"


def _sorted_keys(*maps: dict[str, int]) -> list[str]:
    keys: set[str] = set()
    for item in maps:
        keys.update(item)
    return sorted(keys)


def _sorted_target_keys(*maps: dict[tuple[str, str], int]) -> list[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for item in maps:
        keys.update(item)
    return sorted(keys)


def _escape_md_cell(value: str) -> str:
    return value.replace("|", "\\|")


def _direction_for_metric(metric: str, before: Any, after: Any) -> str:
    if before is None or after is None:
        return "insufficient data"
    if metric in {"snapshot warnings", "readiness blockers"}:
        if after < before:
            return "improved"
        if after > before:
            return "regressed"
        return "unchanged"
    if metric in {"generated/reference volume ratio", "operational detail ratio"}:
        if after > before:
            return "improved"
        if after < before:
            return "regressed"
        return "unchanged"
    return "observed"


def recommendation(before: dict[str, Any], after: dict[str, Any]) -> str:
    failed_actions = after["execution_status_counts"].get("error", 0)
    if failed_actions > 0 or after["action_evidence_failures"] > 0:
        return (
            "Inspect failed remediation jobs before interpreting calibration "
            "movement; rerun or fix the failed action execution report entries first."
        )
    if after["action_evidence_unexecuted"] > 0:
        return (
            "Attached action evidence still contains planned/unexecuted actions; "
            "run remediation with --execute --wait before interpreting calibration movement."
        )
    if after["readiness_blockers"] > 0:
        return (
            "Resolve remaining DOCX readiness blockers first; they can still "
            "distort reference-gap interpretation."
        )
    after_focus = after["gap_focus_counts"]
    if after_focus.get("outline mapping", 0) > 0:
        return (
            "Review outline mapping next; generation depth fixes are weaker when "
            "reference sections still map to the wrong generated section."
        )
    if after_focus.get("drafting depth", 0) > 0:
        return (
            "Run detailed regeneration for remaining drafting-depth gaps and rerun "
            "the calibration bundle."
        )
    if after_focus.get("grounding and checklist coverage", 0) > 0:
        return (
            "Run coverage regeneration for remaining grounding/checklist gaps and "
            "rerun the calibration bundle."
        )
    after_operational_ratio = after.get("operational_detail_ratio")
    after_operational_status = after.get("operational_detail_status")
    before_operational_ratio = before.get("operational_detail_ratio")
    operational_is_weak = after_operational_status in {"weak", "partial"} or (
        after_operational_ratio is not None and after_operational_ratio < 0.70
    )
    operational_did_not_improve = (
        before_operational_ratio is not None
        and after_operational_ratio is not None
        and after_operational_ratio <= before_operational_ratio
    )
    if operational_is_weak and operational_did_not_improve:
        missing_signals = after.get("operational_detail_missing_signals") or []
        signal_hint = (
            " Missing signals: " + ", ".join(missing_signals[:8]) + "."
            if missing_signals
            else ""
        )
        return (
            "Operational detail coverage is still weak and did not improve; run "
            "detailed regeneration focused on roles, controls, records, sequence, "
            "monitoring, acceptance evidence, escalation, and corrective actions."
            f"{signal_hint}"
        )
    if operational_is_weak:
        missing_signals = after.get("operational_detail_missing_signals") or []
        signal_hint = (
            " Missing signals: " + ", ".join(missing_signals[:8]) + "."
            if missing_signals
            else ""
        )
        return (
            "Operational detail coverage improved but remains weak/partial; run "
            "another detailed regeneration pass before treating the generated "
            f"proposal as reference-quality.{signal_hint}"
        )
    before_ratio = before.get("volume_ratio")
    after_ratio = after.get("volume_ratio")
    if before_ratio is not None and after_ratio is not None and after_ratio <= before_ratio:
        return (
            "Gap focus counts are clear, but the volume ratio did not improve; "
            "inspect generated sections for generic or compressed writing."
        )
    return "Calibration metrics improved or remained clear; proceed to human review/export."


def render_comparison(before_manifest: dict[str, Any], after_manifest: dict[str, Any]) -> str:
    before = summarize_manifest(before_manifest)
    after = summarize_manifest(after_manifest)
    lines = [
        "# Calibration manifest comparison",
        "",
        f"- Project before: `{before['project_id'] or 'unknown'}`",
        f"- Project after: `{after['project_id'] or 'unknown'}`",
        "",
        "## Gate deltas",
        "",
        "| Metric | Before | After | Delta | Interpretation |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    gate_rows = [
        (
            "snapshot warnings",
            before["snapshot_warnings"],
            after["snapshot_warnings"],
        ),
        (
            "readiness blockers",
            before["readiness_blockers"],
            after["readiness_blockers"],
        ),
        (
            "generated/reference volume ratio",
            before["volume_ratio"],
            after["volume_ratio"],
        ),
        (
            "operational detail ratio",
            before["operational_detail_ratio"],
            after["operational_detail_ratio"],
        ),
        (
            "content generated sections",
            before["content_generated_sections"],
            after["content_generated_sections"],
        ),
    ]
    for metric, before_value, after_value in gate_rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    metric,
                    _format_number(before_value),
                    _format_number(after_value),
                    _format_delta(before_value, after_value),
                    _direction_for_metric(metric, before_value, after_value),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Operational detail missing signal deltas",
            "",
            "| Signal | Before missing | After missing | Delta |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    before_missing_signals = {
        signal: 1 for signal in before["operational_detail_missing_signals"]
    }
    after_missing_signals = {
        signal: 1 for signal in after["operational_detail_missing_signals"]
    }
    signal_rows_added = False
    for signal in _sorted_keys(before_missing_signals, after_missing_signals):
        before_count = before_missing_signals.get(signal, 0)
        after_count = after_missing_signals.get(signal, 0)
        signal_rows_added = True
        lines.append(
            f"| {_escape_md_cell(signal)} | {before_count} | {after_count} | "
            f"{_format_delta(before_count, after_count)} |"
        )
    if not signal_rows_added:
        lines.append("| n/a | 0 | 0 | +0 |")

    lines.extend(
        [
            "",
            "## Gap focus deltas",
            "",
            "| Focus | Before | After | Delta |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for focus in _sorted_keys(before["gap_focus_counts"], after["gap_focus_counts"]):
        before_count = before["gap_focus_counts"].get(focus, 0)
        after_count = after["gap_focus_counts"].get(focus, 0)
        lines.append(
            f"| {focus} | {before_count} | {after_count} | "
            f"{_format_delta(before_count, after_count)} |"
        )

    lines.extend(
        [
            "",
            "## Executable action deltas",
            "",
            "| Source | Action key | Before | After | Delta |",
            "| --- | --- | ---: | ---: | ---: |",
        ]
    )
    action_sources = [
        ("readiness_actions", before["readiness_action_counts"], after["readiness_action_counts"]),
        ("gap_priority_rows", before["gap_action_counts"], after["gap_action_counts"]),
    ]
    for source, before_counts, after_counts in action_sources:
        for action_key in _sorted_keys(before_counts, after_counts):
            before_count = before_counts.get(action_key, 0)
            after_count = after_counts.get(action_key, 0)
            lines.append(
                f"| {source} | `{action_key}` | {before_count} | {after_count} | "
                f"{_format_delta(before_count, after_count)} |"
            )

    lines.extend(
        [
            "",
            "## Executable action target deltas",
            "",
            "| Source | Action key | Targets | Before | After | Delta |",
            "| --- | --- | --- | ---: | ---: | ---: |",
        ]
    )
    target_sources = [
        (
            "readiness_actions",
            before["readiness_action_target_counts"],
            after["readiness_action_target_counts"],
        ),
        (
            "gap_priority_rows",
            before["gap_action_target_counts"],
            after["gap_action_target_counts"],
        ),
    ]
    target_rows_added = False
    for source, before_counts, after_counts in target_sources:
        for action_key, target_summary in _sorted_target_keys(before_counts, after_counts):
            before_count = before_counts.get((action_key, target_summary), 0)
            after_count = after_counts.get((action_key, target_summary), 0)
            target_rows_added = True
            lines.append(
                f"| {source} | `{action_key}` | {_escape_md_cell(target_summary)} | "
                f"{before_count} | {after_count} | "
                f"{_format_delta(before_count, after_count)} |"
            )
    if not target_rows_added:
        lines.append("| n/a | n/a | no section-specific action targets | 0 | 0 | +0 |")

    lines.extend(
        [
            "",
            "## Missing requirement reason deltas",
            "",
            "| Reason | Before | After | Delta |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    reason_rows_added = False
    for reason in _sorted_keys(
        before["missing_requirement_reason_counts"],
        after["missing_requirement_reason_counts"],
    ):
        before_count = before["missing_requirement_reason_counts"].get(reason, 0)
        after_count = after["missing_requirement_reason_counts"].get(reason, 0)
        reason_rows_added = True
        lines.append(
            f"| {_escape_md_cell(reason)} | {before_count} | {after_count} | "
            f"{_format_delta(before_count, after_count)} |"
        )
    if not reason_rows_added:
        lines.append("| n/a | 0 | 0 | +0 |")

    lines.extend(
        [
            "",
            "## Action execution section label deltas",
            "",
            "| Section label | Before | After | Delta |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    label_rows_added = False
    for label in _sorted_keys(
        before["action_execution_section_label_counts"],
        after["action_execution_section_label_counts"],
    ):
        before_count = before["action_execution_section_label_counts"].get(label, 0)
        after_count = after["action_execution_section_label_counts"].get(label, 0)
        label_rows_added = True
        lines.append(
            f"| {_escape_md_cell(label)} | {before_count} | {after_count} | "
            f"{_format_delta(before_count, after_count)} |"
        )
    if not label_rows_added:
        lines.append("| n/a | 0 | 0 | +0 |")

    lines.extend(
        [
            "",
            "## Action execution operational signal deltas",
            "",
            "| Signal | Before | After | Delta |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    action_signal_rows_added = False
    for signal in _sorted_keys(
        before["action_execution_operational_signal_counts"],
        after["action_execution_operational_signal_counts"],
    ):
        before_count = before["action_execution_operational_signal_counts"].get(
            signal,
            0,
        )
        after_count = after["action_execution_operational_signal_counts"].get(
            signal,
            0,
        )
        action_signal_rows_added = True
        lines.append(
            f"| {_escape_md_cell(signal)} | {before_count} | {after_count} | "
            f"{_format_delta(before_count, after_count)} |"
        )
    if not action_signal_rows_added:
        lines.append("| n/a | 0 | 0 | +0 |")

    lines.extend(
        [
            "",
            "## Action execution evidence",
            "",
            "| Metric | Before | After | Delta |",
            "| --- | ---: | ---: | ---: |",
            (
                "| action evidence ready | "
                f"{int(before['action_evidence_ready'])} | "
                f"{int(after['action_evidence_ready'])} | "
                f"{_format_delta(int(before['action_evidence_ready']), int(after['action_evidence_ready']))} |"
            ),
            (
                "| action evidence level | "
                f"`{before['action_evidence_level']}` | "
                f"`{after['action_evidence_level']}` | n/a |"
            ),
            (
                "| execution reports | "
                f"{before['execution_report_count']} | "
                f"{after['execution_report_count']} | "
                f"{_format_delta(before['execution_report_count'], after['execution_report_count'])} |"
            ),
            (
                "| executed actions | "
                f"{before['executed_action_count']} | "
                f"{after['executed_action_count']} | "
                f"{_format_delta(before['executed_action_count'], after['executed_action_count'])} |"
            ),
            (
                "| reports with failures | "
                f"{before['action_evidence_failures']} | "
                f"{after['action_evidence_failures']} | "
                f"{_format_delta(before['action_evidence_failures'], after['action_evidence_failures'])} |"
            ),
            (
                "| reports with unexecuted actions | "
                f"{before['action_evidence_unexecuted']} | "
                f"{after['action_evidence_unexecuted']} | "
                f"{_format_delta(before['action_evidence_unexecuted'], after['action_evidence_unexecuted'])} |"
            ),
            "",
            "| Final status | Before | After | Delta |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for status in _sorted_keys(
        before["execution_status_counts"],
        after["execution_status_counts"],
    ):
        before_count = before["execution_status_counts"].get(status, 0)
        after_count = after["execution_status_counts"].get(status, 0)
        lines.append(
            f"| `{status}` | {before_count} | {after_count} | "
            f"{_format_delta(before_count, after_count)} |"
        )

    lines.extend(
        [
            "",
            "## Suggested next step",
            "",
            f"- {recommendation(before, after)}",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare before/after calibration_manifest.json files."
    )
    parser.add_argument("--before", required=True, type=Path)
    parser.add_argument("--after", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        text = render_comparison(load_manifest(args.before), load_manifest(args.after))
        if args.out:
            args.out.write_text(text, encoding="utf-8")
        else:
            print(text)
        return 0
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
