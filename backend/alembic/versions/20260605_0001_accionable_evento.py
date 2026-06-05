"""create accionable_evento table

Revision ID: 20260605_0001
Revises: 20260604_0001
Create Date: 2026-06-05

Feat-42.2: tabla polimórfica para Accionables enriquecidos con perfil
opositor. Apunta a norma_bo.id o articulo.id según `tipo_evento`.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260605_0001"
down_revision = "20260604_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "accionable_evento",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("despacho_id", sa.Uuid(), nullable=False),
        sa.Column("tipo_evento", sa.String(length=20), nullable=False),
        sa.Column("evento_id", sa.Uuid(), nullable=False),
        sa.Column("razon_para_despacho", sa.Text(), nullable=False),
        sa.Column("accion_sugerida", sa.String(length=40), nullable=False),
        sa.Column("explicacion_accion", sa.Text(), nullable=False),
        sa.Column(
            "tweets_sugeridos",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "confianza",
            sa.String(length=10),
            nullable=False,
            server_default="media",
        ),
        sa.Column("generado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("editado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("modelo", sa.String(length=100), nullable=True),
        sa.Column(
            "prompt_version", sa.String(length=10), nullable=False, server_default="v1",
        ),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["despacho_id"], ["despacho.id"], ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "despacho_id", "tipo_evento", "evento_id",
            name="uq_accionable_evento_despacho_evento",
        ),
    )
    op.create_index(
        "ix_accionable_evento_evento",
        "accionable_evento",
        ["tipo_evento", "evento_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_accionable_evento_evento", table_name="accionable_evento")
    op.drop_table("accionable_evento")
