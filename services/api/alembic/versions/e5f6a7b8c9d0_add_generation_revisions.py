"""add generation revision metadata

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-17
"""

from alembic import op
import sqlalchemy as sa


revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "generations",
        sa.Column("revision_number", sa.Integer(), nullable=True),
    )
    op.add_column(
        "generations",
        sa.Column("change_summary", sa.Text(), nullable=True),
    )
    op.execute(
        """
        WITH numbered AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY project_id, section_uid
                       ORDER BY created_at ASC, id ASC
                   ) AS revision_number
            FROM generations
        )
        UPDATE generations AS generation
        SET revision_number = numbered.revision_number
        FROM numbered
        WHERE generation.id = numbered.id
        """
    )
    op.alter_column("generations", "revision_number", nullable=False)
    op.create_unique_constraint(
        "uq_generations_project_section_revision",
        "generations",
        ["project_id", "section_uid", "revision_number"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_generations_project_section_revision",
        "generations",
        type_="unique",
    )
    op.drop_column("generations", "change_summary")
    op.drop_column("generations", "revision_number")
