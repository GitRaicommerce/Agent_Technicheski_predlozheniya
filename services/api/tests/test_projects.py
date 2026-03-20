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
# POST /api/v1/projects
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
# GET /api/v1/projects
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
        obj.__dict__.update(
            {"name": "Нов проект", "updated_at": datetime.now(timezone.utc)}
        )

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
