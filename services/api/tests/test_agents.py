"""
Тестове за /api/v1/agents endpoints.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import _make_project


# ---------------------------------------------------------------------------
# POST /api/v1/agents/chat
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_project_not_found(client, mock_db):
    """404 ако проектът не съществува."""
    mock_db.get = AsyncMock(return_value=None)

    resp = await client.post(
        "/api/v1/agents/chat",
        json={
            "project_id": str(uuid.uuid4()),
            "message": "Здравей",
            "history": [],
        },
    )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_chat_returns_orchestrator_result(client, mock_db):
    """Успешен отговор от оркестратора."""
    project = _make_project()
    mock_db.get = AsyncMock(return_value=project)

    expected = {
        "message": "Отговор от агента",
        "agent_result": {},
        "status": "ok",
    }

    with patch(
        "app.agents.orchestrator.run_orchestrator",
        new=AsyncMock(return_value=expected),
    ):
        resp = await client.post(
            "/api/v1/agents/chat",
            json={
                "project_id": project.id,
                "message": "Какво е статусът на проекта?",
                "history": [{"role": "user", "content": "Здравей"}],
            },
        )

    assert resp.status_code == 200
    assert resp.json()["message"] == "Отговор от агента"


# ---------------------------------------------------------------------------
# GET /api/v1/agents/{project_id}/outline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_outline_not_found(client, mock_db):
    """404 ако няма outline за проекта."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none = MagicMock(return_value=None)
    mock_db.execute = AsyncMock(return_value=result_mock)

    resp = await client.get(f"/api/v1/agents/{uuid.uuid4()}/outline")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/v1/agents/{project_id}/generations/{id}/select
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_select_generation_not_found(client, mock_db):
    """404 ако генерацията не съществува."""
    mock_db.get = AsyncMock(return_value=None)

    resp = await client.post(
        f"/api/v1/agents/{uuid.uuid4()}/generations/{uuid.uuid4()}/select"
    )

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/v1/agents/{project_id}/schedule
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_schedule_not_found(client, mock_db):
    """404 ако няма schedule за проекта."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none = MagicMock(return_value=None)
    mock_db.execute = AsyncMock(return_value=result_mock)

    resp = await client.get(f"/api/v1/agents/{uuid.uuid4()}/schedule")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_schedule_found(client, mock_db):
    """Връща schedule JSON при намерен запис."""
    from app.core.models import ScheduleNormalized

    pid = str(uuid.uuid4())
    schedule = ScheduleNormalized(
        id=str(uuid.uuid4()),
        project_id=pid,
        schedule_snapshot_id=str(uuid.uuid4()),
        schedule_json={"tasks": [{"uid": 1, "name": "Проектиране", "duration_days": 10}]},
        status_locked=False,
        version=1,
    )

    result_mock = MagicMock()
    result_mock.scalar_one_or_none = MagicMock(return_value=schedule)
    mock_db.execute = AsyncMock(return_value=result_mock)

    resp = await client.get(f"/api/v1/agents/{pid}/schedule")

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == schedule.id
    assert data["status_locked"] is False
    assert "tasks" in data["schedule_json"]
