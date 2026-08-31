"""add generation hierarchy metadata

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-08-31
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "e1f2a3b4c5d6"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "generations",
        sa.Column(
            "generation_kind",
            sa.String(length=24),
            nullable=False,
            server_default="section",
        ),
    )
    op.add_column(
        "generations",
        sa.Column(
            "parent_section_uid",
            postgresql.UUID(as_uuid=False),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_generations_parent_section_uid",
        "generations",
        ["project_id", "parent_section_uid"],
    )


def downgrade() -> None:
    op.drop_index("ix_generations_parent_section_uid", table_name="generations")
    op.drop_column("generations", "parent_section_uid")
    op.drop_column("generations", "generation_kind")
