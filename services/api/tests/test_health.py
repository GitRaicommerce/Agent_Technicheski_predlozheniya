"""
Тестове за /health endpoint.

Проверяват поведение при: нормален режим, недостъпна БД, недостъпен Redis.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_health_all_ok(client):
    """Returns {status: ok} когато БД и Redis са достъпни."""
    with (
        patch("app.main.AsyncSessionLocal") as mock_session_cls,
        patch("redis.asyncio.from_url") as mock_redis_from_url,
    ):
        # БД session context manager
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=MagicMock())
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

    assert resp.status_code == 200
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
        mock_session.execute = AsyncMock(return_value=MagicMock())
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_cls.return_value = mock_session

        mock_r = AsyncMock()
        mock_r.ping = AsyncMock(side_effect=Exception("timeout"))
        mock_r.aclose = AsyncMock()
        mock_redis_from_url.return_value = mock_r

        resp = await client.get("/health")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "degraded"
    assert "error" in data["redis"]
