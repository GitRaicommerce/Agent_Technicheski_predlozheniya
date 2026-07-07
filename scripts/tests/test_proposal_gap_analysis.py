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
content_sections = proposal_gap_analysis.content_sections
is_content_section = proposal_gap_analysis.is_content_section
render_report = proposal_gap_analysis.render_report
render_calibration_recommendation_lines = (
    proposal_gap_analysis.render_calibration_recommendation_lines
)
split_sections = proposal_gap_analysis.split_sections


class ProposalGapAnalysisTests(unittest.TestCase):
    def test_content_section_filter_excludes_formal_front_matter(self):
        sections = [
            Section("Cover", "Submitted by Example Ltd. Address and contact."),
            Section("Declaration", "The bidder signs this declaration."),
            Section(
                "Work programme",
                (
                    "The approach explains organization, resources, schedule, "
                    "quality control, risk mitigation, communication and "
                    "documentation records for the works."
                ),
            ),
        ]

        filtered = content_sections(sections)

        self.assertFalse(is_content_section(sections[0]))
        self.assertFalse(is_content_section(sections[1]))
        self.assertEqual([section.title for section in filtered], ["Work programme"])

    def test_split_sections_keeps_nested_markdown_headings_in_parent_section(self):
        sections = split_sections(
            "# Proposal\n\n"
            "Intro text.\n\n"
            "## Work programme\n\n"
            "Main approach paragraph.\n\n"
            "### Quality control\n\n"
            "Quality control stays inside the work programme section.\n\n"
            "### Risk management\n\n"
            "Risk management also stays inside the same section.\n\n"
            "## Schedule\n\n"
            "Schedule details."
        )

        titles = [section.title for section in sections]

        self.assertEqual(titles, ["Proposal", "Work programme", "Schedule"])
        self.assertIn("Quality control", sections[1].text)
        self.assertIn("Risk management", sections[1].text)

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
        self.assertIn("## Calibration Recommendations", report)
        self.assertIn("Revisit outline extraction", report)

    def test_render_report_compares_content_sections_not_formal_sections(self):
        test_dir = Path(__file__).resolve().parent
        report = render_report(
            tender_text="The tender requires quality control and risk mitigation.",
            reference_sections=[
                Section("Cover", "Submitted by Example Ltd. Address."),
                Section("Declaration", "Signed declaration by the participant."),
                Section(
                    "Work programme",
                    (
                        "The methodology describes quality control, risk "
                        "mitigation, schedule and documentation records."
                    ),
                ),
            ],
            generated_sections=[
                Section("Cover", "Generated cover page."),
                Section("Work programme", "Quality control and risk mitigation."),
            ],
            reference_path=test_dir / "reference.md",
            generated_path=test_dir / "generated.md",
            tender_paths=[test_dir / "tender.md"],
        )

        self.assertIn("Raw recognized sections in reference TP: `3`", report)
        self.assertIn("Content sections compared in reference TP: `1`", report)
        self.assertIn("Raw recognized sections in generated TP: `2`", report)
        self.assertIn("Content sections compared in generated TP: `1`", report)

    def test_calibration_recommendations_explain_missing_and_partial_topics(self):
        lines = render_calibration_recommendation_lines(
            [
                Section(
                    "Reference",
                    (
                        "Risk mitigation and escalation are described. "
                        "Environmental protection includes dust, waste and "
                        "soil controls."
                    ),
                )
            ],
            [
                Section(
                    "Generated",
                    "The generated text mentions risk only.",
                )
            ],
        )
        text = "\n".join(lines)

        self.assertIn("Environmental protection", text)
        self.assertIn("partially covered topics", text)
        self.assertIn("rerun DOCX readiness", text)


if __name__ == "__main__":
    unittest.main()
