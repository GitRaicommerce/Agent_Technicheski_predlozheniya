"""add pgvector embeddings

Revision ID: a1b2c3d4e5f6
Revises: fd40c3c462b6
Create Date: 2026-03-19

Добавя pgvector extension и embedding колони (vector(1536)) към:
  - extracted_chunks
  - example_snippets
  - lex_chunks

Използва модел text-embedding-3-small (1536 dims).
"""

from alembic import op
import sqlalchemy as sa

try:
    from pgvector.sqlalchemy import Vector

    _has_pgvector = True
except ImportError:  # pragma: no cover
    _has_pgvector = False

revision = "a1b2c3d4e5f6"
down_revision = "fd40c3c462b6"
branch_labels = None
depends_on = None

_DIMS = 1536


def upgrade() -> None:
    # Enable pgvector extension (idempotent)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    col_type = Vector(_DIMS) if _has_pgvector else sa.Text()

    op.add_column(
        "extracted_chunks",
        sa.Column("embedding", col_type, nullable=True),
    )
    op.add_column(
        "example_snippets",
        sa.Column("embedding", col_type, nullable=True),
    )
    op.add_column(
        "lex_chunks",
        sa.Column("embedding", col_type, nullable=True),
    )

    # IVFFlat indexes for cosine similarity (approximate nearest neighbour)
    # lists=100 is suitable for up to ~1M rows; rebuild when data grows significantly
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_extracted_chunks_embedding "
        "ON extracted_chunks USING ivfflat (embedding vector_cosine_ops) "
        "WITH (lists = 100)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_example_snippets_embedding "
        "ON example_snippets USING ivfflat (embedding vector_cosine_ops) "
        "WITH (lists = 100)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_lex_chunks_embedding "
        "ON lex_chunks USING ivfflat (embedding vector_cosine_ops) "
        "WITH (lists = 100)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_extracted_chunks_embedding")
    op.execute("DROP INDEX IF EXISTS ix_example_snippets_embedding")
    op.execute("DROP INDEX IF EXISTS ix_lex_chunks_embedding")

    op.drop_column("extracted_chunks", "embedding")
    op.drop_column("example_snippets", "embedding")
    op.drop_column("lex_chunks", "embedding")
