"""add id_sesion_externa to orden_del_dia

Revision ID: 20260607_0003
Revises: 20260607_0002
Create Date: 2026-06-07

Feat-45.3: el scraper del Plan de Labor identifica cada sesión por
`id_sesion` (entero del portal HCDN). Lo guardamos para deduplicar:
si ya existe un OD con ese `id_sesion_externa`, no creamos otro.

`despacho_id` también se cambia a NULLABLE explícito para que el OD
detectado automáticamente quede como "global" (los briefings se
generan por despacho cuando corresponda).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260607_0003"
down_revision = "20260607_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "orden_del_dia",
        sa.Column("id_sesion_externa", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_orden_del_dia_id_sesion_externa",
        "orden_del_dia",
        ["id_sesion_externa"],
        unique=True,
        postgresql_where=sa.text("id_sesion_externa IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_orden_del_dia_id_sesion_externa",
        table_name="orden_del_dia",
    )
    op.drop_column("orden_del_dia", "id_sesion_externa")
