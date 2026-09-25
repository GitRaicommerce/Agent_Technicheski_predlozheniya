from app.agents.proposal_timing import (
    find_concrete_calendar_dates,
    schedule_for_proposal,
)


def test_finds_numeric_iso_and_bulgarian_calendar_dates_but_not_durations():
    text = (
        "Начало 06.10.2026 г., край 2027-01-23 и междинен етап на "
        "15 май 2027 г. Общият срок е 20 дни и 1 месец."
    )

    assert find_concrete_calendar_dates(text) == [
        "06.10.2026",
        "2027-01-23",
        "15 май 2027 г.",
    ]


def test_schedule_for_proposal_keeps_durations_and_dependencies_but_removes_dates():
    schedule = {
        "tasks": [
            {
                "uid": "1",
                "name": "Проектиране до 25.10.2026",
                "start": "06.10.2026",
                "finish": "25.10.2026",
                "duration_days": 20,
                "predecessors": "0",
            }
        ]
    }

    cleaned = schedule_for_proposal(schedule)
    task = cleaned["tasks"][0]

    assert "start" not in task
    assert "finish" not in task
    assert task["duration_days"] == 20
    assert task["predecessors"] == "0"
    assert find_concrete_calendar_dates(str(cleaned)) == []
