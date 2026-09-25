"""Source manifest: which tender files exist, their revision and extraction coverage.

The manifest is the shared contract (IMPLEMENTATION_PLAN §4.1) used to show
incomplete source coverage, to fingerprint the exact source set a plan or an
audit was made from, and to detect when that set has changed.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select

from app.core.models import ProjectFile

MANIFEST_MODULES = ("tender_docs",)


def _file_entry(file: ProjectFile) -> dict[str, Any]:
    raw_report = getattr(file, "ingest_report_json", None)
    report = raw_report if isinstance(raw_report, dict) else {}
    filename = str(getattr(file, "filename", "") or "")
    ingest_status = getattr(file, "ingest_status", None) or "unknown"
    coverage = report.get("page_coverage") if isinstance(report.get("page_coverage"), dict) else {}
    issues: list[str] = []
    if ingest_status != "done":
        issues.append(f"ingest_status:{ingest_status}")
    if report.get("quality_status") == "error":
        issues.append("extraction_error")
    if coverage.get("status"):
        coverage_status = coverage["status"]
    elif filename.lower().endswith(".pdf"):
        # Ingested before per-page coverage existed: not a failure, but the
        # coverage is unverified until the file is processed again.
        coverage_status = "not_recorded"
    else:
        coverage_status = "not_applicable"
    if coverage_status == "unknown":
        issues.append("page_coverage_unknown")
    elif coverage_status == "not_recorded":
        issues.append("page_coverage_not_recorded")
    missing_pages = [int(page) for page in coverage.get("missing_pages") or []]
    recovered_pages = [int(page) for page in coverage.get("recovered_pages") or []]
    unrecovered = sorted(set(missing_pages) - set(recovered_pages))
    if unrecovered:
        issues.append("pages_missing:" + ",".join(str(page) for page in unrecovered))
    return {
        "file_id": str(file.id),
        "filename": filename,
        "module": getattr(file, "module", None),
        "file_hash": getattr(file, "file_hash", None),
        "version": getattr(file, "version", None),
        "role": "tender_documentation",
        "ingest_status": ingest_status,
        "quality_status": report.get("quality_status")
        or getattr(file, "ingest_quality_status", None),
        "page_count": report.get("page_count"),
        "page_coverage_status": coverage_status,
        "missing_pages": missing_pages,
        "recovered_pages": recovered_pages,
        "warnings": list(report.get("warnings") or []),
        "issues": issues,
    }


def manifest_hash(files: list[dict[str, Any]]) -> str:
    """Stable fingerprint of the exact source revisions (order-independent)."""
    identity = sorted(
        (entry["file_id"], entry.get("file_hash") or "", str(entry.get("version") or ""))
        for entry in files
    )
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode("utf-8")).hexdigest()


def summarize_manifest(files: list[dict[str, Any]]) -> dict[str, Any]:
    incomplete = [entry for entry in files if entry["issues"]]
    return {
        "files": files,
        "file_count": len(files),
        "manifest_hash": manifest_hash(files),
        "complete": bool(files) and not incomplete,
        "incomplete_files": [
            {"file_id": entry["file_id"], "filename": entry["filename"], "issues": entry["issues"]}
            for entry in incomplete
        ],
    }


async def build_source_manifest(project_id: str, db) -> dict[str, Any]:
    result = await db.execute(
        select(ProjectFile)
        .where(
            ProjectFile.project_id == project_id,
            ProjectFile.module.in_(MANIFEST_MODULES),
        )
        .order_by(ProjectFile.filename, ProjectFile.id)
    )
    return summarize_manifest([_file_entry(file) for file in result.scalars().all()])
