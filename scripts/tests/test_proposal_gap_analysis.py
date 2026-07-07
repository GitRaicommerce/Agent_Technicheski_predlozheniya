from pathlib import Path
import importlib.util
import sys
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "proposal_gap_analysis.py"
SPEC = importlib.util.spec_from_file_location("proposal_gap_analysis", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
proposal_gap_analysis = importlib.util.module_from_spec(SPEC)
sys.modules["proposal_gap_analysis"] = proposal_gap_analysis
SPEC.loader.exec_module(proposal_gap_analysis)


Section = proposal_gap_analysis.Section
analyze_topic_coverage = proposal_gap_analysis.analyze_topic_coverage
render_report = proposal_gap_analysis.render_report


class ProposalGapAnalysisTests(unittest.TestCase):
    def test_analyze_topic_coverage_flags_missing_operational_topics(self):
        rows = analyze_topic_coverage(
            (
                "The reference proposal develops risk mitigation and escalation. "
                "It also describes environmental protection with dust, waste and "
                "soil controls plus communication with the authority and supervision."
            ),
            "The generated proposal mentions risk mitigation only.",
        )

        by_key = {row["key"]: row for row in rows}

        self.assertEqual(by_key["risk"]["status"], "covered")
        self.assertEqual(by_key["environment"]["status"], "missing")
        self.assertEqual(by_key["communication"]["status"], "missing")
        self.assertIn("dust", by_key["environment"]["missing_hits"])

    def test_render_report_includes_universal_topic_coverage_section(self):
        test_dir = Path(__file__).resolve().parent
        report = render_report(
            tender_text="The tender requires environmental protection and reporting.",
            reference_sections=[
                Section(
                    "Work programme",
                    (
                        "Environmental protection covers dust control, waste "
                        "segregation, soil protection and reporting records."
                    ),
                )
            ],
            generated_sections=[
                Section("Work programme", "The generated text mentions reporting.")
            ],
            reference_path=test_dir / "reference.md",
            generated_path=test_dir / "generated.md",
            tender_paths=[test_dir / "tender.md"],
        )

        self.assertIn("## Universal Topic Coverage", report)
        self.assertIn("Environmental protection", report)
        self.assertIn("dust, waste, soil", report)
        self.assertTrue("missing" in report or "partial" in report)


if __name__ == "__main__":
    unittest.main()
