from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.legislation import run_legislation
from app.core.models import LexChunk


def _result(items):
    result = MagicMock()
    result.scalars.return_value.all.return_value = items
    return result


@pytest.mark.asyncio
async def test_run_legislation_refreshes_lex_bg_before_fetching_chunks(mock_db):
    project_id = str(uuid.uuid4())
    snapshot_id = str(uuid.uuid4())
    chunk = LexChunk(
        id=str(uuid.uuid4()),
        project_id=project_id,
        snapshot_id=snapshot_id,
        act_name="Закон за устройство на територията",
        article_ref="Чл. 1.",
        text="Чл. 1. Нормативен текст за инвестиционно проектиране.",
        embedding=None,
    )
    mock_db.execute = AsyncMock(return_value=_result([chunk]))

    with (
        patch(
            "app.legislation.lex_bg.ensure_project_legislation_current",
            new=AsyncMock(return_value={"status": "ok", "changed": 1}),
        ) as refresh,
        patch(
            "app.legislation.lex_bg.latest_snapshot_ids_for_project",
            new=AsyncMock(return_value=[snapshot_id]),
        ),
        patch("app.core.embedding.embed_query", new=AsyncMock(return_value=None)),
        patch(
            "app.agents.legislation.llm_gateway.call",
            new=AsyncMock(return_value={"citations": [], "total_found": 0}),
        ),
    ):
        result = await run_legislation(
            project_id=project_id,
            query="инвестиционно проектиране",
            db=mock_db,
        )

    refresh.assert_awaited_once()
    assert result["_legislation_refresh"] == {"status": "ok", "changed": 1}
    assert "snapshot_id" in str(mock_db.execute.await_args.args[0])
