"""add drafting guidance to content plan items

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-09-25
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "a3b4c5d6e7f8"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Additive and nullable: existing plans keep working unchanged.
    op.add_column(
        "content_plan_items",
        sa.Column("drafting_guidance_json", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("content_plan_items", "drafting_guidance_json")
