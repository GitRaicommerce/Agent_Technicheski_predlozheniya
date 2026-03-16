"""
DOCX генератор за експорт на Технически предложения.
Evidence/sources НЕ се включват в exported документа.
"""

from __future__ import annotations

import io
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Project, Generation, TpOutline


async def generate_docx(project_id: str, db: AsyncSession) -> bytes:
    """
    Генерира .docx от заключената структура и генерираните текстове.
    Evidence не се включва в документа.
    """
    from docx import Document
    from docx.shared import Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    project = await db.get(Project, project_id)

    # Взима последния заключен outline
    result = await db.execute(
        select(TpOutline)
        .where(TpOutline.project_id == project_id, TpOutline.status_locked == True)
        .order_by(TpOutline.version.desc())
        .limit(1)
    )
    outline = result.scalar_one_or_none()

    doc = Document()
    doc.core_properties.author = "TP AI"
    doc.core_properties.title = f"Техническо предложение — {project.name}"

    # Заглавие
    title = doc.add_heading(level=1)
    title.text = f"ТЕХНИЧЕСКО ПРЕДЛОЖЕНИЕ\n{project.name}"
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    if project.location:
        doc.add_paragraph(f"Местоположение: {project.location}")
    if project.contracting_authority:
        doc.add_paragraph(f"Възложител: {project.contracting_authority}")

    doc.add_page_break()

    if outline:
        sections = outline.outline_json.get(
            "sections", outline.outline_json.get("outline", [])
        )
        await _write_sections(doc, sections, project_id, db, level=2)
    else:
        doc.add_paragraph("⚠ Структурата на ТП не е заключена.")

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


async def _write_sections(
    doc, sections: list, project_id: str, db: AsyncSession, level: int
):
    from sqlalchemy import select
    from app.core.models import Generation

    for section in sections:
        section_uid = section.get("section_uid", "")
        title = section.get("title", "")
        numbering = section.get("display_numbering", "")

        heading = doc.add_heading(level=min(level, 9))
        heading.text = f"{numbering} {title}".strip()

        # Текст от генерацията (ако има)
        result = await db.execute(
            select(Generation)
            .where(
                Generation.project_id == project_id,
                Generation.section_uid == section_uid,
            )
            .order_by(Generation.created_at.desc())
            .limit(1)
        )
        generation = result.scalar_one_or_none()

        if generation:
            # Evidence НЕ се включва в .docx
            doc.add_paragraph(generation.text)
        else:
            p = doc.add_paragraph("[Текстът за тази точка не е генериран.]")

        children = section.get("children", [])
        if children:
            await _write_sections(doc, children, project_id, db, level=level + 1)
