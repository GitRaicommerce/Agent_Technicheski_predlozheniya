"""add understanding artifacts

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-08-03
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "requirement_register",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_file_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("project_files.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_page", sa.Integer(), nullable=True),
        sa.Column("source_quote", sa.Text(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("target_section_hint", sa.String(1024), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="extracted"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "kind IN ('obligation','prohibition','format','content','evaluation')",
            name="ck_requirement_register_kind",
        ),
        sa.CheckConstraint(
            "status IN ('extracted','confirmed','rejected')",
            name="ck_requirement_register_status",
        ),
    )
    op.create_index(
        "ix_requirement_register_project_status",
        "requirement_register",
        ["project_id", "status"],
    )

    op.create_table(
        "wbs_items",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("wbs_items.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("level", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("title", sa.String(1024), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "source_refs_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("schedule_task_uid", sa.String(128), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="extracted"),
        sa.CheckConstraint(
            "kind IN ('etap','activity','subactivity','task')",
            name="ck_wbs_items_kind",
        ),
        sa.CheckConstraint(
            "status IN ('extracted','confirmed','rejected')",
            name="ck_wbs_items_status",
        ),
    )
    op.create_index(
        "ix_wbs_items_project_order",
        "wbs_items",
        ["project_id", "order_index"],
    )

    op.create_table(
        "project_fact_sheet",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "facts_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.CheckConstraint(
            "status IN ('draft','confirmed')",
            name="ck_project_fact_sheet_status",
        ),
        sa.UniqueConstraint(
            "project_id", "version", name="uq_project_fact_sheet_project_version"
        ),
    )
    op.create_index(
        "ix_project_fact_sheet_project_version",
        "project_fact_sheet",
        ["project_id", "version"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_project_fact_sheet_project_version", table_name="project_fact_sheet"
    )
    op.drop_table("project_fact_sheet")
    op.drop_index("ix_wbs_items_project_order", table_name="wbs_items")
    op.drop_table("wbs_items")
    op.drop_index(
        "ix_requirement_register_project_status", table_name="requirement_register"
    )
    op.drop_table("requirement_register")
