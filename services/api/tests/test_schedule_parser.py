from app.ingestion.schedule_parser import _tasks_from_pdf_tables, schedule_quality


def test_pdf_table_rows_become_structured_schedule_tasks():
    tables = [[
        ["ID", "Вид дейност", "Срок", "Начало", "Край", "Ресурси", "Последователност"],
        ["0", "Общо изпълнение", "110 days", "Mon 6.10.25", "Fri 23.1.26", "", ""],
        [None, None, None, None, None, None, None],
        ["1", "Изготвяне на инвестиционен проект", "20 days", "Mon 6.10.25", "Sat 25.10.25", "Проектант", ""],
        ["2", "Получаване на възлагателно писмо", "0 days", "Mon 6.10.25", "Mon 6.10.25", "", "1"],
    ]]

    tasks = _tasks_from_pdf_tables(tables)

    assert [task["uid"] for task in tasks] == [0, 1, 2]
    assert tasks[0]["duration_days"] == 110
    assert tasks[1]["resources"] == "Проектант"
    assert tasks[2]["predecessors"] == "1"
    assert schedule_quality({"tasks": tasks, "source_quality": "structured_pdf_table"})["reliable"] is True


def test_legacy_one_block_pdf_schedule_is_not_reliable():
    quality = schedule_quality({
        "tasks": [{
            "uid": 1,
            "name": "ID Вид дейност Срок Начало Край",
            "start": None,
            "finish": None,
            "duration_days": None,
            "note": "extracted_from_pdf_text",
        }]
    })

    assert quality["reliable"] is False
    assert quality["task_count"] == 1
    assert any("един запис" in reason for reason in quality["reasons"])
