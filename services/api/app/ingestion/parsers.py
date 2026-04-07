"""
Парсъри за PDF, DOCX и Markdown.
Използва markitdown (Microsoft) като primary метод — запазва структурата
(заглавия, таблици, списъци) в Markdown формат преди chunking.
Fallback към директно pypdf/python-docx при грешка.
"""

from __future__ import annotations

import io
import re
from typing import Any


def extract_chunks(content: bytes, filename: str) -> list[dict[str, Any]]:
    """
    Извлича текстови chunks от PDF, DOCX или Markdown файл.
    Опитва markitdown first (по-добра структурна вярност),
    след това fallback към нативните парсъри.
    Връща list от dict с полета: type, text, page, section_path.
    """
    filename_lower = filename.lower()

    # Markdown — директно chunking без конвертиране
    if filename_lower.endswith((".md", ".txt")):
        text = content.decode("utf-8", errors="replace")
        return _chunks_from_markdown(text)

    # PDF/DOCX — опитай markitdown първо
    md_text = _to_markdown_via_markitdown(content, filename)
    if md_text:
        return _chunks_from_markdown(md_text)

    # Fallback към нативните парсъри
    if filename_lower.endswith(".pdf"):
        return _extract_pdf(content)
    elif filename_lower.endswith(".docx"):
        return _extract_docx(content)
    else:
        return _extract_ocr(content)


# ---------------------------------------------------------------------------
# markitdown conversion
# ---------------------------------------------------------------------------

def _to_markdown_via_markitdown(content: bytes, filename: str) -> str:
    """
    Конвертира файл до Markdown с Microsoft markitdown.
    Запазва заглавия, таблици и списъци.
    Връща празен стринг при грешка (→ fallback).
    """
    try:
        from markitdown import MarkItDown
        import tempfile, os

        # markitdown работи с файлове на диска
        suffix = "." + filename.rsplit(".", 1)[-1] if "." in filename else ".bin"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            md = MarkItDown()
            result = md.convert(tmp_path)
            return result.text_content or ""
        finally:
            os.unlink(tmp_path)
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Chunking from Markdown
# ---------------------------------------------------------------------------

def _chunks_from_markdown(md_text: str) -> list[dict[str, Any]]:
    """
    Разделя Markdown текст на смислени chunks, запазвайки section_path.
    Заглавия (# / ##) стават тип 'heading' и определят section_path.
    Таблици, списъци и абзаци → тип 'text'.
    """
    chunks: list[dict[str, Any]] = []
    current_section: str | None = None
    buffer_lines: list[str] = []
    page_counter = 0  # estimated — Markdown няма реални страници

    def _flush(section: str | None) -> None:
        nonlocal page_counter
        text = "\n".join(buffer_lines).strip()
        if len(text) >= 20:
            chunks.append({
                "type": "text",
                "text": text,
                "page": page_counter or None,
                "section_path": section,
            })
        buffer_lines.clear()

    lines = md_text.splitlines()
    i = 0
    in_table = False

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Page break hint (markitdown вмъква \f или <!-- Page --> при PDF)
        if stripped in ("\f", "<!-- Page -->") or stripped.startswith("<!-- Page "):
            _flush(current_section)
            page_counter += 1
            i += 1
            continue

        # Headings
        heading_match = re.match(r"^(#{1,4})\s+(.*)", stripped)
        if heading_match:
            _flush(current_section)
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()
            current_section = title
            chunks.append({
                "type": "heading",
                "text": title,
                "page": page_counter or None,
                "section_path": title,
            })
            i += 1
            continue

        # Tables — collect entire table as one chunk
        if stripped.startswith("|"):
            if not in_table:
                _flush(current_section)
                in_table = True
            buffer_lines.append(line)
            i += 1
            # Check if next line continues the table
            if i < len(lines) and lines[i].strip().startswith("|"):
                continue
            else:
                in_table = False
                _flush(current_section)
            continue

        # Blank line → flush current paragraph
        if not stripped:
            _flush(current_section)
            i += 1
            continue

        # Regular text / list items
        buffer_lines.append(stripped)
        i += 1

    _flush(current_section)
    return chunks


# ---------------------------------------------------------------------------
# Fallback parsers (kept for reliability)
# ---------------------------------------------------------------------------

def _extract_pdf(content: bytes) -> list[dict[str, Any]]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content))
    chunks = []
    for page_num, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if not text.strip():
            text = _ocr_page_image(page)

        for para in _split_paragraphs(text):
            if para.strip():
                chunks.append({
                    "type": "text",
                    "text": para.strip(),
                    "page": page_num,
                    "section_path": None,
                })
    return chunks


def _extract_docx(content: bytes) -> list[dict[str, Any]]:
    from docx import Document

    doc = Document(io.BytesIO(content))
    chunks = []
    current_section: list[str] = []

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue

        style_name = para.style.name.lower()
        chunk_type = "heading" if "heading" in style_name else "text"
        section_path = (
            text if chunk_type == "heading"
            else (current_section[-1] if current_section else None)
        )

        if chunk_type == "heading":
            current_section = [text]

        chunks.append({
            "type": chunk_type,
            "text": text,
            "page": None,
            "section_path": section_path,
        })

    for table in doc.tables:
        section_path = current_section[-1] if current_section else None
        for row in table.rows:
            cell_texts = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cell_texts:
                chunks.append({
                    "type": "table_row",
                    "text": " | ".join(cell_texts),
                    "page": None,
                    "section_path": section_path,
                })
    return chunks


def _extract_ocr(content: bytes) -> list[dict[str, Any]]:
    """OCR fallback с Tesseract (Bulgarian + English)."""
    try:
        import pytesseract
        from PIL import Image

        image = Image.open(io.BytesIO(content))
        text = pytesseract.image_to_string(image, lang="bul+eng")
        return [
            {"type": "text", "text": para.strip(), "page": 1, "section_path": None}
            for para in _split_paragraphs(text)
            if para.strip()
        ]
    except Exception:
        return []


def _ocr_page_image(page) -> str:
    """OCR на PDF страница при липса на текстов слой."""
    try:
        import pytesseract
        from PIL import Image

        for image_obj in page.images:
            img = Image.open(io.BytesIO(image_obj.data))
            return pytesseract.image_to_string(img, lang="bul+eng")
    except Exception:
        pass
    return ""


def _split_paragraphs(text: str, min_length: int = 20) -> list[str]:
    """Разделя текст на параграфи по двойни нови редове."""
    paragraphs = text.split("\n\n")
    result = []
    for p in paragraphs:
        p = p.replace("\n", " ").strip()
        if len(p) >= min_length:
            result.append(p)
    return result
