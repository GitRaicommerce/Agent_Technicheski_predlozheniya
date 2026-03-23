"""
Тестове за /api/v1/files endpoints.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_file(**kwargs) -> MagicMock:
    f = MagicMock()
    f.id = str(uuid.uuid4())
    f.project_id = str(uuid.uuid4())
    f.filename = kwargs.get("filename", "test.pdf")
    f.module = kwargs.get("module", "tender_docs")
    f.file_size = kwargs.get("file_size", 1024)
    f.ingest_status = kwargs.get("ingest_status", "done")
    f.ingest_error = kwargs.get("ingest_error", None)
    f.content_type = kwargs.get("content_type", "application/pdf")
    f.storage_key = kwargs.get("storage_key", "some/key.pdf")
    f.file_hash = kwargs.get("file_hash", "abc123")
    f.created_at = datetime.now(timezone.utc)
    f.__dict__.update(
        {
            k: getattr(f, k)
            for k in [
                "id", "project_id", "filename", "module", "file_size",
                "ingest_status", "ingest_error", "content_type",
                "storage_key", "file_hash", "created_at",
            ]
        }
    )
    return f


# ---------------------------------------------------------------------------
# GET /api/v1/files/{project_id}/
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_files_empty(client, mock_db):
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = []
    mock_db.execute = AsyncMock(return_value=result_mock)

    project_id = str(uuid.uuid4())
    resp = await client.get(f"/api/v1/files/{project_id}/files")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_files_returns_data(client, mock_db):
    files = [_make_file(filename=f"doc{i}.pdf") for i in range(2)]
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = files
    mock_db.execute = AsyncMock(return_value=result_mock)

    project_id = str(uuid.uuid4())
    resp = await client.get(f"/api/v1/files/{project_id}/files")

    assert resp.status_code == 200
    assert len(resp.json()) == 2


# ---------------------------------------------------------------------------
# GET /api/v1/files/{project_id}/{file_id}/status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_file_status_done(client, mock_db):
    file = _make_file(ingest_status="done")
    mock_db.get = AsyncMock(return_value=file)

    resp = await client.get(f"/api/v1/files/{file.project_id}/files/{file.id}/status")

    assert resp.status_code == 200
    assert resp.json()["ingest_status"] == "done"


@pytest.mark.asyncio
async def test_file_status_not_found(client, mock_db):
    mock_db.get = AsyncMock(return_value=None)

    resp = await client.get(
        f"/api/v1/files/{uuid.uuid4()}/files/{uuid.uuid4()}/status"
    )

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/v1/files/{project_id}/files/{file_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_file_not_found(client, mock_db):
    """404 когато файлът не съществува."""
    mock_db.get = AsyncMock(return_value=None)

    resp = await client.delete(
        f"/api/v1/files/{uuid.uuid4()}/files/{uuid.uuid4()}"
    )

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/v1/files/{project_id}/upload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_invalid_module(client, mock_db):
    """400 при невалиден модул."""
    project_id = str(uuid.uuid4())
    resp = await client.post(
        f"/api/v1/files/{project_id}/upload",
        data={"module": "not_a_module"},
        files={"file": ("test.pdf", b"content", "application/pdf")},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_upload_project_not_found(client, mock_db):
    """404 когато проектът не съществува."""
    mock_db.get = AsyncMock(return_value=None)
    project_id = str(uuid.uuid4())
    resp = await client.post(
        f"/api/v1/files/{project_id}/upload",
        data={"module": "tender_docs"},
        files={"file": ("test.pdf", b"content", "application/pdf")},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_upload_unsupported_mime(client, mock_db):
    """415 при неподдържан MIME тип."""
    from tests.conftest import _make_project

    project = _make_project()
    mock_db.get = AsyncMock(return_value=project)

    resp = await client.post(
        f"/api/v1/files/{project.id}/upload",
        data={"module": "tender_docs"},
        files={"file": ("note.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 415


@pytest.mark.asyncio
async def test_upload_ok(client, mock_db):
    """201 при успешно качване — storage и ingest queue се извикват."""
    from unittest.mock import patch, AsyncMock as AM
    from tests.conftest import _make_project

    project = _make_project()
    mock_db.get = AM(return_value=project)
    # refresh is a no-op in tests; the ProjectFile object already has all fields set
    mock_db.refresh = AM(return_value=None)
    mock_db.execute = AM(return_value=MagicMock())

    with (
        patch("app.routers.files.storage.put_object", new=AM(return_value=None)),
        patch("app.ingestion.worker.enqueue_ingest", return_value=None),
    ):
        resp = await client.post(
            f"/api/v1/files/{project.id}/upload",
            data={"module": "tender_docs"},
            files={"file": ("report.pdf", b"%PDF-1.4 content", "application/pdf")},
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["module"] == "tender_docs"
    assert body["filename"] == "report.pdf"
    assert body["ingest_status"] == "pending"


@pytest.mark.asyncio
async def test_delete_file_marks_stale(client, mock_db):
    """Изтриването на evidence файл маркира генерациите като stale."""
    from unittest.mock import patch, AsyncMock as AM

    file = _make_file(module="tender_docs")

    execute_calls: list = []

    async def fake_execute(stmt, *_a, **_kw):
        execute_calls.append(stmt)
        return MagicMock()

    mock_db.get = AsyncMock(return_value=file)
    mock_db.execute = AM(side_effect=fake_execute)
    mock_db.delete = AM(return_value=None)
    mock_db.commit = AM(return_value=None)

    with patch(
        "app.routers.files.storage.delete_object",
        new=AM(return_value=None),
    ):
        resp = await client.delete(
            f"/api/v1/files/{file.project_id}/files/{file.id}"
        )

    assert resp.status_code == 204
    assert len(execute_calls) >= 1
