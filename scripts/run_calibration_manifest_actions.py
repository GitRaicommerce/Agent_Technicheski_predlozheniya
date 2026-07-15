"""Run remediation actions declared in a calibration manifest JSON."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

TERMINAL_JOB_STATUSES = {"done", "error"}
SUCCESS_ACTION_STATUSES = {"done", "executed"}


@dataclass(frozen=True)
class ManifestAction:
    action_key: str
    api_method: str
    api_path: str
    request_json: dict[str, Any] | None = None
    source: str = "readiness_actions"
    blocker_code: str = ""
    section_count: int = 0
    summary: str = ""
    section_labels: list[str] | None = None
    missing_reason_counts: dict[str, int] | None = None
    operational_detail_missing_signals: list[str] | None = None


def load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Calibration manifest must be a JSON object")
    return payload


def _action_dedupe_key(
    action_key: str,
    api_path: str,
    request_json: dict[str, Any] | None,
) -> tuple[str, str, str]:
    request_part = json.dumps(request_json or {}, ensure_ascii=False, sort_keys=True)
    return (action_key, api_path, request_part)


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        if value.strip().lower() == "n/a":
            return []
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def manifest_actions(manifest: dict[str, Any]) -> list[ManifestAction]:
    raw_readiness_actions = manifest.get("readiness_actions") or []
    if not isinstance(raw_readiness_actions, list):
        raise ValueError("Manifest readiness_actions must be a list")
    raw_gap_rows = manifest.get("gap_priority_rows") or []
    if not isinstance(raw_gap_rows, list):
        raise ValueError("Manifest gap_priority_rows must be a list")
    scorecard = manifest.get("gap_quality_scorecard") or {}
    if not isinstance(scorecard, dict):
        scorecard = {}
    global_operational_missing_signals = _string_list(
        scorecard.get("operational_detail_missing_signals")
    )

    actions: list[ManifestAction] = []
    seen: set[tuple[str, str, str]] = set()
    for index, item in enumerate(raw_readiness_actions, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Manifest readiness action #{index} must be an object")
        action_key = str(item.get("action_key") or "").strip()
        api_method = str(item.get("api_method") or "POST").strip().upper()
        api_path = str(item.get("api_path") or "").strip()
        if not action_key:
            raise ValueError(
                "Manifest readiness action "
                f"#{index} must include action_key"
            )
        if not api_path:
            api_path = f"/api/v1/agents/{{project_id}}/remediation-actions/{action_key}"
        request_json = item.get("request_json")
        if request_json is not None and not isinstance(request_json, dict):
            raise ValueError(
                "Manifest readiness action "
                f"#{index} request_json must be an object"
            )
        missing_reason_counts = item.get("missing_reason_counts")
        if missing_reason_counts is not None and not isinstance(
            missing_reason_counts,
            dict,
        ):
            raise ValueError(
                "Manifest readiness action "
                f"#{index} missing_reason_counts must be an object"
            )
        section_labels = item.get("section_labels")
        if section_labels is not None and not isinstance(section_labels, list):
            raise ValueError(
                "Manifest readiness action "
                f"#{index} section_labels must be a list"
            )
        dedupe_key = _action_dedupe_key(action_key, api_path, request_json)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        actions.append(
            ManifestAction(
                action_key=action_key,
                api_method=api_method,
                api_path=api_path,
                request_json=request_json,
                source="readiness_actions",
                blocker_code=str(item.get("blocker_code") or ""),
                section_count=int(item.get("section_count") or 0),
                summary=str(item.get("summary") or ""),
                section_labels=[
                    str(label).strip()
                    for label in (section_labels or [])
                    if str(label).strip()
                ]
                or None,
                missing_reason_counts={
                    str(reason): int(count)
                    for reason, count in (missing_reason_counts or {}).items()
                    if str(reason).strip()
                }
                or None,
                operational_detail_missing_signals=(
                    global_operational_missing_signals
                    if action_key == "regenerate_quality_depth"
                    else None
                ),
            )
        )

    for index, item in enumerate(raw_gap_rows, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Manifest gap priority row #{index} must be an object")
        action_key = str(item.get("action_key") or "").strip()
        api_path = str(item.get("api_path") or "").strip()
        if not action_key or not api_path:
            continue
        request_json = item.get("request_json")
        if request_json is not None and not isinstance(request_json, dict):
            raise ValueError(
                f"Manifest gap priority row #{index} request_json must be an object"
            )
        dedupe_key = _action_dedupe_key(action_key, api_path, request_json)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        api_method = str(item.get("api_method") or "POST").strip().upper()
        reference_section = str(item.get("reference_section") or "").strip()
        focus = str(item.get("focus") or "").strip()
        summary_parts = []
        if focus:
            summary_parts.append(f"gap={focus}")
        if reference_section:
            summary_parts.append(f"reference={reference_section}")
        actions.append(
            ManifestAction(
                action_key=action_key,
                api_method=api_method,
                api_path=api_path,
                request_json=request_json,
                source="gap_priority_rows",
                blocker_code=focus,
                section_count=1,
                summary=", ".join(summary_parts),
                operational_detail_missing_signals=(
                    global_operational_missing_signals
                    if action_key == "regenerate_quality_depth"
                    else None
                ),
            )
        )
    return actions


def select_actions(
    actions: list[ManifestAction],
    *,
    action_keys: list[str],
    all_actions: bool,
) -> list[ManifestAction]:
    if all_actions and action_keys:
        raise ValueError("Use either --all or --action-key, not both")
    if all_actions:
        return actions
    if not action_keys:
        return actions

    wanted = set(action_keys)
    selected = [action for action in actions if action.action_key in wanted]
    missing = sorted(wanted - {action.action_key for action in selected})
    if missing:
        raise ValueError(f"Action key(s) not found in manifest: {', '.join(missing)}")
    return selected


def action_url(api_base: str, api_path: str, project_id: str | None) -> str:
    path = api_path
    if "{project_id}" in path:
        if not project_id:
            raise ValueError("Manifest project_id is required for templated api_path")
        path = path.replace("{project_id}", urllib.parse.quote(project_id, safe=""))

    if path.startswith("http://") or path.startswith("https://"):
        return path

    return urllib.parse.urljoin(api_base.rstrip("/") + "/", path.lstrip("/"))


def execute_action(
    action: ManifestAction,
    *,
    url: str,
    timeout: float,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    body = json.dumps(action.request_json or {}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method=action.api_method,
        headers={"Content-Type": "application/json"},
    )
    with opener(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")
        if not body:
            return {"status_code": response.status, "body": None}
        try:
            return {"status_code": response.status, "body": json.loads(body)}
        except json.JSONDecodeError:
            return {"status_code": response.status, "body": body}


def job_result_from_action_response(result: dict[str, Any]) -> dict[str, Any] | None:
    body = result.get("body")
    if not isinstance(body, dict):
        return None
    job = body.get("result")
    if not isinstance(job, dict) or not job.get("id"):
        return None
    return job


def fetch_json(
    *,
    url: str,
    timeout: float,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        method="GET",
        headers={"Accept": "application/json"},
    )
    with opener(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")
        if not body:
            return {"status_code": response.status, "body": None}
        try:
            return {"status_code": response.status, "body": json.loads(body)}
        except json.JSONDecodeError:
            return {"status_code": response.status, "body": body}


def job_status_url(api_base: str, project_id: str, job_id: str) -> str:
    project_part = urllib.parse.quote(project_id, safe="")
    job_part = urllib.parse.quote(job_id, safe="")
    return urllib.parse.urljoin(
        api_base.rstrip("/") + "/",
        f"api/v1/agents/{project_part}/generation-jobs/{job_part}",
    )


def wait_for_job_result(
    action_result: dict[str, Any],
    *,
    api_base: str,
    project_id: str | None,
    timeout: float,
    poll_interval: float,
    opener: Callable[..., Any] = urllib.request.urlopen,
    sleeper: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any] | None:
    job = job_result_from_action_response(action_result)
    if not job:
        return None

    job_id = str(job["id"])
    job_project_id = str(job.get("project_id") or project_id or "")
    if not job_project_id:
        raise ValueError("Cannot wait for generation job without project_id")

    url = job_status_url(api_base, job_project_id, job_id)
    deadline = monotonic() + timeout
    last_result: dict[str, Any] | None = None
    while True:
        last_result = fetch_json(url=url, timeout=timeout, opener=opener)
        body = last_result.get("body")
        status = body.get("status") if isinstance(body, dict) else None
        if status in TERMINAL_JOB_STATUSES:
            return last_result
        if monotonic() >= deadline:
            raise TimeoutError(
                f"Timed out waiting for generation job {job_id}; "
                f"last status was {status or 'unknown'}"
            )
        sleeper(poll_interval)


def render_action_line(action: ManifestAction, url: str) -> str:
    bits = [
        action.action_key,
        action.api_method,
        url,
        f"source={action.source}",
        f"sections={action.section_count}",
    ]
    if action.blocker_code:
        bits.append(f"blocker={action.blocker_code}")
    if action.summary:
        bits.append(f"summary={action.summary}")
    return " | ".join(bits)


def request_target_summary(request_json: dict[str, Any] | None) -> str:
    if not isinstance(request_json, dict) or not request_json:
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


def action_target_summary(action: ManifestAction) -> str:
    target_summary = request_target_summary(action.request_json)
    if target_summary:
        return target_summary
    if action.summary and action.section_count:
        return "sections=" + action.summary
    return ""


def guidance_summary(request_json: dict[str, Any] | None) -> str:
    if not isinstance(request_json, dict) or not request_json:
        return ""

    parts: list[str] = []
    gap_reasons = [
        str(item).strip()
        for item in request_json.get("gap_reasons") or []
        if str(item).strip()
    ]
    if gap_reasons:
        parts.append("reasons=" + ", ".join(gap_reasons[:6]))
        if len(gap_reasons) > 6:
            parts.append(f"+{len(gap_reasons) - 6} more reasons")
    reference_section = str(request_json.get("reference_section") or "").strip()
    if reference_section:
        parts.append(f"reference={reference_section}")
    generated_section = str(request_json.get("generated_section") or "").strip()
    if generated_section:
        parts.append(f"generated={generated_section}")
    operational_signals = [
        str(item).strip()
        for item in request_json.get("operational_detail_missing_signals") or []
        if str(item).strip()
    ]
    if operational_signals:
        parts.append("signals=" + ", ".join(operational_signals[:8]))
        if len(operational_signals) > 8:
            parts.append(f"+{len(operational_signals) - 8} more signals")
    return "; ".join(parts)


def missing_reason_summary(action: ManifestAction) -> str:
    if not action.missing_reason_counts:
        return ""
    parts = [
        f"{reason}={count}"
        for reason, count in sorted(
            action.missing_reason_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]
    return "; ".join(parts[:4])


def operational_signal_summary(action: ManifestAction) -> str:
    signals = action.operational_detail_missing_signals or []
    if not signals:
        return ""
    parts = signals[:8]
    if len(signals) > 8:
        parts.append(f"+{len(signals) - 8} more")
    return ", ".join(parts)


def section_label_summary(action: ManifestAction) -> str:
    if action.section_labels:
        parts = action.section_labels[:4]
        if len(action.section_labels) > 4:
            parts.append(f"+{len(action.section_labels) - 4} more")
        return "; ".join(parts)
    return ""


def action_execution_record(
    action: ManifestAction,
    *,
    url: str,
    executed: bool,
    action_result: dict[str, Any] | None = None,
    wait_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    final_status = "planned"
    if executed:
        final_status = "executed"
    wait_body = wait_result.get("body") if isinstance(wait_result, dict) else None
    if isinstance(wait_body, dict) and wait_body.get("status"):
        final_status = str(wait_body["status"])

    return {
        "action_key": action.action_key,
        "source": action.source,
        "api_method": action.api_method,
        "api_path": action.api_path,
        "url": url,
        "blocker_code": action.blocker_code,
        "section_count": action.section_count,
        "summary": action.summary,
        "section_labels": action.section_labels or [],
        "section_label_summary": section_label_summary(action),
        "missing_reason_counts": action.missing_reason_counts or {},
        "missing_reason_summary": missing_reason_summary(action),
        "operational_detail_missing_signals": (
            action.operational_detail_missing_signals or []
        ),
        "operational_detail_missing_signal_summary": operational_signal_summary(
            action
        ),
        "request_json": action.request_json or {},
        "target_summary": action_target_summary(action),
        "guidance_summary": guidance_summary(action.request_json),
        "executed": executed,
        "final_status": final_status,
        "action_result": action_result,
        "wait_result": wait_result,
    }


def action_execution_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    executed_count = 0
    for record in records:
        status = str(record.get("final_status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        if record.get("executed"):
            executed_count += 1

    failure_statuses = sorted(
        status
        for status in status_counts
        if status not in SUCCESS_ACTION_STATUSES and status != "planned"
    )
    planned_count = status_counts.get("planned", 0)
    has_failures = bool(failure_statuses)
    has_unexecuted_actions = planned_count > 0
    ready_for_bundle = bool(records) and not has_failures and not has_unexecuted_actions
    if not records:
        evidence_level = "none"
    elif has_failures:
        evidence_level = "failed"
    elif has_unexecuted_actions:
        evidence_level = "planned"
    else:
        evidence_level = "proof"
    if not records:
        recommendation = "No executable remediation actions were found in the manifest."
    elif has_failures:
        recommendation = (
            "Resolve failed remediation actions before building the next calibration bundle."
        )
    elif has_unexecuted_actions:
        recommendation = (
            "Run the selected remediation actions with --execute --wait before using "
            "this report as proof for a follow-up calibration bundle."
        )
    else:
        recommendation = (
            "All selected remediation actions completed without reported failures; "
            "build the next calibration bundle with this action report attached."
        )
    return {
        "total_actions": len(records),
        "executed_actions": executed_count,
        "status_counts": status_counts,
        "failure_statuses": failure_statuses,
        "has_failures": has_failures,
        "has_unexecuted_actions": has_unexecuted_actions,
        "ready_for_bundle": ready_for_bundle,
        "evidence_level": evidence_level,
        "recommendation": recommendation,
    }


def render_execution_report_json(records: list[dict[str, Any]]) -> str:
    summary = action_execution_summary(records)
    payload = {
        "schema_version": "calibration_action_execution.v1",
        **summary,
        "actions": records,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def render_execution_report_markdown(records: list[dict[str, Any]]) -> str:
    summary = action_execution_summary(records)
    lines = [
        "# Calibration action execution report",
        "",
        f"- Total actions: `{summary['total_actions']}`",
        f"- Executed actions: `{summary['executed_actions']}`",
        f"- Evidence level: `{summary['evidence_level']}`",
        f"- Ready for calibration bundle: `{'yes' if summary['ready_for_bundle'] else 'no'}`",
        f"- Has failures: `{'yes' if summary['has_failures'] else 'no'}`",
        f"- Has unexecuted actions: `{'yes' if summary['has_unexecuted_actions'] else 'no'}`",
        f"- Recommendation: {summary['recommendation']}",
        "",
        "| Action key | Source | Executed | Final status | Sections | Targets | Guidance | Section labels | Missing reasons | Operational signals | Summary |",
        "| --- | --- | --- | --- | ---: | --- | --- | --- | --- | --- | --- |",
    ]
    for record in records:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(record.get("action_key") or ""),
                    str(record.get("source") or ""),
                    "yes" if record.get("executed") else "no",
                    str(record.get("final_status") or "unknown"),
                    str(record.get("section_count") or 0),
                    str(record.get("target_summary") or "").replace("|", "\\|"),
                    str(record.get("guidance_summary") or "").replace("|", "\\|"),
                    str(record.get("section_label_summary") or "").replace(
                        "|",
                        "\\|",
                    ),
                    str(record.get("missing_reason_summary") or "").replace(
                        "|",
                        "\\|",
                    ),
                    str(
                        record.get("operational_detail_missing_signal_summary") or ""
                    ).replace("|", "\\|"),
                    str(record.get("summary") or "").replace("|", "\\|"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "List or execute remediation API actions from calibration_manifest.json. "
            "Dry-run is the default."
        )
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--api-base", default="http://localhost:8000")
    parser.add_argument("--action-key", action="append", default=[])
    parser.add_argument("--all", action="store_true", help="Select all manifest actions")
    parser.add_argument("--execute", action="store_true", help="Actually call the API")
    parser.add_argument(
        "--wait",
        action="store_true",
        help="After executing generation actions, poll their background jobs to completion.",
    )
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--wait-timeout", type=float, default=1800.0)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument(
        "--out-json",
        type=Path,
        help="Write a machine-readable execution report for planned/executed actions.",
    )
    parser.add_argument(
        "--out-md",
        type=Path,
        help="Write a Markdown execution report for planned/executed actions.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
        actions = manifest_actions(manifest)
        selected = select_actions(
            actions,
            action_keys=args.action_key,
            all_actions=args.all,
        )
        if args.execute and not (args.all or args.action_key):
            raise ValueError("Use --all or --action-key when running with --execute")

        project_id = str(manifest.get("project_id") or "") or None
        exit_code = 0
        execution_records: list[dict[str, Any]] = []
        for action in selected:
            url = action_url(args.api_base, action.api_path, project_id)
            print(render_action_line(action, url))
            action_result = None
            wait_result = None
            if args.execute:
                action_result = execute_action(action, url=url, timeout=args.timeout)
                print(json.dumps(action_result, ensure_ascii=False, indent=2))
                if args.wait:
                    wait_result = wait_for_job_result(
                        action_result,
                        api_base=args.api_base,
                        project_id=project_id,
                        timeout=args.wait_timeout,
                        poll_interval=args.poll_interval,
                    )
                    if wait_result is not None:
                        print(json.dumps({"wait_result": wait_result}, ensure_ascii=False, indent=2))
                        body = wait_result.get("body")
                        if isinstance(body, dict) and body.get("status") == "error":
                            exit_code = 1
            execution_records.append(
                action_execution_record(
                    action,
                    url=url,
                    executed=args.execute,
                    action_result=action_result,
                    wait_result=wait_result,
                )
            )
        if not selected:
            print("No executable actions in manifest")
        if args.out_json:
            args.out_json.parent.mkdir(parents=True, exist_ok=True)
            args.out_json.write_text(
                render_execution_report_json(execution_records),
                encoding="utf-8",
            )
        if args.out_md:
            args.out_md.parent.mkdir(parents=True, exist_ok=True)
            args.out_md.write_text(
                render_execution_report_markdown(execution_records),
                encoding="utf-8",
            )
        return exit_code
    except (ValueError, OSError, urllib.error.URLError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
