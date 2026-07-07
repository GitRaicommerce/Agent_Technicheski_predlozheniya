from app.export.readiness_report import render_export_readiness_report


def test_render_export_readiness_report_includes_blockers_and_actions():
    report = render_export_readiness_report(
        {
            "project_id": "project-1",
            "ready": False,
            "status": "blocked",
            "selected_generation_count": 4,
            "selected_section_count": 3,
            "blocker_count": 4,
            "message": "Pre-export check failed.",
            "blockers": [
                {"code": "duplicate_selected", "count": 1, "message": "Duplicates"},
                {"code": "stale_evidence", "count": 1, "message": "Stale"},
                {"code": "missing_requirements", "count": 2, "message": "Missing"},
                {"code": "shallow_sections", "count": 1, "message": "Shallow"},
            ],
            "duplicate_selected_sections": [
                {
                    "section_uid": "sec-duplicate",
                    "section_title": "Duplicate section title",
                    "selected_count": 2,
                    "generation_ids": ["gen-1", "gen-2"],
                }
            ],
            "stale_sections": ["sec-stale"],
            "stale_section_details": [
                {"section_uid": "sec-stale", "section_title": "Stale section title"}
            ],
            "missing_requirement_sections": [
                {
                    "section_uid": "sec-missing",
                    "section_title": "Missing section title",
                    "missing_count": 2,
                    "missing_requirement_ids": ["req-1", "req-2"],
                    "missing_items": [
                        {"id": "req-1", "text": "Describe the detailed schedule."}
                    ],
                }
            ],
            "quality_sections": [
                {
                    "section_uid": "sec-shallow",
                    "section_title": "Shallow section title",
                    "word_count": 180,
                    "min_words": 1200,
                    "sentence_count": 3,
                    "min_sentences": 10,
                    "requirement_count": 2,
                    "blueprint_group_count": 6,
                    "issues": [{"code": "too_short_for_requirements"}],
                }
            ],
        }
    )

    assert "# DOCX export readiness report" in report
    assert "| duplicate_selected | 1 | Duplicates |" in report
    assert "Duplicate section title (`sec-duplicate`): 2 selected variants (gen-1, gen-2)" in report
    assert "Stale section title (`sec-stale`)" in report
    assert "Missing section title (`sec-missing`): 2 missing (req-1, req-2)" in report
    assert "`req-1`: Describe the detailed schedule." in report
    assert "| Shallow section title (`sec-shallow`) | 180 | 1200 | 3 | 10 | 2 | 6 | too_short_for_requirements |" in report
    assert "Остави най-новите" in report
    assert "Регенерирайте избраните stale секции" in report


def test_render_export_readiness_report_handles_ready_state():
    report = render_export_readiness_report(
        {
            "project_id": "project-ready",
            "ready": True,
            "status": "ready",
            "selected_generation_count": 2,
            "selected_section_count": 2,
            "blocker_count": 0,
            "blockers": [],
            "message": "Proposal is ready for DOCX export.",
        }
    )

    assert "Няма readiness блокери." in report
    assert "Proposal is ready for DOCX export." in report
