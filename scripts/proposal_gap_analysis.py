from __future__ import annotations

import argparse
import html
import re
import sys
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree


STOPWORDS = {
    "бъде",
    "бяха",
    "във",
    "върху",
    "г.",
    "да",
    "до",
    "за",
    "или",
    "като",
    "които",
    "който",
    "към",
    "ли",
    "на",
    "не",
    "от",
    "по",
    "при",
    "са",
    "се",
    "след",
    "сме",
    "със",
    "тази",
    "това",
    "този",
    "ще",
    "the",
    "and",
    "with",
}


@dataclass
class Section:
    title: str
    text: str

    @property
    def words(self) -> list[str]:
        return tokenize(self.text)


TOPIC_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "organization",
        "Organization, roles and resources",
        (
            "organization",
            "team",
            "resource",
            "responsib",
            "\u043e\u0440\u0433\u0430\u043d\u0438\u0437\u0430\u0446",
            "\u0435\u043a\u0438\u043f",
            "\u0440\u0435\u0441\u0443\u0440\u0441",
            "\u043e\u0442\u0433\u043e\u0432\u043e\u0440\u043d",
        ),
    ),
    (
        "schedule",
        "Schedule, sequence and milestones",
        (
            "schedule",
            "sequence",
            "milestone",
            "deadline",
            "\u0433\u0440\u0430\u0444\u0438\u043a",
            "\u0435\u0442\u0430\u043f",
            "\u0441\u0440\u043e\u043a",
            "\u043f\u043e\u0441\u043b\u0435\u0434\u043e\u0432\u0430\u0442\u0435\u043b\u043d",
        ),
    ),
    (
        "quality",
        "Quality control and acceptance",
        (
            "quality",
            "control",
            "inspection",
            "acceptance",
            "protocol",
            "\u043a\u0430\u0447\u0435\u0441\u0442\u0432",
            "\u043a\u043e\u043d\u0442\u0440\u043e\u043b",
            "\u043f\u0440\u0438\u0435\u043c\u0430\u043d",
            "\u043f\u0440\u043e\u0442\u043e\u043a\u043e\u043b",
        ),
    ),
    (
        "risk",
        "Risk and unforeseen circumstances",
        (
            "risk",
            "unforeseen",
            "mitigation",
            "escalation",
            "\u0440\u0438\u0441\u043a",
            "\u043d\u0435\u043f\u0440\u0435\u0434\u0432\u0438\u0434",
            "\u0435\u0441\u043a\u0430\u043b\u0430\u0446",
        ),
    ),
    (
        "environment",
        "Environmental protection",
        (
            "environment",
            "dust",
            "waste",
            "soil",
            "pollution",
            "\u043e\u043a\u043e\u043b\u043d\u0430 \u0441\u0440\u0435\u0434\u0430",
            "\u043f\u0440\u0430\u0445",
            "\u043e\u0442\u043f\u0430\u0434",
            "\u043f\u043e\u0447\u0432",
            "\u0437\u0430\u043c\u044a\u0440\u0441",
        ),
    ),
    (
        "communication",
        "Communication and coordination",
        (
            "communication",
            "coordination",
            "meeting",
            "reporting",
            "authority",
            "\u043a\u043e\u043c\u0443\u043d\u0438\u043a\u0430\u0446",
            "\u043a\u043e\u043e\u0440\u0434\u0438\u043d\u0430\u0446",
            "\u0432\u044a\u0437\u043b\u043e\u0436\u0438\u0442\u0435\u043b",
            "\u043d\u0430\u0434\u0437\u043e\u0440",
        ),
    ),
    (
        "safety",
        "Health, safety and fire safety",
        (
            "safety",
            "health",
            "fire",
            "incident",
            "\u0431\u0435\u0437\u043e\u043f\u0430\u0441",
            "\u0437\u0434\u0440\u0430\u0432",
            "\u043f\u043e\u0436\u0430\u0440",
            "\u0438\u043d\u0446\u0438\u0434\u0435\u043d\u0442",
        ),
    ),
    (
        "documentation",
        "Documentation, records and reporting",
        (
            "document",
            "record",
            "report",
            "protocol",
            "\u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442",
            "\u043e\u0442\u0447\u0435\u0442",
            "\u043f\u0440\u043e\u0442\u043e\u043a\u043e\u043b",
            "\u0435\u043a\u0437\u0435\u043a\u0443\u0442\u0438\u0432",
        ),
    ),
)

CONTENT_SECTION_HINTS = (
    "approach",
    "method",
    "methodology",
    "organization",
    "programme",
    "program",
    "schedule",
    "sequence",
    "quality",
    "risk",
    "environment",
    "safety",
    "communication",
    "coordination",
    "resource",
    "control",
    "documentation",
    "\u043f\u043e\u0434\u0445\u043e\u0434",
    "\u043c\u0435\u0442\u043e\u0434",
    "\u043c\u0435\u0442\u043e\u0434\u0438\u043a",
    "\u043e\u0440\u0433\u0430\u043d\u0438\u0437\u0430\u0446",
    "\u0440\u0430\u0431\u043e\u0442\u043d\u0430 \u043f\u0440\u043e\u0433\u0440\u0430\u043c",
    "\u043f\u0440\u043e\u0433\u0440\u0430\u043c\u0430",
    "\u0433\u0440\u0430\u0444\u0438\u043a",
    "\u0435\u0442\u0430\u043f",
    "\u043f\u043e\u0441\u043b\u0435\u0434\u043e\u0432\u0430\u0442\u0435\u043b\u043d",
    "\u043a\u0430\u0447\u0435\u0441\u0442\u0432",
    "\u0440\u0438\u0441\u043a",
    "\u043e\u043a\u043e\u043b\u043d\u0430 \u0441\u0440\u0435\u0434\u0430",
    "\u0431\u0435\u0437\u043e\u043f\u0430\u0441",
    "\u0437\u0434\u0440\u0430\u0432",
    "\u043f\u043e\u0436\u0430\u0440",
    "\u043a\u043e\u043c\u0443\u043d\u0438\u043a\u0430\u0446",
    "\u043a\u043e\u043e\u0440\u0434\u0438\u043d\u0430\u0446",
    "\u0440\u0435\u0441\u0443\u0440\u0441",
    "\u043a\u043e\u043d\u0442\u0440\u043e\u043b",
    "\u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442",
)

NON_CONTENT_TITLE_HINTS = (
    "cover",
    "contents",
    "table of contents",
    "signature",
    "signed",
    "declaration",
    "appendix",
    "annex",
    "form",
    "participant",
    "bidder",
    "price",
    "financial",
    "address",
    "contact",
    "\u0441\u044a\u0434\u044a\u0440\u0436\u0430\u043d\u0438\u0435",
    "\u0434\u0435\u043a\u043b\u0430\u0440\u0430\u0446",
    "\u043f\u043e\u0434\u043f\u0438\u0441",
    "\u043f\u0435\u0447\u0430\u0442",
    "\u043f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u0435",
    "\u043e\u0431\u0440\u0430\u0437\u0435\u0446",
    "\u0443\u0447\u0430\u0441\u0442\u043d\u0438\u043a",
    "\u043a\u0430\u043d\u0434\u0438\u0434\u0430\u0442",
    "\u043e\u0444\u0435\u0440\u0442\u0430",
    "\u0446\u0435\u043d\u043e\u0432",
    "\u0444\u0438\u043d\u0430\u043d\u0441",
    "\u0430\u0434\u0440\u0435\u0441",
    "\u043a\u043e\u043d\u0442\u0430\u043a\u0442",
)


def normalize_text(value: str) -> str:
    value = html.unescape(value)
    value = value.replace("\xa0", " ")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[0-9a-zа-я]+", text.lower())
    return [token for token in tokens if len(token) >= 4 and token not in STOPWORDS]


def extract_docx_text(path: Path) -> str:
    paragraphs: list[str] = []
    with zipfile.ZipFile(path) as archive:
        document_xml = archive.read("word/document.xml")

    root = ElementTree.fromstring(document_xml)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

    for paragraph in root.findall(".//w:p", namespace):
        pieces = [
            node.text or ""
            for node in paragraph.findall(".//w:t", namespace)
            if node.text
        ]
        text = "".join(pieces).strip()
        if text:
            paragraphs.append(text)

    return normalize_text("\n".join(paragraphs))


def extract_pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "PDF extraction requires pypdf in the active Python environment. "
            "Use the app ingest report for PDFs or convert the file to DOCX/TXT."
        ) from exc

    reader = PdfReader(str(path))
    pages = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            pages.append(f"[page {index}]\n{text}")
    return normalize_text("\n\n".join(pages))


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return extract_docx_text(path)
    if suffix == ".pdf":
        return extract_pdf_text(path)
    if suffix in {".txt", ".md"}:
        return normalize_text(path.read_text(encoding="utf-8", errors="replace"))
    raise ValueError(f"Unsupported file type: {path}")


def looks_like_heading(line: str) -> bool:
    clean = line.strip().lstrip("\ufeff")
    if re.match(r"^#{1,6}\s+\S+", clean):
        return True
    clean = re.sub(r"^#{1,6}\s+", "", clean)
    if len(clean) < 4 or len(clean) > 180:
        return False
    if clean.endswith(".") and len(clean.split()) > 10:
        return False
    if re.match(r"^(\d+[\.\)]|[IVX]+[\.\)]|[А-Я]\))\s+", clean):
        return True
    letters = re.findall(r"[A-Za-zА-Яа-я]", clean)
    uppercase = re.findall(r"[A-ZА-Я]", clean)
    return bool(letters) and len(uppercase) / len(letters) > 0.72 and len(clean.split()) <= 12


def split_sections(text: str) -> list[Section]:
    lines = [line.strip() for line in text.splitlines()]
    sections: list[Section] = []
    current_title = "Документ"
    current_lines: list[str] = []

    for line in lines:
        raw_line = line.lstrip("\ufeff").strip()
        markdown_heading = re.match(r"^(#{1,6})\s+\S+", raw_line)
        is_nested_markdown_heading = (
            bool(markdown_heading)
            and len(markdown_heading.group(1)) >= 3
            and current_title != "Р”РѕРєСѓРјРµРЅС‚"
        )
        is_heading = looks_like_heading(raw_line) and not is_nested_markdown_heading
        line = re.sub(r"^#{1,6}\s+", "", raw_line).strip()
        if not line:
            if current_lines:
                current_lines.append("")
            continue
        if is_heading and current_lines:
            sections.append(Section(current_title, normalize_text("\n".join(current_lines))))
            current_title = line
            current_lines = []
        elif is_heading and not current_lines and current_title == "Документ":
            current_title = line
        else:
            current_lines.append(line)

    if current_lines:
        sections.append(Section(current_title, normalize_text("\n".join(current_lines))))

    return sections or [Section("Документ", text)]


def top_keywords(sections: Iterable[Section], limit: int = 80) -> list[str]:
    counts: Counter[str] = Counter()
    for section in sections:
        counts.update(section.words)
    return [word for word, _ in counts.most_common(limit)]


def section_topic_hit_count(section: Section) -> int:
    text = normalize_text(f"{section.title}\n{section.text}").lower()
    hits = 0
    for _, _, keywords in TOPIC_RULES:
        if any(keyword in text for keyword in keywords):
            hits += 1
    return hits


def is_content_section(section: Section) -> bool:
    title = normalize_text(section.title).lower()
    text = normalize_text(section.text).lower()
    combined = f"{title}\n{text}"
    word_count = len(section.words)
    topic_hit_count = section_topic_hit_count(section)
    has_content_hint = any(hint in combined for hint in CONTENT_SECTION_HINTS)
    has_non_content_title_hint = any(
        hint in title for hint in NON_CONTENT_TITLE_HINTS
    )

    if topic_hit_count >= 2 or has_content_hint:
        return True
    if word_count >= 160 and topic_hit_count >= 1:
        return True
    if has_non_content_title_hint and topic_hit_count == 0:
        return False
    if word_count < 45 and topic_hit_count == 0:
        return False
    if word_count < 90 and has_non_content_title_hint:
        return False
    return True


def content_sections(sections: list[Section]) -> list[Section]:
    filtered = [section for section in sections if is_content_section(section)]
    return filtered or sections


def score_overlap(reference_words: list[str], generated_words: list[str]) -> float:
    if not reference_words:
        return 1.0
    reference = Counter(reference_words)
    generated = Counter(generated_words)
    matched = sum(min(count, generated[word]) for word, count in reference.items())
    return matched / sum(reference.values())


def best_generated_match(reference: Section, generated_sections: list[Section]) -> tuple[Section, float]:
    if not generated_sections:
        return Section("Липсва", ""), 0.0
    reference_keywords = set(top_keywords([reference], limit=35))
    best = generated_sections[0]
    best_score = -1.0
    for candidate in generated_sections:
        candidate_keywords = set(top_keywords([candidate], limit=45))
        if not reference_keywords:
            score = 0.0
        else:
            score = len(reference_keywords & candidate_keywords) / len(reference_keywords)
        title_bonus = score_overlap(tokenize(reference.title), tokenize(candidate.title))
        score += title_bonus * 0.4
        if score > best_score:
            best = candidate
            best_score = score
    return best, max(0.0, min(1.0, best_score))


def find_tender_snippets(tender_text: str, keywords: list[str], limit: int = 3) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", tender_text) if p.strip()]
    scored: list[tuple[int, str]] = []
    for paragraph in paragraphs:
        normalized = paragraph.lower()
        score = sum(1 for keyword in keywords if keyword in normalized)
        if score:
            scored.append((score, paragraph))
    snippets = [
        text[:420].replace("\n", " ")
        for _, text in sorted(scored, key=lambda item: (-item[0], len(item[1])))[:limit]
    ]
    return snippets


def analyze_topic_coverage(
    reference_text: str,
    generated_text: str,
) -> list[dict[str, object]]:
    reference_normalized = normalize_text(reference_text).lower()
    generated_normalized = normalize_text(generated_text).lower()
    result: list[dict[str, object]] = []

    for key, label, keywords in TOPIC_RULES:
        reference_hits = [
            keyword for keyword in keywords if keyword in reference_normalized
        ]
        if not reference_hits:
            continue

        generated_hits = [
            keyword for keyword in keywords if keyword in generated_normalized
        ]
        if not generated_hits:
            status = "missing"
        elif len(generated_hits) < max(2, len(reference_hits) // 2):
            status = "partial"
        else:
            status = "covered"

        result.append(
            {
                "key": key,
                "label": label,
                "status": status,
                "reference_hits": reference_hits,
                "generated_hits": generated_hits,
                "missing_hits": [
                    keyword for keyword in reference_hits if keyword not in generated_hits
                ],
            }
        )

    return result


def render_topic_coverage_lines(
    reference_sections: list[Section],
    generated_sections: list[Section],
) -> list[str]:
    rows = analyze_topic_coverage(
        "\n\n".join(section.text for section in reference_sections),
        "\n\n".join(section.text for section in generated_sections),
    )
    lines = [
        "",
        "## Universal Topic Coverage",
        "",
        "| Topic | Status | Reference signals | Generated signals | Missing signals |",
        "| --- | --- | --- | --- | --- |",
    ]

    if not rows:
        lines.append("| n/a | no reference topic signals | n/a | n/a | n/a |")
        return lines

    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["label"]).replace("|", "\\|"),
                    str(row["status"]),
                    ", ".join(row["reference_hits"]).replace("|", "\\|"),
                    ", ".join(row["generated_hits"]).replace("|", "\\|") or "n/a",
                    ", ".join(row["missing_hits"]).replace("|", "\\|") or "n/a",
                ]
            )
            + " |"
        )
    return lines


def render_calibration_recommendation_lines(
    reference_sections: list[Section],
    generated_sections: list[Section],
) -> list[str]:
    rows = analyze_topic_coverage(
        "\n\n".join(section.text for section in reference_sections),
        "\n\n".join(section.text for section in generated_sections),
    )
    risky_rows = [
        row for row in rows if row.get("status") in {"missing", "partial"}
    ]
    lines = ["", "## Calibration Recommendations", ""]

    if not risky_rows:
        lines.append(
            "1. Universal topic coverage looks aligned. Focus calibration on "
            "section-level depth, source grounding, and final DOCX readiness."
        )
        return lines

    missing = [row for row in risky_rows if row.get("status") == "missing"]
    partial = [row for row in risky_rows if row.get("status") == "partial"]
    if missing:
        labels = ", ".join(str(row["label"]) for row in missing)
        signals = sorted(
            {
                str(signal)
                for row in missing
                for signal in row.get("missing_hits", [])
            }
        )
        lines.append(
            "1. Revisit outline extraction and drafting blueprint grouping for "
            f"missing topics: {labels}."
        )
        if signals:
            lines.append(
                "2. Confirm the tender checklist and grounding chunks include "
                "these missing signals: "
                + ", ".join(signals[:16])
                + "."
            )
        next_index = 3 if signals else 2
    else:
        next_index = 1

    if partial:
        labels = ", ".join(str(row["label"]) for row in partial)
        lines.append(
            f"{next_index}. Increase drafting depth and prompt specificity for "
            f"partially covered topics: {labels}."
        )
        next_index += 1

    lines.append(
        f"{next_index}. After regenerating the proposal, rerun DOCX readiness "
        "and this gap analysis to verify topic coverage, section depth, and "
        "requirement coverage together."
    )
    return lines


def coverage_label(coverage: float, length_ratio: float) -> str:
    if coverage >= 0.72 and length_ratio >= 0.65:
        return "добро"
    if coverage >= 0.45 or length_ratio >= 0.45:
        return "частично"
    return "слабо/липсва"


def render_report(
    tender_text: str,
    reference_sections: list[Section],
    generated_sections: list[Section],
    reference_path: Path,
    generated_path: Path,
    tender_paths: list[Path],
) -> str:
    raw_reference_count = len(reference_sections)
    raw_generated_count = len(generated_sections)
    reference_sections = content_sections(reference_sections)
    generated_sections = content_sections(generated_sections)

    lines: list[str] = [
        "# Анализ на пропуските в техническото предложение",
        "",
        "## Входни документи",
        "",
        f"- Реално/референтно ТП: `{reference_path}`",
        f"- Генерирано от приложението ТП: `{generated_path}`",
        *[f"- Тръжен/изходен документ: `{path}`" for path in tender_paths],
        "",
        "## Обобщение",
        "",
    ]

    reference_words = sum(len(section.words) for section in reference_sections)
    generated_words = sum(len(section.words) for section in generated_sections)
    lines.extend(
        [
            f"- Raw recognized sections in reference TP: `{raw_reference_count}`",
            f"- Raw recognized sections in generated TP: `{raw_generated_count}`",
            f"- Content sections compared in reference TP: `{len(reference_sections)}`",
            f"- Content sections compared in generated TP: `{len(generated_sections)}`",
        ]
    )
    lines.extend(
        [
            f"- Разпознати секции в референтното ТП: `{len(reference_sections)}`",
            f"- Разпознати секции в генерираното ТП: `{len(generated_sections)}`",
            f"- Word-like tokens в референтното ТП: `{reference_words}`",
            f"- Word-like tokens в генерираното ТП: `{generated_words}`",
            f"- Общ обемен коефициент: `{generated_words / reference_words:.2f}`"
            if reference_words
            else "- Общ обемен коефициент: `n/a`",
            "",
            "## Покритие по секции",
            "",
            "| Секция в референтното ТП | Най-близка секция в генерираното ТП | Покритие | Обем | Статус | Липсващи ключови термини |",
            "| --- | --- | ---: | ---: | --- | --- |",
        ]
    )

    section_coverage_start = next(
        index
        for index, line in enumerate(lines)
        if line.startswith("## ") and "Покритие" in line
    )
    lines[section_coverage_start:section_coverage_start] = (
        render_topic_coverage_lines(reference_sections, generated_sections)
        + render_calibration_recommendation_lines(
            reference_sections,
            generated_sections,
        )
        + [""]
    )

    detail_blocks: list[str] = []
    for index, reference in enumerate(reference_sections, start=1):
        generated, title_score = best_generated_match(reference, generated_sections)
        reference_keywords = top_keywords([reference], limit=35)
        generated_keywords = set(top_keywords([generated], limit=60))
        missing = [word for word in reference_keywords if word not in generated_keywords][:12]
        coverage = score_overlap(reference.words, generated.words)
        if title_score < 0.12:
            coverage *= 0.75
        length_ratio = len(generated.words) / max(1, len(reference.words))
        status = coverage_label(coverage, length_ratio)

        lines.append(
            "| "
            + " | ".join(
                [
                    reference.title.replace("|", "\\|")[:90],
                    generated.title.replace("|", "\\|")[:90],
                    f"{coverage:.2f}",
                    f"{length_ratio:.2f}",
                    status,
                    ", ".join(missing[:8]).replace("|", "\\|"),
                ]
            )
            + " |"
        )

        if status != "добро":
            snippets = find_tender_snippets(tender_text, missing, limit=3)
            detail_blocks.extend(
                [
                    "",
                    f"### {index}. {reference.title}",
                    "",
                    f"- Най-близка генерирана секция: `{generated.title}`",
                    f"- Покритие: `{coverage:.2f}`",
                    f"- Обемен коефициент: `{length_ratio:.2f}`",
                    f"- Липсващи/рискови термини: {', '.join(missing) if missing else 'n/a'}",
                ]
            )
            if snippets:
                detail_blocks.append("- Пасажи от тръжни/изходни документи, свързани с липсите:")
                detail_blocks.extend(f"  - {snippet}" for snippet in snippets)

    lines.extend(["", "## Високорискови пропуски", *detail_blocks])
    lines.extend(
        [
            "",
            "## Как да се чете отчетът",
            "",
            "- `Покритие` е лексикално припокриване спрямо секцията от спечелилото/референтното ТП.",
            "- `Обем` сравнява дължината на генерираната секция с дължината на референтната секция.",
            "- Ниско покритие плюс нисък обем обикновено значи не просто различна формулировка, а липсващи изисквания, слаб контекст, слаб outline или твърде малка целева дължина при drafting.",
            "- Пасажите от тръжните документи са ориентири за разследване; те не заместват проверка на ingest report-а и избраните grounding chunks в приложението.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare a winning/reference technical proposal with the proposal "
            "generated by the app and produce a Markdown gap report."
        )
    )
    parser.add_argument("--reference", required=True, type=Path, help="Winning/reference proposal DOCX/PDF/TXT/MD")
    parser.add_argument("--generated", required=True, type=Path, help="App-generated proposal DOCX/PDF/TXT/MD")
    parser.add_argument(
        "--tender",
        action="append",
        default=[],
        type=Path,
        help="Tender/source document. Can be passed multiple times.",
    )
    parser.add_argument("--out", required=True, type=Path, help="Output Markdown report path")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    reference_text = extract_text(args.reference)
    generated_text = extract_text(args.generated)
    tender_text = "\n\n".join(extract_text(path) for path in args.tender)

    report = render_report(
        tender_text=tender_text,
        reference_sections=split_sections(reference_text),
        generated_sections=split_sections(generated_text),
        reference_path=args.reference,
        generated_path=args.generated,
        tender_paths=args.tender,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, encoding="utf-8")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
