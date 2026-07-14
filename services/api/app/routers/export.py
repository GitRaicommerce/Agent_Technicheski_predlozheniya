from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.models import Project, Generation, TpOutline
from app.agents.proposal_quality import assess_generation_depth
from app.export.readiness_report import render_export_readiness_report

router = APIRouter()


def _missing_requirement_reason(item: dict) -> str:
    matched_terms = item.get("matched_terms")
    coherent_terms = item.get("coherent_matched_terms")
    operational_signals = item.get("operational_signals")
    required_match_count = item.get("required_match_count")
    required_coherent_match_count = item.get("required_coherent_match_count")
    required_operational_signal_count = item.get("required_operational_signal_count")
    distinctive_matches = item.get("distinctive_matches")
    required_distinctive_count = item.get("required_distinctive_count")

    matched_count = len(matched_terms) if isinstance(matched_terms, list) else 0
    coherent_count = len(coherent_terms) if isinstance(coherent_terms, list) else 0
    operational_count = (
        len(operational_signals) if isinstance(operational_signals, list) else 0
    )
    distinctive_count = (
        len(distinctive_matches) if isinstance(distinctive_matches, list) else 0
    )

    if (
        item.get("requires_operational_detail")
        and isinstance(required_operational_signal_count, int)
        and operational_count < required_operational_signal_count
    ):
        return "needs operational evidence"
    if (
        isinstance(required_coherent_match_count, int)
        and coherent_count < required_coherent_match_count
    ):
        return "needs coherent passage"
    if (
        isinstance(required_distinctive_count, int)
        and distinctive_count < required_distinctive_count
    ):
        return "missing distinctive requirement detail"
    if isinstance(required_match_count, int) and matched_count < required_match_count:
        return "missing key terms"
    return "missing requirement coverage"


def _missing_requirement_remediation_guidance(item: dict) -> str:
    requirement_id = str(item.get("id") or "n/a")
    guidance = [
        f"Regenerate or edit the selected section so `{requirement_id}` has a "
        "dedicated paragraph or bullet that explicitly answers the requirement"
    ]

    missing_terms = [
        str(term)
        for term in item.get("missing_terms") or []
        if term
    ]
    if missing_terms:
        guidance.append(
            "include the missing concepts: " + ", ".join(missing_terms[:8])
        )

    distinctive_terms = [
        str(term)
        for term in item.get("distinctive_terms") or []
        if term
    ]
    distinctive_matches = [
        str(term)
        for term in item.get("distinctive_matches") or []
        if term
    ]
    required_distinctive_count = item.get("required_distinctive_count")
    if (
        isinstance(required_distinctive_count, int)
        and required_distinctive_count > 0
        and len(distinctive_matches) < required_distinctive_count
    ):
        guidance.append(
            "include distinctive requirement details such as "
            + ", ".join(distinctive_terms[:8])
        )

    coherent_terms = [
        str(term)
        for term in item.get("coherent_matched_terms") or []
        if term
    ]
    required_coherent_count = item.get("required_coherent_match_count")
    if (
        isinstance(required_coherent_count, int)
        and required_coherent_count > 0
        and len(coherent_terms) < required_coherent_count
    ):
        guidance.append(
            "keep the requirement concepts together in one coherent passage"
        )

    operational_signals = [
        str(signal)
        for signal in item.get("operational_signals") or []
        if signal
    ]
    required_operational_count = item.get("required_operational_signal_count")
    if (
        item.get("requires_operational_detail")
        and isinstance(required_operational_count, int)
        and required_operational_count > 0
        and len(operational_signals) < required_operational_count
    ):
        guidance.append(
            "add operational evidence such as responsible roles, sequence, "
            "controls, records, acceptance evidence, escalation, or corrective actions"
        )

    return "; ".join(guidance) + "."


def _missing_requirement_coverage(generation: Generation) -> dict | None:
    raw_flags = getattr(generation, "flags_json", None)
    flags = raw_flags if isinstance(raw_flags, dict) else {}

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
                "reason": _missing_requirement_reason(item),
                "remediation_guidance": _missing_requirement_remediation_guidance(
                    item
                ),
                "missing_terms": item.get("missing_terms") or [],
                "matched_terms": item.get("matched_terms") or [],
                "required_match_count": item.get("required_match_count"),
                "distinctive_terms": item.get("distinctive_terms") or [],
                "distinctive_matches": item.get("distinctive_matches") or [],
                "required_distinctive_count": item.get(
                    "required_distinctive_count"
                ),
                "coherent_matched_terms": item.get("coherent_matched_terms") or [],
                "required_coherent_match_count": item.get(
                    "required_coherent_match_count"
                ),
                "matched_ratio": item.get("matched_ratio"),
                "coherent_matched_ratio": item.get("coherent_matched_ratio"),
                "operational_signals": item.get("operational_signals") or [],
                "required_operational_signal_count": item.get(
                    "required_operational_signal_count"
                ),
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


def _outline_requirement_count(section: dict) -> int:
    checklist_items = section.get("requirement_checklist_items")
    requirement_ids = section.get("requirement_ids")
    requirements = section.get("requirements")
    if isinstance(checklist_items, list) and checklist_items:
        return len(checklist_items)
    if isinstance(requirement_ids, list) and requirement_ids:
        return len(requirement_ids)
    if isinstance(requirements, list) and requirements:
        return len(requirements)
    return 0


async def _load_outline_section_metadata(
    project_id: str,
    db: AsyncSession,
) -> dict[str, dict]:
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
    metadata: dict[str, dict] = {}
    for section in _walk_outline_sections(sections):
        section_uid = section.get("uid") or section.get("section_uid")
        if not section_uid:
            continue

        metadata[section_uid] = {
            "section_title": section.get("title"),
            "requirement_count": _outline_requirement_count(section),
        }
    return metadata


def _requirement_counts_from_metadata(metadata: dict[str, dict]) -> dict[str, int]:
    return {
        section_uid: requirement_count
        for section_uid, item in metadata.items()
        if isinstance((requirement_count := item.get("requirement_count")), int)
        and requirement_count > 0
    }


def _section_title(
    section_uid: str,
    outline_section_metadata: dict[str, dict],
) -> str | None:
    metadata = outline_section_metadata.get(section_uid)
    if not isinstance(metadata, dict):
        return None
    title = metadata.get("section_title")
    return title if isinstance(title, str) and title.strip() else None


def _attach_section_titles(
    sections: list[dict],
    outline_section_metadata: dict[str, dict],
) -> list[dict]:
    titled_sections = []
    for section in sections:
        titled_section = dict(section)
        section_uid = str(titled_section.get("section_uid") or "")
        title = _section_title(section_uid, outline_section_metadata)
        if title:
            titled_section["section_title"] = title
        titled_sections.append(titled_section)
    return titled_sections


def _stale_section_details(
    stale_sections: list[str],
    outline_section_metadata: dict[str, dict],
) -> list[dict]:
    return [
        {
            "section_uid": section_uid,
            **(
                {"section_title": title}
                if (title := _section_title(section_uid, outline_section_metadata))
                else {}
            ),
        }
        for section_uid in stale_sections
    ]


def _quality_review_issue(
    generation: Generation,
    outline_requirement_counts: dict[str, int],
) -> dict | None:
    raw_flags = getattr(generation, "flags_json", None)
    flags = raw_flags if isinstance(raw_flags, dict) else {}
    coverage = flags.get("requirement_coverage")
    if not isinstance(coverage, dict):
        requirement_count = outline_requirement_counts.get(generation.section_uid, 0)
        if requirement_count <= 0:
            return None
        coverage = {"total": requirement_count, "missing_ids": []}

    missing_ids = coverage.get("missing_ids")
    if isinstance(missing_ids, list) and missing_ids:
        return None

    raw_used_sources = getattr(generation, "used_sources_json", None)
    used_sources = raw_used_sources if isinstance(raw_used_sources, dict) else {}
    raw_blueprint = used_sources.get("drafting_blueprint")
    drafting_blueprint = raw_blueprint if isinstance(raw_blueprint, dict) else None

    assessment = assess_generation_depth(
        getattr(generation, "text", "") or "",
        coverage,
        drafting_blueprint=drafting_blueprint,
    )
    if assessment["status"] == "ok":
        return None

    return {
        "section_uid": generation.section_uid,
        "generation_id": generation.id,
        "word_count": assessment["word_count"],
        "sentence_count": assessment["sentence_count"],
        "requirement_count": assessment["requirement_count"],
        "blueprint_group_count": assessment["blueprint_group_count"],
        "blueprint_topic_count": assessment["blueprint_topic_count"],
        "blueprint_requirement_id_count": assessment[
            "blueprint_requirement_id_count"
        ],
        "min_words": assessment["min_words"],
        "min_sentences": assessment["min_sentences"],
        "suggested_words_per_structure": assessment[
            "suggested_words_per_structure"
        ],
        "structure_coverage": assessment.get("structure_coverage"),
        "issues": assessment["issues"],
    }


def _selected_section_count(generations: list[Generation]) -> int:
    return len({generation.section_uid for generation in generations})


def _stale_sections(generations: list[Generation]) -> list[str]:
    section_uids: list[str] = []
    seen: set[str] = set()
    for generation in generations:
        if generation.evidence_status != "stale" or generation.section_uid in seen:
            continue
        section_uids.append(generation.section_uid)
        seen.add(generation.section_uid)
    return section_uids


def _readiness_message(readiness: dict) -> str:
    blockers = readiness.get("blockers") or []
    if len(blockers) != 1:
        return "Pre-export check failed: multiple readiness issues were found."

    code = blockers[0].get("code")
    if code == "duplicate_selected":
        return (
            "Pre-export check failed: some sections have multiple selected "
            "generated variants."
        )
    if code == "stale_evidence":
        return "Pre-export check failed: some selected sections have stale evidence."
    if code == "missing_requirements":
        return (
            "Pre-export check failed: some selected sections do not cover all "
            "tender requirements."
        )
    if code == "shallow_sections":
        return (
            "Pre-export check failed: some selected sections are too short for "
            "their mapped tender requirements."
        )
    return "Pre-export check failed: proposal is not ready for DOCX export."


async def _build_export_readiness(
    project_id: str,
    selected_generations: list[Generation],
    db: AsyncSession,
) -> dict:
    duplicate_sections = _duplicate_selected_sections(selected_generations)
    stale_sections = _stale_sections(selected_generations)
    missing_requirement_sections = [
        issue
        for generation in selected_generations
        if (issue := _missing_requirement_coverage(generation))
    ]
    outline_section_metadata = (
        await _load_outline_section_metadata(project_id, db)
        if selected_generations
        else {}
    )
    outline_requirement_counts = _requirement_counts_from_metadata(
        outline_section_metadata
    )
    quality_sections = [
        issue
        for generation in selected_generations
        if (issue := _quality_review_issue(generation, outline_requirement_counts))
    ]
    duplicate_sections = _attach_section_titles(
        duplicate_sections,
        outline_section_metadata,
    )
    missing_requirement_sections = _attach_section_titles(
        missing_requirement_sections,
        outline_section_metadata,
    )
    quality_sections = _attach_section_titles(
        quality_sections,
        outline_section_metadata,
    )
    stale_section_details = _stale_section_details(
        stale_sections,
        outline_section_metadata,
    )

    missing_requirement_count = sum(
        section["missing_count"] for section in missing_requirement_sections
    )
    blockers: list[dict] = []
    if duplicate_sections:
        blockers.append(
            {
                "code": "duplicate_selected",
                "count": len(duplicate_sections),
                "message": "Some sections have multiple selected generated variants.",
            }
        )
    if stale_sections:
        blockers.append(
            {
                "code": "stale_evidence",
                "count": len(stale_sections),
                "message": "Some selected sections have stale evidence.",
            }
        )
    if missing_requirement_sections:
        blockers.append(
            {
                "code": "missing_requirements",
                "count": missing_requirement_count,
                "message": "Some selected sections do not cover all tender requirements.",
            }
        )
    if quality_sections:
        blockers.append(
            {
                "code": "shallow_sections",
                "count": len(quality_sections),
                "message": "Some selected sections are too short for their mapped tender requirements.",
            }
        )

    readiness = {
        "project_id": project_id,
        "ready": not blockers,
        "status": "ready" if not blockers else "blocked",
        "selected_generation_count": len(selected_generations),
        "selected_section_count": _selected_section_count(selected_generations),
        "blocker_count": len(blockers),
        "blockers": blockers,
        "duplicate_selected_sections": duplicate_sections,
        "duplicate_selected_count": len(duplicate_sections),
        "stale_sections": stale_sections,
        "stale_section_details": stale_section_details,
        "stale_section_count": len(stale_sections),
        "missing_requirement_sections": missing_requirement_sections,
        "missing_requirement_count": missing_requirement_count,
        "quality_sections": quality_sections,
        "quality_section_count": len(quality_sections),
    }
    readiness["message"] = (
        "Proposal is ready for DOCX export."
        if readiness["ready"]
        else _readiness_message(readiness)
    )
    return readiness


async def _load_selected_generations(
    project_id: str,
    db: AsyncSession,
) -> list[Generation]:
    selected_result = await db.execute(
        select(Generation).where(
            Generation.project_id == project_id,
            Generation.selected.is_(True),
        )
    )
    return list(selected_result.scalars().all())


async def _require_export_ready(project_id: str, db: AsyncSession) -> dict:
    selected_generations = await _load_selected_generations(project_id, db)
    readiness = await _build_export_readiness(project_id, selected_generations, db)
    if readiness["ready"]:
        return readiness

    raise HTTPException(
        status_code=409,
        detail=readiness,
    )


@router.get("/{project_id}/readiness")
async def export_readiness(project_id: str, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    selected_generations = await _load_selected_generations(project_id, db)
    return await _build_export_readiness(project_id, selected_generations, db)


@router.get("/{project_id}/readiness/report", response_class=PlainTextResponse)
async def export_readiness_report(project_id: str, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    selected_generations = await _load_selected_generations(project_id, db)
    readiness = await _build_export_readiness(project_id, selected_generations, db)
    return PlainTextResponse(
        render_export_readiness_report(readiness),
        media_type="text/markdown; charset=utf-8",
    )


@router.get("/{project_id}/docx")
async def export_docx(project_id: str, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    await _require_export_ready(project_id, db)

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
