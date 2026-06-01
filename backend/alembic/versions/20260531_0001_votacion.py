"""create votacion + voto_legislador tables

Revision ID: 20260531_0001
Revises: 20260529_0001
Create Date: 2026-05-31

Módulo de votaciones nominales. Modelo aprobado por ADR 0005 y
validado por el spike feat/26.1.

- `votacion` agrega: encabezado + conteos + metadata del portal HCDN
- `voto_legislador` detalla cada voto individual con PK compuesta
  (votacion_id, legislador_nombre)

No FK a legislador canónico todavía: deuda asumida en ADR 0005.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260531_0001"
down_revision: str | None = "20260529_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "votacion",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("camara", sa.String(length=10), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("sesion", sa.String(length=200), nullable=False),
        sa.Column("asunto", sa.Text(), nullable=False),
        sa.Column("tipo", sa.String(length=20), nullable=False),
        sa.Column("resultado_afirmativos", sa.Integer(), nullable=False),
        sa.Column("resultado_negativos", sa.Integer(), nullable=False),
        sa.Column("resultado_abstenciones", sa.Integer(), nullable=False),
        sa.Column("resultado_sin_votar", sa.Integer(), nullable=False),
        sa.Column("resultado_ausentes", sa.Integer(), nullable=False),
        sa.Column("aprobada", sa.Boolean(), nullable=False),
        sa.Column("presidida_por", sa.String(length=200), nullable=True),
        sa.Column("expediente_id", sa.Uuid(), nullable=True),
        sa.Column("titulo_od", sa.String(length=50), nullable=True),
        sa.Column("acta_id_hcdn", sa.Integer(), nullable=True),
        sa.Column("acta_pdf_url", sa.String(length=500), nullable=True),
        sa.Column("fuente_url", sa.String(length=500), nullable=True),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["expediente_id"], ["expediente.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint("acta_id_hcdn", name="uq_votacion_acta_id_hcdn"),
    )
    op.create_index(
        "ix_votacion_expediente_id",
        "votacion",
        ["expediente_id"],
        postgresql_where=sa.text("expediente_id IS NOT NULL"),
    )
    op.create_index(
        "ix_votacion_titulo_od",
        "votacion",
        ["titulo_od"],
        postgresql_where=sa.text("titulo_od IS NOT NULL"),
    )
    op.create_index(
        "ix_votacion_camara_fecha",
        "votacion",
        ["camara", "fecha"],
    )

    op.create_table(
        "voto_legislador",
        sa.Column("votacion_id", sa.Uuid(), nullable=False),
        sa.Column("legislador_nombre", sa.String(length=200), nullable=False),
        sa.Column("voto", sa.String(length=20), nullable=False),
        sa.Column("bloque", sa.String(length=150), nullable=True),
        sa.Column("distrito", sa.String(length=80), nullable=True),
        sa.Column("que_dijo", sa.Text(), nullable=True),
        sa.Column("legislador_hcdn_id", sa.String(length=20), nullable=True),
        sa.PrimaryKeyConstraint("votacion_id", "legislador_nombre"),
        sa.ForeignKeyConstraint(
            ["votacion_id"], ["votacion.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_voto_legislador_bloque",
        "voto_legislador",
        ["bloque"],
    )


def downgrade() -> None:
    op.drop_index("ix_voto_legislador_bloque", table_name="voto_legislador")
    op.drop_table("voto_legislador")
    op.drop_index("ix_votacion_camara_fecha", table_name="votacion")
    op.drop_index("ix_votacion_titulo_od", table_name="votacion")
    op.drop_index("ix_votacion_expediente_id", table_name="votacion")
    op.drop_table("votacion")
