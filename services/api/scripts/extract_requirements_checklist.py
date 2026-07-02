from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.requirements import (
    extract_requirement_checklist,
    render_requirements_markdown,
)
from app.core.database import AsyncSessionLocal
from app.core.models import ExtractedChunk, Project, ProjectFile


async def load_project_name(project_id: str) -> str:
    async with AsyncSessionLocal() as db:
        project = await db.get(Project, project_id)
        return project.name if project else project_id


async def load_tender_chunks(project_id: str) -> list[SimpleNamespace]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ExtractedChunk, ProjectFile.filename)
            .join(ProjectFile, ExtractedChunk.file_id == ProjectFile.id)
            .where(ProjectFile.project_id == project_id)
            .where(ProjectFile.module == "tender_docs")
            .order_by(ProjectFile.filename, ExtractedChunk.page, ExtractedChunk.id)
        )
        return [
            SimpleNamespace(
                id=chunk.id,
                text=chunk.text,
                page=chunk.page,
                section_path=chunk.section_path,
                source_file=filename,
            )
            for chunk, filename in result.all()
        ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract a universal requirements checklist from tender document chunks."
    )
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--limit", type=int)
    return parser.parse_args()


async def async_main() -> int:
    args = parse_args()
    chunks = await load_tender_chunks(args.project_id)
    project_name = await load_project_name(args.project_id)
    items = extract_requirement_checklist(chunks, limit=args.limit)
    markdown = render_requirements_markdown(
        items,
        title=f"Чеклист на изискванията - {project_name}",
    )
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(markdown, encoding="utf-8")
        print(f"Wrote {args.out}")
    else:
        print(markdown)
    return 0


def main() -> int:
    return asyncio.run(async_main())


if __name__ == "__main__":
    raise SystemExit(main())
