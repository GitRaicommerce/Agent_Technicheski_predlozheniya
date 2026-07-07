from pathlib import Path
import asyncio
import importlib.util
import json
import sys
import tempfile
import unittest


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

MODULE_PATH = SCRIPTS_DIR / "run_proposal_calibration.py"
SPEC = importlib.util.spec_from_file_location("run_proposal_calibration", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
calibration = importlib.util.module_from_spec(SPEC)
sys.modules["run_proposal_calibration"] = calibration
SPEC.loader.exec_module(calibration)


calibration_output_paths = calibration.calibration_output_paths
gap_calibration_focus_counts = calibration.gap_calibration_focus_counts
gap_regeneration_priority_rows = calibration.gap_regeneration_priority_rows
gap_summary_metrics = calibration.gap_summary_metrics
readiness_priority_actions = calibration.readiness_priority_actions
render_manifest = calibration.render_manifest
render_manifest_json = calibration.render_manifest_json
run_calibration_bundle = calibration.run_calibration_bundle
structured_readiness_priority_actions = calibration.structured_readiness_priority_actions
snapshot_warning_count = calibration.snapshot_warning_count
GenerationSnapshot = calibration.GenerationSnapshot


class RunProposalCalibrationTests(unittest.TestCase):
    def test_calibration_output_paths_are_stable(self):
        paths = calibration_output_paths(Path("analysis/pernik"))

        self.assertEqual(
            paths["selected_snapshot"],
            Path("analysis/pernik/selected_proposal_snapshot.md"),
        )
        self.assertEqual(
            paths["gap_report"],
            Path("analysis/pernik/proposal_gap_report.md"),
        )
        self.assertEqual(
            paths["effective_snapshot"],
            Path("analysis/pernik/effective_proposal_snapshot.md"),
        )
        self.assertEqual(
            paths["readiness_report"],
            Path("analysis/pernik/docx_readiness_report.md"),
        )
        self.assertEqual(
            paths["manifest"],
            Path("analysis/pernik/calibration_manifest.md"),
        )
        self.assertEqual(
            paths["manifest_json"],
            Path("analysis/pernik/calibration_manifest.json"),
        )

    def test_render_manifest_lists_bundle_files_and_review_order(self):
        manifest = render_manifest(
            project_id="project-1",
            reference=Path("reference.docx"),
            selected_snapshot=Path("out/selected.md"),
            effective_snapshot=Path("out/effective.md"),
            readiness_report=Path("out/readiness.md"),
            gap_report=Path("out/gap.md"),
            tenders=[Path("tender.pdf")],
            readiness={
                "status": "blocked",
                "blockers": [
                    {"code": "duplicate_selected", "count": 2},
                    {"code": "stale_evidence", "count": 1},
                ],
                "duplicate_selected_sections": [
                    {"section_title": "Organization", "selected_count": 2}
                ],
                "stale_section_details": [{"section_title": "Schedule"}],
            },
            snapshot_warnings=3,
            gap_focus_counts={
                "drafting depth": 5,
                "outline mapping": 2,
            },
            gap_summary={
                "content_reference_sections": 12,
                "content_generated_sections": 10,
                "reference_word_tokens": 8000,
                "generated_word_tokens": 2400,
                "generated_reference_volume_ratio": 0.30,
            },
            gap_priority_rows=[
                {
                    "reference_section": "Organization",
                    "generated_section": "Work programme",
                    "coverage": 0.20,
                    "volume": 0.40,
                    "reasons": "structure mismatch, thin detail",
                    "focus": "outline mapping",
                }
            ],
        )

        self.assertIn("Mode: `non-mutating`", manifest)
        self.assertIn("Snapshot warnings: `3`", manifest)
        self.assertIn("DOCX readiness status: `blocked`", manifest)
        self.assertIn("`duplicate_selected`: `2`", manifest)
        self.assertIn("resolve readiness blockers", manifest)
        self.assertIn("reference.docx", manifest)
        self.assertIn("out/selected.md", manifest)
        self.assertIn("out/effective.md", manifest)
        self.assertIn("Gap input snapshot: `effective_proposal_snapshot.md`", manifest)
        self.assertIn("out/readiness.md", manifest)
        self.assertIn("out/gap.md", manifest)
        self.assertIn("tender.pdf", manifest)
        self.assertIn("Snapshot Warnings", manifest)
        self.assertIn("Gap quality scorecard", manifest)
        self.assertIn("`10` generated / `12` reference", manifest)
        self.assertIn("`2400` generated / `8000` reference", manifest)
        self.assertIn("Generated/reference volume ratio: `0.30`", manifest)
        self.assertIn("resolve export blockers", manifest)
        self.assertIn("Universal Topic Coverage", manifest)
        self.assertIn("Gap calibration focus summary", manifest)
        self.assertIn("`drafting depth`: `5` sections", manifest)
        self.assertIn("`outline mapping`: `2` sections", manifest)
        self.assertIn("Regeneration priority shortlist", manifest)
        self.assertIn("Readiness blockers come first", manifest)
        self.assertIn(
            "`duplicate_selected` action_key=`resolve_duplicate_selected`",
            manifest,
        )
        self.assertIn("`Остави най-новите`", manifest)
        self.assertIn("Gap `outline mapping`: regenerate/reference-align", manifest)
        self.assertIn("Organization", manifest)

    def test_gap_summary_metrics_reads_report_summary(self):
        metrics = gap_summary_metrics(
            "\n".join(
                [
                    "- Raw recognized sections in reference TP: `26`",
                    "- Raw recognized sections in generated TP: `24`",
                    "- Content sections compared in reference TP: `23`",
                    "- Content sections compared in generated TP: `22`",
                    "- Word-like tokens в референтното ТП: `62445`",
                    "- Word-like tokens в генерираното ТП: `9122`",
                ]
            )
        )

        self.assertEqual(metrics["raw_reference_sections"], 26)
        self.assertEqual(metrics["raw_generated_sections"], 24)
        self.assertEqual(metrics["content_reference_sections"], 23)
        self.assertEqual(metrics["content_generated_sections"], 22)
        self.assertEqual(metrics["reference_word_tokens"], 62445)
        self.assertEqual(metrics["generated_word_tokens"], 9122)
        self.assertAlmostEqual(
            metrics["generated_reference_volume_ratio"],
            9122 / 62445,
        )

    def test_gap_calibration_focus_counts_reads_diagnostics_table_only(self):
        counts = gap_calibration_focus_counts(
            "\n".join(
                [
                    "# Gap report",
                    "- Content sections compared in reference TP: `1`",
                    "- Content sections compared in generated TP: `1`",
                    "- Word-like tokens в референтното ТП: `1000`",
                    "- Word-like tokens в генерираното ТП: `250`",
                    "",
                    "## Section Gap Diagnostics",
                    "",
                    "| Reference section | Best generated section | Coverage | Volume | Gap reasons | Calibration focus |",
                    "| --- | --- | ---: | ---: | --- | --- |",
                    "| A | A generated | 0.20 | 0.10 | too short | drafting depth |",
                    "| B | C generated | 0.10 | 0.80 | structure mismatch | outline mapping |",
                    "| C | C generated | 0.40 | 0.90 | weak lexical coverage | grounding and checklist coverage |",
                    "| D | D generated | 0.30 | 0.20 | too short | drafting depth |",
                    "",
                    "## Other",
                    "| ignored | ignored | ignored | ignored | ignored | monitor |",
                ]
            )
        )

        self.assertEqual(
            counts,
            {
                "drafting depth": 2,
                "outline mapping": 1,
                "grounding and checklist coverage": 1,
            },
        )

    def test_gap_regeneration_priority_rows_rank_non_monitor_sections(self):
        rows = gap_regeneration_priority_rows(
            "\n".join(
                [
                    "# Gap report",
                    "- Content sections compared in reference TP: `1`",
                    "- Content sections compared in generated TP: `1`",
                    "- Word-like tokens в референтното ТП: `1000`",
                    "- Word-like tokens в генерираното ТП: `250`",
                    "",
                    "## Section Gap Diagnostics",
                    "",
                    "| Reference section | Best generated section | Coverage | Volume | Gap reasons | Calibration focus |",
                    "| --- | --- | ---: | ---: | --- | --- |",
                    "| Quality | Quality generated | 0.40 | 0.30 | thin detail | drafting depth |",
                    "| Organization | Generic generated | 0.60 | 0.90 | structure mismatch | outline mapping |",
                    "| Environment | Environment generated | 0.10 | 0.80 | missing key terms | grounding and checklist coverage |",
                    "| Acceptable | Acceptable generated | 0.90 | 1.10 | acceptable alignment | monitor |",
                    "",
                    "## Other",
                ]
            )
        )

        self.assertEqual(
            [row["reference_section"] for row in rows],
            ["Organization", "Quality", "Environment"],
        )
        self.assertEqual(rows[0]["focus"], "outline mapping")
        self.assertEqual(rows[1]["focus"], "drafting depth")
        self.assertEqual(rows[2]["focus"], "grounding and checklist coverage")

    def test_readiness_priority_actions_summarize_specific_sections(self):
        actions = readiness_priority_actions(
            {
                "duplicate_selected_sections": [
                    {"section_title": "Organization", "selected_count": 2}
                ],
                "stale_section_details": [{"section_title": "Schedule"}],
                "missing_requirement_sections": [
                    {"section_title": "Quality", "missing_count": 3},
                    {"section_title": "Safety", "missing_count": 1},
                ],
                "quality_sections": [
                    {
                        "section_title": "Environment",
                        "word_count": 120,
                        "min_words": 420,
                        "requirement_count": 5,
                        "blueprint_topic_count": 7,
                    }
                ],
            }
        )

        self.assertEqual(len(actions), 4)
        self.assertIn("action_key=`resolve_duplicate_selected`", actions[0])
        self.assertIn("`Остави най-новите`", actions[0])
        self.assertIn("Organization", actions[0])
        self.assertIn("action_key=`regenerate_stale`", actions[1])
        self.assertIn("bulk `Regenerate`", actions[1])
        self.assertIn("Schedule", actions[1])
        self.assertIn("action_key=`regenerate_missing_requirements`", actions[2])
        self.assertIn("bulk `Regenerate coverage`", actions[2])
        self.assertIn("Quality (3 missing)", actions[2])
        self.assertIn("action_key=`regenerate_quality_depth`", actions[3])
        self.assertIn("bulk `Regenerate detailed`", actions[3])
        self.assertIn("Environment (120/420 words)", actions[3])

    def test_render_manifest_json_exposes_structured_gates_and_actions(self):
        readiness = {
            "status": "blocked",
            "blockers": [
                {"code": "duplicate_selected", "count": 1},
                {"code": "stale_evidence", "count": 1},
                {"code": "missing_requirements", "count": 1},
                {"code": "shallow_sections", "count": 1},
            ],
            "duplicate_selected_sections": [
                {"section_title": "Organization", "selected_count": 2}
            ],
            "stale_section_details": [{"section_title": "Schedule"}],
            "missing_requirement_sections": [
                {"section_title": "Quality", "missing_count": 3}
            ],
            "quality_sections": [
                {
                    "section_title": "Environment",
                    "word_count": 120,
                    "min_words": 420,
                    "requirement_count": 5,
                    "blueprint_topic_count": 7,
                }
            ],
        }
        manifest = json.loads(
            render_manifest_json(
                project_id="project-1",
                reference=Path("reference.docx"),
                selected_snapshot=Path("out/selected.md"),
                effective_snapshot=Path("out/effective.md"),
                readiness_report=Path("out/readiness.md"),
                gap_report=Path("out/gap.md"),
                tenders=[Path("tender.pdf")],
                readiness=readiness,
                snapshot_warnings=2,
                gap_summary={
                    "generated_reference_volume_ratio": 0.25,
                    "content_generated_sections": 10,
                },
                gap_focus_counts={"drafting depth": 4},
                gap_priority_rows=[
                    {
                        "reference_section": "A",
                        "generated_section": "A generated",
                        "coverage": 0.2,
                        "volume": 0.1,
                        "reasons": "too short",
                        "focus": "drafting depth",
                    }
                ],
            )
        )

        self.assertEqual(manifest["schema_version"], "calibration_manifest.v1")
        self.assertEqual(manifest["project_id"], "project-1")
        self.assertEqual(manifest["mode"], "non-mutating")
        self.assertEqual(
            manifest["calibration_gates"]["docx_readiness_status"],
            "blocked",
        )
        self.assertEqual(manifest["calibration_gates"]["snapshot_warnings"], 2)
        self.assertEqual(
            manifest["gap_quality_scorecard"]["generated_reference_volume_ratio"],
            0.25,
        )
        self.assertEqual(
            [action["action_key"] for action in manifest["readiness_actions"]],
            [
                "resolve_duplicate_selected",
                "regenerate_stale",
                "regenerate_missing_requirements",
                "regenerate_quality_depth",
            ],
        )
        self.assertEqual(
            manifest["readiness_actions"][2]["ui_action"],
            "Regenerate coverage",
        )
        self.assertEqual(manifest["readiness_actions"][0]["api_method"], "POST")
        self.assertEqual(
            manifest["readiness_actions"][0]["api_path"],
            "/api/v1/agents/project-1/remediation-actions/resolve_duplicate_selected",
        )
        self.assertEqual(
            manifest["readiness_actions"][2]["api_path"],
            "/api/v1/agents/project-1/remediation-actions/regenerate_missing_requirements",
        )
        self.assertEqual(manifest["gap_priority_rows"][0]["focus"], "drafting depth")

    def test_snapshot_warning_count_reads_warning_section_only(self):
        count = snapshot_warning_count(
            "\n".join(
                [
                    "# Snapshot",
                    "- regular bullet",
                    "## Snapshot Warnings",
                    "- duplicate selected generations for section one",
                    "- missing selected generation for section two",
                    "",
                    "## Other Section",
                    "- not a warning",
                ]
            )
        )

        self.assertEqual(count, 2)

    def test_run_calibration_bundle_writes_snapshot_readiness_gap_and_manifest(self):
        original_load_snapshot = calibration.load_snapshot
        original_export_readiness = calibration.export_readiness_report_markdown
        original_extract_text = calibration.extract_text
        original_render_report = calibration.render_report

        async def fake_load_snapshot(project_id):
            self.assertEqual(project_id, "project-1")
            return (
                "Calibration Project",
                [{"uid": "sec-a", "title": "Section A"}],
                [
                    GenerationSnapshot(
                        id="gen-old",
                        section_uid="sec-a",
                        variant="1",
                        text="Old generated section",
                        evidence_status="stale",
                        selected=True,
                        created_at="2026-01-01T00:00:00",
                    ),
                    GenerationSnapshot(
                        id="gen-new",
                        section_uid="sec-a",
                        variant="2",
                        text="New generated section",
                        evidence_status="ok",
                        selected=True,
                        created_at="2026-01-02T00:00:00",
                    ),
                ],
            )

        async def fake_export_readiness(project_id, out_path):
            self.assertEqual(project_id, "project-1")
            out_path.write_text("# DOCX export readiness report", encoding="utf-8")
            return {
                "status": "blocked",
                "blockers": [{"code": "stale_evidence", "count": 1}],
            }

        def fake_extract_text(path):
            if path.name == "reference.md":
                return "# Reference\n\nReference section"
            if path.name == "tender.md":
                return "Tender source text"
            return path.read_text(encoding="utf-8")

        def fake_render_report(**kwargs):
            self.assertIn("Tender source text", kwargs["tender_text"])
            self.assertEqual(kwargs["reference_path"], Path("reference.md"))
            self.assertEqual(
                kwargs["generated_path"].name,
                "effective_proposal_snapshot.md",
            )
            return "\n".join(
                [
                    "# Gap report",
                    "- Content sections compared in reference TP: `1`",
                    "- Content sections compared in generated TP: `1`",
                    "- Word-like tokens в референтното ТП: `1000`",
                    "- Word-like tokens в генерираното ТП: `250`",
                    "",
                    "## Section Gap Diagnostics",
                    "",
                    "| Reference section | Best generated section | Coverage | Volume | Gap reasons | Calibration focus |",
                    "| --- | --- | ---: | ---: | --- | --- |",
                    "| A | A generated | 0.20 | 0.10 | too short | drafting depth |",
                    "| B | B generated | 0.10 | 0.20 | missing key terms | grounding and checklist coverage |",
                ]
            )

        calibration.load_snapshot = fake_load_snapshot
        calibration.export_readiness_report_markdown = fake_export_readiness
        calibration.extract_text = fake_extract_text
        calibration.render_report = fake_render_report
        try:
            with tempfile.TemporaryDirectory() as tmp:
                paths = asyncio.run(
                    run_calibration_bundle(
                        project_id="project-1",
                        reference=Path("reference.md"),
                        out_dir=Path(tmp),
                        tenders=[Path("tender.md")],
                    )
                )

                selected_snapshot = paths["selected_snapshot"].read_text(encoding="utf-8")
                effective_snapshot = paths["effective_snapshot"].read_text(encoding="utf-8")
                self.assertIn("Old generated section", selected_snapshot)
                self.assertIn("New generated section", selected_snapshot)
                self.assertIn("Selected variant 1", selected_snapshot)
                self.assertNotIn("Old generated section", effective_snapshot)
                self.assertIn("New generated section", effective_snapshot)
                self.assertIn(
                    "effective-newest-selected-per-section",
                    effective_snapshot,
                )
                self.assertEqual(
                    paths["readiness_report"].read_text(encoding="utf-8"),
                    "# DOCX export readiness report",
                )
                gap_report = paths["gap_report"].read_text(encoding="utf-8")
                self.assertIn("# Gap report", gap_report)
                self.assertIn("Section Gap Diagnostics", gap_report)
                self.assertIn(
                    "docx_readiness_report.md",
                    paths["manifest"].read_text(encoding="utf-8"),
                )
                manifest_json = json.loads(
                    paths["manifest_json"].read_text(encoding="utf-8")
                )
                self.assertEqual(
                    manifest_json["paths"]["readiness_report"],
                    str(paths["readiness_report"]).replace("\\", "/"),
                )
                self.assertEqual(
                    manifest_json["readiness_actions"][0]["action_key"],
                    "regenerate_stale",
                )
                self.assertEqual(
                    manifest_json["readiness_actions"][0]["api_path"],
                    "/api/v1/agents/project-1/remediation-actions/regenerate_stale",
                )
                self.assertIn(
                    "effective_proposal_snapshot.md",
                    paths["manifest"].read_text(encoding="utf-8"),
                )
                self.assertIn(
                    "`stale_evidence`: `1`",
                    paths["manifest"].read_text(encoding="utf-8"),
                )
                self.assertIn(
                    "`drafting depth`: `1` sections",
                    paths["manifest"].read_text(encoding="utf-8"),
                )
                self.assertIn(
                    "Generated/reference volume ratio: `0.25`",
                    paths["manifest"].read_text(encoding="utf-8"),
                )
                self.assertIn(
                    "Regeneration priority shortlist",
                    paths["manifest"].read_text(encoding="utf-8"),
                )
                self.assertIn(
                    "Gap `drafting depth`: regenerate/reference-align `A`",
                    paths["manifest"].read_text(encoding="utf-8"),
                )
        finally:
            calibration.load_snapshot = original_load_snapshot
            calibration.export_readiness_report_markdown = original_export_readiness
            calibration.extract_text = original_extract_text
            calibration.render_report = original_render_report


if __name__ == "__main__":
    unittest.main()
