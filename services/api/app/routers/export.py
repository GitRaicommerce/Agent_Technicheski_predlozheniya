from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.models import Project, Generation, TpOutline, ScheduleNormalized

router = APIRouter()


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

    from app.export.docx_generator import generate_docx

    docx_bytes = await generate_docx(project_id=project_id, db=db)

    filename = f"TP_{project.name[:50].replace(' ', '_')}.docx"
    return StreamingResponse(
        iter([docx_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
