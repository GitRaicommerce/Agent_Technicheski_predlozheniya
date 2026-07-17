"""default generation revision number

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-07-17
"""

from alembic import op
import sqlalchemy as sa


revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "generations",
        "revision_number",
        existing_type=sa.Integer(),
        server_default="1",
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "generations",
        "revision_number",
        existing_type=sa.Integer(),
        server_default=None,
        existing_nullable=False,
    )
