from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from export_selected_proposal_markdown import export_markdown
from proposal_gap_analysis import (
    extract_text,
    render_report,
    split_sections,
)


def _display_path(path: Path) -> str:
    return path.as_posix()


def calibration_output_paths(out_dir: Path) -> dict[str, Path]:
    return {
        "selected_snapshot": out_dir / "selected_proposal_snapshot.md",
        "gap_report": out_dir / "proposal_gap_report.md",
        "manifest": out_dir / "calibration_manifest.md",
    }


def render_manifest(
    *,
    project_id: str,
    reference: Path,
    selected_snapshot: Path,
    gap_report: Path,
    tenders: list[Path],
) -> str:
    lines = [
        "# Proposal calibration bundle",
        "",
        f"- Project ID: `{project_id}`",
        f"- Reference proposal: `{_display_path(reference)}`",
        f"- Selected proposal snapshot: `{_display_path(selected_snapshot)}`",
        f"- Gap report: `{_display_path(gap_report)}`",
        "- Mode: `non-mutating`",
        "",
        "## Tender/source documents",
        "",
    ]
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
            "2. Open the gap report and review Universal Topic Coverage.",
            "3. Follow Calibration Recommendations before regenerating sections.",
            "4. Rerun DOCX readiness and this calibration bundle after regeneration.",
            "",
        ]
    )
    return "\n".join(lines)


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

    reference_text = extract_text(reference)
    selected_text = extract_text(paths["selected_snapshot"])
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
            gap_report=paths["gap_report"],
            tenders=tenders,
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
    print(f"Wrote {paths['gap_report']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
