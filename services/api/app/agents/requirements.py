from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass
from typing import Any, Iterable


DIRECT_REQUIREMENT_CUES = (
    "следва да",
    "трябва да",
    "необходимо е да",
    "изисква се",
    "се изисква",
    "задължително",
    "минимално съдържание",
    "да съдържа",
    "да включва",
    "да опише",
    "да представи",
    "да посочи",
    "да предложи",
    "да обоснове",
    "да разработи",
    "да докаже",
    "да осигури",
    "да предвиди",
    "да изготви",
)

TP_CONTEXT_CUES = (
    "техническото предложение",
    "техническо предложение",
    "предложение за изпълнение",
    "работна програма",
    "организация и изпълнение",
    "методология",
    "офертата",
    "участникът",
)

STRONG_TP_CONTEXT_CUES = (
    "техническото предложение",
    "техническо предложение",
    "предложение за изпълнение",
    "работна програма",
    "организация и изпълнение",
    "методология",
)

EVALUATION_CUES = (
    "ще се оценява",
    "оценява се",
    "методика за оценка",
    "показател",
    "критерий",
    "точки",
)

SCOPE_CUES = (
    "предметът на поръчката включва",
    "обхватът включва",
    "дейностите включват",
    "в обхвата на поръчката",
    "предвидените дейности",
)

ADMIN_NOISE = (
    "еедоп",
    "ценово предложение",
    "предложените цени",
    "предложената цена",
    "гаранция за участие",
    "лично състояние",
    "критерии за подбор",
    "подбор",
    "отстраняване на участник",
    "комисията",
    "декларация",
    "срок на валидност на офертата",
    "документи за подбор",
    "обединение",
    "консорциум",
    "булстат",
    "централния професионален регистър",
    "цпрс",
    "правоспособност",
    "чуждестранен участник",
    "подизпълнител",
    "изпълнил строителство",
    "изпълнил дейност",
    "идентичен или сходен",
    "сходен с този",
    "допуснати до оценяване",
    "три или повече оферти",
)

EXECUTION_RELEVANCE_CUES = (
    "изпълнение",
    "работна програма",
    "методология",
    "организация",
    "график",
    "качество",
    "контрол",
    "риск",
    "комуникация",
    "координация",
    "безопасност",
    "околна среда",
    "отпад",
    "материал",
    "доставка",
    "дейност",
    "смр",
    "строител",
    "проект",
    "авторски надзор",
)

CATEGORY_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("communication", "Комуникация и координация", ("комуникация", "координация", "възложител", "институц", "надзор", "субординация")),
    ("quality", "Качество и контрол", ("качество", "контрол", "провер", "приемане", "протокол", "изпитван")),
    ("risk", "Риск и непредвидени обстоятелства", ("риск", "непредвид", "авар", "затруднен", "мерки за")),
    ("schedule", "График и срокове", ("срок", "график", "етап", "последователност", "време", "дейностите по време")),
    ("safety", "Безопасност", ("безопасност", "збут", "пбз", "пожар", "здравослов", "охрана на труда")),
    ("environment", "Околна среда", ("околна среда", "отпад", "прах", "почв", "вод", "пусо", "замърся")),
    ("deliveries", "Доставки и материали", ("материал", "доставка", "склад", "транспорт", "логистика")),
    ("organization", "Организация, екип и ресурси", ("организация", "екип", "ресурс", "персонал", "отговорност", "ръководител")),
    ("documentation", "Документиране и отчетност", ("документ", "документация", "протокол", "отчет", "екзекутив")),
    ("warranty", "Гаранционни дейности", ("гаранцион", "дефект", "отстраняване")),
    ("compliance", "Нормативно съответствие", ("норматив", "закон", "наредба", "разреш", "съгласув", "изискванията на")),
    ("methodology", "Методология и подход", ("метод", "подход", "концепция", "програма", "технология", "изпълнение")),
    ("scope", "Обхват и предмет", ("обхват", "предмет", "дейност", "част", "проект", "смр", "доставка", "услуга")),
)

SUGGESTED_SECTIONS = {
    "scope": "Обхват и разбиране на предмета",
    "methodology": "Концепция, подход и методология",
    "organization": "Организация на изпълнението",
    "schedule": "Линеен график и организация във времето",
    "quality": "Мерки за осигуряване на качеството",
    "risk": "Управление на риска",
    "communication": "Комуникация, координация и контрол",
    "safety": "Безопасност и здравословни условия",
    "environment": "Опазване на околната среда",
    "deliveries": "Организация на доставките и материалите",
    "documentation": "Документиране, отчетност и приемане",
    "warranty": "Гаранционни дейности",
    "compliance": "Нормативно съответствие",
    "other": "Други специфични изисквания",
}


@dataclass(frozen=True)
class RequirementItem:
    id: str
    text: str
    category: str
    category_label: str
    topic: str
    importance: str
    suggested_section: str
    coverage_question: str
    source_chunk_id: str
    source_page: int | None
    source_section_path: str | None
    source_file: str | None
    source_excerpt: str
    evidence_cues: list[str]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_text(value: Any) -> str:
    text = str(value or "").replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _normalize_for_match(value: Any) -> str:
    return normalize_text(value).lower()


def _strip_marker(line: str) -> str:
    line = line.strip()
    line = re.sub(r"^[\-•*]\s+", "", line)
    line = re.sub(r"^\(?\d+(?:\.\d+)*[\.\)]\s*", "", line)
    line = re.sub(r"^[а-я]\)\s*", "", line, flags=re.IGNORECASE)
    return line.strip(" :-")


def _looks_like_list_item(line: str) -> bool:
    stripped = line.strip()
    return bool(re.match(r"^([\-•*]|\(?\d+(?:\.\d+)*[\.\)]|[а-я]\))\s+", stripped, re.IGNORECASE))


def _find_cues(text: str) -> list[str]:
    normalized = _normalize_for_match(text)
    cues: list[str] = []
    for cue in (*DIRECT_REQUIREMENT_CUES, *EVALUATION_CUES, *SCOPE_CUES):
        if cue in normalized and cue not in cues:
            cues.append(cue)
    return cues


def _has_tp_context(text: str) -> bool:
    normalized = _normalize_for_match(text)
    return any(cue in normalized for cue in TP_CONTEXT_CUES)


def _contains_requirement_cue(text: str) -> bool:
    normalized = _normalize_for_match(text)
    if any(cue in normalized for cue in DIRECT_REQUIREMENT_CUES):
        return True
    if any(cue in normalized for cue in EVALUATION_CUES):
        return True
    if any(cue in normalized for cue in SCOPE_CUES):
        return True
    return _has_tp_context(text) and any(
        verb in normalized
        for verb in (
            "опис",
            "представ",
            "посоч",
            "включ",
            "съдърж",
            "разработ",
            "предлож",
            "обоснов",
            "доказ",
        )
    )


def _has_strong_tp_context(text: str) -> bool:
    normalized = _normalize_for_match(text)
    return any(cue in normalized for cue in STRONG_TP_CONTEXT_CUES)


def _is_noise(text: str) -> bool:
    normalized = _normalize_for_match(text)
    if _has_strong_tp_context(normalized):
        return False
    return any(noise in normalized for noise in ADMIN_NOISE)


def _is_relevant_to_technical_proposal(text: str, context: str) -> bool:
    combined = _normalize_for_match(f"{context} {text}")
    text_normalized = _normalize_for_match(text)

    if _has_strong_tp_context(combined):
        return True
    if any(cue in text_normalized for cue in SCOPE_CUES):
        return True
    if any(cue in combined for cue in EVALUATION_CUES) and not any(
        noise in combined for noise in ("ценови показател", "най-ниска цена", "ценово предложение")
    ):
        return True

    if any(noise in combined for noise in ADMIN_NOISE):
        return False

    category, _, _ = _classify(text)
    if category == "other":
        return False

    return any(cue in combined for cue in EXECUTION_RELEVANCE_CUES)


def _split_sentences(text: str) -> list[str]:
    text = normalize_text(text)
    if not text:
        return []

    pieces = re.split(r"(?<=[\.;:])\s+|\n+", text)
    if len(pieces) == 1 and len(text) > 420:
        pieces = re.split(r"\s+(?=да\s+(?:се\s+)?(?:опише|представи|посочи|включи|разработи|предложи|обоснове|докаже|осигури|предвиди|изготви))", text, flags=re.IGNORECASE)

    result: list[str] = []
    for piece in pieces:
        cleaned = normalize_text(piece).strip(" ;")
        if len(cleaned) >= 18:
            result.append(cleaned)
    return result


def _candidate_requirements_from_text(text: str) -> list[str]:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if not lines:
        lines = [normalize_text(text)] if normalize_text(text) else []

    candidates: list[str] = []
    active_header: str | None = None
    active_header_budget = 0

    for raw_line in lines:
        line = normalize_text(raw_line)
        if not line:
            continue

        if _contains_requirement_cue(line):
            for sentence in _split_sentences(line):
                if (
                    _contains_requirement_cue(sentence)
                    and not sentence.rstrip().endswith(":")
                    and not _is_noise(sentence)
                ):
                    candidates.append(_strip_marker(sentence))

            normalized = _normalize_for_match(line)
            if line.endswith(":") or "съдържа" in normalized or "включва" in normalized:
                active_header = _strip_marker(line).rstrip(":")
                active_header_budget = 10
            continue

        if active_header and active_header_budget > 0:
            active_header_budget -= 1
            if _looks_like_list_item(raw_line):
                item = _strip_marker(line)
                if len(item) >= 12 and not _is_noise(item):
                    candidates.append(f"{active_header}: {item}")
                continue

        if active_header_budget <= 0:
            active_header = None

    return _dedupe_texts(candidates)


def _dedupe_texts(texts: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for text in texts:
        cleaned = normalize_text(text).strip(" .;:")
        if len(cleaned) < 18:
            continue
        fingerprint = re.sub(r"[^0-9a-zа-я]+", "", cleaned.lower())[:220]
        if not fingerprint or fingerprint in seen:
            continue
        seen.add(fingerprint)
        result.append(cleaned)
    return result


def _importance(text: str) -> str:
    normalized = _normalize_for_match(text)
    if any(cue in normalized for cue in EVALUATION_CUES):
        return "scored"
    if any(cue in normalized for cue in SCOPE_CUES):
        return "scope"
    if "може да" in normalized and "трябва да" not in normalized and "следва да" not in normalized:
        return "optional"
    return "mandatory"


def _classify(text: str) -> tuple[str, str, str]:
    normalized = _normalize_for_match(text)
    best_category = "other"
    best_label = "Други специфични изисквания"
    best_score = 0
    best_topic = ""

    for category, label, keywords in CATEGORY_RULES:
        matches = [keyword for keyword in keywords if keyword in normalized]
        score = len(matches)
        if score > best_score:
            best_category = category
            best_label = label
            best_score = score
            best_topic = matches[0] if matches else ""

    topic = best_topic or _topic_from_text(text)
    return best_category, best_label, topic


def _topic_from_text(text: str) -> str:
    tokens = [
        token
        for token in re.findall(r"[0-9a-zа-я]+", text.lower())
        if len(token) >= 5
        and token not in {"следва", "трябва", "изисква", "участникът", "офертата", "техническото", "предложение"}
    ]
    return " ".join(tokens[:4]) if tokens else "специфично изискване"


def _coverage_question(text: str) -> str:
    short = normalize_text(text)
    if len(short) > 180:
        short = short[:177].rstrip() + "..."
    return f"Покрито ли е изискването: {short}?"


def _stable_requirement_id(chunk_id: str, text: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{chunk_id}:{normalize_text(text).lower()}"))


def extract_requirement_checklist(chunks: Iterable[Any], *, limit: int | None = None) -> list[RequirementItem]:
    items: list[RequirementItem] = []
    seen: set[str] = set()

    for chunk in chunks:
        chunk_text = getattr(chunk, "text", "") or ""
        chunk_context = " ".join(
            str(value or "")
            for value in (
                getattr(chunk, "section_path", None),
                getattr(chunk, "source_file", None),
                chunk_text[:500],
            )
        )
        source_chunk_id = str(getattr(chunk, "id", "unknown"))
        for requirement_text in _candidate_requirements_from_text(chunk_text):
            if not _is_relevant_to_technical_proposal(requirement_text, chunk_context):
                continue
            fingerprint = re.sub(r"[^0-9a-zа-я]+", "", requirement_text.lower())[:220]
            if not fingerprint or fingerprint in seen:
                continue
            seen.add(fingerprint)

            category, category_label, topic = _classify(requirement_text)
            items.append(
                RequirementItem(
                    id=_stable_requirement_id(source_chunk_id, requirement_text),
                    text=requirement_text,
                    category=category,
                    category_label=category_label,
                    topic=topic,
                    importance=_importance(requirement_text),
                    suggested_section=SUGGESTED_SECTIONS.get(category, SUGGESTED_SECTIONS["other"]),
                    coverage_question=_coverage_question(requirement_text),
                    source_chunk_id=source_chunk_id,
                    source_page=getattr(chunk, "page", None),
                    source_section_path=getattr(chunk, "section_path", None),
                    source_file=getattr(chunk, "source_file", None),
                    source_excerpt=normalize_text(chunk_text)[:500],
                    evidence_cues=_find_cues(requirement_text),
                )
            )

            if limit is not None and len(items) >= limit:
                return items

    return items


def format_requirements_for_prompt(items: list[RequirementItem], *, limit: int = 80) -> str:
    if not items:
        return ""

    lines = [
        "=== УНИВЕРСАЛЕН ЧЕКЛИСТ НА ИЗИСКВАНИЯТА ОТ ДОКУМЕНТАЦИЯТА ===",
        "Използвай тези точки като задължителни контролни въпроси при структурата на техническото предложение.",
    ]
    for index, item in enumerate(items[:limit], start=1):
        page = f", стр. {item.source_page}" if item.source_page else ""
        lines.append(
            f"{index}. [{item.importance}/{item.category_label}] {item.text} "
            f"(предложена секция: {item.suggested_section}; източник: {item.source_chunk_id}{page})"
        )
    if len(items) > limit:
        lines.append(f"... още {len(items) - limit} извлечени изисквания.")
    return "\n".join(lines)


def render_requirements_markdown(
    items: list[RequirementItem],
    *,
    title: str = "Чеклист на изискванията",
) -> str:
    lines = [
        f"# {title}",
        "",
        "Този чеклист е извлечен от тръжната документация. Той не е шаблон за конкретна поръчка, а карта на задълженията, които генерираното техническо предложение трябва да покрие.",
        "",
        "## Обобщение",
        "",
        f"- Общо извлечени изисквания: `{len(items)}`",
    ]

    by_importance: dict[str, int] = {}
    by_category: dict[str, int] = {}
    for item in items:
        by_importance[item.importance] = by_importance.get(item.importance, 0) + 1
        by_category[item.category_label] = by_category.get(item.category_label, 0) + 1

    lines.extend(f"- `{key}`: `{value}`" for key, value in sorted(by_importance.items()))
    lines.extend(["", "## По категории", ""])
    lines.extend(f"- {category}: `{count}`" for category, count in sorted(by_category.items()))

    lines.extend(
        [
            "",
            "## Чеклист",
            "",
            "| # | Статус | Важност | Категория | Изискване | Предложена секция | Източник | Контролен въпрос |",
            "| ---: | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )

    for index, item in enumerate(items, start=1):
        source_parts = []
        if item.source_file:
            source_parts.append(item.source_file)
        if item.source_page:
            source_parts.append(f"стр. {item.source_page}")
        source_parts.append(item.source_chunk_id)
        source = ", ".join(source_parts)
        lines.append(
            "| "
            + " | ".join(
                [
                    str(index),
                    "[ ]",
                    item.importance,
                    item.category_label.replace("|", "\\|"),
                    item.text.replace("|", "\\|"),
                    item.suggested_section.replace("|", "\\|"),
                    source.replace("|", "\\|"),
                    item.coverage_question.replace("|", "\\|"),
                ]
            )
            + " |"
        )

    return "\n".join(lines) + "\n"
