from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.models import Project, Generation, TpOutline
from app.agents.proposal_quality import assess_generation_depth

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


def _duplicate_selected_sections(generations: list[Generation]) -> list[dict]:
    grouped: dict[str, list[Generation]] = {}
    for generation in generations:
        grouped.setdefault(generation.section_uid, []).append(generation)

    return [
        {
            "section_uid": section_uid,
            "selected_count": len(section_generations),
            "generation_ids": [generation.id for generation in section_generations],
        }
        for section_uid, section_generations in grouped.items()
        if len(section_generations) > 1
    ]


def _walk_outline_sections(sections: list[dict]):
    for section in sections:
        yield section
        children = section.get("subsections") or section.get("children") or []
        yield from _walk_outline_sections(children)


async def _load_outline_requirement_counts(project_id: str, db: AsyncSession) -> dict[str, int]:
    result = await db.execute(
        select(TpOutline)
        .where(TpOutline.project_id == project_id)
        .order_by(TpOutline.version.desc())
        .limit(1)
    )
    outline = result.scalar_one_or_none()
    if not outline:
        return {}

    sections = outline.outline_json.get("sections", outline.outline_json.get("outline", []))
    counts: dict[str, int] = {}
    for section in _walk_outline_sections(sections):
        section_uid = section.get("uid") or section.get("section_uid")
        if not section_uid:
            continue

        checklist_items = section.get("requirement_checklist_items")
        requirement_ids = section.get("requirement_ids")
        requirements = section.get("requirements")
        if isinstance(checklist_items, list) and checklist_items:
            counts[section_uid] = len(checklist_items)
        elif isinstance(requirement_ids, list) and requirement_ids:
            counts[section_uid] = len(requirement_ids)
        elif isinstance(requirements, list) and requirements:
            counts[section_uid] = len(requirements)
    return counts


def _quality_review_issue(
    generation: Generation,
    outline_requirement_counts: dict[str, int],
) -> dict | None:
    flags = generation.flags_json or {}
    coverage = flags.get("requirement_coverage") if isinstance(flags, dict) else None
    if not isinstance(coverage, dict):
        requirement_count = outline_requirement_counts.get(generation.section_uid, 0)
        if requirement_count <= 0:
            return None
        coverage = {"total": requirement_count, "missing_ids": []}

    missing_ids = coverage.get("missing_ids")
    if isinstance(missing_ids, list) and missing_ids:
        return None

    assessment = assess_generation_depth(generation.text or "", coverage)
    if assessment["status"] == "ok":
        return None

    return {
        "section_uid": generation.section_uid,
        "generation_id": generation.id,
        "word_count": assessment["word_count"],
        "sentence_count": assessment["sentence_count"],
        "requirement_count": assessment["requirement_count"],
        "min_words": assessment["min_words"],
        "min_sentences": assessment["min_sentences"],
        "issues": assessment["issues"],
    }


@router.get("/{project_id}/docx")
async def export_docx(project_id: str, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    selected_result = await db.execute(
        select(Generation).where(
            Generation.project_id == project_id,
            Generation.selected.is_(True),
        )
    )
    selected_generations = selected_result.scalars().all()

    duplicate_sections = _duplicate_selected_sections(selected_generations)
    if duplicate_sections:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Pre-export check failed: some sections have multiple selected generated variants.",
                "duplicate_selected_sections": duplicate_sections,
                "duplicate_selected_count": len(duplicate_sections),
            },
        )

    stale = [
        generation
        for generation in selected_generations
        if generation.evidence_status == "stale"
    ]
    if stale:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Pre-export check failed: some selected sections have stale evidence.",
                "stale_sections": [g.section_uid for g in stale],
            },
        )

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

    outline_requirement_counts = (
        await _load_outline_requirement_counts(project_id, db)
        if selected_generations
        else {}
    )
    quality_sections = [
        issue
        for generation in selected_generations
        if (issue := _quality_review_issue(generation, outline_requirement_counts))
    ]
    if quality_sections:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Pre-export check failed: some selected sections are too short for their mapped tender requirements.",
                "quality_sections": quality_sections,
                "quality_section_count": len(quality_sections),
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
