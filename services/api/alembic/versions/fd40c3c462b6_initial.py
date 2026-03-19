"""initial schema

Revision ID: fd40c3c462b6
Revises:
Create Date: 2026-03-01

Създава всички базови таблици за TP AI Assistant.
Vector колоните (embeddings) се добавят в миграция a1b2c3d4e5f6.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "fd40c3c462b6"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("location", sa.String(512), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("contracting_authority", sa.String(512), nullable=True),
        sa.Column("tender_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("profile_json", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "project_files",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("module", sa.String(32), nullable=False),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("storage_key", sa.String(1024), nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=True),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("version", sa.Integer, server_default="1", nullable=False),
        sa.Column(
            "ingest_status", sa.String(32), server_default="pending", nullable=False
        ),
        sa.Column("ingest_error", sa.Text, nullable=True),
    )
    op.create_index("ix_project_files_project_id", "project_files", ["project_id"])

    op.create_table(
        "extracted_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "file_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("project_files.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_type", sa.String(32), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("page", sa.Integer, nullable=True),
        sa.Column("section_path", sa.String(1024), nullable=True),
        sa.Column("meta_json", postgresql.JSONB, nullable=True),
    )
    op.create_index(
        "ix_extracted_chunks_project_id", "extracted_chunks", ["project_id"]
    )

    op.create_table(
        "example_snippets",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "file_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("project_files.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("snippet_kind", sa.String(32), nullable=False),
        sa.Column("topics_json", postgresql.JSONB, nullable=True),
        sa.Column("applicability_rules_json", postgresql.JSONB, nullable=True),
        sa.Column("risk_flags_json", postgresql.JSONB, nullable=True),
        sa.Column("source_group", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_example_snippets_project_id", "example_snippets", ["project_id"]
    )

    op.create_table(
        "tp_outlines",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("outline_json", postgresql.JSONB, nullable=False),
        sa.Column("status_locked", sa.Boolean, server_default="false", nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.String(256), nullable=True),
        sa.Column("version", sa.Integer, server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "schedule_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "file_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("project_files.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("file_hash", sa.String(64), nullable=False),
        sa.Column(
            "extracted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("parser_version", sa.String(32), nullable=False),
    )

    op.create_table(
        "schedule_normalized",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "schedule_snapshot_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("schedule_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("schedule_json", postgresql.JSONB, nullable=False),
        sa.Column("status_locked", sa.Boolean, server_default="false", nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.String(256), nullable=True),
        sa.Column("version", sa.Integer, server_default="1", nullable=False),
    )

    op.create_table(
        "schedule_mpp_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "schedule_snapshot_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("schedule_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("mpp_task_uid", sa.Integer, nullable=False),
        sa.Column("raw_json", postgresql.JSONB, nullable=False),
    )

    op.create_table(
        "schedule_mpp_resources",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "schedule_snapshot_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("schedule_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("mpp_resource_uid", sa.Integer, nullable=False),
        sa.Column("raw_json", postgresql.JSONB, nullable=False),
    )

    op.create_table(
        "schedule_mpp_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "schedule_snapshot_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("schedule_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("mpp_assignment_uid", sa.Integer, nullable=False),
        sa.Column("raw_json", postgresql.JSONB, nullable=False),
    )

    op.create_table(
        "lex_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("act_name", sa.String(512), nullable=False),
        sa.Column("lex_url", sa.String(2048), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "snapshot_id", postgresql.UUID(as_uuid=False), nullable=False, unique=True
        ),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("parser_version", sa.String(32), nullable=False),
        sa.Column("storage_key_raw", sa.String(1024), nullable=True),
        sa.Column("storage_key_normalized", sa.String(1024), nullable=True),
    )

    op.create_table(
        "lex_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "snapshot_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("lex_snapshots.snapshot_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("act_name", sa.String(512), nullable=False),
        sa.Column("article_ref", sa.String(256), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
    )
    op.create_index("ix_lex_chunks_snapshot_id", "lex_chunks", ["snapshot_id"])

    op.create_table(
        "generations",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("section_uid", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("variant", sa.String(16), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("evidence_map_json", postgresql.JSONB, nullable=True),
        sa.Column("used_sources_json", postgresql.JSONB, nullable=True),
        sa.Column("flags_json", postgresql.JSONB, nullable=True),
        sa.Column(
            "evidence_status", sa.String(16), server_default="ok", nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("trace_id", postgresql.UUID(as_uuid=False), nullable=True),
    )
    op.create_index("ix_generations_project_id", "generations", ["project_id"])
    op.create_index(
        "ix_generations_section_uid", "generations", ["project_id", "section_uid"]
    )


def downgrade() -> None:
    op.drop_table("generations")
    op.drop_table("lex_chunks")
    op.drop_table("lex_snapshots")
    op.drop_table("schedule_mpp_assignments")
    op.drop_table("schedule_mpp_resources")
    op.drop_table("schedule_mpp_tasks")
    op.drop_table("schedule_normalized")
    op.drop_table("schedule_snapshots")
    op.drop_table("tp_outlines")
    op.drop_table("example_snippets")
    op.drop_table("extracted_chunks")
    op.drop_table("project_files")
    op.drop_table("projects")
