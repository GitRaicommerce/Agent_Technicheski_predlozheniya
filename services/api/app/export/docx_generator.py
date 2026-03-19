"""
DOCX генератор за експорт на Технически предложения.
Evidence/sources НЕ се включват в exported документа.
"""

from __future__ import annotations

import io
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Project, Generation, TpOutline, ScheduleNormalized


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

    # Раздел "ЛИНЕЕН ГРАФИК" от нормализирания график
    sched_result = await db.execute(
        select(ScheduleNormalized)
        .where(ScheduleNormalized.project_id == project_id)
        .order_by(ScheduleNormalized.version.desc())
        .limit(1)
    )
    schedule_norm = sched_result.scalar_one_or_none()
    if schedule_norm:
        doc.add_page_break()
        sched_heading = doc.add_heading(level=2)
        sched_heading.text = "ЛИНЕЕН ГРАФИК"
        _write_schedule_section(doc, schedule_norm.schedule_json)

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def _write_schedule_section(doc, schedule_json: dict) -> None:
    """Форматира задачите от нормализирания график в .docx таблица."""
    tasks = schedule_json.get("tasks", schedule_json.get("normalized", {}).get("tasks", []))
    resources = schedule_json.get("resources", schedule_json.get("normalized", {}).get("resources", []))

    if not tasks:
        doc.add_paragraph("[Графикът не съдържа задачи.]")
        return

    # Обобщение
    doc.add_paragraph(f"Общо задачи: {len(tasks)}   |   Ресурси: {len(resources)}")

    # Таблица: задача / продължителност / начало / край
    table = doc.add_table(rows=1, cols=4)
    table.style = "Table Grid"
    hdr = table.rows[0].cells
    hdr[0].text = "Задача"
    hdr[1].text = "Продължителност (дни)"
    hdr[2].text = "Начало"
    hdr[3].text = "Край"

    for task in tasks:
        row = table.add_row().cells
        row[0].text = str(task.get("name", "") or "")
        row[1].text = str(task.get("duration_days", task.get("duration", "")) or "")
        row[2].text = str(task.get("start", "") or "")
        row[3].text = str(task.get("finish", task.get("end", "")) or "")


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
            .order_by(
                Generation.selected.desc(),   # закрепен от потребителя
                Generation.variant.asc(),     # вариант 1 преди 2
                Generation.created_at.desc(),
            )
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
