"""Run a repeatable remediation + calibration rerun cycle."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from run_calibration_manifest_actions import main as run_manifest_actions
from run_proposal_calibration import main as run_proposal_calibration


def action_report_paths(out_dir: Path) -> dict[str, Path]:
    return {
        "json": out_dir / "calibration_action_execution.json",
        "markdown": out_dir / "calibration_action_execution.md",
    }


def build_action_args(args: argparse.Namespace, reports: dict[str, Path]) -> list[str]:
    action_args = [
        "--manifest",
        str(args.manifest),
        "--api-base",
        args.api_base,
        "--timeout",
        str(args.timeout),
        "--poll-interval",
        str(args.poll_interval),
        "--wait-timeout",
        str(args.wait_timeout),
        "--out-json",
        str(reports["json"]),
        "--out-md",
        str(reports["markdown"]),
    ]
    if args.execute:
        action_args.append("--execute")
    if args.wait:
        action_args.append("--wait")
    if args.all:
        action_args.append("--all")
    for action_key in args.action_key:
        action_args.extend(["--action-key", action_key])
    return action_args


def build_calibration_args(
    args: argparse.Namespace,
    reports: dict[str, Path],
) -> list[str]:
    calibration_args = [
        "--project-id",
        args.project_id,
        "--reference",
        str(args.reference),
        "--out-dir",
        str(args.out_dir),
        "--previous-manifest",
        str(args.manifest),
        "--action-report",
        str(reports["json"]),
    ]
    for tender in args.tender:
        calibration_args.extend(["--tender", str(tender)])
    return calibration_args


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run calibration manifest actions, write execution reports, then "
            "build a new calibration bundle with the action report attached. "
            "Dry-run action execution is the default."
        )
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--tender", action="append", default=[], type=Path)
    parser.add_argument("--api-base", default="http://localhost:8000")
    parser.add_argument("--action-key", action="append", default=[])
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--wait-timeout", type=float, default=1800.0)
    return parser.parse_args(argv)


def validate_args(args: argparse.Namespace) -> None:
    if args.execute and not args.wait:
        raise ValueError(
            "Use --wait with --execute so the calibration bundle is built after "
            "generation remediation jobs finish."
        )
    manifest_project_id = calibration_manifest_project_id(args.manifest)
    if manifest_project_id and manifest_project_id != args.project_id:
        raise ValueError(
            "Manifest project_id does not match --project-id: "
            f"{manifest_project_id} != {args.project_id}"
        )


def calibration_manifest_project_id(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return str(payload.get("project_id") or "").strip()


def main(argv: list[str]) -> int:
    try:
        args = parse_args(argv)
        validate_args(args)
        reports = action_report_paths(args.out_dir)
        args.out_dir.mkdir(parents=True, exist_ok=True)

        action_status = run_manifest_actions(build_action_args(args, reports))
        if action_status != 0:
            return action_status

        return run_proposal_calibration(build_calibration_args(args, reports))
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
