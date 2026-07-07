from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

from export_selected_proposal_markdown import (
    GenerationSnapshot,
    load_snapshot,
    newest_generation_per_section,
    render_selected_proposal_markdown,
)
from proposal_gap_analysis import (
    extract_text,
    render_report,
    split_sections,
)


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "services" / "api"
GAP_FOCUS_PRIORITY = {
    "outline mapping": 0,
    "drafting depth": 1,
    "grounding and checklist coverage": 2,
    "monitor": 3,
}


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


def _split_markdown_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|"):
        return []
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for char in stripped.strip("|"):
        if char == "|" and not escaped:
            cells.append("".join(current).strip().replace("\\|", "|"))
            current = []
            escaped = False
            continue
        current.append(char)
        escaped = char == "\\" and not escaped
        if char != "\\":
            escaped = False
    cells.append("".join(current).strip().replace("\\|", "|"))
    return cells


def gap_calibration_focus_counts(markdown: str) -> dict[str, int]:
    in_diagnostics = False
    counts: dict[str, int] = {}
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped == "## Section Gap Diagnostics":
            in_diagnostics = True
            continue
        if in_diagnostics and stripped.startswith("## "):
            break
        if not in_diagnostics or not stripped.startswith("|"):
            continue
        cells = _split_markdown_table_row(stripped)
        if len(cells) < 6 or cells[0] in {"Reference section", "---"}:
            continue
        focus = cells[5]
        if focus:
            counts[focus] = counts.get(focus, 0) + 1
    return counts


def gap_regeneration_priority_rows(
    markdown: str,
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    in_diagnostics = False
    rows: list[dict[str, Any]] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped == "## Section Gap Diagnostics":
            in_diagnostics = True
            continue
        if in_diagnostics and stripped.startswith("## "):
            break
        if not in_diagnostics or not stripped.startswith("|"):
            continue
        cells = _split_markdown_table_row(stripped)
        if len(cells) < 6 or cells[0] in {"Reference section", "---"}:
            continue
        focus = cells[5]
        if not focus or focus == "monitor":
            continue
        try:
            coverage = float(cells[2])
        except ValueError:
            coverage = 1.0
        try:
            volume = float(cells[3])
        except ValueError:
            volume = 1.0
        rows.append(
            {
                "reference_section": cells[0],
                "generated_section": cells[1],
                "coverage": coverage,
                "volume": volume,
                "reasons": cells[4],
                "focus": focus,
            }
        )
    rows.sort(
        key=lambda row: (
            GAP_FOCUS_PRIORITY.get(str(row["focus"]), 9),
            float(row["coverage"]),
            float(row["volume"]),
            str(row["reference_section"]),
        )
    )
    return rows[:limit]


def _section_label(section: dict[str, Any]) -> str:
    for key in ("section_title", "title", "section_uid"):
        value = section.get(key)
        if value:
            return str(value)
    return "unknown section"


def _summarize_labels(labels: list[str], limit: int = 6) -> str:
    visible = labels[:limit]
    suffix = f" (+{len(labels) - limit} more)" if len(labels) > limit else ""
    return "; ".join(visible) + suffix


def readiness_priority_actions(readiness: dict[str, Any] | None) -> list[str]:
    readiness = readiness or {}
    actions: list[str] = []
    duplicate_sections = [
        item
        for item in readiness.get("duplicate_selected_sections") or []
        if isinstance(item, dict)
    ]
    if duplicate_sections:
        labels = [_section_label(item) for item in duplicate_sections]
        actions.append(
            "`duplicate_selected`: resolve selection ambiguity before regeneration - "
            + _summarize_labels(labels)
        )

    stale_sections = [
        item
        for item in readiness.get("stale_section_details") or []
        if isinstance(item, dict)
    ]
    if not stale_sections:
        stale_sections = [
            {"section_uid": str(item)}
            for item in readiness.get("stale_sections") or []
            if item is not None
        ]
    if stale_sections:
        labels = [_section_label(item) for item in stale_sections]
        actions.append(
            "`stale_evidence`: regenerate selected sections with fresh evidence - "
            + _summarize_labels(labels)
        )

    missing_sections = [
        item
        for item in readiness.get("missing_requirement_sections") or []
        if isinstance(item, dict)
    ]
    if missing_sections:
        missing_sections.sort(
            key=lambda item: int(item.get("missing_count") or 0),
            reverse=True,
        )
        labels = [
            f"{_section_label(item)} ({int(item.get('missing_count') or 0)} missing)"
            for item in missing_sections
        ]
        actions.append(
            "`missing_requirements`: regenerate with explicit checklist coverage - "
            + _summarize_labels(labels)
        )

    quality_sections = [
        item
        for item in readiness.get("quality_sections") or []
        if isinstance(item, dict)
    ]
    if quality_sections:
        quality_sections.sort(
            key=lambda item: (
                int(item.get("requirement_count") or 0),
                int(item.get("blueprint_topic_count") or 0),
            ),
            reverse=True,
        )
        labels = [
            (
                f"{_section_label(item)} "
                f"({int(item.get('word_count') or 0)}/"
                f"{int(item.get('min_words') or 0)} words)"
            )
            for item in quality_sections
        ]
        actions.append(
            "`shallow_sections`: regenerate with deeper narrative and controls - "
            + _summarize_labels(labels)
        )

    return actions


def calibration_output_paths(out_dir: Path) -> dict[str, Path]:
    return {
        "selected_snapshot": out_dir / "selected_proposal_snapshot.md",
        "effective_snapshot": out_dir / "effective_proposal_snapshot.md",
        "readiness_report": out_dir / "docx_readiness_report.md",
        "gap_report": out_dir / "proposal_gap_report.md",
        "manifest": out_dir / "calibration_manifest.md",
    }


def render_manifest(
    *,
    project_id: str,
    reference: Path,
    selected_snapshot: Path,
    effective_snapshot: Path,
    readiness_report: Path,
    gap_report: Path,
    tenders: list[Path],
    readiness: dict[str, Any] | None = None,
    snapshot_warnings: int = 0,
    gap_focus_counts: dict[str, int] | None = None,
    gap_priority_rows: list[dict[str, Any]] | None = None,
) -> str:
    readiness = readiness or {}
    blockers = [
        item
        for item in readiness.get("blockers") or []
        if isinstance(item, dict)
    ]
    gap_focus_counts = gap_focus_counts or {}
    gap_priority_rows = gap_priority_rows or []
    readiness_actions = readiness_priority_actions(readiness)
    lines = [
        "# Proposal calibration bundle",
        "",
        f"- Project ID: `{project_id}`",
        f"- Reference proposal: `{_display_path(reference)}`",
        f"- Raw selected proposal snapshot: `{_display_path(selected_snapshot)}`",
        f"- Effective proposal snapshot: `{_display_path(effective_snapshot)}`",
        f"- DOCX readiness report: `{_display_path(readiness_report)}`",
        f"- Gap report: `{_display_path(gap_report)}`",
        "- Mode: `non-mutating`",
        "",
        "## Calibration gates",
        "",
        f"- Snapshot warnings: `{snapshot_warnings}`",
        f"- DOCX readiness status: `{readiness.get('status', 'unknown')}`",
        f"- DOCX readiness blockers: `{len(blockers)}`",
        "- Gap input snapshot: `effective_proposal_snapshot.md`",
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
    lines.extend(["", "## Gap calibration focus summary", ""])
    if gap_focus_counts:
        for focus, count in sorted(
            gap_focus_counts.items(),
            key=lambda item: (-item[1], item[0]),
        ):
            lines.append(f"- `{focus}`: `{count}` sections")
    else:
        lines.append("- `none`: Section Gap Diagnostics not found or no section rows.")
    lines.extend(["", "## Regeneration priority shortlist", ""])
    if readiness_actions:
        lines.append(
            "- Readiness blockers come first because they affect exportability and "
            "can distort reference-gap interpretation."
        )
        lines.extend(
            f"{index}. {action}"
            for index, action in enumerate(readiness_actions, start=1)
        )
        next_index = len(readiness_actions) + 1
    else:
        lines.append(
            "- No readiness blockers found; use the gap diagnostics to choose the "
            "first regeneration targets."
        )
        next_index = 1
    if gap_priority_rows:
        for row in gap_priority_rows:
            lines.append(
                f"{next_index}. Gap `{row['focus']}`: regenerate/reference-align "
                f"`{row['reference_section']}` using generated section "
                f"`{row['generated_section']}` as the nearest current base "
                f"(coverage `{row['coverage']:.2f}`, volume `{row['volume']:.2f}`, "
                f"reasons: {row['reasons']})."
            )
            next_index += 1
    elif not readiness_actions:
        lines.append(
            "1. No concrete regeneration targets were found in readiness or gap diagnostics."
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
            "3. Open the effective proposal snapshot to see the in-memory newest-per-section view.",
            "4. Open the gap report and review Universal Topic Coverage.",
            "5. Follow Calibration Recommendations before regenerating sections.",
            "6. Rerun this calibration bundle after regeneration.",
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

    project_name, outline_sections, selected_generations = await load_snapshot(project_id)
    paths["selected_snapshot"].write_text(
        render_selected_proposal_markdown(
            project_name=project_name,
            project_id=project_id,
            outline_sections=outline_sections,
            selected_generations=selected_generations,
        ),
        encoding="utf-8",
    )
    effective_generations = newest_generation_per_section(selected_generations)
    paths["effective_snapshot"].write_text(
        render_selected_proposal_markdown(
            project_name=project_name,
            project_id=project_id,
            outline_sections=outline_sections,
            selected_generations=effective_generations,
            snapshot_mode="effective-newest-selected-per-section",
        ),
        encoding="utf-8",
    )
    readiness = await export_readiness_report_markdown(
        project_id,
        paths["readiness_report"],
    )

    reference_text = extract_text(reference)
    selected_text = extract_text(paths["selected_snapshot"])
    effective_text = extract_text(paths["effective_snapshot"])
    warning_count = snapshot_warning_count(selected_text)
    tender_text = "\n\n".join(extract_text(path) for path in tenders)
    report = render_report(
        tender_text=tender_text,
        reference_sections=split_sections(reference_text),
        generated_sections=split_sections(effective_text),
        reference_path=reference,
        generated_path=paths["effective_snapshot"],
        tender_paths=tenders,
    )
    paths["gap_report"].write_text(report, encoding="utf-8")
    gap_focus_counts = gap_calibration_focus_counts(report)
    gap_priority_rows = gap_regeneration_priority_rows(report)
    paths["manifest"].write_text(
        render_manifest(
            project_id=project_id,
            reference=reference,
            selected_snapshot=paths["selected_snapshot"],
            effective_snapshot=paths["effective_snapshot"],
            readiness_report=paths["readiness_report"],
            gap_report=paths["gap_report"],
            tenders=tenders,
            readiness=readiness,
            snapshot_warnings=warning_count,
            gap_focus_counts=gap_focus_counts,
            gap_priority_rows=gap_priority_rows,
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
    print(f"Wrote {paths['effective_snapshot']}")
    print(f"Wrote {paths['readiness_report']}")
    print(f"Wrote {paths['gap_report']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
