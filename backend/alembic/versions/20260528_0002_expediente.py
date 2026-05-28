"""create expediente, firmante, giro, tramite_evento tables

Revision ID: 20260528_0002
Revises: 20260528_0001
Create Date: 2026-05-28

Persistencia del modelo de Expediente. UUID v7 PKs, UNIQUE en la identidad
natural del expediente, FKs con ON DELETE CASCADE para los hijos.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260528_0002"
down_revision: str | None = "20260528_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Expediente.
    op.create_table(
        "expediente",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("origen", sa.String(length=10), nullable=False),
        sa.Column("anio", sa.Integer(), nullable=False),
        sa.Column("camara", sa.String(length=10), nullable=False),
        sa.Column("tipo", sa.String(length=30), nullable=False),
        sa.Column("titulo", sa.String(length=2000), nullable=False),
        sa.Column("sumario", sa.String(), nullable=True),
        sa.Column("fecha_ingreso", sa.Date(), nullable=True),
        sa.Column("estado", sa.String(length=40), nullable=False, server_default="desconocido"),
        sa.Column("texto_url", sa.String(length=2000), nullable=True),
        sa.Column("fuente_url", sa.String(length=2000), nullable=True),
        sa.Column("fecha_caducidad", sa.Date(), nullable=True),
        sa.Column("fecha_caducidad_original", sa.Date(), nullable=True),
        sa.Column(
            "prorrogado",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
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
    )
    op.create_index(
        "uq_expediente_numero",
        "expediente",
        ["numero", "origen", "anio", "camara"],
        unique=True,
    )

    # Firmante.
    op.create_table(
        "firmante",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("expediente_id", sa.Uuid(), nullable=False),
        sa.Column("nombre", sa.String(length=300), nullable=False),
        sa.Column("distrito", sa.String(length=100), nullable=True),
        sa.Column("bloque", sa.String(length=200), nullable=True),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["expediente_id"], ["expediente.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_firmante_expediente_id", "firmante", ["expediente_id"])

    # Giro.
    op.create_table(
        "giro",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("expediente_id", sa.Uuid(), nullable=False),
        sa.Column("comision", sa.String(length=300), nullable=False),
        sa.Column("fecha_ingreso", sa.Date(), nullable=True),
        sa.Column("fecha_egreso", sa.Date(), nullable=True),
        sa.Column("orden", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["expediente_id"], ["expediente.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_giro_expediente_id", "giro", ["expediente_id"])

    # Tramite evento.
    op.create_table(
        "tramite_evento",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("expediente_id", sa.Uuid(), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=True),
        sa.Column("camara", sa.String(length=10), nullable=False),
        sa.Column("evento", sa.String(length=500), nullable=False),
        sa.Column("detalle", sa.String(), nullable=True),
        sa.Column("fuente", sa.String(length=50), nullable=True),
        sa.ForeignKeyConstraint(["expediente_id"], ["expediente.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_tramite_evento_expediente_id", "tramite_evento", ["expediente_id"])


def downgrade() -> None:
    op.drop_index("ix_tramite_evento_expediente_id", table_name="tramite_evento")
    op.drop_table("tramite_evento")
    op.drop_index("ix_giro_expediente_id", table_name="giro")
    op.drop_table("giro")
    op.drop_index("ix_firmante_expediente_id", table_name="firmante")
    op.drop_table("firmante")
    op.drop_index("uq_expediente_numero", table_name="expediente")
    op.drop_table("expediente")
