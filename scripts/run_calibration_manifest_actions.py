"""Run remediation actions declared in a calibration manifest JSON."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class ManifestAction:
    action_key: str
    api_method: str
    api_path: str
    blocker_code: str = ""
    section_count: int = 0
    summary: str = ""


def load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Calibration manifest must be a JSON object")
    return payload


def manifest_actions(manifest: dict[str, Any]) -> list[ManifestAction]:
    raw_actions = manifest.get("readiness_actions") or []
    if not isinstance(raw_actions, list):
        raise ValueError("Manifest readiness_actions must be a list")

    actions: list[ManifestAction] = []
    for index, item in enumerate(raw_actions, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Manifest action #{index} must be an object")
        action_key = str(item.get("action_key") or "").strip()
        api_method = str(item.get("api_method") or "POST").strip().upper()
        api_path = str(item.get("api_path") or "").strip()
        if not action_key or not api_path:
            raise ValueError(
                f"Manifest action #{index} must include action_key and api_path"
            )
        actions.append(
            ManifestAction(
                action_key=action_key,
                api_method=api_method,
                api_path=api_path,
                blocker_code=str(item.get("blocker_code") or ""),
                section_count=int(item.get("section_count") or 0),
                summary=str(item.get("summary") or ""),
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
    request = urllib.request.Request(
        url,
        data=b"{}",
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


def render_action_line(action: ManifestAction, url: str) -> str:
    bits = [
        action.action_key,
        action.api_method,
        url,
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
        for action in selected:
            url = action_url(args.api_base, action.api_path, project_id)
            print(render_action_line(action, url))
            if args.execute:
                result = execute_action(action, url=url, timeout=args.timeout)
                print(json.dumps(result, ensure_ascii=False, indent=2))
        if not selected:
            print("No readiness actions in manifest")
        return 0
    except (ValueError, OSError, urllib.error.URLError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
