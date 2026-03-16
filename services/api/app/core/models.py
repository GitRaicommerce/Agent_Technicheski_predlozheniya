"""
SQLAlchemy модели по спецификация v1.3 раздел 7.5
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    location: Mapped[Optional[str]] = mapped_column(String(512))
    description: Mapped[Optional[str]] = mapped_column(Text)
    contracting_authority: Mapped[Optional[str]] = mapped_column(String(512))
    tender_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    profile_json: Mapped[Optional[dict]] = mapped_column(JSONB)  # Project Profile
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    files: Mapped[list[ProjectFile]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    tp_outlines: Mapped[list[TpOutline]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    schedule_snapshots: Mapped[list[ScheduleSnapshot]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    lex_snapshots: Mapped[list[LexSnapshot]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    generations: Mapped[list[Generation]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class ProjectFile(Base):
    __tablename__ = "project_files"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    project_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("projects.id", ondelete="CASCADE")
    )
    module: Mapped[str] = mapped_column(
        String(32)
    )  # examples|tender_docs|schedule|legislation
    filename: Mapped[str] = mapped_column(String(512))
    storage_key: Mapped[str] = mapped_column(String(1024))
    file_hash: Mapped[Optional[str]] = mapped_column(String(64))
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    ingest_status: Mapped[str] = mapped_column(
        String(32), default="pending"
    )  # pending|processing|done|error
    ingest_error: Mapped[Optional[str]] = mapped_column(Text)

    project: Mapped[Project] = relationship(back_populates="files")
    chunks: Mapped[list[ExtractedChunk]] = relationship(
        back_populates="file", cascade="all, delete-orphan"
    )


class ExtractedChunk(Base):
    __tablename__ = "extracted_chunks"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    project_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("projects.id", ondelete="CASCADE")
    )
    file_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("project_files.id", ondelete="CASCADE")
    )
    chunk_type: Mapped[str] = mapped_column(String(32))  # text|table|heading
    text: Mapped[str] = mapped_column(Text)
    page: Mapped[Optional[int]] = mapped_column(Integer)
    section_path: Mapped[Optional[str]] = mapped_column(String(1024))
    # embedding stored via pgvector — added via migration
    meta_json: Mapped[Optional[dict]] = mapped_column(JSONB)

    file: Mapped[ProjectFile] = relationship(back_populates="chunks")


class ExampleSnippet(Base):
    __tablename__ = "example_snippets"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    project_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("projects.id", ondelete="CASCADE")
    )
    file_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("project_files.id", ondelete="CASCADE")
    )
    chunk_id: Mapped[str] = mapped_column(UUID(as_uuid=False))
    text: Mapped[str] = mapped_column(Text)
    snippet_kind: Mapped[str] = mapped_column(
        String(32)
    )  # generic_boilerplate|context_specific
    topics_json: Mapped[Optional[dict]] = mapped_column(JSONB)
    applicability_rules_json: Mapped[Optional[dict]] = mapped_column(JSONB)
    risk_flags_json: Mapped[Optional[dict]] = mapped_column(JSONB)
    source_group: Mapped[Optional[str]] = mapped_column(
        String(64)
    )  # design|engineering|construction_wss|construction_roads


class TpOutline(Base):
    __tablename__ = "tp_outlines"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    project_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("projects.id", ondelete="CASCADE")
    )
    outline_json: Mapped[dict] = mapped_column(JSONB)
    status_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[Optional[str]] = mapped_column(String(256))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    project: Mapped[Project] = relationship(back_populates="tp_outlines")


class ScheduleSnapshot(Base):
    __tablename__ = "schedule_snapshots"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    project_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("projects.id", ondelete="CASCADE")
    )
    file_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("project_files.id", ondelete="CASCADE")
    )
    file_hash: Mapped[str] = mapped_column(String(64))
    extracted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    parser_version: Mapped[str] = mapped_column(String(32))

    project: Mapped[Project] = relationship(back_populates="schedule_snapshots")
    normalized: Mapped[list[ScheduleNormalized]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )
    mpp_tasks: Mapped[list[ScheduleMppTask]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )
    mpp_resources: Mapped[list[ScheduleMppResource]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )
    mpp_assignments: Mapped[list[ScheduleMppAssignment]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )


class ScheduleNormalized(Base):
    __tablename__ = "schedule_normalized"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    project_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("projects.id", ondelete="CASCADE")
    )
    schedule_snapshot_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("schedule_snapshots.id", ondelete="CASCADE")
    )
    schedule_json: Mapped[dict] = mapped_column(JSONB)
    status_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[Optional[str]] = mapped_column(String(256))
    version: Mapped[int] = mapped_column(Integer, default=1)

    snapshot: Mapped[ScheduleSnapshot] = relationship(back_populates="normalized")


class ScheduleMppTask(Base):
    __tablename__ = "schedule_mpp_tasks"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    project_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("projects.id", ondelete="CASCADE")
    )
    schedule_snapshot_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("schedule_snapshots.id", ondelete="CASCADE")
    )
    mpp_task_uid: Mapped[int] = mapped_column(Integer)
    raw_json: Mapped[dict] = mapped_column(JSONB)

    snapshot: Mapped[ScheduleSnapshot] = relationship(back_populates="mpp_tasks")


class ScheduleMppResource(Base):
    __tablename__ = "schedule_mpp_resources"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    project_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("projects.id", ondelete="CASCADE")
    )
    schedule_snapshot_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("schedule_snapshots.id", ondelete="CASCADE")
    )
    mpp_resource_uid: Mapped[int] = mapped_column(Integer)
    raw_json: Mapped[dict] = mapped_column(JSONB)

    snapshot: Mapped[ScheduleSnapshot] = relationship(back_populates="mpp_resources")


class ScheduleMppAssignment(Base):
    __tablename__ = "schedule_mpp_assignments"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    project_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("projects.id", ondelete="CASCADE")
    )
    schedule_snapshot_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("schedule_snapshots.id", ondelete="CASCADE")
    )
    mpp_assignment_uid: Mapped[int] = mapped_column(Integer)
    raw_json: Mapped[dict] = mapped_column(JSONB)

    snapshot: Mapped[ScheduleSnapshot] = relationship(back_populates="mpp_assignments")


class LexSnapshot(Base):
    __tablename__ = "lex_snapshots"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    project_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("projects.id", ondelete="CASCADE")
    )
    act_name: Mapped[str] = mapped_column(String(512))
    lex_url: Mapped[str] = mapped_column(String(2048))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    snapshot_id: Mapped[str] = mapped_column(UUID(as_uuid=False), default=_uuid)
    content_hash: Mapped[str] = mapped_column(String(64))
    parser_version: Mapped[str] = mapped_column(String(32))
    storage_key_raw: Mapped[Optional[str]] = mapped_column(String(1024))
    storage_key_normalized: Mapped[Optional[str]] = mapped_column(String(1024))

    project: Mapped[Project] = relationship(back_populates="lex_snapshots")
    chunks: Mapped[list[LexChunk]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )


class LexChunk(Base):
    __tablename__ = "lex_chunks"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    project_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("projects.id", ondelete="CASCADE")
    )
    snapshot_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("lex_snapshots.snapshot_id", ondelete="CASCADE")
    )
    act_name: Mapped[str] = mapped_column(String(512))
    article_ref: Mapped[str] = mapped_column(String(256))
    text: Mapped[str] = mapped_column(Text)
    # embedding via pgvector — added via migration

    snapshot: Mapped[LexSnapshot] = relationship(back_populates="chunks")


class Generation(Base):
    __tablename__ = "generations"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    project_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("projects.id", ondelete="CASCADE")
    )
    section_uid: Mapped[str] = mapped_column(UUID(as_uuid=False))
    variant: Mapped[str] = mapped_column(String(16))  # 1|2
    text: Mapped[str] = mapped_column(Text)
    evidence_map_json: Mapped[Optional[dict]] = mapped_column(JSONB)
    used_sources_json: Mapped[Optional[dict]] = mapped_column(JSONB)
    flags_json: Mapped[Optional[dict]] = mapped_column(JSONB)
    evidence_status: Mapped[str] = mapped_column(String(16), default="ok")  # ok|stale
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    trace_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False))

    project: Mapped[Project] = relationship(back_populates="generations")
