"""K-18 (T-22 + T-01..T-27 integrated): one deterministic v2 journey.

Real PostgreSQL, real API routes and real job bodies; only the model,
embeddings and the RQ enqueue are replaced. The journey goes from a confirmed
requirement through the content plan, the independent plan audit, drafting,
final criteria verification and consistency to the exported DOCX. A second
run deliberately drops the required content and must fail for that reason.

This is an integration test on synthetic input, not an accepted proposal.
"""

from __future__ import annotations

import io
import json
import re
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from alembic import command
from alembic.config import Config
from docx import Document
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.config import settings

API_DIR = Path(__file__).resolve().parents[1]

CHUNK_TEXT = (
    "Участникът описва организацията на изпълнението. "
    "Ръководителят на екипа организира седмичен контрол на качеството "
    "и съставя протокол за всяка проверка."
)
REQUIRED_QUOTE = (
    "Ръководителят на екипа организира седмичен контрол на качеството "
    "и съставя протокол за всяка проверка."
)
CRITERION = "Ръководителят на екипа организира седмичен контрол на качеството и съставя протокол за всяка проверка."
EVIDENCE = "Ръководителят на екипа организира седмичен контрол на качеството"

FILLER = [
    "Екипът разпределя отговорностите между експертите по части и дейности.",
    "Всеки експерт проверява входящите документи и отбелязва установените несъответствия.",
    "Техническият ръководител координира изпълнението и докладва напредъка на възложителя.",
    "Отговорното лице води дневник на дейностите и съхранява всички документи по поръчката.",
    "При установено отклонение отговорникът организира коригиращо действие и проверява резултата.",
    "Комуникацията с възложителя се осъществява писмено чрез определено контактно лице.",
    "Документите се предават с приемо-предавателен протокол, подписан от двете страни.",
    "Рисковете се преглеждат редовно и за всеки риск се определя мярка и отговорник.",
]


def _complete_text() -> str:
    sentences = [
        f"{REQUIRED_QUOTE} Протоколът от проверката се подписва от ръководителя и се съхранява в документацията."
    ]
    while len(" ".join(sentences).split()) < 320:
        sentences.extend(FILLER)
    return " ".join(sentences)


def _omitted_text() -> str:
    # Same length and style, but the required weekly quality control is absent.
    sentences: list[str] = []
    while len(" ".join(sentences).split()) < 320:
        sentences.extend(FILLER[:3])
    return " ".join(sentences)


@pytest.fixture(scope="module", autouse=True)
def _migrated_session_database():
    command.upgrade(Config(str(API_DIR / "alembic.ini")), "head")


@pytest.fixture
async def journey(monkeypatch):
    monkeypatch.setattr(settings, "generation_pipeline", "v2")
    monkeypatch.setattr(settings, "plan_audit_required", True)
    monkeypatch.setattr(settings, "lex_bg_auto_refresh_enabled", False)
    monkeypatch.setattr(settings, "llm_role_policy_mode", "legacy")

    from app.core.database import engine
    from app.main import app

    enqueued: dict[str, list[str]] = {"audit": [], "generation": [], "criteria": [], "consistency": []}

    class FakeQueue:
        def __init__(self, *args, **kwargs):
            pass

        def enqueue(self, func, *args, **kwargs):
            enqueued["audit"].append(args[0])

    patches = [
        patch("rq.Queue", FakeQueue),
        patch("redis.Redis.from_url", lambda *a, **k: None),
        patch("app.agents.generation_jobs._enqueue_generation_job", lambda job_id: enqueued["generation"].append(job_id)),
        patch("app.agents.criteria_verifier.enqueue_criteria_job", lambda job_id: enqueued["criteria"].append(job_id)),
        patch("app.agents.consistency.enqueue_consistency_job", lambda job_id: enqueued["consistency"].append(job_id)),
        patch("app.core.embedding.embed_query", AsyncMock(return_value=[])),
    ]
    for item in patches:
        item.start()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://it") as client:
        yield client, enqueued
    for item in reversed(patches):
        item.stop()
    await engine.dispose()


def _fake_model(text_to_write: str, plan_item_ids: list[str]):
    calls: list[str] = []

    async def fake_call(**kwargs):
        agent = kwargs.get("agent")
        calls.append(agent)
        message = kwargs.get("user_message") or ""
        if agent == "plan_audit_extract":
            chunks = json.loads(message.split("\n", 1)[1].rsplit("\n", 1)[0])
            chunk = next(c for c in chunks if REQUIRED_QUOTE in c["text"])
            return {
                "obligations": [
                    {"source_chunk_id": chunk["chunk_id"], "quote": REQUIRED_QUOTE, "kind": "obligation", "text": CRITERION}
                ],
                "uncertainties": [],
            }
        if agent == "plan_audit_compare":
            ids = re.findall(r'"(A\d+)"', message)
            return {
                "findings": [
                    {"inventory_id": inv, "plan_item_ids": plan_item_ids, "verdict": "covered", "rationale": "Точката съдържа задължението.", "required_correction": ""}
                    for inv in dict.fromkeys(ids)
                ],
                "plan_additions": [],
            }
        if agent == "drafting":
            return {"variant_1": {"text": text_to_write, "change_summary": "", "evidence_map": {}, "requirement_coverage": []}, "flags": []}
        if agent == "criteria_verifier":
            criteria = json.loads(message.split("КРИТЕРИИ ЗА ПРИЕМАНЕ:\n", 1)[1].split("\n\nГЕНЕРИРАН ТЕКСТ", 1)[0])
            present = EVIDENCE in message
            return {
                "checks": [
                    {"criterion_id": c["id"], "verdict": "covered" if present else "missing", "evidence": EVIDENCE if present else "", "note": ""}
                    for c in criteria
                ],
                "unsupported_commitments": [],
            }
        if agent == "consistency_claims":
            return {"claims": []}
        if agent == "consistency_conflicts":
            return {"conflicts": []}
        raise AssertionError(f"unexpected model call: {agent}")

    return fake_call, calls


async def _seed_project(client) -> tuple[str, str]:
    from app.core.database import AsyncSessionLocal
    from app.core.models import ExtractedChunk, ProjectFile

    response = await client.post("/api/v1/projects", json={"name": "Интеграционен проект", "location": "Перник"})
    assert response.status_code == 201, response.text
    project_id = response.json()["id"]
    async with AsyncSessionLocal() as db:
        # Ingestion (MinIO/OCR) is outside this test; the file is seeded as ingested.
        tender = ProjectFile(
            project_id=project_id, module="tender_docs", filename="tender.docx",
            storage_key="it/tender.docx", file_hash="it-hash", ingest_status="done",
            ingest_quality_status="ok", ingest_report_json={"quality_status": "ok"},
        )
        db.add(tender)
        await db.flush()
        db.add(ExtractedChunk(project_id=project_id, file_id=tender.id, chunk_type="text", text=CHUNK_TEXT, page=3))
        await db.commit()
        return project_id, tender.id


async def _run_journey(client, enqueued, text_to_write):
    from app.agents.consistency import _process_consistency_job_async
    from app.agents.criteria_verifier import _process_criteria_job_async
    from app.agents.generation_jobs import _process_generation_job_async
    from app.agents.plan_audit import _process_plan_audit_job_async
    from app.core.database import AsyncSessionLocal
    from app.core.models import ContentPlanItem

    project_id, file_id = await _seed_project(client)

    # 1. Durable, confirmed inputs.
    response = await client.post(f"/api/v1/understanding/{project_id}/requirements", json={
        "source_file_id": file_id, "source_page": 3, "source_quote": REQUIRED_QUOTE,
        "normalized_text": CRITERION, "kind": "obligation", "scope": "proposal_content",
        "proposal_path_json": ["Програма за организация и изпълнение на поръчката", "Организация на контрола на качеството"],
        "acceptance_criteria_json": [CRITERION], "status": "confirmed",
    })
    assert response.is_success, response.text
    response = await client.put(f"/api/v1/understanding/{project_id}/fact-sheet", json={"facts_json": {"subject": "Проектиране"}, "status": "confirmed"})
    assert response.is_success, response.text

    # 2. Content plan and approval.
    response = await client.post(f"/api/v1/content-plan/{project_id}/build")
    assert response.is_success, response.text
    response = await client.post(f"/api/v1/content-plan/{project_id}/approve")
    assert response.is_success, response.text

    # 3. Drafting is refused before the independent audit passes.
    response = await client.post(f"/api/v1/agents/{project_id}/generation-jobs/retry")
    assert response.status_code == 409, response.text

    async with AsyncSessionLocal() as db:
        leaves = (await db.execute(
            select(ContentPlanItem).where(ContentPlanItem.project_id == project_id, ContentPlanItem.generation_uid.is_not(None))
        )).scalars().all()
    assert leaves, "the plan must have a draftable point"
    fake_call, calls = _fake_model(text_to_write, [leaf.id for leaf in leaves])

    with patch("app.core.llm_gateway.llm_gateway.call", new=fake_call):
        # 4. Independent plan audit.
        response = await client.post(f"/api/v1/plan-audit/{project_id}/jobs")
        assert response.is_success, response.text
        await _process_plan_audit_job_async(enqueued["audit"][-1])
        audit = (await client.get(f"/api/v1/plan-audit/{project_id}")).json()
        assert json.dumps(audit, ensure_ascii=False).count('"passed"') >= 1, audit

        # 5. Drafting against the frozen inputs.
        response = await client.post(f"/api/v1/agents/{project_id}/generation-jobs/retry")
        assert response.is_success, response.text
        await _process_generation_job_async(enqueued["generation"][-1])

        # 6. Final verification of the exact exported text.
        response = await client.post(f"/api/v1/criteria/{project_id}/jobs")
        assert response.is_success, response.text
        await _process_criteria_job_async(enqueued["criteria"][-1])
        response = await client.post(f"/api/v1/consistency/{project_id}/jobs")
        assert response.is_success, response.text
        await _process_consistency_job_async(enqueued["consistency"][-1])

    readiness = (await client.get(f"/api/v1/export/{project_id}/readiness")).json()
    docx = await client.get(f"/api/v1/export/{project_id}/docx")
    return project_id, readiness, docx, calls


async def test_full_v2_journey_reaches_a_verified_docx(journey):
    client, enqueued = journey
    project_id, readiness, docx, calls = await _run_journey(client, enqueued, _complete_text())

    assert {"plan_audit_extract", "plan_audit_compare", "drafting", "criteria_verifier"} <= set(calls)
    assert readiness["ready"] is True, readiness["blockers"]
    assert docx.status_code == 200, docx.text[:500]
    document = Document(io.BytesIO(docx.content))
    body = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert REQUIRED_QUOTE in body

    criteria = (await client.get(f"/api/v1/criteria/{project_id}")).json()
    assert criteria["totals"]["covered"] == criteria["totals"]["total"] >= 1
    consistency = (await client.get(f"/api/v1/consistency/{project_id}")).json()
    assert consistency["stale"] is False


async def test_journey_fails_when_the_required_content_is_removed(journey):
    client, enqueued = journey
    _project_id, readiness, docx, _calls = await _run_journey(client, enqueued, _omitted_text())

    codes = {blocker["code"] for blocker in readiness["blockers"]}
    assert readiness["ready"] is False
    # The writer omitted the required control. Drafting's safety net appends
    # the missing commitment as template text, which is never exportable
    # without human review; otherwise the verifier reports it unmet.
    assert codes & {"auto_assurance_text", "criteria_unmet"}, codes
    assert docx.status_code == 409
