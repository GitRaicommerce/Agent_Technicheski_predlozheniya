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
render_manifest = calibration.render_manifest
run_calibration_bundle = calibration.run_calibration_bundle


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
            readiness_report=Path("out/readiness.md"),
            gap_report=Path("out/gap.md"),
            tenders=[Path("tender.pdf")],
        )

        self.assertIn("Mode: `non-mutating`", manifest)
        self.assertIn("reference.docx", manifest)
        self.assertIn("out/selected.md", manifest)
        self.assertIn("out/readiness.md", manifest)
        self.assertIn("out/gap.md", manifest)
        self.assertIn("tender.pdf", manifest)
        self.assertIn("Snapshot Warnings", manifest)
        self.assertIn("resolve export blockers", manifest)
        self.assertIn("Universal Topic Coverage", manifest)

    def test_run_calibration_bundle_writes_snapshot_readiness_gap_and_manifest(self):
        original_export_markdown = calibration.export_markdown
        original_export_readiness = calibration.export_readiness_report_markdown
        original_extract_text = calibration.extract_text
        original_render_report = calibration.render_report

        async def fake_export_markdown(project_id, out_path):
            self.assertEqual(project_id, "project-1")
            out_path.write_text("# Generated\n\nGenerated section", encoding="utf-8")

        async def fake_export_readiness(project_id, out_path):
            self.assertEqual(project_id, "project-1")
            out_path.write_text("# DOCX export readiness report", encoding="utf-8")

        def fake_extract_text(path):
            if path.name == "reference.md":
                return "# Reference\n\nReference section"
            if path.name == "tender.md":
                return "Tender source text"
            return path.read_text(encoding="utf-8")

        def fake_render_report(**kwargs):
            self.assertIn("Tender source text", kwargs["tender_text"])
            self.assertEqual(kwargs["reference_path"], Path("reference.md"))
            return "# Gap report"

        calibration.export_markdown = fake_export_markdown
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

                self.assertEqual(
                    paths["selected_snapshot"].read_text(encoding="utf-8"),
                    "# Generated\n\nGenerated section",
                )
                self.assertEqual(
                    paths["readiness_report"].read_text(encoding="utf-8"),
                    "# DOCX export readiness report",
                )
                self.assertEqual(
                    paths["gap_report"].read_text(encoding="utf-8"),
                    "# Gap report",
                )
                self.assertIn(
                    "docx_readiness_report.md",
                    paths["manifest"].read_text(encoding="utf-8"),
                )
        finally:
            calibration.export_markdown = original_export_markdown
            calibration.export_readiness_report_markdown = original_export_readiness
            calibration.extract_text = original_extract_text
            calibration.render_report = original_render_report


if __name__ == "__main__":
    unittest.main()
