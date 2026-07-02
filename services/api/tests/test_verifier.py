from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.verifier import run_verifier
from app.core.models import Generation, TpOutline


def _one_result(item):
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=item)
    return result


@pytest.mark.asyncio
async def test_verifier_marks_missing_requirement_coverage_as_needs_review(mock_db):
    project_id = str(uuid.uuid4())
    section_uid = str(uuid.uuid4())
    generation_id = str(uuid.uuid4())
    generation = Generation(
        id=generation_id,
        project_id=project_id,
        section_uid=section_uid,
        variant="1",
        text="Представя се обща организация на изпълнението.",
        evidence_map_json={},
        used_sources_json={
            "grounding_context": {"tender_chunks": [], "schedule": {"tasks": []}}
        },
        flags_json={},
        selected=True,
    )
    outline = TpOutline(
        id=str(uuid.uuid4()),
        project_id=project_id,
        outline_json={
            "sections": [
                {
                    "uid": section_uid,
                    "title": "Линеен график",
                    "requirements": [
                        "Следва да се представи подробен линеен график за изпълнение."
                    ],
                    "requirement_ids": ["req-schedule"],
                    "requirement_checklist_items": [
                        {
                            "id": "req-schedule",
                            "text": "Следва да се представи подробен линеен график за изпълнение.",
                            "importance": "mandatory",
                            "category_label": "График и срокове",
                        }
                    ],
                    "subsections": [],
                }
            ]
        },
        status_locked=True,
        version=1,
    )

    mock_db.get = AsyncMock(return_value=generation)
    mock_db.execute = AsyncMock(return_value=_one_result(outline))

    with patch(
        "app.agents.verifier.llm_gateway.call",
        new=AsyncMock(return_value={"verdict": "ok", "gaps": [], "summary": "ok"}),
    ):
        result = await run_verifier(
            project_id=project_id,
            generation_id=generation_id,
            db=mock_db,
            trace_id=str(uuid.uuid4()),
        )

    assert result["verdict"] == "needs_review"
    assert result["requirement_coverage"]["missing_ids"] == ["req-schedule"]
    assert generation.evidence_status == "stale"
    assert generation.flags_json["requirement_coverage"]["missing_ids"] == [
        "req-schedule"
    ]
    assert (
        "req-schedule"
        in generation.flags_json["verification"]["gaps"][0]["description"]
    )
