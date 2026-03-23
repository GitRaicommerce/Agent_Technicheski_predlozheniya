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


# ---------------------------------------------------------------------------
# GET /api/v1/agents/{project_id}/generations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_generations_empty(client, mock_db):
    """Връща [] когато няма генерации за проекта."""
    # outline lookup returns nothing
    outline_result = MagicMock()
    outline_result.scalar_one_or_none = MagicMock(return_value=None)
    # generations scalars returns empty list
    gen_result = MagicMock()
    gen_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    mock_db.execute = AsyncMock(side_effect=[outline_result, gen_result])

    resp = await client.get(f"/api/v1/agents/{uuid.uuid4()}/generations")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_get_generations_grouped(client, mock_db):
    """Групира генерациите по section_uid и ги връща."""
    from datetime import datetime, timezone
    from app.core.models import Generation

    pid = str(uuid.uuid4())
    sec_uid = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    g1 = Generation(
        id=str(uuid.uuid4()),
        project_id=pid,
        section_uid=sec_uid,
        variant=1,
        text="Текст вариант 1",
        evidence_status="ok",
        selected=True,
        created_at=now,
    )
    g2 = Generation(
        id=str(uuid.uuid4()),
        project_id=pid,
        section_uid=sec_uid,
        variant=2,
        text="Текст вариант 2",
        evidence_status="ok",
        selected=False,
        created_at=now,
    )

    outline_result = MagicMock()
    outline_result.scalar_one_or_none = MagicMock(return_value=None)
    gen_result = MagicMock()
    gen_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[g1, g2])))
    mock_db.execute = AsyncMock(side_effect=[outline_result, gen_result])

    resp = await client.get(f"/api/v1/agents/{pid}/generations")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    section = data[0]
    assert section["section_uid"] == sec_uid
    assert len(section["variants"]) == 2
    # selected comes first
    assert section["variants"][0]["selected"] is True


# ---------------------------------------------------------------------------
# POST /api/v1/agents/{project_id}/sections/{section_uid}/regenerate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_regenerate_section_not_found(client, mock_db):
    """404 когато проектът не съществува."""
    mock_db.get = AsyncMock(return_value=None)

    resp = await client.post(
        f"/api/v1/agents/{uuid.uuid4()}/sections/{uuid.uuid4()}/regenerate"
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_regenerate_section_ok(client, mock_db):
    """200 с generation_ids когато pipeline успее."""
    pid = str(uuid.uuid4())
    sec_uid = str(uuid.uuid4())
    project = _make_project()
    project.id = pid

    # db.get returns project; db.execute returns no outline (scalar_one_or_none = None)
    outline_result = MagicMock()
    outline_result.scalar_one_or_none = MagicMock(return_value=None)
    mock_db.get = AsyncMock(return_value=project)
    mock_db.execute = AsyncMock(return_value=outline_result)

    fake_ids = {"variant_1": str(uuid.uuid4()), "variant_2": str(uuid.uuid4())}

    with patch(
        "app.agents.orchestrator._run_drafting_pipeline",
        new=AsyncMock(return_value={"generation_ids": fake_ids}),
    ):
        resp = await client.post(
            f"/api/v1/agents/{pid}/sections/{sec_uid}/regenerate"
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["generation_ids"] == fake_ids
    assert "trace_id" in data


# ---------------------------------------------------------------------------
# POST /api/v1/agents/{project_id}/outline/unlock
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unlock_outline_not_found(client, mock_db):
    """404 ако outline-ът не съществува."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none = MagicMock(return_value=None)
    mock_db.execute = AsyncMock(return_value=result_mock)

    resp = await client.post(
        f"/api/v1/agents/{uuid.uuid4()}/outline/unlock",
        params={"outline_id": str(uuid.uuid4())},
    )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_unlock_outline_ok(client, mock_db):
    """200 и status=unlocked за намерен outline."""
    from app.core.models import TpOutline

    pid = str(uuid.uuid4())
    oid = str(uuid.uuid4())
    outline = TpOutline(
        id=oid,
        project_id=pid,
        outline_json={"sections": []},
        status_locked=True,
        version=2,
    )

    result_mock = MagicMock()
    result_mock.scalar_one_or_none = MagicMock(return_value=outline)
    mock_db.execute = AsyncMock(return_value=result_mock)

    resp = await client.post(
        f"/api/v1/agents/{pid}/outline/unlock",
        params={"outline_id": oid},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "unlocked"
    assert data["outline_id"] == oid
    assert outline.status_locked is False


# ---------------------------------------------------------------------------
# POST /api/v1/agents/{project_id}/schedule/unlock
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unlock_schedule_not_found(client, mock_db):
    """404 ако schedule-ът не съществува."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none = MagicMock(return_value=None)
    mock_db.execute = AsyncMock(return_value=result_mock)

    resp = await client.post(
        f"/api/v1/agents/{uuid.uuid4()}/schedule/unlock",
        params={"schedule_id": str(uuid.uuid4())},
    )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_unlock_schedule_ok(client, mock_db):
    """200 и status=unlocked за намерен schedule."""
    from app.core.models import ScheduleNormalized

    pid = str(uuid.uuid4())
    sid = str(uuid.uuid4())
    schedule = ScheduleNormalized(
        id=sid,
        project_id=pid,
        schedule_snapshot_id=str(uuid.uuid4()),
        schedule_json={"tasks": []},
        status_locked=True,
        version=3,
    )

    result_mock = MagicMock()
    result_mock.scalar_one_or_none = MagicMock(return_value=schedule)
    mock_db.execute = AsyncMock(return_value=result_mock)

    resp = await client.post(
        f"/api/v1/agents/{pid}/schedule/unlock",
        params={"schedule_id": sid},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "unlocked"
    assert data["schedule_id"] == sid
    assert schedule.status_locked is False


# ---------------------------------------------------------------------------
# POST /api/v1/agents/{project_id}/outline/lock
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lock_outline_not_found(client, mock_db):
    """404 ако outline-ът не съществува."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none = MagicMock(return_value=None)
    mock_db.execute = AsyncMock(return_value=result_mock)

    resp = await client.post(
        f"/api/v1/agents/{uuid.uuid4()}/outline/lock",
        params={"outline_id": str(uuid.uuid4())},
    )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_lock_outline_ok(client, mock_db):
    """200 и status=locked за намерен outline."""
    from app.core.models import TpOutline

    pid = str(uuid.uuid4())
    oid = str(uuid.uuid4())
    outline = TpOutline(
        id=oid,
        project_id=pid,
        outline_json={"sections": []},
        status_locked=False,
        version=1,
    )

    result_mock = MagicMock()
    result_mock.scalar_one_or_none = MagicMock(return_value=outline)
    mock_db.execute = AsyncMock(return_value=result_mock)

    resp = await client.post(
        f"/api/v1/agents/{pid}/outline/lock",
        params={"outline_id": oid},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "locked"
    assert data["outline_id"] == oid
    assert outline.status_locked is True


# ---------------------------------------------------------------------------
# POST /api/v1/agents/{project_id}/schedule/lock
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lock_schedule_not_found(client, mock_db):
    """404 ако schedule-ът не съществува."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none = MagicMock(return_value=None)
    mock_db.execute = AsyncMock(return_value=result_mock)

    resp = await client.post(
        f"/api/v1/agents/{uuid.uuid4()}/schedule/lock",
        params={"schedule_id": str(uuid.uuid4())},
    )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_lock_schedule_ok(client, mock_db):
    """200 и status=locked за намерен schedule."""
    from app.core.models import ScheduleNormalized

    pid = str(uuid.uuid4())
    sid = str(uuid.uuid4())
    schedule = ScheduleNormalized(
        id=sid,
        project_id=pid,
        schedule_snapshot_id=str(uuid.uuid4()),
        schedule_json={"tasks": []},
        status_locked=False,
        version=1,
    )

    result_mock = MagicMock()
    result_mock.scalar_one_or_none = MagicMock(return_value=schedule)
    mock_db.execute = AsyncMock(return_value=result_mock)

    resp = await client.post(
        f"/api/v1/agents/{pid}/schedule/lock",
        params={"schedule_id": sid},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "locked"
    assert data["schedule_id"] == sid
    assert schedule.status_locked is True


# ---------------------------------------------------------------------------
# GET /api/v1/agents/{project_id}/outline — success path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_outline_found(client, mock_db):
    """200 с outline JSON при намерен запис."""
    from app.core.models import TpOutline

    pid = str(uuid.uuid4())
    outline = TpOutline(
        id=str(uuid.uuid4()),
        project_id=pid,
        outline_json={"sections": [{"uid": "s1", "title": "Въведение"}]},
        status_locked=True,
        version=2,
    )

    result_mock = MagicMock()
    result_mock.scalar_one_or_none = MagicMock(return_value=outline)
    mock_db.execute = AsyncMock(return_value=result_mock)

    resp = await client.get(f"/api/v1/agents/{pid}/outline")

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == outline.id
    assert data["status_locked"] is True


# ---------------------------------------------------------------------------
# POST /api/v1/agents/{project_id}/generations/{id}/select — success path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_select_generation_ok(client, mock_db):
    """200 — маркира генерацията като избрана и деселектира останалите."""
    from app.core.models import Generation
    from datetime import datetime, timezone

    pid = str(uuid.uuid4())
    gid = str(uuid.uuid4())
    gen = Generation(
        id=gid,
        project_id=pid,
        section_uid="s1",
        variant=1,
        text="Текст",
        evidence_status="ok",
        selected=False,
        created_at=datetime.now(timezone.utc),
    )

    # db.get returns the generation; db.execute for the bulk update
    mock_db.get = AsyncMock(return_value=gen)
    mock_db.execute = AsyncMock(return_value=MagicMock())

    resp = await client.post(
        f"/api/v1/agents/{pid}/generations/{gid}/select"
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "selected"
    assert data["generation_id"] == gid
    assert gen.selected is True
