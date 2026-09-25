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


@pytest.mark.asyncio
async def test_schedule_agent_hides_conditional_dates_and_rejects_date_output():
    schedule = SimpleNamespace(
        schedule_json={
            "tasks": [{
                "uid": 1,
                "name": "Проектиране",
                "start": "06.10.2026",
                "finish": "25.10.2026",
                "duration_days": 20,
            }]
        },
        status_locked=True,
        version=1,
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = schedule
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)

    with patch(
        "app.agents.schedule.llm_gateway.call",
        new=AsyncMock(return_value={
            "analysis": {},
            "tp_section_text": "Проектирането започва на 06.10.2026 г.",
            "warnings": [],
        }),
    ) as call:
        response = await run_schedule("project-1", db)

    prompt = call.await_args.kwargs["user_message"]
    assert "06.10.2026" not in prompt
    assert "25.10.2026" not in prompt
    assert "duration_days': 20" in prompt
    assert response["status"] == "error_calendar_dates"
    assert response["tp_section_text"] == ""
