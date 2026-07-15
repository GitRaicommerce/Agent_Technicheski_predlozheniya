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
analyze_operational_detail_coverage = (
    proposal_gap_analysis.analyze_operational_detail_coverage
)
content_sections = proposal_gap_analysis.content_sections
calibration_focus_for_reasons = proposal_gap_analysis.calibration_focus_for_reasons
is_content_section = proposal_gap_analysis.is_content_section
render_report = proposal_gap_analysis.render_report
render_calibration_recommendation_lines = (
    proposal_gap_analysis.render_calibration_recommendation_lines
)
render_section_gap_diagnostics_lines = (
    proposal_gap_analysis.render_section_gap_diagnostics_lines
)
section_gap_reasons = proposal_gap_analysis.section_gap_reasons
split_sections = proposal_gap_analysis.split_sections
score_overlap = proposal_gap_analysis.score_overlap
tokenize = proposal_gap_analysis.tokenize


class ProposalGapAnalysisTests(unittest.TestCase):
    def test_tokenize_uses_full_unicode_cyrillic_range(self):
        text = (
            "\u0418\u0437\u043f\u044a\u043b\u043d\u0438\u0442\u0435\u043b\u044f\u0442 "
            "\u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u0438\u0440\u0430 "
            "\u043e\u0442\u0433\u043e\u0432\u043e\u0440\u043d\u043e\u0441\u0442\u0442\u0430 "
            "\u045d \u0438 \u043f\u0430\u0437\u0438 "
            "\u043a\u043e\u043d\u0442\u0440\u043e\u043b\u043d\u0438 "
            "\u0437\u0430\u043f\u0438\u0441\u0438."
        )

        tokens = tokenize(text)

        self.assertIn(
            "\u043e\u0442\u0433\u043e\u0432\u043e\u0440\u043d\u043e\u0441\u0442\u0442\u0430",
            tokens,
        )
        self.assertIn("\u043a\u043e\u043d\u0442\u0440\u043e\u043b\u043d\u0438", tokens)
        self.assertIn("\u0437\u0430\u043f\u0438\u0441\u0438", tokens)
        self.assertEqual(score_overlap(tokens, tokenize(text)), 1.0)

    def test_content_section_filter_excludes_formal_front_matter(self):
        sections = [
            Section("Cover", "Submitted by Example Ltd. Address and contact."),
            Section("Declaration", "The bidder signs this declaration."),
            Section(
                "\u0423\u0412\u0410\u0416\u0410\u0415\u041c\u0418 \u0414\u0410\u041c\u0418 \u0438 \u0413\u041e\u0421\u041f\u041e\u0414\u0410,",
                "We submit our proposal and remain available for questions.",
            ),
            Section(
                "\u0423\u0427\u0410\u0421\u0422\u041d\u0418\u041a",
                (
                    "Example Ltd. registration, address, representative and contact. "
                    "The company has organization, team, resources, quality control, "
                    "risk management and documentation experience listed here."
                ),
            ),
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
        self.assertFalse(is_content_section(sections[2]))
        self.assertFalse(is_content_section(sections[3]))
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

    def test_analyze_operational_detail_coverage_flags_weak_generated_detail(self):
        row = analyze_operational_detail_coverage(
            (
                "The reference defines responsible roles, control records, "
                "monitoring evidence, acceptance criteria, reporting sequence, "
                "escalation path and corrective actions."
            ),
            (
                "The generated proposal mentions the general approach and "
                "expected positive effect."
            ),
        )

        self.assertEqual(row["status"], "weak")
        self.assertLess(row["ratio"], 0.4)
        self.assertIn("responsible", row["missing_hits"])
        self.assertIn("record", row["missing_hits"])
        self.assertIn("corrective", row["missing_hits"])

    def test_section_gap_reasons_map_metrics_to_calibration_focus(self):
        reasons = section_gap_reasons(
            title_score=0.8,
            coverage=0.7,
            length_ratio=0.2,
            missing_keywords=[],
        )
        self.assertIn("too short", reasons)
        self.assertEqual(calibration_focus_for_reasons(reasons), "drafting depth")

        reasons = section_gap_reasons(
            title_score=0.05,
            coverage=0.5,
            length_ratio=0.8,
            missing_keywords=["quality"],
        )
        self.assertIn("structure mismatch", reasons)
        self.assertEqual(calibration_focus_for_reasons(reasons), "outline mapping")

        reasons = section_gap_reasons(
            title_score=0.8,
            coverage=0.8,
            length_ratio=0.9,
            missing_keywords=[],
            operational_detail_ratio=0.25,
        )
        self.assertIn("weak operational detail", reasons)
        self.assertEqual(calibration_focus_for_reasons(reasons), "drafting depth")

    def test_section_gap_diagnostics_render_actionable_focus_rows(self):
        lines = render_section_gap_diagnostics_lines(
            [
                Section(
                    "Quality control",
                    (
                        "Quality control acceptance inspection protocol "
                        "documentation records and reporting are described "
                        "with detailed responsibilities."
                    ),
                )
            ],
            [Section("Quality control", "Quality control is mentioned.")],
        )
        text = "\n".join(lines)

        self.assertIn("## Section Gap Diagnostics", text)
        self.assertIn("too short", text)
        self.assertIn("drafting depth", text)

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
        self.assertIn("## Operational Detail Coverage", report)
        self.assertIn("Environmental protection", report)
        self.assertIn("dust, waste, soil", report)
        self.assertTrue("missing" in report or "partial" in report)
        self.assertIn("## Calibration Recommendations", report)
        self.assertIn("## Section Gap Diagnostics", report)
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
                        "soil controls. The plan defines responsible roles, "
                        "control records, monitoring evidence, acceptance "
                        "criteria, reporting sequence and corrective actions."
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
        self.assertIn("Strengthen operational drafting detail", text)
        self.assertIn("corrective", text)
        self.assertIn("rerun DOCX readiness", text)


if __name__ == "__main__":
    unittest.main()
