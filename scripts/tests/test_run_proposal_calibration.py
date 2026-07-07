from pathlib import Path
import importlib.util
import sys
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
            paths["manifest"],
            Path("analysis/pernik/calibration_manifest.md"),
        )

    def test_render_manifest_lists_bundle_files_and_review_order(self):
        manifest = render_manifest(
            project_id="project-1",
            reference=Path("reference.docx"),
            selected_snapshot=Path("out/selected.md"),
            gap_report=Path("out/gap.md"),
            tenders=[Path("tender.pdf")],
        )

        self.assertIn("Mode: `non-mutating`", manifest)
        self.assertIn("reference.docx", manifest)
        self.assertIn("out/selected.md", manifest)
        self.assertIn("out/gap.md", manifest)
        self.assertIn("tender.pdf", manifest)
        self.assertIn("Snapshot Warnings", manifest)
        self.assertIn("Universal Topic Coverage", manifest)


if __name__ == "__main__":
    unittest.main()
