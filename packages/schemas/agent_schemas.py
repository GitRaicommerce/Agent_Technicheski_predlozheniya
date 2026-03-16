"""
Pydantic схеми за агентски отговори (v1.3)
Всеки агент връща САМО един валиден JSON обект.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field
import uuid


SCHEMA_VERSION = "v1.3"


# ─── Общи типове ─────────────────────────────────────────────────────────────


class AgentName(str, Enum):
    orchestrator = "orchestrator"
    examples = "examples"
    tender_struct = "tender_struct"
    schedule = "schedule"
    legislation = "legislation"
    drafting = "drafting"
    verifier = "verifier"


class ResponseStatus(str, Enum):
    ok = "ok"
    needs_confirmation = "needs_confirmation"
    needs_user_action = "needs_user_action"
    error = "error"


class SnippetKind(str, Enum):
    generic_boilerplate = "generic_boilerplate"
    context_specific = "context_specific"


class EvidenceStatus(str, Enum):
    ok = "ok"
    stale = "stale"


class SectionOrigin(str, Enum):
    tender_required = "tender_required"
    tender_inferred = "tender_inferred"
    template = "template"
    user_added = "user_added"


# ─── 8.0 Оркестратор output ──────────────────────────────────────────────────


class UiAction(BaseModel):
    type: str  # show_outline|show_schedule|show_draft|show_warnings|ask_confirmation
    payload: dict[str, Any] = Field(default_factory=dict)


class OrchestratorOutput(BaseModel):
    schema_version: str = SCHEMA_VERSION
    status: ResponseStatus
    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    assistant_message: str
    ui_actions: list[UiAction] = Field(default_factory=list)
    agent_called: Optional[AgentName] = None
    questions_to_user: list[str] = Field(default_factory=list)


# ─── 8.1 Агентен wrapper ─────────────────────────────────────────────────────


class AgentRequest(BaseModel):
    schema_version: str = SCHEMA_VERSION
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    agent: AgentName
    action: str
    payload: dict[str, Any] = Field(default_factory=dict)


# ─── 8.3 Tender Structure Agent ──────────────────────────────────────────────


class OutlineSection(BaseModel):
    section_uid: str = Field(default_factory=lambda: str(uuid.uuid4()))
    display_numbering: str
    title: str
    origin: SectionOrigin
    parent_uid: Optional[str] = None
    children: list["OutlineSection"] = Field(default_factory=list)


class TenderStructureOutput(BaseModel):
    schema_version: str = SCHEMA_VERSION
    status: ResponseStatus
    trace_id: str
    outline: list[OutlineSection]
    required_sources: list[str] = Field(default_factory=list)
    questions_to_user: list[str] = Field(default_factory=list)


# ─── Schedule Agent ──────────────────────────────────────────────────────────


class ScheduleTaskRef(BaseModel):
    file_id: str
    schedule_snapshot_id: str
    mpp_task_uid: int
    wbs: Optional[str] = None


class ScheduleTask(BaseModel):
    task_uid: int
    name: str
    start: Optional[str] = None
    finish: Optional[str] = None
    duration_days: Optional[float] = None
    resources: list[str] = Field(default_factory=list)
    source_ref: ScheduleTaskRef


class ScheduleAgentOutput(BaseModel):
    schema_version: str = SCHEMA_VERSION
    status: ResponseStatus
    trace_id: str
    tasks: list[ScheduleTask]
    errors: list[str] = Field(default_factory=list)
    actions_required: list[str] = Field(default_factory=list)


# ─── Examples Agent ──────────────────────────────────────────────────────────


class ExampleCandidate(BaseModel):
    chunk_id: str
    snippet_kind: SnippetKind
    topics: list[str]
    source_group: str
    reason: str
    rules_passed: bool = False


class ExamplesAgentOutput(BaseModel):
    schema_version: str = SCHEMA_VERSION
    status: ResponseStatus
    trace_id: str
    candidates: list[ExampleCandidate]
    template_recommendation: Optional[str] = None


# ─── Legislation Agent ───────────────────────────────────────────────────────


class LexPassage(BaseModel):
    act_name: str
    article_ref: str
    snapshot_id: str
    chunk_id: str
    text: str


class LegislationAgentOutput(BaseModel):
    schema_version: str = SCHEMA_VERSION
    status: ResponseStatus
    trace_id: str
    relevant_passages: list[LexPassage]
    warnings: list[str] = Field(default_factory=list)


# ─── Drafting Agent ──────────────────────────────────────────────────────────


class EvidenceEntry(BaseModel):
    source_type: str  # schedule|tender_docs|lex|example
    source_id: str
    field: Optional[str] = None
    article_ref: Optional[str] = None
    chunk_id: Optional[str] = None


class DraftingAgentOutput(BaseModel):
    schema_version: str = SCHEMA_VERSION
    status: ResponseStatus
    trace_id: str
    section_uid: str
    text: str
    evidence_map: dict[str, list[EvidenceEntry]]  # paragraph_index -> sources
    questions_to_user: list[str] = Field(default_factory=list)


# ─── Verifier Agent ──────────────────────────────────────────────────────────


class VerifierWarning(BaseModel):
    severity: str  # critical|warning|info
    paragraph_index: Optional[int] = None
    section_uid: Optional[str] = None
    message: str
    fix_type: Optional[str] = (
        None  # regenerate|add_evidence|user_input|conflict_resolve
    )
    suggested_patch: Optional[str] = None


class VerifierAgentOutput(BaseModel):
    schema_version: str = SCHEMA_VERSION
    status: ResponseStatus
    trace_id: str
    passed: bool
    warnings: list[VerifierWarning]
    questions_to_user: list[str] = Field(default_factory=list)


OutlineSection.model_rebuild()
