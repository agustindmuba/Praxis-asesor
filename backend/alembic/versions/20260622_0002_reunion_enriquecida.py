"""enriquecer reunion_comision con campos parseados + LLM

Revision ID: 20260622_0002
Revises: 20260622_0001
Create Date: 2026-06-22

Feat-61.4.B.1: separa el título crudo en hora/sala/descripción y agrega
slots para enriquecimiento por LLM (tema_corto, oportunidad política,
acción sugerida, etc.). Todo nullable: el enriquecimiento se hace a
demanda, no en cada scrap.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260622_0002"
down_revision = "20260622_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "reunion_comision",
        sa.Column("descripcion", sa.Text(), nullable=True),
    )
    op.add_column(
        "reunion_comision",
        sa.Column(
            "comisiones_invitadas",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )
    op.add_column(
        "reunion_comision",
        sa.Column("tema_corto", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "reunion_comision",
        sa.Column("tipo_reunion", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "reunion_comision",
        sa.Column("convocada_por", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "reunion_comision",
        sa.Column(
            "expedientes_citados",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )
    op.add_column(
        "reunion_comision",
        sa.Column("oportunidad_politica", sa.Text(), nullable=True),
    )
    op.add_column(
        "reunion_comision",
        sa.Column("accion_sugerida", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "reunion_comision",
        sa.Column("huella_historica", sa.Text(), nullable=True),
    )
    op.add_column(
        "reunion_comision",
        sa.Column("enriquecida_en", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("reunion_comision", "enriquecida_en")
    op.drop_column("reunion_comision", "huella_historica")
    op.drop_column("reunion_comision", "accion_sugerida")
    op.drop_column("reunion_comision", "oportunidad_politica")
    op.drop_column("reunion_comision", "expedientes_citados")
    op.drop_column("reunion_comision", "convocada_por")
    op.drop_column("reunion_comision", "tipo_reunion")
    op.drop_column("reunion_comision", "tema_corto")
    op.drop_column("reunion_comision", "comisiones_invitadas")
    op.drop_column("reunion_comision", "descripcion")
