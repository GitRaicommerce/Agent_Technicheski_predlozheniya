from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

from export_selected_proposal_markdown import export_markdown
from proposal_gap_analysis import (
    extract_text,
    render_report,
    split_sections,
)


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "services" / "api"


def _display_path(path: Path) -> str:
    return path.as_posix()


def snapshot_warning_count(markdown: str) -> int:
    in_warnings = False
    count = 0
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped == "## Snapshot Warnings":
            in_warnings = True
            continue
        if in_warnings and stripped.startswith("## "):
            break
        if in_warnings and stripped.startswith("- "):
            count += 1
    return count


def calibration_output_paths(out_dir: Path) -> dict[str, Path]:
    return {
        "selected_snapshot": out_dir / "selected_proposal_snapshot.md",
        "readiness_report": out_dir / "docx_readiness_report.md",
        "gap_report": out_dir / "proposal_gap_report.md",
        "manifest": out_dir / "calibration_manifest.md",
    }


def render_manifest(
    *,
    project_id: str,
    reference: Path,
    selected_snapshot: Path,
    readiness_report: Path,
    gap_report: Path,
    tenders: list[Path],
    readiness: dict[str, Any] | None = None,
    snapshot_warnings: int = 0,
) -> str:
    readiness = readiness or {}
    blockers = [
        item
        for item in readiness.get("blockers") or []
        if isinstance(item, dict)
    ]
    lines = [
        "# Proposal calibration bundle",
        "",
        f"- Project ID: `{project_id}`",
        f"- Reference proposal: `{_display_path(reference)}`",
        f"- Selected proposal snapshot: `{_display_path(selected_snapshot)}`",
        f"- DOCX readiness report: `{_display_path(readiness_report)}`",
        f"- Gap report: `{_display_path(gap_report)}`",
        "- Mode: `non-mutating`",
        "",
        "## Calibration gates",
        "",
        f"- Snapshot warnings: `{snapshot_warnings}`",
        f"- DOCX readiness status: `{readiness.get('status', 'unknown')}`",
        f"- DOCX readiness blockers: `{len(blockers)}`",
    ]
    if blockers:
        lines.extend(
            f"  - `{blocker.get('code', 'unknown')}`: `{blocker.get('count', 0)}`"
            for blocker in blockers
        )
        lines.append(
            "- Gap report interpretation: resolve readiness blockers before treating "
            "reference-gap findings as final generation-quality evidence."
        )
    else:
        lines.append(
            "- Gap report interpretation: readiness is clear enough for calibration review."
        )
    lines.extend(
        [
            "",
            "## Tender/source documents",
            "",
        ]
    )
    if tenders:
        lines.extend(f"- `{_display_path(path)}`" for path in tenders)
    else:
        lines.append("- `none`")
    lines.extend(
        [
            "",
            "## Recommended review order",
            "",
            "1. Open the selected proposal snapshot and check Snapshot Warnings.",
            "2. Open the DOCX readiness report and resolve export blockers.",
            "3. Open the gap report and review Universal Topic Coverage.",
            "4. Follow Calibration Recommendations before regenerating sections.",
            "5. Rerun this calibration bundle after regeneration.",
            "",
        ]
    )
    return "\n".join(lines)


def _api_imports() -> None:
    api_path = str(API_ROOT)
    if api_path not in sys.path:
        sys.path.insert(0, api_path)


async def export_readiness_report_markdown(
    project_id: str,
    out_path: Path,
) -> dict[str, Any]:
    _api_imports()
    from app.core.database import AsyncSessionLocal
    from app.core.models import Project
    from app.export.readiness_report import render_export_readiness_report
    from app.routers.export import _build_export_readiness, _load_selected_generations

    async with AsyncSessionLocal() as db:
        project = await db.get(Project, project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")

        selected_generations = await _load_selected_generations(project_id, db)
        readiness = await _build_export_readiness(project_id, selected_generations, db)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(render_export_readiness_report(readiness), encoding="utf-8")
        return readiness


async def run_calibration_bundle(
    *,
    project_id: str,
    reference: Path,
    out_dir: Path,
    tenders: list[Path],
) -> dict[str, Path]:
    paths = calibration_output_paths(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    await export_markdown(project_id, paths["selected_snapshot"])
    readiness = await export_readiness_report_markdown(
        project_id,
        paths["readiness_report"],
    )

    reference_text = extract_text(reference)
    selected_text = extract_text(paths["selected_snapshot"])
    warning_count = snapshot_warning_count(selected_text)
    tender_text = "\n\n".join(extract_text(path) for path in tenders)
    report = render_report(
        tender_text=tender_text,
        reference_sections=split_sections(reference_text),
        generated_sections=split_sections(selected_text),
        reference_path=reference,
        generated_path=paths["selected_snapshot"],
        tender_paths=tenders,
    )
    paths["gap_report"].write_text(report, encoding="utf-8")
    paths["manifest"].write_text(
        render_manifest(
            project_id=project_id,
            reference=reference,
            selected_snapshot=paths["selected_snapshot"],
            readiness_report=paths["readiness_report"],
            gap_report=paths["gap_report"],
            tenders=tenders,
            readiness=readiness,
            snapshot_warnings=warning_count,
        ),
        encoding="utf-8",
    )
    return paths


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a non-mutating calibration bundle: selected proposal "
            "snapshot plus gap analysis against a reference proposal."
        )
    )
    parser.add_argument("--project-id", required=True, help="Project UUID")
    parser.add_argument(
        "--reference",
        required=True,
        type=Path,
        help="Winning/reference proposal DOCX/PDF/TXT/MD",
    )
    parser.add_argument(
        "--tender",
        action="append",
        default=[],
        type=Path,
        help="Tender/source document. Can be passed multiple times.",
    )
    parser.add_argument("--out-dir", required=True, type=Path, help="Bundle output directory")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    paths = asyncio.run(
        run_calibration_bundle(
            project_id=args.project_id,
            reference=args.reference,
            out_dir=args.out_dir,
            tenders=args.tender,
        )
    )
    print(f"Wrote {paths['manifest']}")
    print(f"Wrote {paths['selected_snapshot']}")
    print(f"Wrote {paths['readiness_report']}")
    print(f"Wrote {paths['gap_report']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
