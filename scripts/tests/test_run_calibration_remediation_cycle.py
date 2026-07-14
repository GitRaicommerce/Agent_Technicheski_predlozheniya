from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

SCRIPT = SCRIPTS_DIR / "run_calibration_remediation_cycle.py"
spec = importlib.util.spec_from_file_location(
    "run_calibration_remediation_cycle",
    SCRIPT,
)
cycle = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = cycle
spec.loader.exec_module(cycle)

action_report_paths = cycle.action_report_paths
build_action_args = cycle.build_action_args
build_calibration_args = cycle.build_calibration_args
calibration_manifest_project_id = cycle.calibration_manifest_project_id
main = cycle.main
parse_args = cycle.parse_args


def write_manifest(path: Path, project_id: str = "project-1") -> Path:
    path.write_text(json.dumps({"project_id": project_id}), encoding="utf-8")
    return path


class CalibrationRemediationCycleTests(unittest.TestCase):
    def test_action_report_paths_are_stable(self):
        paths = action_report_paths(Path("out/pernik-rerun"))

        self.assertEqual(
            paths["json"],
            Path("out/pernik-rerun/calibration_action_execution.json"),
        )
        self.assertEqual(
            paths["markdown"],
            Path("out/pernik-rerun/calibration_action_execution.md"),
        )

    def test_build_args_connect_actions_to_next_calibration_bundle(self):
        args = parse_args(
            [
                "--manifest",
                "before/calibration_manifest.json",
                "--project-id",
                "project-1",
                "--reference",
                "reference.docx",
                "--out-dir",
                "after",
                "--tender",
                "tender.pdf",
                "--action-key",
                "regenerate_stale",
                "--execute",
                "--wait",
            ]
        )
        reports = action_report_paths(args.out_dir)

        action_args = build_action_args(args, reports)
        calibration_args = build_calibration_args(args, reports)

        self.assertIn("--execute", action_args)
        self.assertIn("--wait", action_args)
        self.assertIn("regenerate_stale", action_args)
        self.assertIn(str(reports["json"]), action_args)
        self.assertEqual(
            calibration_args,
            [
                "--project-id",
                "project-1",
                "--reference",
                "reference.docx",
                "--out-dir",
                "after",
                "--previous-manifest",
                str(Path("before/calibration_manifest.json")),
                "--action-report",
                str(Path("after/calibration_action_execution.json")),
                "--tender",
                "tender.pdf",
            ],
        )

    def test_main_runs_actions_then_calibration_bundle(self):
        original_actions = cycle.run_manifest_actions
        original_calibration = cycle.run_proposal_calibration
        cycle.run_manifest_actions = Mock(return_value=0)
        cycle.run_proposal_calibration = Mock(return_value=0)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                out_dir = Path(tmp) / "after"
                manifest_path = write_manifest(Path(tmp) / "before.json")
                status = main(
                    [
                        "--manifest",
                        str(manifest_path),
                        "--project-id",
                        "project-1",
                        "--reference",
                        "reference.docx",
                        "--out-dir",
                        str(out_dir),
                        "--all",
                    ]
                )

                self.assertEqual(status, 0)
                self.assertTrue(out_dir.exists())
                self.assertEqual(cycle.run_manifest_actions.call_count, 1)
                self.assertEqual(cycle.run_proposal_calibration.call_count, 1)
                calibration_args = cycle.run_proposal_calibration.call_args.args[0]
                self.assertIn("--previous-manifest", calibration_args)
                self.assertIn("--action-report", calibration_args)
        finally:
            cycle.run_manifest_actions = original_actions
            cycle.run_proposal_calibration = original_calibration

    def test_main_stops_when_action_phase_fails(self):
        original_actions = cycle.run_manifest_actions
        original_calibration = cycle.run_proposal_calibration
        cycle.run_manifest_actions = Mock(return_value=1)
        cycle.run_proposal_calibration = Mock(return_value=0)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                manifest_path = write_manifest(Path(tmp) / "before.json")
                status = main(
                    [
                        "--manifest",
                        str(manifest_path),
                        "--project-id",
                        "project-1",
                        "--reference",
                        "reference.docx",
                        "--out-dir",
                        str(Path(tmp) / "after"),
                        "--action-key",
                        "regenerate_stale",
                        "--execute",
                        "--wait",
                    ]
                )

                self.assertEqual(status, 1)
                cycle.run_manifest_actions.assert_called_once()
                cycle.run_proposal_calibration.assert_not_called()
        finally:
            cycle.run_manifest_actions = original_actions
            cycle.run_proposal_calibration = original_calibration

    def test_main_rejects_execute_without_wait(self):
        original_actions = cycle.run_manifest_actions
        original_calibration = cycle.run_proposal_calibration
        cycle.run_manifest_actions = Mock(return_value=0)
        cycle.run_proposal_calibration = Mock(return_value=0)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                manifest_path = write_manifest(Path(tmp) / "before.json")
                status = main(
                    [
                        "--manifest",
                        str(manifest_path),
                        "--project-id",
                        "project-1",
                        "--reference",
                        "reference.docx",
                        "--out-dir",
                        str(Path(tmp) / "after"),
                        "--action-key",
                        "regenerate_stale",
                        "--execute",
                    ]
                )

                self.assertEqual(status, 1)
                cycle.run_manifest_actions.assert_not_called()
                cycle.run_proposal_calibration.assert_not_called()
        finally:
            cycle.run_manifest_actions = original_actions
            cycle.run_proposal_calibration = original_calibration

    def test_main_rejects_manifest_project_mismatch(self):
        original_actions = cycle.run_manifest_actions
        original_calibration = cycle.run_proposal_calibration
        cycle.run_manifest_actions = Mock(return_value=0)
        cycle.run_proposal_calibration = Mock(return_value=0)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                manifest_path = write_manifest(
                    Path(tmp) / "before.json",
                    project_id="project-a",
                )
                status = main(
                    [
                        "--manifest",
                        str(manifest_path),
                        "--project-id",
                        "project-b",
                        "--reference",
                        "reference.docx",
                        "--out-dir",
                        str(Path(tmp) / "after"),
                        "--all",
                    ]
                )

                self.assertEqual(status, 1)
                cycle.run_manifest_actions.assert_not_called()
                cycle.run_proposal_calibration.assert_not_called()
        finally:
            cycle.run_manifest_actions = original_actions
            cycle.run_proposal_calibration = original_calibration

    def test_calibration_manifest_project_id_rejects_non_object_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "before.json"
            manifest_path.write_text("[]", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "JSON object"):
                calibration_manifest_project_id(manifest_path)


if __name__ == "__main__":
    unittest.main()
