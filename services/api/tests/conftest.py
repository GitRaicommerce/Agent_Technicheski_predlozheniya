"""
Общи pytest fixtures за TP AI backend тестове.

Стратегия: изолирани unit тестове без реална БД/Redis.
  - get_db се override-ва с AsyncMock
  - AsyncSessionLocal и redis се patch-ват при нужда
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.main import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_project(**kwargs) -> MagicMock:
    """Връща mock обект, имитиращ Project ORM модел."""
    p = MagicMock()
    p.id = str(uuid.uuid4())
    p.name = kwargs.get("name", "Тестов проект")
    p.location = kwargs.get("location", "София")
    p.description = kwargs.get("description", None)
    p.contracting_authority = kwargs.get("contracting_authority", None)
    p.tender_date = kwargs.get("tender_date", None)
    p.created_at = datetime.now(timezone.utc)
    p.updated_at = datetime.now(timezone.utc)
    # Позволява `from_attributes` на Pydantic да работи
    p.__dict__.update(
        {
            "id": p.id,
            "name": p.name,
            "location": p.location,
            "description": p.description,
            "contracting_authority": p.contracting_authority,
            "tender_date": p.tender_date,
            "created_at": p.created_at,
            "updated_at": p.updated_at,
        }
    )
    return p


# ---------------------------------------------------------------------------
# DB mock fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db() -> AsyncMock:
    """Mock AsyncSession — замества реална БД."""
    db = AsyncMock()
    db.get = AsyncMock(return_value=None)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# HTTP client fixture
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client(mock_db: AsyncMock) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient, свързан директно с FastAPI app (без реален сокет)."""

    async def _override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Convenience re-exports
# ---------------------------------------------------------------------------

__all__ = ["client", "mock_db", "_make_project"]
