from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "services" / "api"


@dataclass(frozen=True)
class GenerationSnapshot:
    id: str
    section_uid: str
    variant: str
    text: str
    evidence_status: str
    selected: bool
    created_at: str


def _section_uid(section: dict[str, Any]) -> str:
    return str(section.get("section_uid") or section.get("uid") or "")


def _section_title(section: dict[str, Any]) -> str:
    return str(section.get("title") or "Untitled section").strip()


def _section_numbering(section: dict[str, Any]) -> str:
    return str(section.get("display_numbering") or "").strip()


def walk_outline_sections(sections: list[dict[str, Any]]) -> list[tuple[int, dict[str, Any]]]:
    result: list[tuple[int, dict[str, Any]]] = []

    def walk(items: list[dict[str, Any]], level: int) -> None:
        for item in items:
            result.append((level, item))
            children = item.get("children") or item.get("subsections") or []
            if isinstance(children, list):
                walk(children, level + 1)

    walk(sections, 2)
    return result


def _heading(level: int, section: dict[str, Any]) -> str:
    marks = "#" * max(2, min(level, 6))
    numbering = _section_numbering(section)
    title = _section_title(section)
    label = f"{numbering} {title}".strip()
    return f"{marks} {label}".strip()


def _generation_meta_line(generation: GenerationSnapshot) -> str:
    return (
        f"<!-- generation_id={generation.id}; variant={generation.variant}; "
        f"evidence_status={generation.evidence_status}; created_at={generation.created_at} -->"
    )


def newest_generation_per_section(
    generations: list[GenerationSnapshot],
) -> list[GenerationSnapshot]:
    newest_by_section: dict[str, GenerationSnapshot] = {}
    for generation in generations:
        current = newest_by_section.get(generation.section_uid)
        if current is None or generation.created_at > current.created_at:
            newest_by_section[generation.section_uid] = generation
    return list(newest_by_section.values())


def render_selected_proposal_markdown(
    *,
    project_name: str,
    project_id: str,
    outline_sections: list[dict[str, Any]],
    selected_generations: list[GenerationSnapshot],
    snapshot_mode: str = "selected-generations-markdown",
) -> str:
    generations_by_section: dict[str, list[GenerationSnapshot]] = {}
    for generation in selected_generations:
        generations_by_section.setdefault(generation.section_uid, []).append(generation)

    lines = [
        f"# Technical proposal snapshot: {project_name}",
        "",
        f"- Project ID: `{project_id}`",
        f"- Selected generations: `{len(selected_generations)}`",
        f"- Snapshot mode: `{snapshot_mode}`",
        "",
    ]
    warnings: list[str] = []
    emitted_sections: set[str] = set()

    for level, section in walk_outline_sections(outline_sections):
        section_uid = _section_uid(section)
        if not section_uid:
            continue
        emitted_sections.add(section_uid)
        lines.extend([_heading(level, section), ""])

        generations = generations_by_section.get(section_uid) or []
        if not generations:
            warnings.append(f"missing selected generation for section {section_uid}")
            lines.extend([f"<!-- missing_selected_generation section_uid={section_uid} -->", ""])
            continue

        if len(generations) > 1:
            warnings.append(
                f"duplicate selected generations for section {section_uid}: "
                + ", ".join(generation.id for generation in generations)
            )

        for index, generation in enumerate(generations, start=1):
            if len(generations) > 1:
                lines.extend([f"**Selected variant {index}**", ""])
            lines.extend([_generation_meta_line(generation), "", generation.text.strip(), ""])

    extra_generations = [
        generation
        for generation in selected_generations
        if generation.section_uid not in emitted_sections
    ]
    if extra_generations:
        lines.extend(["## Selected Generations Outside Current Outline", ""])
        for generation in extra_generations:
            warnings.append(
                f"selected generation outside current outline: {generation.id}"
            )
            lines.extend(
                [
                    f"### Section `{generation.section_uid}`",
                    "",
                    _generation_meta_line(generation),
                    "",
                    generation.text.strip(),
                    "",
                ]
            )

    if warnings:
        lines.extend(["## Snapshot Warnings", ""])
        lines.extend(f"- {warning}" for warning in warnings)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _api_imports() -> None:
    api_path = str(API_ROOT)
    if api_path not in sys.path:
        sys.path.insert(0, api_path)


async def load_snapshot(project_id: str) -> tuple[str, list[dict[str, Any]], list[GenerationSnapshot]]:
    _api_imports()
    from sqlalchemy import select

    from app.core.database import AsyncSessionLocal
    from app.core.models import Generation, Project, TpOutline

    async with AsyncSessionLocal() as db:
        project = await db.get(Project, project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")

        outline_result = await db.execute(
            select(TpOutline)
            .where(TpOutline.project_id == project_id)
            .order_by(TpOutline.status_locked.desc(), TpOutline.version.desc())
            .limit(1)
        )
        outline = outline_result.scalar_one_or_none()
        outline_json = outline.outline_json if outline else {}
        sections = outline_json.get("sections", outline_json.get("outline", []))
        if not isinstance(sections, list):
            sections = []

        generation_result = await db.execute(
            select(Generation)
            .where(Generation.project_id == project_id, Generation.selected.is_(True))
            .order_by(
                Generation.section_uid.asc(),
                Generation.created_at.desc(),
                Generation.variant.asc(),
            )
        )
        generations = [
            GenerationSnapshot(
                id=str(row.id),
                section_uid=str(row.section_uid),
                variant=str(row.variant),
                text=str(row.text or ""),
                evidence_status=str(row.evidence_status or ""),
                selected=bool(row.selected),
                created_at=str(row.created_at or ""),
            )
            for row in generation_result.scalars().all()
        ]
        return str(project.name), sections, generations


async def export_markdown(project_id: str, out_path: Path) -> None:
    project_name, sections, generations = await load_snapshot(project_id)
    markdown = render_selected_proposal_markdown(
        project_name=project_name,
        project_id=project_id,
        outline_sections=sections,
        selected_generations=generations,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(markdown, encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Export selected project generations to Markdown for non-mutating "
            "calibration and proposal gap analysis."
        )
    )
    parser.add_argument("--project-id", required=True, help="Project UUID")
    parser.add_argument("--out", required=True, type=Path, help="Output Markdown path")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    asyncio.run(export_markdown(args.project_id, args.out))
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
