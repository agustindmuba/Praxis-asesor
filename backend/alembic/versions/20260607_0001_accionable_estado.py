"""add feedback columns to accionable_evento

Revision ID: 20260607_0001
Revises: 20260605_0003
Create Date: 2026-06-07

Feat-43.2: feedback loop del asesor sobre cada accionable.
Agrega 3 columnas:
- estado: enum {pendiente, hecho, ignorado, adaptado}
- nota_asesor: text opcional, solo si estado=adaptado
- marcado_en: timestamp del momento del feedback
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260607_0001"
down_revision = "20260605_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "accionable_evento",
        sa.Column(
            "estado",
            sa.String(length=20),
            nullable=False,
            server_default="pendiente",
        ),
    )
    op.add_column(
        "accionable_evento",
        sa.Column("nota_asesor", sa.Text(), nullable=True),
    )
    op.add_column(
        "accionable_evento",
        sa.Column(
            "marcado_en",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    # Index sobre (despacho_id, estado) para que la query "accionables
    # pendientes de este despacho" del dashboard sea rápida.
    op.create_index(
        "ix_accionable_evento_despacho_estado",
        "accionable_evento",
        ["despacho_id", "estado"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_accionable_evento_despacho_estado",
        table_name="accionable_evento",
    )
    op.drop_column("accionable_evento", "marcado_en")
    op.drop_column("accionable_evento", "nota_asesor")
    op.drop_column("accionable_evento", "estado")
