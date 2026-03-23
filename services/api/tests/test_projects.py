"""
Тестове за /api/v1/projects CRUD endpoints.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import _make_project


# ---------------------------------------------------------------------------
# POST /api/v1/projects/
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_project_returns_201(client, mock_db):
    project = _make_project(name="Нов проект", location="Пловдив")

    async def _refresh(obj):
        obj.id = project.id
        obj.name = project.name
        obj.location = project.location
        obj.description = project.description
        obj.contracting_authority = project.contracting_authority
        obj.tender_date = project.tender_date
        obj.created_at = project.created_at
        obj.updated_at = project.updated_at

    mock_db.refresh = AsyncMock(side_effect=_refresh)

    resp = await client.post(
        "/api/v1/projects",
        json={"name": "Нов проект", "location": "Пловдив"},
    )

    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Нов проект"
    assert data["location"] == "Пловдив"


@pytest.mark.asyncio
async def test_create_project_missing_name(client):
    """Липсва задължителното поле name → 422."""
    resp = await client.post("/api/v1/projects", json={"location": "Варна"})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/v1/projects/
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_projects_empty(client, mock_db):
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = []
    mock_db.execute = AsyncMock(return_value=result_mock)

    resp = await client.get("/api/v1/projects")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_projects_returns_all(client, mock_db):
    projects = [_make_project(name=f"Проект {i}") for i in range(3)]
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = projects
    mock_db.execute = AsyncMock(return_value=result_mock)

    resp = await client.get("/api/v1/projects")

    assert resp.status_code == 200
    assert len(resp.json()) == 3


# ---------------------------------------------------------------------------
# GET /api/v1/projects/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_project_found(client, mock_db):
    project = _make_project(name="Намерен проект")
    mock_db.get = AsyncMock(return_value=project)

    resp = await client.get(f"/api/v1/projects/{project.id}")

    assert resp.status_code == 200
    assert resp.json()["name"] == "Намерен проект"


@pytest.mark.asyncio
async def test_get_project_not_found(client, mock_db):
    mock_db.get = AsyncMock(return_value=None)

    resp = await client.get(f"/api/v1/projects/{uuid.uuid4()}")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PUT /api/v1/projects/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_project(client, mock_db):
    project = _make_project(name="Стар проект")
    mock_db.get = AsyncMock(return_value=project)

    async def _refresh(obj):
        obj.__dict__.update({"name": "Нов проект", "updated_at": datetime.now(timezone.utc)})

    mock_db.refresh = AsyncMock(side_effect=_refresh)

    resp = await client.put(
        f"/api/v1/projects/{project.id}",
        json={"name": "Нов проект"},
    )

    assert resp.status_code == 200
    assert resp.json()["name"] == "Нов проект"


@pytest.mark.asyncio
async def test_update_project_not_found(client, mock_db):
    mock_db.get = AsyncMock(return_value=None)

    resp = await client.put(
        f"/api/v1/projects/{uuid.uuid4()}",
        json={"name": "Нещо"},
    )

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/v1/projects/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_project(client, mock_db):
    project = _make_project()
    mock_db.get = AsyncMock(return_value=project)
    # No files for this project
    files_result = MagicMock()
    files_result.scalars.return_value.all.return_value = []
    mock_db.execute = AsyncMock(return_value=files_result)

    with patch("app.routers.projects.storage.delete_object", new=AsyncMock()):
        resp = await client.delete(f"/api/v1/projects/{project.id}")

    assert resp.status_code == 204
    mock_db.delete.assert_called_once_with(project)


@pytest.mark.asyncio
async def test_delete_project_not_found(client, mock_db):
    mock_db.get = AsyncMock(return_value=None)

    resp = await client.delete(f"/api/v1/projects/{uuid.uuid4()}")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/v1/projects/stats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_project_stats_empty(client, mock_db):
    """Връща празен dict когато няма проекти."""
    # 5 execute calls: files, outlines, gen, sel, all_ids
    empty_result = MagicMock()
    empty_result.__iter__ = MagicMock(return_value=iter([]))
    mock_db.execute = AsyncMock(return_value=empty_result)

    resp = await client.get("/api/v1/projects/stats")

    assert resp.status_code == 200
    assert resp.json() == {}


@pytest.mark.asyncio
async def test_project_stats_returns_counts(client, mock_db):
    """Агрегира файлове, outline, генерации и избрани секции по проект."""
    pid = str(uuid.uuid4())

    # Row helpers
    def _row(**kwargs):
        r = MagicMock()
        for k, v in kwargs.items():
            setattr(r, k, v)
        return r

    files_result   = MagicMock(); files_result.__iter__ = lambda s: iter([_row(project_id=pid, cnt=3)])
    outline_result = MagicMock(); outline_result.__iter__ = lambda s: iter([_row(project_id=pid)])
    gen_result     = MagicMock(); gen_result.__iter__ = lambda s: iter([_row(project_id=pid, generated=5)])
    sel_result     = MagicMock(); sel_result.__iter__ = lambda s: iter([_row(project_id=pid, selected=2)])
    ids_result     = MagicMock(); ids_result.__iter__ = lambda s: iter([_row(id=pid)])

    mock_db.execute = AsyncMock(side_effect=[
        files_result, outline_result, gen_result, sel_result, ids_result
    ])

    resp = await client.get("/api/v1/projects/stats")

    assert resp.status_code == 200
    data = resp.json()
    assert pid in data
    stat = data[pid]
    assert stat["files"] == 3
    assert stat["outline_locked"] is True
    assert stat["sections_generated"] == 5
    assert stat["sections_selected"] == 2
