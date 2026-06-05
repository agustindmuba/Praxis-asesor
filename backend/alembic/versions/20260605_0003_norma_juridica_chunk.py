"""create norma_juridica_chunk with pgvector embedding

Revision ID: 20260605_0003
Revises: 20260605_0002
Create Date: 2026-06-05

Feat-42.6: corpus normativo (Constitución + códigos + leyes nacionales)
chunkeado por artículo + embeddings para búsqueda semántica.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260605_0003"
down_revision = "20260605_0002"
branch_labels = None
depends_on = None


# Dimensión del modelo de embeddings:
# paraphrase-multilingual-MiniLM-L12-v2 → 384 dims.
EMBEDDING_DIM = 384


def upgrade() -> None:
    # Crear extensión vector si no existe (idempotente).
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "norma_juridica_chunk",
        sa.Column("id", sa.Uuid(), nullable=False),
        # Identificador legible de la norma fuente. Ej "constitucion_nacional",
        # "codigo_civil_y_comercial", "ley_25188_etica_publica".
        sa.Column("fuente", sa.String(length=80), nullable=False),
        # Etiqueta visible del artículo (libre): "Artículo 14", "Art. 14 bis",
        # "Capítulo III - Disposiciones generales", etc.
        sa.Column("articulo_label", sa.String(length=120), nullable=False),
        # Orden dentro de la fuente (1, 2, 3...).
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        # Vector embedding (384 dims para MiniLM multilingual).
        sa.Column(
            "embedding",
            sa.dialects.postgresql.ARRAY(sa.Float()).with_variant(
                sa.String(), "sqlite",
            ),
            nullable=True,
        ),
        sa.Column(
            "modelo_embedding",
            sa.String(length=80),
            nullable=False,
            server_default="paraphrase-multilingual-MiniLM-L12-v2",
        ),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # En Postgres queremos VECTOR(384), no ARRAY(Float). Reemplazamos
    # con SQL directo porque alembic ORM no soporta el tipo nativo de
    # pgvector de forma directa en esta versión.
    op.execute(
        "ALTER TABLE norma_juridica_chunk "
        f"ALTER COLUMN embedding TYPE vector({EMBEDDING_DIM}) "
        "USING NULL",
    )
    # Índice IVFFlat para cosine similarity (rápido en N>1000).
    op.execute(
        "CREATE INDEX ix_norma_juridica_chunk_embedding "
        "ON norma_juridica_chunk "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50)",
    )
    op.create_index(
        "ix_norma_juridica_chunk_fuente",
        "norma_juridica_chunk",
        ["fuente"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_norma_juridica_chunk_embedding",
        table_name="norma_juridica_chunk",
    )
    op.drop_index(
        "ix_norma_juridica_chunk_fuente",
        table_name="norma_juridica_chunk",
    )
    op.drop_table("norma_juridica_chunk")
