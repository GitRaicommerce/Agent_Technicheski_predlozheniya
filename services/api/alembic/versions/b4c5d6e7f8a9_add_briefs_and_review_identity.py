"""add project briefs and requirement review identity

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-09-25
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "b4c5d6e7f8a9"
down_revision = "a3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # K-11: durable, versioned project brief.
    op.create_table(
        "project_briefs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_project_briefs_project_version",
        "project_briefs",
        ["project_id", "version"],
        unique=True,
    )
    # K-07: stable identity and preserved human decisions. Additive, nullable.
    op.add_column(
        "requirement_register",
        sa.Column("identity_key", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "requirement_register",
        sa.Column("human_decision_json", postgresql.JSONB(), nullable=True),
    )
    op.create_index(
        "ix_requirement_register_identity",
        "requirement_register",
        ["project_id", "identity_key"],
    )


def downgrade() -> None:
    op.drop_index("ix_requirement_register_identity", table_name="requirement_register")
    op.drop_column("requirement_register", "human_decision_json")
    op.drop_column("requirement_register", "identity_key")
    op.drop_index("ix_project_briefs_project_version", table_name="project_briefs")
    op.drop_table("project_briefs")
