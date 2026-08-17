"""add phase 2 content plan items

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-08-17
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d0e1f2a3b4c5"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "content_plan_items",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "outline_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("tp_outlines.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("content_plan_items.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("uid", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("number", sa.String(32), nullable=False),
        sa.Column("title", sa.String(1024), nullable=False),
        sa.Column(
            "source_quotes_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "acceptance_criteria_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("content_kind", sa.String(16), nullable=False, server_default="mixed"),
        sa.Column(
            "linked_wbs_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "linked_fact_keys",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("forlage_section_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("generation_uid", postgresql.UUID(as_uuid=False), nullable=True),
        sa.CheckConstraint(
            "content_kind IN ('reuse','specific','mixed')",
            name="ck_content_plan_items_content_kind",
        ),
        sa.CheckConstraint(
            "status IN ('draft','approved')",
            name="ck_content_plan_items_status",
        ),
        sa.UniqueConstraint("outline_id", "uid", name="uq_content_plan_outline_uid"),
    )
    op.create_index(
        "ix_content_plan_items_project_id", "content_plan_items", ["project_id"]
    )
    op.create_index(
        "ix_content_plan_items_outline_id", "content_plan_items", ["outline_id"]
    )
    op.create_index(
        "ix_content_plan_items_parent_id", "content_plan_items", ["parent_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_content_plan_items_parent_id", table_name="content_plan_items")
    op.drop_index("ix_content_plan_items_outline_id", table_name="content_plan_items")
    op.drop_index("ix_content_plan_items_project_id", table_name="content_plan_items")
    op.drop_table("content_plan_items")
