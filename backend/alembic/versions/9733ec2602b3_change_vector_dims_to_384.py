"""change_vector_dims_to_384

Revision ID: 9733ec2602b3
Revises: 2cb61514cf94
Create Date: 2026-06-17 14:51:03.455982
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '9733ec2602b3'
down_revision: str | None = '2cb61514cf94'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _change_dims(dim: int) -> None:
    """Resize both vector columns to ``dim``.

    The IVFFlat index is dim-bound, so it must be dropped before the column is
    altered and recreated after. Existing vectors are nulled first: embeddings
    of the old dimension are meaningless at the new dimension (and pgvector has
    no implicit cast between sizes), so they must be regenerated via the
    backfill task / re-analysis anyway.
    """
    op.drop_index('ix_clauses_embedding', table_name='clauses')

    op.execute("UPDATE clauses SET embedding = NULL")
    op.execute("UPDATE regulatory_updates SET embedding = NULL")

    op.execute(f"ALTER TABLE clauses ALTER COLUMN embedding TYPE vector({dim})")
    op.execute(
        f"ALTER TABLE regulatory_updates ALTER COLUMN embedding TYPE vector({dim})"
    )

    op.create_index(
        'ix_clauses_embedding',
        'clauses',
        ['embedding'],
        unique=False,
        postgresql_using='ivfflat',
        postgresql_with={'lists': 100},
        postgresql_ops={'embedding': 'vector_cosine_ops'},
    )


def upgrade() -> None:
    _change_dims(384)


def downgrade() -> None:
    _change_dims(1536)
