"""Deterministic Phase 3 hierarchy and matching for reusable proposal forlage."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import delete, select

from app.core.models import ContentPlanItem, ExampleSnippet, TpOutline


_NUMBERED_HEADING_RE = re.compile(
    r"^\s*(?P<number>\d+(?:\.\d+){0,5})[.)]?\s+(?P<title>[^\n]{3,220})$"
)
_WORD_RE = re.compile(r"[0-9A-Za-zА-Яа-яЍѝ]+", re.UNICODE)
_MARKDOWN_RE = re.compile(r"^[#>*_\-\s]+|[#>*_\-\s]+$")
_STOPWORDS = {
    "автор", "всички", "всяка", "всяко", "във", "върху", "дейност", "дейности",
    "за", "изпълнение", "изпълнението", "изпълнител", "или", "към", "като", "на",
    "при", "по", "поръчката", "предложение", "със", "съответствие", "техническо",
    "това", "част", "чрез", "ще", "and", "for", "the", "with",
}
AUTO_MATCH_MIN_SCORE = 0.35


def _clean_heading(value: str) -> str:
    cleaned = _MARKDOWN_RE.sub("", value.strip())
    return re.sub(r"\s+", " ", cleaned).strip(" .:;–—-")


def _heading_candidate(text: str, chunk_type: str | None = None) -> tuple[str | None, str] | None:
    raw = text.strip()
    if not raw:
        return None
    first_line = raw.splitlines()[0].strip()
    cleaned = _clean_heading(first_line)
    if not cleaned or len(cleaned) > 220:
        return None
    numbered = _NUMBERED_HEADING_RE.match(cleaned)
    if numbered:
        return numbered.group("number"), _clean_heading(numbered.group("title"))
    markdown_heading = (
        first_line.startswith("#")
        or (first_line.startswith("**") and first_line.endswith("**"))
        or (first_line.startswith("***") and first_line.endswith("***"))
    )
    letters = [char for char in cleaned if char.isalpha()]
    uppercase_heading = bool(letters) and len(cleaned.split()) <= 18 and (
        sum(char.isupper() for char in letters) / len(letters) >= 0.72
    )
    if chunk_type == "heading" or markdown_heading or uppercase_heading:
        return None, cleaned
    return None


def extract_forlage_sections(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group ordered parser chunks into reviewable hierarchical proposal sections."""
    sections: list[dict[str, Any]] = []
    number_stack: list[tuple[int, str, str]] = []
    current: dict[str, Any] | None = None

    def start(number: str | None, title: str, index: int, page: int | None) -> dict[str, Any]:
        nonlocal number_stack
        if number:
            depth = number.count(".") + 1
            number_stack = [entry for entry in number_stack if entry[0] < depth]
            number_stack.append((depth, number, title))
            path = [entry[2] for entry in number_stack]
        else:
            path = [entry[2] for entry in number_stack] + [title]
        return {
            "number": number,
            "title": title,
            "path": path,
            "order_index": len(sections),
            "chunk_indexes": [index],
            "pages": [page] if page is not None else [],
            "parts": [],
        }

    for index, chunk in enumerate(chunks):
        text = str(chunk.get("text") or "").strip()
        if not text:
            continue
        heading = _heading_candidate(text, str(chunk.get("type") or ""))
        if heading:
            if current:
                sections.append(current)
            current = start(heading[0], heading[1], index, chunk.get("page"))
        elif current is None:
            current = start(None, "Начална част", index, chunk.get("page"))
        else:
            current["chunk_indexes"].append(index)
            if chunk.get("page") is not None:
                current["pages"].append(chunk.get("page"))
        current["parts"].append(text)

    if current:
        sections.append(current)

    normalized: list[dict[str, Any]] = []
    for section in sections:
        text = "\n\n".join(dict.fromkeys(section.pop("parts")))
        if not text.strip():
            continue
        pages = sorted(set(section.pop("pages")))
        normalized.append({
            **section,
            "order_index": len(normalized),
            "page_start": pages[0] if pages else None,
            "page_end": pages[-1] if pages else None,
            "text": text,
        })
    return normalized


def _average_embeddings(indexes: list[int], embeddings: list[list[float] | None]) -> list[float] | None:
    vectors = [embeddings[index] for index in indexes if index < len(embeddings) and embeddings[index]]
    if not vectors:
        return None
    dims = len(vectors[0])
    valid = [vector for vector in vectors if len(vector) == dims]
    if not valid:
        return None
    return [sum(vector[pos] for vector in valid) / len(valid) for pos in range(dims)]


async def replace_forlage_sections(
    *,
    project_id: str,
    file_id: str,
    chunks: list[dict[str, Any]],
    embeddings: list[list[float] | None] | None,
    db,
) -> list[ExampleSnippet]:
    """Replace legacy paragraph snippets with complete hierarchical sections."""
    await db.execute(delete(ExampleSnippet).where(ExampleSnippet.file_id == file_id))
    sections = extract_forlage_sections(chunks)
    snippets: list[ExampleSnippet] = []
    vectors = embeddings or []
    for section in sections:
        snippet = ExampleSnippet(
            project_id=project_id,
            file_id=file_id,
            chunk_id=file_id,
            text=section["text"],
            snippet_kind="forlage_section",
            embedding=_average_embeddings(section["chunk_indexes"], vectors),
            topics_json={
                "phase3_schema": 1,
                "section_number": section["number"],
                "section_title": section["title"],
                "section_path": section["path"],
                "order_index": section["order_index"],
                "page_start": section["page_start"],
                "page_end": section["page_end"],
            },
            applicability_rules_json={
                "purpose": "reusable_forlage_only",
                "may_define_current_requirements": False,
            },
            risk_flags_json={"requires_current_tender_adaptation": True},
            source_group="hierarchical_section",
        )
        db.add(snippet)
        snippets.append(snippet)
    await db.flush()
    return snippets


def _tokens(value: str) -> set[str]:
    result: set[str] = set()
    for raw in _WORD_RE.findall(value.lower()):
        if len(raw) < 3 or raw in _STOPWORDS:
            continue
        result.add(raw)
        if len(raw) >= 8:
            result.add(raw[:7])
    return result


def _snippet_title(snippet: ExampleSnippet) -> str:
    topics = snippet.topics_json if isinstance(snippet.topics_json, dict) else {}
    return str(topics.get("section_title") or snippet.text.splitlines()[0][:220]).strip()


def _target_features(item: ContentPlanItem) -> tuple[set[str], set[str], str]:
    criteria_text = " ".join(
        str(entry.get("text") or entry.get("requirement_text") or "")
        for entry in (item.acceptance_criteria_json or [])
        if isinstance(entry, dict)
    )
    target_title = _tokens(item.title)
    target_all = _tokens(f"{item.title} {criteria_text}")
    return target_title, target_all, _clean_heading(item.title).lower()


def _snippet_features(snippet: ExampleSnippet) -> tuple[set[str], set[str], str]:
    snippet_title_text = _snippet_title(snippet)
    topics = snippet.topics_json if isinstance(snippet.topics_json, dict) else {}
    path_text = " ".join(str(value) for value in topics.get("section_path") or [])
    source_title = _tokens(f"{snippet_title_text} {path_text}")
    source_all = source_title | _tokens(snippet.text[:12000])
    return source_title, source_all, _clean_heading(snippet_title_text).lower()


def _score_features(
    target: tuple[set[str], set[str], str],
    source: tuple[set[str], set[str], str],
) -> tuple[float, list[str]]:
    target_title, target_all, target_title_text = target
    source_title, source_all, source_title_text = source
    shared = target_all & source_all
    title_shared = target_title & source_title
    title_coverage = len(title_shared) / max(1, len(target_title))
    content_coverage = len(shared) / max(1, len(target_all))
    title_similarity = SequenceMatcher(
        None, target_title_text, source_title_text
    ).ratio()
    score = min(1.0, 0.55 * title_coverage + 0.30 * content_coverage + 0.15 * title_similarity)
    visible_shared = sorted(token for token in shared if len(token) >= 4 and not token.isdigit())[:8]
    return round(score, 4), visible_shared


def score_forlage_match(item: ContentPlanItem, snippet: ExampleSnippet) -> tuple[float, list[str]]:
    return _score_features(_target_features(item), _snippet_features(snippet))


def candidate_matches(
    item: ContentPlanItem,
    snippets: list[ExampleSnippet],
    *,
    limit: int = 3,
) -> list[dict[str, Any]]:
    ranked = []
    for snippet in snippets:
        score, shared = score_forlage_match(item, snippet)
        if score < 0.08:
            continue
        ranked.append((score, snippet, shared))
    ranked.sort(key=lambda row: (-row[0], _snippet_title(row[1]).lower()))
    return [
        {
            "section_id": snippet.id,
            "score": score,
            "reason": "Общи понятия: " + ", ".join(shared) if shared else "Сходно заглавие и тематичен контекст",
        }
        for score, snippet, shared in ranked[:limit]
    ]


def candidate_match_map(
    items: list[ContentPlanItem],
    snippets: list[ExampleSnippet],
    *,
    limit: int = 3,
) -> dict[str, list[dict[str, Any]]]:
    """Rank all mappings while tokenizing each large forlage section only once."""
    snippet_features = [(snippet, _snippet_features(snippet)) for snippet in snippets]
    result: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        target = _target_features(item)
        ranked = []
        for snippet, source in snippet_features:
            score, shared = _score_features(target, source)
            if score >= 0.08:
                ranked.append((score, snippet, shared))
        ranked.sort(key=lambda row: (-row[0], _snippet_title(row[1]).lower()))
        result[item.id] = [
            {
                "section_id": snippet.id,
                "score": score,
                "reason": "Общи понятия: " + ", ".join(shared) if shared else "Сходно заглавие и тематичен контекст",
            }
            for score, snippet, shared in ranked[:limit]
        ]
    return result


async def confirmed_forlage_for_item(
    *, project_id: str, content_plan_item_id: str | None, db
) -> ExampleSnippet | None:
    _reviewed, snippet = await reviewed_forlage_for_item(
        project_id=project_id,
        content_plan_item_id=content_plan_item_id,
        db=db,
    )
    return snippet


async def reviewed_forlage_for_item(
    *, project_id: str, content_plan_item_id: str | None, db
) -> tuple[bool, ExampleSnippet | None]:
    if not content_plan_item_id:
        return False, None
    item = await db.get(ContentPlanItem, content_plan_item_id)
    if not item or item.project_id != project_id:
        return False, None
    outline = await db.get(TpOutline, item.outline_id)
    review = (
        outline.outline_json.get("forlage_review", {})
        if outline and isinstance(outline.outline_json, dict)
        else {}
    )
    if review.get("status") != "confirmed":
        return False, None
    if not item.forlage_section_id:
        return True, None
    snippet = await db.get(ExampleSnippet, item.forlage_section_id)
    if not snippet or snippet.project_id != project_id:
        return True, None
    return True, snippet
