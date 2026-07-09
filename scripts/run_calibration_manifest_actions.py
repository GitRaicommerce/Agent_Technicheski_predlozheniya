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


def load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Calibration manifest must be a JSON object")
    return payload


def manifest_actions(manifest: dict[str, Any]) -> list[ManifestAction]:
    raw_readiness_actions = manifest.get("readiness_actions") or []
    if not isinstance(raw_readiness_actions, list):
        raise ValueError("Manifest readiness_actions must be a list")
    raw_gap_rows = manifest.get("gap_priority_rows") or []
    if not isinstance(raw_gap_rows, list):
        raise ValueError("Manifest gap_priority_rows must be a list")

    actions: list[ManifestAction] = []
    seen: set[tuple[str, str]] = set()
    for index, item in enumerate(raw_readiness_actions, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Manifest readiness action #{index} must be an object")
        action_key = str(item.get("action_key") or "").strip()
        api_method = str(item.get("api_method") or "POST").strip().upper()
        api_path = str(item.get("api_path") or "").strip()
        if not action_key or not api_path:
            raise ValueError(
                "Manifest readiness action "
                f"#{index} must include action_key and api_path"
            )
        request_json = item.get("request_json")
        if request_json is not None and not isinstance(request_json, dict):
            raise ValueError(
                "Manifest readiness action "
                f"#{index} request_json must be an object"
            )
        seen.add((action_key, api_path))
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
            )
        )

    for index, item in enumerate(raw_gap_rows, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Manifest gap priority row #{index} must be an object")
        action_key = str(item.get("action_key") or "").strip()
        api_path = str(item.get("api_path") or "").strip()
        if not action_key or not api_path:
            continue
        dedupe_key = (action_key, api_path)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        api_method = str(item.get("api_method") or "POST").strip().upper()
        request_json = item.get("request_json")
        if request_json is not None and not isinstance(request_json, dict):
            raise ValueError(
                f"Manifest gap priority row #{index} request_json must be an object"
            )
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
        for action in selected:
            url = action_url(args.api_base, action.api_path, project_id)
            print(render_action_line(action, url))
            if args.execute:
                result = execute_action(action, url=url, timeout=args.timeout)
                print(json.dumps(result, ensure_ascii=False, indent=2))
                if args.wait:
                    wait_result = wait_for_job_result(
                        result,
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
        if not selected:
            print("No executable actions in manifest")
        return exit_code
    except (ValueError, OSError, urllib.error.URLError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
