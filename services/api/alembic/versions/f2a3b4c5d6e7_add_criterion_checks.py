"""add criterion checks table

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-09-14
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "criterion_checks",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "generation_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("generations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("section_uid", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("criterion_id", sa.String(length=64), nullable=False),
        sa.Column("criterion_text", sa.Text(), nullable=False),
        sa.Column(
            "criterion_kind",
            sa.String(length=32),
            nullable=False,
            server_default="content",
        ),
        sa.Column("requirement_id", sa.String(length=64), nullable=True),
        sa.Column("source_quote", sa.Text(), nullable=True),
        sa.Column("verdict", sa.String(length=16), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("trace_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_criterion_checks_project_section",
        "criterion_checks",
        ["project_id", "section_uid"],
    )
    op.create_index(
        "ix_criterion_checks_generation",
        "criterion_checks",
        ["generation_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_criterion_checks_generation", table_name="criterion_checks")
    op.drop_index(
        "ix_criterion_checks_project_section", table_name="criterion_checks"
    )
    op.drop_table("criterion_checks")
