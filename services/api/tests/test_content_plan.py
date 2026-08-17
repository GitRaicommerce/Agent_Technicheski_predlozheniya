from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.content_plan import (
    CONTROL_ROOT,
    FORMAL_ROOT,
    MandatoryHeading,
    PROGRAM_ROOT,
    SCHEDULE_ROOT,
    _content_kind,
    _extract_mandatory_headings,
    _heading_anchor,
    _item_outline_payload,
    _requirement_path,
)


def requirement(path, *, scope="proposal_content", **values):
    return SimpleNamespace(
        proposal_path_json=path,
        target_section_hint=values.get("target_section_hint"),
        normalized_text=values.get("normalized_text", "Изискване"),
        scope=scope,
        kind=values.get("kind", "content"),
        source_page=values.get("source_page"),
    )


@pytest.mark.parametrize(
    ("item", "expected"),
    [
        (
            requirement(["Техническо предложение", "5. Управление на риска", "Мерки"]),
            [PROGRAM_ROOT, "Управление на риска", "Мерки"],
        ),
        (
            requirement(["Техническо предложение", "Подробен линеен график", "Ресурси"]),
            [SCHEDULE_ROOT, "Ресурси"],
        ),
        (
            requirement(["Техническо предложение", "Приложения", "Образец"]),
            [FORMAL_ROOT, "Приложения", "Образец"],
        ),
        (
            requirement(["Оценка на техническото предложение", "Допустимост"], scope="evaluation_rule"),
            [CONTROL_ROOT, "Допустимост"],
        ),
    ],
)
def test_requirement_paths_consolidate_into_human_content_plan_roots(item, expected):
    assert _requirement_path(item) == expected


def test_non_proposal_roots_are_excluded_even_if_scope_is_polluted():
    assert _requirement_path(requirement(["Ценово предложение", "Обща цена"])) == []
    assert _requirement_path(requirement(["Доказателства за технически и професионални способности – услуги"])) == []


def test_outline_payload_marks_only_generatable_branches_for_document():
    structural_item = SimpleNamespace(
        uid="structural",
        number="4",
        title=CONTROL_ROOT,
        acceptance_criteria_json=[],
        source_quotes_json=[],
        content_kind="evaluation_control",
        linked_wbs_ids=[],
        linked_fact_keys=[],
        generation_uid=None,
    )
    narrative_item = SimpleNamespace(
        uid="narrative",
        number="1.1",
        title="Цялостен подход",
        acceptance_criteria_json=[],
        source_quotes_json=[],
        content_kind="proposal_content",
        linked_wbs_ids=[],
        linked_fact_keys=[],
        generation_uid="11111111-1111-1111-1111-111111111111",
    )

    structural_payload = _item_outline_payload(structural_item, [])
    narrative_payload = _item_outline_payload(narrative_item, [])
    parent_payload = _item_outline_payload(structural_item, [narrative_payload])

    assert structural_payload["include_in_document"] is False
    assert narrative_payload["include_in_document"] is True
    assert parent_payload["include_in_document"] is True


@pytest.mark.parametrize(
    ("item", "path", "expected"),
    [
        (requirement(["Управление на риска"], normalized_text="Описват се превантивни мерки", kind="content"), [PROGRAM_ROOT, "Управление на риска"], "reuse"),
        (requirement(["Обхват"], normalized_text="Обектът включва 12 проектни части", kind="content"), [PROGRAM_ROOT, "Обхват"], "specific"),
        (requirement(["Качество"], normalized_text="Контролът обхваща 12 проектни части", kind="content"), [PROGRAM_ROOT, "Качество"], "mixed"),
    ],
)
def test_content_kind_distinguishes_reuse_specific_and_mixed(item, path, expected):
    assert _content_kind(item, path) == expected


def test_extracts_exact_minimum_numbered_structure_from_tender_pages():
    pages = [
        (25, "ПОДРОБЕН ЛИНЕЕН ГРАФИК\n1. Неприложимо заглавие"),
        (26, "ПРОГРАМА ЗА ОРГАНИЗАЦИЯ И ИЗПЪЛНЕНИЕ НА ПОРЪЧКАТА\n1.Концепция и подход.\nТекст\n2.Разработване на инвестиционен проект:\n2.1. Обхват и дейности:"),
        (27, "2.2. Организация при изпълнение на проектирането с оглед\nпредвидените човешки ресурси\n2.3. Комуникация\n3. Авторски надзор\n4. Изпълнение на строително-монтажни работи\n4.1 Обхват и дейности. Технология на изпълнение"),
        (28, "4.2. Организация на ресурсите\n4.3. Комуникация\n4.4. Организация за доставка на материали\n5. Управление на риска"),
        (29, "6. Ограничаване и предотвратяване на негативното въздействие върху\nоколната среда по време на изпълнение на строителството.\n7. Мерки за осигуряване на качеството."),
        (30, "8. Организация на дейностите по отстраняване на гаранционни\nдефекти по време на гаранционния срок.\n9.Мерки за минимизиране на негативното влияние при изпълнението\nна строителството."),
    ]

    headings = _extract_mandatory_headings(pages, source_file_id="file-1")

    assert [heading.number for heading in headings] == [
        "1", "2", "2.1", "2.2", "2.3", "3", "4", "4.1", "4.2", "4.3",
        "4.4", "5", "6", "7", "8", "9",
    ]
    assert headings[3].title == "Организация при изпълнение на проектирането с оглед предвидените човешки ресурси"
    assert headings[-1].title == "Мерки за минимизиране на негативното влияние при изпълнението на строителството"


def test_semantic_heading_corrects_a_misnested_communication_path():
    headings = [
        MandatoryHeading("2.2", "Организация при изпълнение на проектирането с оглед предвидените човешки ресурси", 27, "2.2"),
        MandatoryHeading("2.3", "Комуникация", 27, "2.3"),
    ]
    item = requirement([
        "Програма за организация и изпълнение на поръчката",
        "2. Разработване на инвестиционен проект",
        "2.2. Организация при изпълнение на проектирането",
        "Комуникация, контрол и субординация",
    ])

    assert _heading_anchor(item, headings).number == "2.3"


def test_schedule_requirements_do_not_become_narrative_plan_points():
    headings = [MandatoryHeading("4", "Изпълнение на строително-монтажни работи", 27, "4")]
    item = requirement(["Техническо предложение", "Линеен график", "Предвидени дейности"])

    assert _heading_anchor(item, headings) is None


def test_parent_section_disambiguates_repeated_subpoint_titles():
    headings = [
        MandatoryHeading("2", "Разработване на инвестиционен проект", 26, "2"),
        MandatoryHeading("2.1", "Обхват и дейности", 26, "2.1"),
        MandatoryHeading("4", "Изпълнение на строително-монтажни работи", 27, "4"),
        MandatoryHeading("4.1", "Обхват и дейности. Технология на изпълнение", 27, "4.1"),
    ]
    item = requirement([
        "Програма за организация и изпълнение на поръчката",
        "Изпълнение на строително-монтажни работи",
        "Обхват, дейности и технология",
    ])

    assert _heading_anchor(item, headings).number == "4.1"


@pytest.mark.asyncio
async def test_content_plan_get_returns_null_without_phase_2_outline(client, mock_db):
    project_id = "11111111-1111-1111-1111-111111111111"
    mock_db.get.return_value = SimpleNamespace(id=project_id)
    result = SimpleNamespace()
    result.scalars = lambda: SimpleNamespace(all=lambda: [])
    result.scalar_one_or_none = lambda: None
    mock_db.execute.return_value = result

    response = await client.get(f"/api/v1/content-plan/{project_id}")

    assert response.status_code == 200
    assert response.json() is None


@pytest.mark.asyncio
async def test_mandatory_heading_title_cannot_be_changed(client, mock_db):
    project_id = "11111111-1111-1111-1111-111111111111"
    item_id = "22222222-2222-2222-2222-222222222222"
    outline_id = "33333333-3333-3333-3333-333333333333"
    item = SimpleNamespace(
        id=item_id,
        project_id=project_id,
        outline_id=outline_id,
        title="Авторски надзор",
        source_quotes_json=[{"source_kind": "mandatory_heading"}],
    )
    outline = SimpleNamespace(id=outline_id, status_locked=False)
    mock_db.get.side_effect = [item, outline]

    response = await client.put(
        f"/api/v1/content-plan/{project_id}/items/{item_id}",
        json={"title": "Друго заглавие"},
    )

    assert response.status_code == 409
    assert "задължително" in response.json()["detail"]


@pytest.mark.asyncio
async def test_orchestrator_builds_phase_2_plan_without_llm_call(mock_db):
    from app.agents.orchestrator import run_orchestrator

    project = SimpleNamespace(
        id="11111111-1111-1111-1111-111111111111",
        name="Перник",
        location="Перник",
        description=None,
        tender_date=None,
    )
    outline = SimpleNamespace(id="22222222-2222-2222-2222-222222222222", version=3)
    with (
        patch(
            "app.agents.content_plan.build_content_plan",
            new=AsyncMock(return_value=outline),
        ) as build_mock,
        patch("app.agents.orchestrator.llm_gateway.call", new=AsyncMock()) as llm_mock,
    ):
        result = await run_orchestrator(
            project=project,
            message="Създай подробен план на ТП — Phase 2",
            history=[],
            db=mock_db,
        )

    build_mock.assert_awaited_once_with(project.id, mock_db)
    llm_mock.assert_not_awaited()
    assert result["agent_called"] == "content_plan"
    assert result["ui_actions"] == [{"type": "show_outline", "payload": {}}]
