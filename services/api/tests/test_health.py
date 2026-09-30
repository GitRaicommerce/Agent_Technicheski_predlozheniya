"""
Тестове за /health endpoint.

Проверяват поведение при: нормален режим, недостъпна БД, недостъпен Redis.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.main import expected_migration_heads

HEADS = sorted(expected_migration_heads())


def _db_results(revisions):
    """SELECT 1 result, then the alembic_version rows."""
    versions = MagicMock()
    versions.scalars.return_value.all.return_value = list(revisions)
    return [MagicMock(), versions]


def _session(execute):
    session = AsyncMock()
    session.execute = execute
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


def _redis_ok():
    r = AsyncMock()
    r.ping = AsyncMock(return_value=True)
    r.aclose = AsyncMock()
    return r


@pytest.mark.asyncio
async def test_health_all_ok(client):
    """Returns {status: ok} когато БД и Redis са достъпни."""
    with (
        patch("app.main.AsyncSessionLocal") as mock_session_cls,
        patch("redis.asyncio.from_url") as mock_redis_from_url,
    ):
        # БД session context manager
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=_db_results(HEADS))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_cls.return_value = mock_session

        # Redis
        mock_r = AsyncMock()
        mock_r.ping = AsyncMock(return_value=True)
        mock_r.aclose = AsyncMock()
        mock_redis_from_url.return_value = mock_r

        resp = await client.get("/health")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["db"] == "ok"
    assert data["redis"] == "ok"
    assert data["migrations"] == "ok"


@pytest.mark.asyncio
async def test_health_db_down(client):
    """status = 'degraded' + db = 'error: ...' когато БД не отговаря."""
    with (
        patch("app.main.AsyncSessionLocal") as mock_session_cls,
        patch("redis.asyncio.from_url") as mock_redis_from_url,
    ):
        mock_session_cls.side_effect = Exception("connection refused")

        mock_r = AsyncMock()
        mock_r.ping = AsyncMock(return_value=True)
        mock_r.aclose = AsyncMock()
        mock_redis_from_url.return_value = mock_r

        resp = await client.get("/health")

    assert resp.status_code == 503
    data = resp.json()
    assert data["status"] == "degraded"
    assert "error" in data["db"]


@pytest.mark.asyncio
async def test_health_redis_down(client):
    """status = 'degraded' + redis = 'error: ...' когато Redis не отговаря."""
    with (
        patch("app.main.AsyncSessionLocal") as mock_session_cls,
        patch("redis.asyncio.from_url") as mock_redis_from_url,
    ):
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=_db_results(HEADS))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_cls.return_value = mock_session

        mock_r = AsyncMock()
        mock_r.ping = AsyncMock(side_effect=Exception("timeout"))
        mock_r.aclose = AsyncMock()
        mock_redis_from_url.return_value = mock_r

        resp = await client.get("/health")

    assert resp.status_code == 503
    data = resp.json()
    assert data["status"] == "degraded"
    assert "error" in data["redis"]


@pytest.mark.asyncio
@pytest.mark.parametrize("revisions", [[], ["fd40c3c462b6"]])
async def test_health_pending_migration_is_not_ready(client, revisions):
    """K-19 / T-22: an old or empty schema revision answers 503, not ready."""
    with (
        patch("app.main.AsyncSessionLocal", return_value=_session(AsyncMock(side_effect=_db_results(revisions)))),
        patch("redis.asyncio.from_url", return_value=_redis_ok()),
    ):
        resp = await client.get("/health")

    assert resp.status_code == 503
    data = resp.json()
    assert data["status"] == "degraded"
    assert data["migrations"].startswith("pending")


@pytest.mark.asyncio
async def test_health_missing_version_table_is_not_ready(client):
    execute = AsyncMock(side_effect=[MagicMock(), Exception('relation "alembic_version" does not exist')])
    with (
        patch("app.main.AsyncSessionLocal", return_value=_session(execute)),
        patch("redis.asyncio.from_url", return_value=_redis_ok()),
    ):
        resp = await client.get("/health")

    assert resp.status_code == 503
    assert "alembic_version" in resp.json()["migrations"]
