"""create perfil_opositor_despacho table

Revision ID: 20260604_0001
Revises: 20260602_0001
Create Date: 2026-06-04

Feat-42.1: tabla para el perfil opositor narrativo del despacho —
qué milita, contra qué, con qué tono. Distinta del perfil de interés
(que es de filtrado técnico).

Aditiva pura. Reversible.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260604_0001"
down_revision = "20260602_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "perfil_opositor_despacho",
        sa.Column("despacho_id", sa.Uuid(), nullable=False),
        sa.Column("bandera_principal", sa.Text(), nullable=False),
        sa.Column(
            "banderas_secundarias",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "temas_de_cuidado",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "tono_comunicacional",
            sa.String(length=40),
            nullable=False,
            server_default="mixto",
        ),
        sa.Column(
            "adversarios",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "aliados",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column("linea_de_bloque", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "justificacion_evidencia",
            sa.Text(),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "advertencias",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "confianza_global",
            sa.String(length=10),
            nullable=False,
            server_default="media",
        ),
        sa.Column("inferido_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("editado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("modelo_inferencia", sa.String(length=100), nullable=True),
        sa.Column(
            "prompt_version",
            sa.String(length=10),
            nullable=False,
            server_default="v1",
        ),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["despacho_id"], ["despacho.id"], ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("despacho_id"),
    )


def downgrade() -> None:
    op.drop_table("perfil_opositor_despacho")
