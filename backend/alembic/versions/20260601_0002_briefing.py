"""create orden_del_dia + briefing tables

Revision ID: 20260601_0002
Revises: 20260601_0001
Create Date: 2026-06-01

Spec 14 + feat/29. Tablas para persistir el orden del día (lista de
expedientes) y el briefing pre-sesión generado.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260601_0002"
down_revision: str | None = "20260601_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "orden_del_dia",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("despacho_id", sa.Uuid(), nullable=True),
        sa.Column("camara", sa.String(length=10), nullable=False),
        sa.Column("fecha_sesion", sa.Date(), nullable=False),
        sa.Column("hora_sesion", sa.Time(), nullable=True),
        sa.Column("titulo", sa.String(length=200), nullable=True),
        sa.Column(
            "fuente",
            sa.String(length=30),
            nullable=False,
            server_default="upload_manual",
        ),
        sa.Column("expedientes_ids", sa.JSON(), nullable=False),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["despacho_id"], ["despacho.id"], ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_orden_del_dia_despacho_id",
        "orden_del_dia",
        ["despacho_id"],
    )
    op.create_index(
        "ix_orden_del_dia_fecha_sesion",
        "orden_del_dia",
        ["fecha_sesion"],
    )

    op.create_table(
        "briefing",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("despacho_id", sa.Uuid(), nullable=False),
        sa.Column("orden_del_dia_id", sa.Uuid(), nullable=False),
        sa.Column("modelo_llm", sa.String(length=80), nullable=False),
        sa.Column(
            "prompt_version",
            sa.String(length=20),
            nullable=False,
            server_default="v1",
        ),
        sa.Column("contenido", sa.JSON(), nullable=False),
        sa.Column(
            "generado_en",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["despacho_id"], ["despacho.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["orden_del_dia_id"], ["orden_del_dia.id"], ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "despacho_id", "orden_del_dia_id",
            name="uq_briefing_despacho_od",
        ),
    )
    op.create_index(
        "ix_briefing_despacho_id",
        "briefing",
        ["despacho_id"],
    )
    op.create_index(
        "ix_briefing_orden_del_dia_id",
        "briefing",
        ["orden_del_dia_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_briefing_orden_del_dia_id", table_name="briefing")
    op.drop_index("ix_briefing_despacho_id", table_name="briefing")
    op.drop_table("briefing")
    op.drop_index(
        "ix_orden_del_dia_fecha_sesion", table_name="orden_del_dia",
    )
    op.drop_index(
        "ix_orden_del_dia_despacho_id", table_name="orden_del_dia",
    )
    op.drop_table("orden_del_dia")
