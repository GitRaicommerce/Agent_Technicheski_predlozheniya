from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.schedule import run_schedule


@pytest.mark.asyncio
async def test_schedule_agent_does_not_describe_unreliable_parser_output():
    schedule = SimpleNamespace(
        schedule_json={
            "tasks": [{
                "uid": 1,
                "name": "ID Вид дейност Срок Начало Край",
                "start": None,
                "finish": None,
                "duration_days": None,
                "note": "extracted_from_pdf_text",
            }]
        },
        status_locked=True,
        version=1,
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = schedule
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)

    with patch("app.agents.schedule.llm_gateway.call", new=AsyncMock()) as call:
        response = await run_schedule("project-1", db)

    assert response["status"] == "error_unreliable_schedule"
    assert response["tp_section_text"] == ""
    call.assert_not_awaited()
