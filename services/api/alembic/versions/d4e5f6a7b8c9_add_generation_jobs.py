"""add generation jobs

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-08
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "generation_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("job_type", sa.String(32), nullable=False, server_default="drafting_all"),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("total_sections", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_sections", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_sections", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_section_uid", sa.String(128), nullable=True),
        sa.Column("current_section_title", sa.String(1024), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("result_json", postgresql.JSONB, nullable=True),
        sa.Column("trace_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_generation_jobs_project_created",
        "generation_jobs",
        ["project_id", "created_at"],
    )
    op.create_index(
        "ix_generation_jobs_project_status",
        "generation_jobs",
        ["project_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_generation_jobs_project_status", table_name="generation_jobs")
    op.drop_index("ix_generation_jobs_project_created", table_name="generation_jobs")
    op.drop_table("generation_jobs")
