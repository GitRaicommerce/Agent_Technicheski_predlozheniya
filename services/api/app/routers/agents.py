"""
Agents router — оркестратор endpoint.
Всички LLM агенти се извикват тук чрез оркестратора.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any
import uuid
import structlog
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.database import get_db
from app.core.models import Project

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)
log = structlog.get_logger()


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
    from app.core.llm_gateway import LLMNotConfiguredError

    try:
        result = await run_orchestrator(
            project=project,
            message=req.message,
            history=req.history,
            db=db,
        )
    except LLMNotConfiguredError as exc:
        result = {
            "schema_version": "v1.3",
            "status": "needs_user_action",
            "trace_id": "",
            "assistant_message": (
                "⚙️ **LLM не е конфигуриран.** "
                "Добавете `OPENAI_API_KEY` (или `ANTHROPIC_API_KEY`) в `.env` файла "
                "и рестартирайте контейнерите с `docker compose up -d --build`."
            ),
            "ui_actions": [],
            "questions_to_user": [],
            "agent_called": None,
        }
        log.warning("llm_not_configured", error=str(exc))
    except Exception as exc:
        result = {
            "schema_version": "v1.3",
            "status": "error",
            "trace_id": "",
            "assistant_message": f"⚠ Грешка при генерирането: {exc}",
            "ui_actions": [],
            "questions_to_user": [],
            "agent_called": None,
        }
        log.error("orchestrator_unexpected_error", error=str(exc))
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


@router.post("/{project_id}/outline/unlock")
async def unlock_outline(
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
    outline.status_locked = False
    return {"status": "unlocked", "outline_id": outline_id}


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


@router.post("/{project_id}/schedule/unlock")
async def unlock_schedule(
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
    schedule.status_locked = False
    return {"status": "unlocked", "schedule_id": schedule_id}


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
    return {"status": "selected", "generation_id": generation_id}


class ScheduleNormalizedResponse(BaseModel):
    id: str
    schedule_json: dict
    status_locked: bool
    version: int

    model_config = {"from_attributes": True}


@router.get("/{project_id}/schedule", response_model=ScheduleNormalizedResponse)
async def get_schedule(project_id: str, db: AsyncSession = Depends(get_db)):
    """Връща последния нормализиран график за проекта."""
    from app.core.models import ScheduleNormalized
    from sqlalchemy import select

    result = await db.execute(
        select(ScheduleNormalized)
        .where(ScheduleNormalized.project_id == project_id)
        .order_by(ScheduleNormalized.version.desc())
        .limit(1)
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return schedule


# ---------------------------------------------------------------------------
# GET /api/v1/agents/{project_id}/generations
# ---------------------------------------------------------------------------

class GenerationResponse(BaseModel):
    id: str
    section_uid: str
    variant: int
    text: str
    evidence_map_json: dict | None = None
    used_sources_json: dict | None = None
    flags_json: dict | None = None
    evidence_status: str
    selected: bool
    created_at: str
    trace_id: str | None = None

    model_config = {"from_attributes": True}


class SectionGenerations(BaseModel):
    section_uid: str
    section_title: str | None = None
    variants: list[GenerationResponse]


@router.get("/{project_id}/generations", response_model=list[SectionGenerations])
async def list_generations(project_id: str, db: AsyncSession = Depends(get_db)):
    """
    Връща всички генерации за проекта, групирани по section_uid.
    Сортирани: selected DESC, variant ASC, created_at DESC.
    """
    from app.core.models import Generation, TpOutline
    from sqlalchemy import select

    # Load section titles from the latest outline (best-effort)
    outline_result = await db.execute(
        select(TpOutline)
        .where(TpOutline.project_id == project_id)
        .order_by(TpOutline.version.desc())
        .limit(1)
    )
    outline = outline_result.scalar_one_or_none()

    section_title_map: dict[str, str] = {}
    if outline:
        sections = outline.outline_json.get("sections", outline.outline_json.get("outline", []))

        def _collect(secs: list) -> None:
            for s in secs:
                uid = s.get("uid") or s.get("section_uid", "")
                if uid:
                    section_title_map[uid] = s.get("title", "")
                _collect(s.get("subsections", s.get("children", [])))

        _collect(sections)

    gen_result = await db.execute(
        select(Generation)
        .where(Generation.project_id == project_id)
        .order_by(
            Generation.section_uid,
            Generation.selected.desc(),
            Generation.variant.asc(),
            Generation.created_at.desc(),
        )
    )
    generations = gen_result.scalars().all()

    # Group by section_uid preserving order
    grouped: dict[str, list[Generation]] = {}
    for g in generations:
        grouped.setdefault(g.section_uid, []).append(g)

    result = []
    for section_uid, variants in grouped.items():
        result.append(
            SectionGenerations(
                section_uid=section_uid,
                section_title=section_title_map.get(section_uid),
                variants=[
                    GenerationResponse(
                        id=v.id,
                        section_uid=v.section_uid,
                        variant=v.variant,
                        text=v.text,
                        evidence_map_json=v.evidence_map_json,
                        used_sources_json=v.used_sources_json,
                        flags_json=v.flags_json,
                        evidence_status=v.evidence_status,
                        selected=v.selected,
                        created_at=v.created_at.isoformat(),
                        trace_id=v.trace_id,
                    )
                    for v in variants
                ],
            )
        )
    return result


# ---------------------------------------------------------------------------
# POST /{project_id}/sections/{section_uid}/regenerate
# ---------------------------------------------------------------------------


class RegenerateResponse(BaseModel):
    generation_ids: dict[str, str]
    trace_id: str


@router.post(
    "/{project_id}/sections/{section_uid}/regenerate",
    response_model=RegenerateResponse,
)
async def regenerate_section(
    project_id: str,
    section_uid: str,
    db: AsyncSession = Depends(get_db),
) -> RegenerateResponse:
    """
    Тригерира пълен drafting pipeline (examples→legislation→drafting→verifier)
    за конкретен раздел и връща generation_ids на новите варианти.
    """
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Load the latest outline to resolve section title + requirements
    from sqlalchemy import select
    from app.core.models import TpOutline

    outline_res = await db.execute(
        select(TpOutline)
        .where(TpOutline.project_id == project_id)
        .order_by(TpOutline.version.desc())
        .limit(1)
    )
    outline = outline_res.scalar_one_or_none()

    section_title = section_uid
    section_requirements: list[str] = []

    if outline:
        def _find(secs: list) -> bool:
            for s in secs:
                uid = s.get("uid") or s.get("section_uid", "")
                if uid == section_uid:
                    nonlocal section_title, section_requirements
                    section_title = s.get("title", section_uid)
                    section_requirements = s.get("requirements", [])
                    return True
                if _find(s.get("subsections", s.get("children", []))):
                    return True
            return False

        sections = outline.outline_json.get(
            "sections", outline.outline_json.get("outline", [])
        )
        _find(sections)

    from app.agents.orchestrator import _run_drafting_pipeline

    trace_id = str(uuid.uuid4())
    result = await _run_drafting_pipeline(
        project_id=project_id,
        params={
            "section_uid": section_uid,
            "section_title": section_title,
            "section_requirements": section_requirements,
        },
        db=db,
        trace_id=trace_id,
    )

    generation_ids: dict[str, str] = result.get("generation_ids") or {}
    return RegenerateResponse(generation_ids=generation_ids, trace_id=trace_id)
