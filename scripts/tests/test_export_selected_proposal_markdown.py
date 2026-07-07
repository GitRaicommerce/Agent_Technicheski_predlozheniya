from pathlib import Path
import importlib.util
import sys
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "export_selected_proposal_markdown.py"
SPEC = importlib.util.spec_from_file_location(
    "export_selected_proposal_markdown",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
export_selected = importlib.util.module_from_spec(SPEC)
sys.modules["export_selected_proposal_markdown"] = export_selected
SPEC.loader.exec_module(export_selected)


GenerationSnapshot = export_selected.GenerationSnapshot
newest_generation_per_section = export_selected.newest_generation_per_section
render_selected_proposal_markdown = export_selected.render_selected_proposal_markdown


class ExportSelectedProposalMarkdownTests(unittest.TestCase):
    def test_render_selected_proposal_markdown_keeps_outline_order(self):
        markdown = render_selected_proposal_markdown(
            project_name="Calibration Project",
            project_id="project-1",
            outline_sections=[
                {"uid": "sec-a", "title": "Organization"},
                {"uid": "sec-b", "title": "Quality"},
            ],
            selected_generations=[
                GenerationSnapshot(
                    id="gen-b",
                    section_uid="sec-b",
                    variant="1",
                    text="Quality text.",
                    evidence_status="ok",
                    selected=True,
                    created_at="2026-01-02T00:00:00",
                ),
                GenerationSnapshot(
                    id="gen-a",
                    section_uid="sec-a",
                    variant="1",
                    text="Organization text.",
                    evidence_status="ok",
                    selected=True,
                    created_at="2026-01-01T00:00:00",
                ),
            ],
        )

        self.assertLess(markdown.index("## Organization"), markdown.index("## Quality"))
        self.assertIn("Organization text.", markdown)
        self.assertIn("generation_id=gen-a", markdown)
        self.assertNotIn("Snapshot Warnings", markdown)

    def test_render_selected_proposal_markdown_marks_duplicate_and_missing_sections(self):
        markdown = render_selected_proposal_markdown(
            project_name="Calibration Project",
            project_id="project-1",
            outline_sections=[
                {"uid": "sec-duplicate", "title": "Risk"},
                {"uid": "sec-missing", "title": "Environment"},
            ],
            selected_generations=[
                GenerationSnapshot(
                    id="gen-1",
                    section_uid="sec-duplicate",
                    variant="1",
                    text="Risk text one.",
                    evidence_status="ok",
                    selected=True,
                    created_at="2026-01-01T00:00:00",
                ),
                GenerationSnapshot(
                    id="gen-2",
                    section_uid="sec-duplicate",
                    variant="2",
                    text="Risk text two.",
                    evidence_status="stale",
                    selected=True,
                    created_at="2026-01-02T00:00:00",
                ),
            ],
        )

        self.assertIn("Selected variant 1", markdown)
        self.assertIn("Selected variant 2", markdown)
        self.assertIn("duplicate selected generations for section sec-duplicate", markdown)
        self.assertIn("missing selected generation for section sec-missing", markdown)
        self.assertIn("evidence_status=stale", markdown)

    def test_render_selected_proposal_markdown_appends_selected_generations_outside_outline(self):
        markdown = render_selected_proposal_markdown(
            project_name="Calibration Project",
            project_id="project-1",
            outline_sections=[],
            selected_generations=[
                GenerationSnapshot(
                    id="gen-extra",
                    section_uid="sec-extra",
                    variant="1",
                    text="Extra selected text.",
                    evidence_status="ok",
                    selected=True,
                    created_at="2026-01-01T00:00:00",
                )
            ],
        )

        self.assertIn("Selected Generations Outside Current Outline", markdown)
        self.assertIn("Extra selected text.", markdown)
        self.assertIn("selected generation outside current outline: gen-extra", markdown)

    def test_newest_generation_per_section_keeps_latest_selected_variant(self):
        generations = [
            GenerationSnapshot(
                id="gen-old",
                section_uid="sec-a",
                variant="1",
                text="Old text.",
                evidence_status="stale",
                selected=True,
                created_at="2026-01-01T00:00:00",
            ),
            GenerationSnapshot(
                id="gen-new",
                section_uid="sec-a",
                variant="2",
                text="New text.",
                evidence_status="ok",
                selected=True,
                created_at="2026-01-02T00:00:00",
            ),
            GenerationSnapshot(
                id="gen-other",
                section_uid="sec-b",
                variant="1",
                text="Other text.",
                evidence_status="ok",
                selected=True,
                created_at="2026-01-01T00:00:00",
            ),
        ]

        effective = newest_generation_per_section(generations)

        self.assertEqual(
            {generation.section_uid: generation.id for generation in effective},
            {"sec-a": "gen-new", "sec-b": "gen-other"},
        )


if __name__ == "__main__":
    unittest.main()
