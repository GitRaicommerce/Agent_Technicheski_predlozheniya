from __future__ import annotations

import hashlib
import html
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import TYPE_CHECKING, Any

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.models import LexChunk, LexSnapshot, Project

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger()

PARSER_VERSION = "lex_bg_v1"


@dataclass(frozen=True)
class LexBgAct:
    act_name: str
    url: str
    topics: tuple[str, ...] = ()


@dataclass(frozen=True)
class ParsedLexBgAct:
    act_name: str
    url: str
    title: str
    text: str
    content_hash: str
    articles: list[dict[str, str]]


DEFAULT_LEX_BG_ACTS: tuple[LexBgAct, ...] = (
    LexBgAct(
        act_name="Закон за устройство на територията",
        url="https://lex.bg/bg/laws/ldoc/2135163904",
        topics=("строителство", "проектиране", "разрешение за строеж"),
    ),
    LexBgAct(
        act_name="Закон за обществените поръчки",
        url="https://lex.bg/bg/laws/ldoc/2136735703",
        topics=("обществена поръчка", "изпълнител", "оферта"),
    ),
    LexBgAct(
        act_name="Правилник за прилагане на Закона за обществените поръчки",
        url="https://lex.bg/bg/laws/ldoc/2136789316",
        topics=("обществена поръчка", "процедура", "документация"),
    ),
    LexBgAct(
        act_name="Наредба № 1 от 30 юли 2003 г. за номенклатурата на видовете строежи",
        url="https://lex.bg/bg/laws/ldoc/2135470556",
        topics=("категория строеж", "видове строежи", "чл. 137 ЗУТ"),
    ),
    LexBgAct(
        act_name="Наредба № 3 от 31 юли 2003 г. за съставяне на актове и протоколи по време на строителството",
        url="https://lex.bg/bg/laws/ldoc/2135470582",
        topics=("актове", "протоколи", "строителство", "строителна площадка"),
    ),
    LexBgAct(
        act_name="Наредба № 4 от 21 май 2001 г. за обхвата и съдържанието на инвестиционните проекти",
        url="https://lex.bg/bg/laws/ldoc/-549165055",
        topics=("инвестиционен проект", "проектиране", "фази", "проектни части"),
    ),
    LexBgAct(
        act_name="Наредба № 2 от 22 март 2004 г. за минималните изисквания за ЗБУТ при СМР",
        url="https://lex.bg/bg/laws/ldoc/2135484002",
        topics=("ЗБУТ", "СМР", "безопасност", "строителна площадка"),
    ),
    LexBgAct(
        act_name="Наредба № Iз-1971 от 29 октомври 2009 г. за строително-технически правила и норми за безопасност при пожар",
        url="https://lex.bg/bg/laws/ldoc/2135653786",
        topics=("пожарна безопасност", "проектиране", "строителство"),
    ),
    LexBgAct(
        act_name="Наредба № РД-02-20-2 от 26 януари 2021 г. за достъпност и универсален дизайн",
        url="https://lex.bg/bg/laws/ldoc/2137209812",
        topics=("достъпност", "универсален дизайн", "сгради", "съоръжения"),
    ),
)


async def ensure_project_legislation_current(
    project_id: str,
    db: "AsyncSession",
    trace_id: str | None = None,
    *,
    force: bool = False,
    acts: tuple[LexBgAct, ...] = DEFAULT_LEX_BG_ACTS,
) -> dict[str, Any]:
    """Refresh known Lex.bg acts for a project when snapshots are missing or stale."""
    if not settings.lex_bg_auto_refresh_enabled:
        return {
            "status": "disabled",
            "checked": 0,
            "changed": 0,
            "unchanged": 0,
            "skipped_fresh": 0,
            "refreshed": [],
            "errors": [],
        }

    checked = 0
    changed = 0
    unchanged = 0
    skipped = 0
    errors: list[dict[str, str]] = []
    refreshed: list[dict[str, str]] = []

    for act in acts:
        if not await _project_exists(db, project_id):
            return _deleted_project_result(
                checked, changed, unchanged, skipped, refreshed, errors
            )

        latest = await _latest_snapshot(db, project_id, act.act_name)
        if latest and not force and _is_snapshot_fresh(latest.fetched_at):
            skipped += 1
            continue

        checked += 1
        try:
            parsed = await fetch_lex_bg_act(act)
        except Exception as exc:
            errors.append({"act_name": act.act_name, "error": str(exc)})
            log.warning(
                "lex_bg_refresh_failed",
                project_id=project_id,
                act_name=act.act_name,
                error=str(exc),
                trace_id=trace_id,
            )
            continue

        if latest and latest.content_hash == parsed.content_hash:
            latest.fetched_at = datetime.now(timezone.utc)
            latest.parser_version = PARSER_VERSION
            unchanged += 1
            continue

        if not await _project_exists(db, project_id):
            return _deleted_project_result(
                checked, changed, unchanged, skipped, refreshed, errors
            )

        try:
            await _replace_project_act_snapshot(db, project_id, parsed)
        except IntegrityError as exc:
            await db.rollback()
            log.info(
                "lex_bg_refresh_project_deleted",
                project_id=project_id,
                act_name=parsed.act_name,
                error=str(exc),
                trace_id=trace_id,
            )
            return _deleted_project_result(
                checked, changed, unchanged, skipped, refreshed, errors
            )
        changed += 1
        refreshed.append(
            {
                "act_name": parsed.act_name,
                "content_hash": parsed.content_hash,
                "articles": str(len(parsed.articles)),
            }
        )

    await db.flush()
    return {
        "status": "ok" if not errors else "warning",
        "checked": checked,
        "changed": changed,
        "unchanged": unchanged,
        "skipped_fresh": skipped,
        "refreshed": refreshed,
        "errors": errors,
    }


async def _project_exists(db: "AsyncSession", project_id: str) -> bool:
    return await db.get(Project, project_id) is not None


def _deleted_project_result(
    checked: int,
    changed: int,
    unchanged: int,
    skipped: int,
    refreshed: list[dict[str, str]],
    errors: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "status": "skipped",
        "checked": checked,
        "changed": changed,
        "unchanged": unchanged,
        "skipped_fresh": skipped,
        "refreshed": refreshed,
        "errors": errors,
    }


async def fetch_lex_bg_act(act: LexBgAct) -> ParsedLexBgAct:
    headers = {
        "User-Agent": "TP-AI/1.0 (+https://github.com/GitRaicommerce/Agent_Technicheski_predlozheniya)",
        "Accept": "text/html,application/xhtml+xml",
    }
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=settings.lex_bg_request_timeout_seconds,
        headers=headers,
    ) as client:
        response = await client.get(act.url)
        response.raise_for_status()

    text = _extract_text_from_html(response.text)
    if len(text.strip()) < 500:
        raise ValueError("lex_bg_response_has_too_little_text")

    title = _extract_title(text) or act.act_name
    articles = _split_lex_articles(text)
    if not articles:
        articles = [{"article_ref": "full_text", "text": text[:12000]}]

    return ParsedLexBgAct(
        act_name=act.act_name,
        url=act.url,
        title=title,
        text=text,
        content_hash=_content_hash(text),
        articles=articles,
    )


async def latest_snapshot_ids_for_project(
    project_id: str, db: "AsyncSession"
) -> list[str]:
    result = await db.execute(
        select(LexSnapshot)
        .where(LexSnapshot.project_id == project_id)
        .order_by(LexSnapshot.act_name.asc(), LexSnapshot.fetched_at.desc())
    )
    snapshots = result.scalars().all()
    latest_by_act: dict[str, LexSnapshot] = {}
    for snapshot in snapshots:
        latest_by_act.setdefault(snapshot.act_name, snapshot)
    return [snapshot.snapshot_id for snapshot in latest_by_act.values()]


async def _latest_snapshot(
    db: "AsyncSession", project_id: str, act_name: str
) -> LexSnapshot | None:
    result = await db.execute(
        select(LexSnapshot)
        .where(
            LexSnapshot.project_id == project_id,
            LexSnapshot.act_name == act_name,
        )
        .order_by(LexSnapshot.fetched_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _replace_project_act_snapshot(
    db: "AsyncSession", project_id: str, parsed: ParsedLexBgAct
) -> None:
    existing = await db.execute(
        select(LexSnapshot).where(
            LexSnapshot.project_id == project_id,
            LexSnapshot.act_name == parsed.act_name,
        )
    )
    for snapshot in existing.scalars().all():
        await db.delete(snapshot)
    await db.flush()

    snapshot = LexSnapshot(
        project_id=project_id,
        act_name=parsed.act_name,
        lex_url=parsed.url,
        snapshot_id=str(uuid.uuid4()),
        content_hash=parsed.content_hash,
        parser_version=PARSER_VERSION,
        storage_key_raw=None,
        storage_key_normalized=None,
    )
    db.add(snapshot)
    await db.flush()

    texts = [article["text"] for article in parsed.articles]
    embeddings = await _embed_lex_texts(texts)
    for index, article in enumerate(parsed.articles):
        db.add(
            LexChunk(
                project_id=project_id,
                snapshot_id=snapshot.snapshot_id,
                act_name=parsed.act_name,
                article_ref=article["article_ref"],
                text=article["text"],
                embedding=embeddings[index] if index < len(embeddings) else None,
            )
        )


async def _embed_lex_texts(texts: list[str]) -> list[list[float] | None]:
    try:
        from app.core.embedding import embed_texts

        return await embed_texts(texts)
    except Exception as exc:
        log.warning("lex_bg_embedding_failed", error=str(exc))
        return [None] * len(texts)


def _is_snapshot_fresh(fetched_at: datetime | None) -> bool:
    if not fetched_at:
        return False
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
    max_age = timedelta(hours=settings.lex_bg_refresh_ttl_hours)
    return datetime.now(timezone.utc) - fetched_at <= max_age


def _extract_text_from_html(html_text: str) -> str:
    parser = _VisibleTextParser()
    parser.feed(html_text)
    parser.close()
    raw = html.unescape("\n".join(parser.parts))
    raw = re.sub(r"[ \t\r\f\v]+", " ", raw)
    raw = re.sub(r"\n\s*\n+", "\n", raw)
    return raw.strip()


def _extract_title(text: str) -> str | None:
    for line in text.splitlines():
        clean = line.strip()
        if clean.startswith(("ЗАКОН", "НАРЕДБА", "ПРАВИЛНИК")):
            return clean[:512]
    return None


def _split_lex_articles(text: str) -> list[dict[str, str]]:
    article_pattern = re.compile(
        r"(?ms)(Чл\.\s*\d+[а-яА-Я]?\..*?)(?=\n\s*Чл\.\s*\d+[а-яА-Я]?\.|\Z)"
    )
    articles: list[dict[str, str]] = []
    for match in article_pattern.finditer(text):
        article_text = _normalize_article_text(match.group(1))
        if len(article_text) < 40:
            continue
        ref_match = re.match(r"(Чл\.\s*\d+[а-яА-Я]?\.)", article_text)
        articles.append(
            {
                "article_ref": ref_match.group(1) if ref_match else "Чл.",
                "text": article_text[:6000],
            }
        )
    return articles


def _normalize_article_text(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s+", "\n", text)
    return text.strip()


def _content_hash(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
        if tag in {"p", "div", "br", "li", "tr", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
        if tag in {"p", "div", "li", "tr", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if data.strip():
            self.parts.append(data)
