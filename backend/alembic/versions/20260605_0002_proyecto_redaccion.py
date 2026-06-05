"""create proyecto_redaccion table

Revision ID: 20260605_0002
Revises: 20260605_0001
Create Date: 2026-06-05

Feat-42.3: tabla para borradores internos de proyectos parlamentarios.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260605_0002"
down_revision = "20260605_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "proyecto_redaccion",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("despacho_id", sa.Uuid(), nullable=False),
        sa.Column("tipo", sa.String(length=20), nullable=False),
        sa.Column("titulo", sa.Text(), nullable=False),
        sa.Column("sumario", sa.Text(), nullable=False),
        sa.Column(
            "articulado",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column("fundamentos", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "cofirmantes_sugeridos",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "estado",
            sa.String(length=15),
            nullable=False,
            server_default="borrador",
        ),
        sa.Column(
            "autor_legislador",
            sa.String(length=120),
            nullable=False,
            server_default="",
        ),
        sa.Column("modelo_asistente", sa.String(length=100), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_proyecto_redaccion_despacho",
        "proyecto_redaccion",
        ["despacho_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_proyecto_redaccion_despacho", table_name="proyecto_redaccion")
    op.drop_table("proyecto_redaccion")
