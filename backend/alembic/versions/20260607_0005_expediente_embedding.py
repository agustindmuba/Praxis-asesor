"""add embedding to expediente

Revision ID: 20260607_0005
Revises: 20260607_0004
Create Date: 2026-06-07

Feat-48.5: cada expediente con titulo+sumario+texto_completo se
embebe con el mismo modelo que el corpus normativo
(`paraphrase-multilingual-MiniLM-L12-v2`, 384 dims) para que el
buscador semántico de antecedentes corra contra el mismo espacio
vectorial.

El embedding se calcula con `scripts/embeber_expedientes.py` usando
sentence-transformers local — $0 API. Re-embebimos cada vez que
`titulo`, `sumario` o `texto_completo` cambian.

Índice IVFFlat con cosine similarity para búsqueda rápida cuando
el corpus crezca a >1000 expedientes.
"""

from __future__ import annotations

from alembic import op

revision = "20260607_0005"
down_revision = "20260607_0004"
branch_labels = None
depends_on = None


EMBEDDING_DIM = 384


def upgrade() -> None:
    # Idempotente — pgvector ya está instalado por feat-42.6,
    # pero por las dudas.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Agregamos la columna nullable. NULL = aún no embebido.
    op.execute(
        f"ALTER TABLE expediente ADD COLUMN embedding vector({EMBEDDING_DIM})"
    )

    # Índice IVFFlat para cosine similarity. `lists=50` da buen
    # balance para corpus de ~10k-50k vectores; subir cuando crezca.
    op.execute(
        "CREATE INDEX ix_expediente_embedding "
        "ON expediente "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_expediente_embedding")
    op.execute("ALTER TABLE expediente DROP COLUMN IF EXISTS embedding")
