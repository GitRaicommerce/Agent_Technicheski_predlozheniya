"""WP-02 / K-17 acceptance (T-19): schedule data is preserved or visibly missing."""

from __future__ import annotations

import io
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import openpyxl
import pytest

from app.ingestion.schedule_parser import parse_duration, parse_schedule, schedule_quality
from app.ingestion.worker import _ingest_schedule


def _xlsx(rows: list[list[object]]) -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_excel_units_dependencies_and_resources_are_preserved():
    """The exact case from the audit: previously unknown durations, no detail."""
    content = _xlsx(
        [
            ["Name", "Duration", "Predecessors", "Resource Names"],
            ["Design", "20 days", "1", "Engineer"],
            ["Construction", "30 days", "2", "Team"],
        ]
    )

    result = parse_schedule(content, "plan.xlsx")
    tasks = result["tasks"]

    assert [task["duration_days"] for task in tasks] == [20.0, 30.0]
    assert [task["predecessors"] for task in tasks] == ["1", "2"]
    assert [task["resources"] for task in tasks] == ["Engineer", "Team"]
    quality = schedule_quality(result["normalized"])
    assert quality["reliable"] is True
    assert quality["detailed_task_count"] == 2
    assert quality["field_coverage"] == {
        "duration": 2,
        "predecessors": 2,
        "resources": 2,
        "dates": 0,
    }


def test_rows_without_timing_are_not_reliable():
    content = _xlsx([["Name", "Notes"], ["Design", "x"], ["Construction", "y"]])

    quality = schedule_quality(parse_schedule(content, "plan.xlsx")["normalized"])

    assert quality["reliable"] is False
    assert any("продължителност" in reason for reason in quality["reasons"])


@pytest.mark.parametrize(
    "raw,days,unit,warning",
    [
        ("20 days", 20.0, "days", None),
        ("15 дни", 15.0, "days", None),
        ("5d", 5.0, "days", None),
        ("20 days?", 20.0, "days", None),
        ("3 weeks", None, "weeks", "duration_not_in_days:weeks"),
        ("2 седмици", None, "weeks", "duration_not_in_days:weeks"),
        ("16 hrs", None, "hours", "duration_not_in_days:hours"),
        ("1 month", None, "months", "duration_not_in_days:months"),
        ("7 fortnights", None, None, "unknown_duration_unit:fortnights"),
        ("около месец", None, None, "unparsed_duration"),
    ],
)
def test_duration_units_are_never_silently_converted(raw, days, unit, warning):
    parsed = parse_duration(raw)
    assert parsed["days"] == days
    assert parsed["unit"] == unit
    assert parsed["warning"] == warning
    assert parsed["text"] == raw


def test_bare_number_is_days_only_with_a_visible_assumption():
    assert parse_duration(12, header_unit_days=True)["warning"] is None
    assumed = parse_duration(12)
    assert assumed["days"] == 12.0
    assert assumed["warning"] == "unit_assumed_days"


def test_unknown_unit_is_reported_in_quality():
    content = _xlsx(
        [["Name", "Duration"], ["Design", "20 days"], ["Review", "7 fortnights"]]
    )
    quality = schedule_quality(parse_schedule(content, "plan.xlsx")["normalized"])
    assert any("Непозната единица" in reason for reason in quality["reasons"])
    assert "unknown_duration_unit:fortnights" in quality["duration_warnings"]


@pytest.mark.asyncio
async def test_failed_mpp_does_not_replace_the_active_schedule():
    """T-19: a good schedule followed by a broken MPP stays usable."""
    file = SimpleNamespace(
        id="file-mpp",
        project_id="project-1",
        filename="broken.mpp",
        file_hash="hash",
        ingest_status="processing",
        ingest_error=None,
        ingest_quality_status="pending",
        ingest_report_json=None,
    )
    db = MagicMock()
    db.add = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    broken = {
        "normalized": {"tasks": [], "resources": [], "error": "corrupt file"},
        "tasks": [],
        "resources": [],
        "error": "corrupt file",
        "parser": "mpxj",
        "parser_version": "1.2.0",
    }

    with patch("app.ingestion.schedule_parser.parse_schedule", return_value=broken):
        await _ingest_schedule(file, b"not-an-mpp", db)

    db.add.assert_not_called()
    db.execute.assert_not_awaited()
    assert file.ingest_status == "error"
    assert "Предишният използваем график остава активен" in file.ingest_error
    assert file.ingest_report_json["active_schedule_unchanged"] is True
