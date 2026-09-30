"""K-18/K-21 (T-22 part): the migration chain works on real PostgreSQL."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import settings

API_DIR = Path(__file__).resolve().parents[1]
# Oldest revision with generations.selected/revision_number: a realistic
# "existing installation" before the understanding / content-plan work.
OLD_REVISION = "e5f6a7b8c9d0"


def _alembic(monkeypatch, async_url: str) -> Config:
    # env.py reads settings.database_url on every command.
    monkeypatch.setattr(settings, "database_url", async_url)
    return Config(str(API_DIR / "alembic.ini"))


def _sync_engine(async_url: str):
    return create_engine(make_url(async_url).set(drivername="postgresql+psycopg2"))


def test_empty_database_upgrades_to_the_single_head(monkeypatch, fresh_database):
    config = _alembic(monkeypatch, fresh_database)
    heads = ScriptDirectory.from_config(config).get_heads()
    assert len(heads) == 1, f"migration chain must have one head, got {heads}"

    command.upgrade(config, "head")

    engine = _sync_engine(fresh_database)
    try:
        with engine.connect() as connection:
            assert MigrationContext.configure(connection).get_current_heads() == tuple(heads)
            from app.core.models import Base

            diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    finally:
        engine.dispose()
    # The database may carry extra indexes/constraints the models don't
    # declare; any missing table/column or type change is a real defect.
    def kind(op):
        return op[0] if isinstance(op, tuple) else op[0][0]

    missing = [op for op in diff if kind(op) not in {"remove_index", "remove_constraint"}]
    assert missing == [], f"models and migrated schema disagree: {missing}"


def test_upgrade_keeps_old_projects_and_texts_readable(monkeypatch, fresh_database):
    config = _alembic(monkeypatch, fresh_database)
    command.upgrade(config, OLD_REVISION)

    engine = _sync_engine(fresh_database)
    project_id = "11111111-1111-1111-1111-111111111111"
    try:
        with engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO projects (id, name, location) VALUES (:id, 'Стар проект', 'Перник')"
            ), {"id": project_id})
            connection.execute(text(
                "INSERT INTO tp_outlines (id, project_id, outline_json, status_locked, version) "
                "VALUES ('22222222-2222-2222-2222-222222222222', :id, CAST(:outline AS jsonb), true, 1)"
            ), {"id": project_id, "outline": '{"sections": [{"uid": "33333333-3333-3333-3333-333333333333", "title": "1. Организация"}]}'})
            connection.execute(text(
                "INSERT INTO generations (id, project_id, section_uid, variant, text, selected, revision_number) "
                "VALUES ('44444444-4444-4444-4444-444444444444', :id, '33333333-3333-3333-3333-333333333333', '1', "
                "'Старият текст на раздела.', true, 1)"
            ), {"id": project_id})
    finally:
        engine.dispose()

    command.upgrade(config, "head")

    async def read_back():
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from app.core.models import Generation, Project

        async_engine = create_async_engine(fresh_database)
        try:
            async with async_sessionmaker(async_engine)() as session:
                project = await session.get(Project, project_id)
                generations = (
                    await session.execute(select(Generation).where(Generation.project_id == project_id))
                ).scalars().all()
                return project, generations
        finally:
            await async_engine.dispose()

    project, generations = asyncio.run(read_back())
    assert project is not None and project.name == "Стар проект"
    assert [g.text for g in generations] == ["Старият текст на раздела."]
    generation = generations[0]
    # New columns get explicit, safe values on old rows.
    assert generation.selected is True
    assert generation.generation_kind == "section"
    assert generation.parent_section_uid is None


@pytest.mark.parametrize("revision", [OLD_REVISION])
def test_health_reports_an_old_schema_as_not_ready(monkeypatch, fresh_database, revision):
    """T-22: a real database behind the code's head is not 'ready'."""
    config = _alembic(monkeypatch, fresh_database)
    command.upgrade(config, revision)

    async def probe():
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        import app.main as main

        async_engine = create_async_engine(fresh_database)
        monkeypatch.setattr(main, "AsyncSessionLocal", async_sessionmaker(async_engine))
        try:
            response = await main.health()
        finally:
            await async_engine.dispose()
        return response

    response = asyncio.run(probe())
    assert response.status_code == 503
    assert b"pending" in response.body
