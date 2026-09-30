"""Integration tests against a real, disposable PostgreSQL (K-18, K-19, K-21).

Run only when INTEGRATION_PG_ADMIN_URL points to an administrative database
(for example ``postgresql://tpai:tpai_test@localhost:5432/postgres``). Each
run creates throw-away databases and drops them afterwards; nothing touches
the developer or production database. Model calls are always mocked.
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy.engine import make_url

ADMIN_URL = os.environ.get("INTEGRATION_PG_ADMIN_URL", "")

if not ADMIN_URL:
    collect_ignore_glob = ["test_*.py"]
else:
    import psycopg2

    def _admin_execute(sql: str) -> None:
        connection = psycopg2.connect(make_url(ADMIN_URL).render_as_string(hide_password=False).replace("postgresql+psycopg2://", "postgresql://"))
        connection.autocommit = True
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql)
        finally:
            connection.close()

    def create_database(prefix: str) -> str:
        """Create an empty database; return its asyncpg URL (app format)."""
        name = f"{prefix}_{uuid.uuid4().hex[:10]}"
        _admin_execute(f'CREATE DATABASE "{name}"')
        return (
            make_url(ADMIN_URL)
            .set(drivername="postgresql+asyncpg", database=name)
            .render_as_string(hide_password=False)
        )

    def drop_database(async_url: str) -> None:
        name = make_url(async_url).database
        _admin_execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')

    # The application binds its engine at import time, so the journey
    # database must exist and be configured before anything imports `app`.
    SESSION_DATABASE_URL = create_database("tpai_it")
    os.environ["DATABASE_URL"] = SESSION_DATABASE_URL
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
    os.environ.setdefault("OPENAI_API_KEY", "sk-integration-placeholder")
    os.environ.setdefault("APP_SECRET_KEY", "integration-secret")

    # Bind the application's engine to the journey database now, before any
    # test temporarily points settings at a migration-test database.
    import app.main  # noqa: E402,F401

    def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
        drop_database(SESSION_DATABASE_URL)

    @pytest.fixture
    def fresh_database():
        url = create_database("tpai_mig")
        yield url
        drop_database(url)
