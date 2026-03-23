"""
Тестове за /api/v1/export endpoints.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import _make_project


# ---------------------------------------------------------------------------
# GET /api/v1/export/{project_id}/docx
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_docx_project_not_found(client, mock_db):
    """404 ако проектът не съществува."""
    mock_db.get = AsyncMock(return_value=None)

    resp = await client.get(f"/api/v1/export/{uuid.uuid4()}/docx")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_export_docx_stale_returns_409(client, mock_db):
    """409 ако има генерации с evidence_status='stale'."""
    project = _make_project()
    mock_db.get = AsyncMock(return_value=project)

    stale_gen = MagicMock()
    stale_gen.section_uid = "s1"

    stale_result = MagicMock()
    stale_result.scalars.return_value.all.return_value = [stale_gen]
    mock_db.execute = AsyncMock(return_value=stale_result)

    resp = await client.get(f"/api/v1/export/{project.id}/docx")

    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert "stale" in detail["message"]
    assert "s1" in detail["stale_sections"]


@pytest.mark.asyncio
async def test_export_docx_ok(client, mock_db):
    """200 с DOCX bytes при успешен export."""
    project = _make_project(name="Test Project")
    mock_db.get = AsyncMock(return_value=project)

    # No stale generations
    clean_result = MagicMock()
    clean_result.scalars.return_value.all.return_value = []
    mock_db.execute = AsyncMock(return_value=clean_result)

    fake_docx = b"PK\x03\x04fake-docx-content"

    with patch(
        "app.export.docx_generator.generate_docx",
        new=AsyncMock(return_value=fake_docx),
    ):
        resp = await client.get(f"/api/v1/export/{project.id}/docx")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert resp.content == fake_docx
