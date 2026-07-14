from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "compare_calibration_manifests.py"
spec = importlib.util.spec_from_file_location("compare_calibration_manifests", SCRIPT)
compare_module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = compare_module
spec.loader.exec_module(compare_module)

main = compare_module.main
render_comparison = compare_module.render_comparison
summarize_manifest = compare_module.summarize_manifest


def manifest(
    *,
    project_id: str = "project-1",
    blockers: int = 0,
    warnings: int = 0,
    volume_ratio: float = 0.30,
    focus_counts: dict[str, int] | None = None,
    readiness_actions: list[dict] | None = None,
    gap_rows: list[dict] | None = None,
    action_execution_summary: dict | None = None,
) -> dict:
    return {
        "schema_version": "calibration_manifest.v1",
        "project_id": project_id,
        "calibration_gates": {
            "snapshot_warnings": warnings,
            "docx_readiness_status": "blocked" if blockers else "ready",
            "docx_readiness_blockers": blockers,
        },
        "gap_quality_scorecard": {
            "generated_reference_volume_ratio": volume_ratio,
            "content_generated_sections": 10,
            "content_reference_sections": 12,
        },
        "gap_calibration_focus_counts": focus_counts or {},
        "action_execution_summary": action_execution_summary or {},
        "readiness_actions": readiness_actions or [],
        "gap_priority_rows": gap_rows or [],
    }


class CompareCalibrationManifestsTests(unittest.TestCase):
    def test_summarize_manifest_reads_gates_scorecard_focuses_and_actions(self):
        summary = summarize_manifest(
            manifest(
                blockers=2,
                warnings=1,
                volume_ratio=0.42,
                focus_counts={"drafting depth": 3},
                readiness_actions=[
                    {"action_key": "regenerate_stale"},
                    {"action_key": "regenerate_stale"},
                ],
                gap_rows=[
                    {"action_key": "regenerate_quality_depth"},
                    {"focus": "outline mapping"},
                ],
                action_execution_summary={
                    "report_count": 1,
                    "total_actions": 2,
                    "status_counts": {"done": 1, "error": 1},
                },
            )
        )

        self.assertEqual(summary["readiness_blockers"], 2)
        self.assertEqual(summary["snapshot_warnings"], 1)
        self.assertEqual(summary["volume_ratio"], 0.42)
        self.assertEqual(summary["gap_focus_counts"]["drafting depth"], 3)
        self.assertEqual(
            summary["readiness_action_counts"],
            {"regenerate_stale": 2},
        )
        self.assertEqual(
            summary["gap_action_counts"],
            {"regenerate_quality_depth": 1},
        )
        self.assertEqual(summary["execution_report_count"], 1)
        self.assertEqual(summary["executed_action_count"], 2)
        self.assertEqual(
            summary["execution_status_counts"],
            {"done": 1, "error": 1},
        )

    def test_render_comparison_shows_improvement_and_next_step(self):
        before = manifest(
            blockers=3,
            warnings=2,
            volume_ratio=0.20,
            focus_counts={"drafting depth": 5, "outline mapping": 1},
            readiness_actions=[{"action_key": "regenerate_stale"}],
            gap_rows=[{"action_key": "regenerate_quality_depth"}],
        )
        after = manifest(
            blockers=0,
            warnings=0,
            volume_ratio=0.45,
            focus_counts={"drafting depth": 1},
            gap_rows=[{"action_key": "regenerate_quality_depth"}],
            action_execution_summary={
                "report_count": 1,
                "total_actions": 2,
                "status_counts": {"done": 2},
            },
        )

        text = render_comparison(before, after)

        self.assertIn("| readiness blockers | 3 | 0 | -3 | improved |", text)
        self.assertIn(
            "| generated/reference volume ratio | 0.20 | 0.45 | +0.25 | improved |",
            text,
        )
        self.assertIn("| outline mapping | 1 | 0 | -1 |", text)
        self.assertIn(
            "| readiness_actions | `regenerate_stale` | 1 | 0 | -1 |",
            text,
        )
        self.assertIn("## Action execution evidence", text)
        self.assertIn("| executed actions | 0 | 2 | +2 |", text)
        self.assertIn("| `done` | 0 | 2 | +2 |", text)
        self.assertIn("Run detailed regeneration", text)

    def test_render_comparison_prioritizes_remaining_readiness_blockers(self):
        text = render_comparison(
            manifest(blockers=1, volume_ratio=0.20),
            manifest(
                blockers=2,
                volume_ratio=0.40,
                focus_counts={"drafting depth": 1},
            ),
        )

        self.assertIn("| readiness blockers | 1 | 2 | +1 | regressed |", text)
        self.assertIn("Resolve remaining DOCX readiness blockers first", text)

    def test_render_comparison_prioritizes_failed_action_execution(self):
        text = render_comparison(
            manifest(blockers=3, volume_ratio=0.20),
            manifest(
                blockers=0,
                volume_ratio=0.50,
                action_execution_summary={
                    "report_count": 1,
                    "total_actions": 2,
                    "status_counts": {"done": 1, "error": 1},
                },
            ),
        )

        self.assertIn("| `error` | 0 | 1 | +1 |", text)
        self.assertIn("Inspect failed remediation jobs", text)

    def test_render_comparison_prioritizes_outline_mapping_after_readiness(self):
        text = render_comparison(
            manifest(blockers=0, focus_counts={"outline mapping": 3}),
            manifest(blockers=0, focus_counts={"outline mapping": 2}),
        )

        self.assertIn("Review outline mapping next", text)

    def test_main_writes_markdown_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            before_path = Path(tmp) / "before.json"
            after_path = Path(tmp) / "after.json"
            out_path = Path(tmp) / "comparison.md"
            before_path.write_text(json.dumps(manifest(blockers=1)), encoding="utf-8")
            after_path.write_text(json.dumps(manifest(blockers=0)), encoding="utf-8")

            self.assertEqual(
                main(
                    [
                        "--before",
                        str(before_path),
                        "--after",
                        str(after_path),
                        "--out",
                        str(out_path),
                    ]
                ),
                0,
            )

            self.assertIn(
                "Calibration manifest comparison",
                out_path.read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
