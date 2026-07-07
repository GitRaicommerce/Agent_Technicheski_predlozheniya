from pathlib import Path
import asyncio
import importlib.util
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
render_manifest = calibration.render_manifest
run_calibration_bundle = calibration.run_calibration_bundle
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
            },
            snapshot_warnings=3,
            gap_focus_counts={
                "drafting depth": 5,
                "outline mapping": 2,
            },
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
        self.assertIn("resolve export blockers", manifest)
        self.assertIn("Universal Topic Coverage", manifest)
        self.assertIn("Gap calibration focus summary", manifest)
        self.assertIn("`drafting depth`: `5` sections", manifest)
        self.assertIn("`outline mapping`: `2` sections", manifest)

    def test_gap_calibration_focus_counts_reads_diagnostics_table_only(self):
        counts = gap_calibration_focus_counts(
            "\n".join(
                [
                    "# Gap report",
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
                    "",
                    "## Section Gap Diagnostics",
                    "",
                    "| Reference section | Best generated section | Coverage | Volume | Gap reasons | Calibration focus |",
                    "| --- | --- | ---: | ---: | --- | --- |",
                    "| A | A generated | 0.20 | 0.10 | too short | drafting depth |",
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
        finally:
            calibration.load_snapshot = original_load_snapshot
            calibration.export_readiness_report_markdown = original_export_readiness
            calibration.extract_text = original_extract_text
            calibration.render_report = original_render_report


if __name__ == "__main__":
    unittest.main()
