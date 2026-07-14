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
        "executed_action_count": _int_value(
            action_execution_summary.get("total_actions")
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


def _direction_for_metric(metric: str, before: Any, after: Any) -> str:
    if before is None or after is None:
        return "insufficient data"
    if metric in {"snapshot warnings", "readiness blockers"}:
        if after < before:
            return "improved"
        if after > before:
            return "regressed"
        return "unchanged"
    if metric == "generated/reference volume ratio":
        if after > before:
            return "improved"
        if after < before:
            return "regressed"
        return "unchanged"
    return "observed"


def recommendation(before: dict[str, Any], after: dict[str, Any]) -> str:
    failed_actions = after["execution_status_counts"].get("error", 0)
    if failed_actions > 0:
        return (
            "Inspect failed remediation jobs before interpreting calibration "
            "movement; rerun or fix the failed action execution report entries first."
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
            "## Action execution evidence",
            "",
            "| Metric | Before | After | Delta |",
            "| --- | ---: | ---: | ---: |",
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
