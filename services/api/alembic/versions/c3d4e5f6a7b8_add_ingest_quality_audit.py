"""add ingest quality audit fields

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-04-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "project_files",
        sa.Column(
            "ingest_quality_status",
            sa.String(16),
            server_default="pending",
            nullable=False,
        ),
    )
    op.add_column(
        "project_files",
        sa.Column("ingest_report_json", postgresql.JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("project_files", "ingest_report_json")
    op.drop_column("project_files", "ingest_quality_status")
