"""add generation selected field

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-19

Добавя колона `selected` (boolean, default false) към таблица generations.
Позволява потребителят да закрепи кой вариант (1 или 2) да влезе в .docx експорта.
"""

from alembic import op
import sqlalchemy as sa

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "generations",
        sa.Column("selected", sa.Boolean(), server_default="false", nullable=False),
    )
    # Композитен индекс за бърза заявка по project + section + selected
    op.create_index(
        "ix_generations_selected",
        "generations",
        ["project_id", "section_uid", "selected"],
    )


def downgrade() -> None:
    op.drop_index("ix_generations_selected", table_name="generations")
    op.drop_column("generations", "selected")
