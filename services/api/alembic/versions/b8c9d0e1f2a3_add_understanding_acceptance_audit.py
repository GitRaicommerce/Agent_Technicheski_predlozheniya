"""add understanding acceptance audit fields

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-08-03
"""

from alembic import op
import sqlalchemy as sa

revision = "b8c9d0e1f2a3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "requirement_register",
        sa.Column("origin", sa.String(16), nullable=False, server_default="map"),
    )
    op.drop_constraint(
        "ck_requirement_register_kind", "requirement_register", type_="check"
    )
    op.create_check_constraint(
        "ck_requirement_register_kind",
        "requirement_register",
        "kind IN ('obligation','prohibition','format','content','evaluation','cross_ref')",
    )
    op.create_check_constraint(
        "ck_requirement_register_origin",
        "requirement_register",
        "origin IN ('map','audit','manual')",
    )


def downgrade() -> None:
    op.execute("UPDATE requirement_register SET kind = 'content' WHERE kind = 'cross_ref'")
    op.drop_constraint(
        "ck_requirement_register_origin", "requirement_register", type_="check"
    )
    op.drop_constraint(
        "ck_requirement_register_kind", "requirement_register", type_="check"
    )
    op.create_check_constraint(
        "ck_requirement_register_kind",
        "requirement_register",
        "kind IN ('obligation','prohibition','format','content','evaluation')",
    )
    op.drop_column("requirement_register", "origin")
