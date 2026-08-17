"""
Детерминиран парсър за линеен график.
Поддържа .mpp (чрез python-mpxj) и Excel/PDF fallback.
LLM не парсва .mpp директно.
"""

from __future__ import annotations

import io
import re
from typing import Any


PARSER_VERSION = "1.1.0"


def parse_schedule(content: bytes, filename: str) -> dict[str, Any]:
    """
    Парсва файл с график и връща нормализиран JSON.
    Провенанс: към всяка задача се пази mpp_task_uid.
    """
    filename_lower = filename.lower()

    if filename_lower.endswith(".mpp"):
        return _parse_mpp(content)
    elif filename_lower.endswith((".xlsx", ".xls")):
        return _parse_excel(content)
    elif filename_lower.endswith(".pdf"):
        return _parse_pdf_schedule(content)
    else:
        raise ValueError(f"Unsupported schedule format: {filename}")


def _parse_mpp(content: bytes) -> dict[str, Any]:
    """
    Парсване на .mpp чрез mpxj (Java-based, достъпна чрез jpype или subprocess).
    При неналичност — връща структурирана грешка.
    """
    try:
        import jpype
        import mpxj

        # mpxj parsing
        project_file = mpxj.ProjectFile()
        reader = mpxj.reader.MPPReader()
        reader.read(io.BytesIO(content), project_file)

        tasks = []
        resources = []
        assignments = []

        for task in project_file.tasks:
            if task.id is None:
                continue
            tasks.append(
                {
                    "uid": int(task.unique_id or 0),
                    "name": str(task.name or ""),
                    "start": str(task.start) if task.start else None,
                    "finish": str(task.finish) if task.finish else None,
                    "duration_days": (
                        float(task.duration.duration) if task.duration else None
                    ),
                    "wbs": str(task.wbs) if task.wbs else None,
                }
            )

        for resource in project_file.resources:
            if resource.id is None:
                continue
            resources.append(
                {
                    "uid": int(resource.unique_id or 0),
                    "name": str(resource.name or ""),
                    "type": str(resource.type),
                }
            )

        return {
            "normalized": {
                "tasks": tasks,
                "resources": resources,
                "assignments": assignments,
            },
            "tasks": tasks,
            "resources": resources,
            "parser": "mpxj",
            "parser_version": PARSER_VERSION,
        }

    except ImportError:
        return _mpp_not_available_error()
    except Exception as e:
        return {
            "normalized": {"tasks": [], "resources": [], "error": str(e)},
            "tasks": [],
            "resources": [],
            "error": str(e),
            "parser": "mpxj",
            "parser_version": PARSER_VERSION,
        }


def _mpp_not_available_error() -> dict[str, Any]:
    return {
        "normalized": {"tasks": [], "resources": []},
        "tasks": [],
        "resources": [],
        "error": "MPP parsing not available. Please upload Excel or PDF export of the schedule.",
        "actions_required": [
            "Upload an Excel (.xlsx) or PDF export of the MS Project schedule.",
        ],
        "parser": "none",
        "parser_version": PARSER_VERSION,
    }


def _pick(row_dict: dict, *keys: str) -> Any:
    """Върни първата намерена стойност по наредените ключове (без None/празни)."""
    for k in keys:
        v = row_dict.get(k)
        if v is not None and str(v).strip() not in ("", "None"):
            return v
    return None


def _to_str_date(val: Any) -> str | None:
    """Нормализира дата/стринг към ISO string или None."""
    if val is None:
        return None
    import datetime
    if isinstance(val, (datetime.date, datetime.datetime)):
        return val.isoformat()
    s = str(val).strip()
    return s if s and s.lower() != "none" else None


def _parse_excel(content: bytes) -> dict[str, Any]:
    """Парсване на Excel export от MS Project."""
    try:
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return {
                "normalized": {"tasks": []},
                "tasks": [],
                "parser": "excel",
                "parser_version": PARSER_VERSION,
            }

        headers = [str(h).strip().lower() if h else "" for h in rows[0]]
        tasks = []
        for i, row in enumerate(rows[1:], start=1):
            row_dict = {headers[j]: row[j] for j in range(min(len(headers), len(row)))}

            # Skip fully-empty rows
            if all(v is None or str(v).strip() == "" for v in row_dict.values()):
                continue

            name_val = _pick(
                row_dict,
                "name", "task name", "task_name",
                "задача", "наименование", "дейност", "activity",
            )
            start_val = _pick(
                row_dict,
                "start", "start date", "start_date",
                "начало", "начална дата", "begin",
            )
            finish_val = _pick(
                row_dict,
                "finish", "end", "end date", "end_date",
                "finish date", "finish_date",
                "край", "крайна дата",
            )
            dur_val = _pick(
                row_dict,
                "duration", "duration (days)", "duration_days",
                "продължителност", "days",
            )
            wbs_val = _pick(row_dict, "wbs", "task id", "id", "no", "№")

            try:
                dur_float = float(dur_val) if dur_val is not None else None
            except (ValueError, TypeError):
                dur_float = None

            tasks.append(
                {
                    "uid": i,
                    "name": str(name_val) if name_val is not None else f"Задача {i}",
                    "start": _to_str_date(start_val),
                    "finish": _to_str_date(finish_val),
                    "duration_days": dur_float,
                    "wbs": str(wbs_val) if wbs_val is not None else None,
                }
            )

        return {
            "normalized": {"tasks": tasks, "resources": []},
            "tasks": tasks,
            "resources": [],
            "parser": "excel",
            "parser_version": PARSER_VERSION,
        }
    except Exception as e:
        raise ValueError(f"Excel schedule parse error: {e}") from e


def _parse_pdf_schedule(content: bytes) -> dict[str, Any]:
    """Extract schedule rows from vector PDF tables, with a guarded text fallback."""
    try:
        import pdfplumber

        with pdfplumber.open(io.BytesIO(content)) as pdf:
            tables = [
                table
                for page in pdf.pages
                for table in (page.extract_tables() or [])
                if table
            ]
        tasks = _tasks_from_pdf_tables(tables)
        if tasks:
            normalized = {
                "tasks": tasks,
                "resources": [],
                "source_quality": "structured_pdf_table",
            }
            return {
                "normalized": normalized,
                "tasks": tasks,
                "resources": [],
                "parser": "pdf_table",
                "parser_version": PARSER_VERSION,
            }
    except Exception:
        # The text fallback below is deliberately marked unreliable. It is
        # useful for diagnostics, but must never ground proposal assertions.
        pass

    from app.ingestion.parsers import _extract_pdf

    chunks = _extract_pdf(content)
    tasks = [
        {
            "uid": i + 1,
            "name": chunk["text"][:200],
            "start": None,
            "finish": None,
            "duration_days": None,
            "wbs": None,
            "note": "extracted_from_pdf_text",
        }
        for i, chunk in enumerate(chunks)
        if str(chunk.get("text") or "").strip()
    ]
    warning = (
        "PDF schedule table could not be reconstructed reliably. "
        "Upload an Excel or MPP export; this data will not be used for drafting."
    )
    normalized = {
        "tasks": tasks,
        "resources": [],
        "source_quality": "unreliable_text_fallback",
        "warning": warning,
    }
    return {
        "normalized": normalized,
        "tasks": tasks,
        "resources": [],
        "parser": "pdf_text",
        "parser_version": PARSER_VERSION,
        "warning": warning,
    }


def _clean_pdf_cell(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _duration_days(value: Any) -> float | None:
    match = re.search(r"-?\d+(?:[.,]\d+)?", _clean_pdf_cell(value))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", "."))
    except ValueError:
        return None


def _tasks_from_pdf_tables(tables: list[list[list[Any]]]) -> list[dict[str, Any]]:
    """Normalize the first seven columns of common MS Project PDF exports."""
    tasks: list[dict[str, Any]] = []
    seen_uids: set[int] = set()
    for table in tables:
        for row in table:
            if not isinstance(row, list) or len(row) < 2:
                continue
            uid_text = _clean_pdf_cell(row[0])
            name = _clean_pdf_cell(row[1])
            if not uid_text or not name or not uid_text.isdigit():
                continue
            uid = int(uid_text)
            if uid in seen_uids:
                continue
            seen_uids.add(uid)
            duration = row[2] if len(row) > 2 else None
            start = row[3] if len(row) > 3 else None
            finish = row[4] if len(row) > 4 else None
            resources = row[5] if len(row) > 5 else None
            predecessor = row[6] if len(row) > 6 else None
            task: dict[str, Any] = {
                "uid": uid,
                "name": name,
                "start": _to_str_date(_clean_pdf_cell(start)),
                "finish": _to_str_date(_clean_pdf_cell(finish)),
                "duration_days": _duration_days(duration),
                "wbs": uid_text,
                "note": "extracted_from_pdf_table",
            }
            resource_text = _clean_pdf_cell(resources)
            predecessor_text = _clean_pdf_cell(predecessor)
            if resource_text:
                task["resources"] = resource_text
            if predecessor_text:
                task["predecessors"] = predecessor_text
            tasks.append(task)
    return tasks


def schedule_quality(schedule_json: dict[str, Any] | None) -> dict[str, Any]:
    """Return a deterministic safety verdict for drafting and approval."""
    payload = schedule_json if isinstance(schedule_json, dict) else {}
    tasks = [task for task in payload.get("tasks", []) if isinstance(task, dict)]
    text_fallback = payload.get("source_quality") == "unreliable_text_fallback" or (
        bool(tasks)
        and all(task.get("note") == "extracted_from_pdf_text" for task in tasks)
    )
    detailed = [
        task
        for task in tasks
        if task.get("start") or task.get("finish") or task.get("duration_days") is not None
    ]
    reliable = bool(tasks) and not text_fallback and (
        len(tasks) > 1 or bool(detailed)
    )
    reasons: list[str] = []
    if not tasks:
        reasons.append("Графикът не съдържа разпознати задачи.")
    if text_fallback:
        reasons.append("PDF таблицата не е разпозната структурирано.")
    if len(tasks) == 1 and not detailed:
        reasons.append("Разпознат е само един запис без срок или продължителност.")
    return {
        "reliable": reliable,
        "task_count": len(tasks),
        "detailed_task_count": len(detailed),
        "reasons": reasons,
    }
