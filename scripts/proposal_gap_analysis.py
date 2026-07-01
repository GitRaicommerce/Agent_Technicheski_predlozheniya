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
        is_heading = looks_like_heading(raw_line)
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
