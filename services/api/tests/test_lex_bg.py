from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.models import LexSnapshot
from app.legislation import lex_bg


SAMPLE_HTML = """
<html>
  <body>
    <h1>ЗАКОН ЗА УСТРОЙСТВО НА ТЕРИТОРИЯТА</h1>
    <p>В сила от 31.03.2001 г.</p>
    <p>Чл. 1. Този закон урежда устройството на територията.</p>
    <p>Чл. 2. Разпоредбите се прилагат при инвестиционно проектиране.</p>
  </body>
</html>
"""


def _result(items=None, scalar=None):
    result = MagicMock()
    result.scalars.return_value.all.return_value = items or []
    result.scalar_one_or_none.return_value = scalar
    return result


def test_parse_lex_bg_html_extracts_title_and_articles():
    text = lex_bg._extract_text_from_html(SAMPLE_HTML)
    articles = lex_bg._split_lex_articles(text)

    assert lex_bg._extract_title(text) == "ЗАКОН ЗА УСТРОЙСТВО НА ТЕРИТОРИЯТА"
    assert len(articles) == 2
    assert articles[0]["article_ref"] == "Чл. 1."
    assert "устройството на територията" in articles[0]["text"]


@pytest.mark.asyncio
async def test_ensure_project_legislation_current_creates_snapshot_and_chunks(monkeypatch):
    project_id = str(uuid.uuid4())
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_result(scalar=None), _result(items=[])])
    db.flush = AsyncMock()
    db.add = MagicMock()

    parsed = lex_bg.ParsedLexBgAct(
        act_name="Закон за устройство на територията",
        url="https://lex.bg/bg/laws/ldoc/test",
        title="ЗАКОН ЗА УСТРОЙСТВО НА ТЕРИТОРИЯТА",
        text="Чл. 1. Текст.\nЧл. 2. Текст.",
        content_hash="abc123",
        articles=[
            {"article_ref": "Чл. 1.", "text": "Чл. 1. Първи текст."},
            {"article_ref": "Чл. 2.", "text": "Чл. 2. Втори текст."},
        ],
    )
    monkeypatch.setattr(lex_bg, "fetch_lex_bg_act", AsyncMock(return_value=parsed))
    monkeypatch.setattr(
        lex_bg,
        "_embed_lex_texts",
        AsyncMock(return_value=[None, None]),
    )

    result = await lex_bg.ensure_project_legislation_current(
        project_id,
        db,
        acts=(lex_bg.LexBgAct(parsed.act_name, parsed.url),),
        force=True,
    )

    assert result["changed"] == 1
    assert db.add.call_count == 3
    added_types = [type(call.args[0]).__name__ for call in db.add.call_args_list]
    assert added_types == ["LexSnapshot", "LexChunk", "LexChunk"]


@pytest.mark.asyncio
async def test_ensure_project_legislation_current_skips_fresh_snapshot():
    project_id = str(uuid.uuid4())
    snapshot = LexSnapshot(
        project_id=project_id,
        act_name="Закон за устройство на територията",
        lex_url="https://lex.bg/bg/laws/ldoc/test",
        fetched_at=datetime.now(timezone.utc),
        snapshot_id=str(uuid.uuid4()),
        content_hash="abc123",
        parser_version=lex_bg.PARSER_VERSION,
    )
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_result(scalar=snapshot))
    db.flush = AsyncMock()

    result = await lex_bg.ensure_project_legislation_current(
        project_id,
        db,
        acts=(lex_bg.LexBgAct(snapshot.act_name, snapshot.lex_url),),
    )

    assert result["skipped_fresh"] == 1
    assert result["checked"] == 0
