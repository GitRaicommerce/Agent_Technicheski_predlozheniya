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
    operational_detail_ratio: float | None = None,
    operational_detail_status: str | None = None,
    operational_detail_missing_signals: list[str] | None = None,
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
            **(
                {"operational_detail_ratio": operational_detail_ratio}
                if operational_detail_ratio is not None
                else {}
            ),
            **(
                {"operational_detail_status": operational_detail_status}
                if operational_detail_status is not None
                else {}
            ),
            **(
                {
                    "operational_detail_missing_signals": (
                        operational_detail_missing_signals
                    ),
                    "operational_detail_missing_signal_count": len(
                        operational_detail_missing_signals
                    ),
                }
                if operational_detail_missing_signals is not None
                else {}
            ),
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
                operational_detail_ratio=0.35,
                operational_detail_status="weak",
                operational_detail_missing_signals=["responsible", "corrective"],
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
                    "executed_actions": 2,
                    "status_counts": {"done": 1, "error": 1},
                    "ready_for_bundle": False,
                    "evidence_level": "failed",
                    "failure_report_count": 1,
                },
            )
        )

        self.assertEqual(summary["readiness_blockers"], 2)
        self.assertEqual(summary["snapshot_warnings"], 1)
        self.assertEqual(summary["volume_ratio"], 0.42)
        self.assertEqual(summary["operational_detail_ratio"], 0.35)
        self.assertEqual(summary["operational_detail_status"], "weak")
        self.assertEqual(
            summary["operational_detail_missing_signals"],
            ["responsible", "corrective"],
        )
        self.assertEqual(summary["operational_detail_missing_signal_count"], 2)
        self.assertEqual(summary["gap_focus_counts"]["drafting depth"], 3)
        self.assertEqual(
            summary["readiness_action_counts"],
            {"regenerate_stale": 2},
        )
        self.assertEqual(
            summary["gap_action_counts"],
            {"regenerate_quality_depth": 1},
        )
        self.assertEqual(summary["readiness_action_target_counts"], {})
        self.assertEqual(summary["gap_action_target_counts"], {})
        self.assertEqual(summary["execution_report_count"], 1)
        self.assertEqual(summary["executed_action_count"], 2)
        self.assertFalse(summary["action_evidence_ready"])
        self.assertEqual(summary["action_evidence_level"], "failed")
        self.assertEqual(summary["action_evidence_failures"], 1)
        self.assertEqual(
            summary["execution_status_counts"],
            {"done": 1, "error": 1},
        )

    def test_render_comparison_shows_improvement_and_next_step(self):
        before = manifest(
            blockers=3,
            warnings=2,
            volume_ratio=0.20,
            operational_detail_ratio=0.30,
            operational_detail_missing_signals=["responsible", "record"],
            focus_counts={"drafting depth": 5, "outline mapping": 1},
            readiness_actions=[{"action_key": "regenerate_stale"}],
            gap_rows=[{"action_key": "regenerate_quality_depth"}],
        )
        after = manifest(
            blockers=0,
            warnings=0,
            volume_ratio=0.45,
            operational_detail_ratio=0.75,
            operational_detail_missing_signals=[],
            focus_counts={"drafting depth": 1},
            gap_rows=[{"action_key": "regenerate_quality_depth"}],
            action_execution_summary={
                "report_count": 1,
                "total_actions": 2,
                "executed_actions": 2,
                "status_counts": {"done": 2},
                "ready_for_bundle": True,
            },
        )

        text = render_comparison(before, after)

        self.assertIn("| readiness blockers | 3 | 0 | -3 | improved |", text)
        self.assertIn(
            "| generated/reference volume ratio | 0.20 | 0.45 | +0.25 | improved |",
            text,
        )
        self.assertIn(
            "| operational detail ratio | 0.30 | 0.75 | +0.45 | improved |",
            text,
        )
        self.assertIn("## Operational detail missing signal deltas", text)
        self.assertIn("| record | 1 | 0 | -1 |", text)
        self.assertIn("| responsible | 1 | 0 | -1 |", text)
        self.assertIn("| outline mapping | 1 | 0 | -1 |", text)
        self.assertIn(
            "| readiness_actions | `regenerate_stale` | 1 | 0 | -1 |",
            text,
        )
        self.assertIn("## Action execution evidence", text)
        self.assertIn("| action evidence ready | 0 | 1 | +1 |", text)
        self.assertIn("| action evidence level | `none` | `proof` | n/a |", text)
        self.assertIn("| executed actions | 0 | 2 | +2 |", text)
        self.assertIn("| `done` | 0 | 2 | +2 |", text)
        self.assertIn("Run detailed regeneration", text)

    def test_summarize_manifest_reads_action_targets(self):
        summary = summarize_manifest(
            manifest(
                readiness_actions=[
                    {
                        "action_key": "regenerate_missing_requirements",
                        "missing_reason_counts": {
                            "missing distinctive requirement detail": 2,
                            "needs execution action": 1,
                            "needs operational evidence": 1,
                        },
                        "request_json": {
                            "section_uids": ["sec-quality"],
                            "section_title_hints": ["Quality controls"],
                        },
                        "section_labels": [
                            "Quality controls (120/420 words, 3 groups)",
                        ],
                    }
                ],
                gap_rows=[
                    {
                        "action_key": "regenerate_quality_depth",
                        "request_json": {
                            "section_title_hints": ["Environmental measures"]
                        },
                    }
                ],
            )
        )

        self.assertEqual(
            summary["readiness_action_target_counts"],
            {
                (
                    "regenerate_missing_requirements",
                    (
                        "uids=sec-quality; titles=Quality controls; "
                        "labels=Quality controls (120/420 words, 3 groups)"
                    ),
                ): 1,
            },
        )
        self.assertEqual(
            summary["missing_requirement_reason_counts"],
            {
                "missing distinctive requirement detail": 2,
                "needs execution action": 1,
                "needs operational evidence": 1,
            },
        )
        self.assertEqual(
            summary["gap_action_target_counts"],
            {
                (
                    "regenerate_quality_depth",
                    "titles=Environmental measures",
                ): 1,
            },
        )

    def test_render_comparison_shows_section_label_target_context(self):
        before = manifest(
            readiness_actions=[
                {
                    "action_key": "regenerate_quality_depth",
                    "request_json": {
                        "section_uids": ["sec-quality"],
                        "section_title_hints": ["Quality"],
                    },
                    "section_labels": [
                        "Quality (120/420 words, 3 groups, 7 topics)",
                    ],
                }
            ],
        )
        after = manifest(
            readiness_actions=[
                {
                    "action_key": "regenerate_quality_depth",
                    "request_json": {
                        "section_uids": ["sec-quality"],
                        "section_title_hints": ["Quality"],
                    },
                    "section_labels": [
                        "Quality (390/420 words, 3 groups, 7 topics)",
                    ],
                }
            ],
        )

        text = render_comparison(before, after)

        self.assertIn(
            "uids=sec-quality; titles=Quality; "
            "labels=Quality (120/420 words, 3 groups, 7 topics)",
            text,
        )
        self.assertIn(
            "uids=sec-quality; titles=Quality; "
            "labels=Quality (390/420 words, 3 groups, 7 topics)",
            text,
        )

    def test_render_comparison_shows_action_execution_section_label_deltas(self):
        before = manifest(
            action_execution_summary={
                "section_label_counts": {
                    "Quality (120/420 words, 3 groups)": 1,
                },
            },
        )
        after = manifest(
            action_execution_summary={
                "section_label_counts": {
                    "Quality (420/420 words, 3 groups)": 1,
                    "Environment (360/360 words, 2 groups)": 1,
                },
            },
        )

        text = render_comparison(before, after)

        self.assertIn("## Action execution section label deltas", text)
        self.assertIn(
            "| Quality (120/420 words, 3 groups) | 1 | 0 | -1 |",
            text,
        )
        self.assertIn(
            "| Quality (420/420 words, 3 groups) | 0 | 1 | +1 |",
            text,
        )
        self.assertIn(
            "| Environment (360/360 words, 2 groups) | 0 | 1 | +1 |",
            text,
        )

    def test_render_comparison_shows_action_execution_operational_signal_deltas(self):
        before = manifest(
            action_execution_summary={
                "operational_detail_missing_signal_counts": {
                    "record": 2,
                    "monitoring": 1,
                },
            },
        )
        after = manifest(
            action_execution_summary={
                "operational_detail_missing_signal_counts": {
                    "record": 1,
                    "corrective": 1,
                },
            },
        )

        summary = summarize_manifest(before)
        text = render_comparison(before, after)

        self.assertEqual(
            summary["action_execution_operational_signal_counts"],
            {"record": 2, "monitoring": 1},
        )
        self.assertIn("## Action execution operational signal deltas", text)
        self.assertIn("| corrective | 0 | 1 | +1 |", text)
        self.assertIn("| monitoring | 1 | 0 | -1 |", text)
        self.assertIn("| record | 2 | 1 | -1 |", text)

    def test_render_comparison_shows_action_target_deltas(self):
        before = manifest(
            readiness_actions=[
                {
                    "action_key": "regenerate_missing_requirements",
                    "missing_reason_counts": {
                        "missing distinctive requirement detail": 2,
                        "needs execution action": 1,
                        "needs operational evidence": 1,
                    },
                    "request_json": {
                        "section_uids": ["sec-quality"],
                        "section_title_hints": ["Quality"],
                    },
                }
            ],
            gap_rows=[
                {
                    "action_key": "regenerate_quality_depth",
                    "request_json": {"section_title_hints": ["Old section"]},
                }
            ],
        )
        after = manifest(
            readiness_actions=[
                {
                    "action_key": "regenerate_missing_requirements",
                    "missing_reason_counts": {
                        "missing distinctive requirement detail": 1,
                        "needs coherent passage": 1,
                        "needs execution action": 0,
                    },
                    "request_json": {
                        "section_uids": ["sec-environment"],
                        "section_title_hints": ["Environment"],
                    },
                }
            ],
            gap_rows=[
                {
                    "action_key": "regenerate_quality_depth",
                    "request_json": {
                        "section_uids": ["sec-a"],
                        "section_title_hints": ["New section"],
                    },
                }
            ],
        )

        text = render_comparison(before, after)

        self.assertIn("## Executable action target deltas", text)
        self.assertIn(
            "| readiness_actions | `regenerate_missing_requirements` | "
            "uids=sec-quality; titles=Quality | 1 | 0 | -1 |",
            text,
        )
        self.assertIn(
            "| readiness_actions | `regenerate_missing_requirements` | "
            "uids=sec-environment; titles=Environment | 0 | 1 | +1 |",
            text,
        )
        self.assertIn(
            "| gap_priority_rows | `regenerate_quality_depth` | "
            "titles=Old section | 1 | 0 | -1 |",
            text,
        )
        self.assertIn(
            "| gap_priority_rows | `regenerate_quality_depth` | "
            "uids=sec-a; titles=New section | 0 | 1 | +1 |",
            text,
        )
        self.assertIn("## Missing requirement reason deltas", text)
        self.assertIn(
            "| missing distinctive requirement detail | 2 | 1 | -1 |",
            text,
        )
        self.assertIn("| needs coherent passage | 0 | 1 | +1 |", text)
        self.assertIn("| needs execution action | 1 | 0 | -1 |", text)
        self.assertIn("| needs operational evidence | 1 | 0 | -1 |", text)

    def test_render_comparison_shows_legacy_summary_action_targets(self):
        before = manifest(
            readiness_actions=[
                {
                    "action_key": "regenerate_stale",
                    "section_count": 14,
                    "summary": "Schedule; Quality (+12 more)",
                }
            ]
        )
        after = manifest(readiness_actions=[])

        summary = summarize_manifest(before)
        text = render_comparison(before, after)

        self.assertEqual(
            summary["readiness_action_target_counts"],
            {
                (
                    "regenerate_stale",
                    "sections=Schedule; Quality (+12 more)",
                ): 1,
            },
        )
        self.assertIn(
            "| readiness_actions | `regenerate_stale` | "
            "sections=Schedule; Quality (+12 more) | 1 | 0 | -1 |",
            text,
        )

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
                    "executed_actions": 2,
                    "status_counts": {"done": 1, "error": 1},
                    "ready_for_bundle": False,
                    "failure_report_count": 1,
                },
            ),
        )

        self.assertIn("| reports with failures | 0 | 1 | +1 |", text)
        self.assertIn("| `error` | 0 | 1 | +1 |", text)
        self.assertIn("Inspect failed remediation jobs", text)

    def test_render_comparison_prioritizes_unexecuted_action_evidence(self):
        text = render_comparison(
            manifest(blockers=2, volume_ratio=0.20),
            manifest(
                blockers=0,
                volume_ratio=0.50,
                action_execution_summary={
                    "report_count": 1,
                    "total_actions": 2,
                    "executed_actions": 0,
                    "status_counts": {"planned": 2},
                    "ready_for_bundle": False,
                    "unexecuted_report_count": 1,
                },
            ),
        )

        self.assertIn("| reports with unexecuted actions | 0 | 1 | +1 |", text)
        self.assertIn("run remediation with --execute --wait", text)

    def test_render_comparison_prioritizes_outline_mapping_after_readiness(self):
        text = render_comparison(
            manifest(blockers=0, focus_counts={"outline mapping": 3}),
            manifest(blockers=0, focus_counts={"outline mapping": 2}),
        )

        self.assertIn("Review outline mapping next", text)

    def test_render_comparison_prioritizes_weak_operational_detail_after_readiness(self):
        text = render_comparison(
            manifest(
                blockers=0,
                volume_ratio=0.30,
                operational_detail_ratio=0.45,
                operational_detail_status="partial",
            ),
            manifest(
                blockers=0,
                volume_ratio=0.65,
                operational_detail_ratio=0.55,
                operational_detail_status="partial",
                operational_detail_missing_signals=["record", "monitoring"],
            ),
        )

        self.assertIn(
            "| operational detail ratio | 0.45 | 0.55 | +0.10 | improved |",
            text,
        )
        self.assertIn(
            "Operational detail coverage improved but remains weak/partial",
            text,
        )
        self.assertIn("Missing signals: record, monitoring.", text)

    def test_render_comparison_flags_operational_detail_that_did_not_improve(self):
        text = render_comparison(
            manifest(
                blockers=0,
                volume_ratio=0.30,
                operational_detail_ratio=0.45,
                operational_detail_status="partial",
            ),
            manifest(
                blockers=0,
                volume_ratio=0.70,
                operational_detail_ratio=0.45,
                operational_detail_status="partial",
                operational_detail_missing_signals=["record", "monitoring"],
            ),
        )

        self.assertIn(
            "Operational detail coverage is still weak and did not improve",
            text,
        )
        self.assertIn("Missing signals: record, monitoring.", text)

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
