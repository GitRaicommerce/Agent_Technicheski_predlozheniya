"""
Детерминирани парсъри за PDF и DOCX.
Без LLM — само извличане на текст и chunking.
"""

from __future__ import annotations

import io
from typing import Any


def extract_chunks(content: bytes, filename: str) -> list[dict[str, Any]]:
    """
    Извлича текстови chunks от PDF или DOCX файл.
    Връща list от dict с полета: type, text, page, section_path.
    """
    filename_lower = filename.lower()
    if filename_lower.endswith(".pdf"):
        return _extract_pdf(content)
    elif filename_lower.endswith(".docx"):
        return _extract_docx(content)
    else:
        # Опит за OCR при неизвестен тип
        return _extract_ocr(content)


def _extract_pdf(content: bytes) -> list[dict[str, Any]]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content))
    chunks = []
    for page_num, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if not text.strip():
            # Fallback to OCR
            text = _ocr_page_image(page)

        for para in _split_paragraphs(text):
            if para.strip():
                chunks.append(
                    {
                        "type": "text",
                        "text": para.strip(),
                        "page": page_num,
                        "section_path": None,
                    }
                )
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
            text
            if chunk_type == "heading"
            else (current_section[-1] if current_section else None)
        )

        if chunk_type == "heading":
            current_section = [text]

        chunks.append(
            {
                "type": chunk_type,
                "text": text,
                "page": None,
                "section_path": section_path,
            }
        )

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
        from pypdf import PdfReader

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
