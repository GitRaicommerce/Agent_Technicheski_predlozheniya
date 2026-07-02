from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.models import Project, Generation, TpOutline, ScheduleNormalized

router = APIRouter()


def _missing_requirement_coverage(generation: Generation) -> dict | None:
    flags = generation.flags_json or {}
    if not isinstance(flags, dict):
        return None

    coverage = flags.get("requirement_coverage")
    if not isinstance(coverage, dict):
        return None

    missing_ids = coverage.get("missing_ids")
    if not isinstance(missing_ids, list) or not missing_ids:
        return None

    items = coverage.get("items")
    missing_items = []
    if isinstance(items, list):
        missing_ids_set = {str(item) for item in missing_ids}
        missing_items = [
            {
                "id": str(item.get("id")),
                "text": item.get("text"),
                "importance": item.get("importance"),
            }
            for item in items
            if isinstance(item, dict) and str(item.get("id")) in missing_ids_set
        ]

    return {
        "section_uid": generation.section_uid,
        "generation_id": generation.id,
        "missing_requirement_ids": [str(item) for item in missing_ids],
        "missing_count": len(missing_ids),
        "missing_items": missing_items,
    }


@router.get("/{project_id}/docx")
async def export_docx(project_id: str, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Pre-export check
    result = await db.execute(
        select(Generation).where(
            Generation.project_id == project_id,
            Generation.evidence_status == "stale",
        )
    )
    stale = result.scalars().all()
    if stale:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Pre-export check failed: some sections have stale evidence.",
                "stale_sections": [g.section_uid for g in stale],
            },
        )

    coverage_result = await db.execute(
        select(Generation).where(
            Generation.project_id == project_id,
            Generation.selected.is_(True),
        )
    )
    selected_generations = coverage_result.scalars().all()
    missing_requirement_sections = [
        issue
        for generation in selected_generations
        if (issue := _missing_requirement_coverage(generation))
    ]
    if missing_requirement_sections:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Pre-export check failed: some selected sections do not cover all tender requirements.",
                "missing_requirement_sections": missing_requirement_sections,
                "missing_requirement_count": sum(
                    section["missing_count"] for section in missing_requirement_sections
                ),
            },
        )

    from urllib.parse import quote
    from app.export.docx_generator import generate_docx

    docx_bytes = await generate_docx(project_id=project_id, db=db)

    safe_name = project.name[:50].replace(" ", "_")
    ascii_name = safe_name.encode("ascii", "replace").decode("ascii")
    utf8_encoded = quote(safe_name, safe="")
    filename = f"TP_{ascii_name}.docx"
    filename_star = f"UTF-8''{utf8_encoded}.docx"
    return StreamingResponse(
        iter([docx_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"; filename*={filename_star}'},
    )
