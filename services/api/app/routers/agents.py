"""
Agents router — оркестратор endpoint.
Всички LLM агенти се извикват тук чрез оркестратора.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.database import get_db
from app.core.models import Project

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


class ChatMessage(BaseModel):
    role: str  # user|assistant
    content: str


class OrchestratorRequest(BaseModel):
    project_id: str
    message: str
    history: list[ChatMessage] = []


@router.post("/chat")
@limiter.limit("20/minute")
async def orchestrator_chat(
    request: Request,
    req: OrchestratorRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    project = await db.get(Project, req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    from app.agents.orchestrator import run_orchestrator

    result = await run_orchestrator(
        project=project,
        message=req.message,
        history=req.history,
        db=db,
    )
    return result


@router.post("/{project_id}/outline/lock")
async def lock_outline(
    project_id: str, outline_id: str, db: AsyncSession = Depends(get_db)
):
    from app.core.models import TpOutline
    from sqlalchemy import select

    result = await db.execute(
        select(TpOutline).where(
            TpOutline.id == outline_id, TpOutline.project_id == project_id
        )
    )
    outline = result.scalar_one_or_none()
    if not outline:
        raise HTTPException(status_code=404, detail="Outline not found")
    outline.status_locked = True
    from datetime import datetime, timezone

    outline.approved_at = datetime.now(timezone.utc)
    return {"status": "locked", "outline_id": outline_id}


@router.post("/{project_id}/schedule/lock")
async def lock_schedule(
    project_id: str, schedule_id: str, db: AsyncSession = Depends(get_db)
):
    from app.core.models import ScheduleNormalized
    from sqlalchemy import select

    result = await db.execute(
        select(ScheduleNormalized).where(
            ScheduleNormalized.id == schedule_id,
            ScheduleNormalized.project_id == project_id,
        )
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    schedule.status_locked = True
    from datetime import datetime, timezone

    schedule.approved_at = datetime.now(timezone.utc)
    return {"status": "locked", "schedule_id": schedule_id}


class TpOutlineResponse(BaseModel):
    id: str
    outline_json: dict
    status_locked: bool
    version: int

    model_config = {"from_attributes": True}


@router.get("/{project_id}/outline", response_model=TpOutlineResponse)
async def get_outline(project_id: str, db: AsyncSession = Depends(get_db)):
    """Връща последния (най-нов) outline за проекта."""
    from app.core.models import TpOutline
    from sqlalchemy import select

    result = await db.execute(
        select(TpOutline)
        .where(TpOutline.project_id == project_id)
        .order_by(TpOutline.version.desc())
        .limit(1)
    )
    outline = result.scalar_one_or_none()
    if not outline:
        raise HTTPException(status_code=404, detail="Outline not found")
    return outline


@router.post("/{project_id}/generations/{generation_id}/select")
async def select_generation(
    project_id: str, generation_id: str, db: AsyncSession = Depends(get_db)
):
    """Закрепва конкретна генерация като предпочитана за раздела в .docx."""
    from app.core.models import Generation
    from sqlalchemy import update

    gen = await db.get(Generation, generation_id)
    if not gen or gen.project_id != project_id:
        raise HTTPException(status_code=404, detail="Generation not found")

    # Отмаркираме всички останали за същия раздел
    await db.execute(
        update(Generation)
        .where(
            Generation.project_id == project_id,
            Generation.section_uid == gen.section_uid,
        )
        .values(selected=False)
    )
    gen.selected = True
    return {
        "status": "ok",
        "generation_id": generation_id,
        "section_uid": gen.section_uid,
    }
