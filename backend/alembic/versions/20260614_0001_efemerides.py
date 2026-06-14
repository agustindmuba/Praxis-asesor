"""create efemeride

Revision ID: 20260614_0001
Revises: 20260607_0005
Create Date: 2026-06-14

Feat-53.1: tabla de efemérides (fechas conmemorativas) para
generar declaraciones automáticas, agenda y briefings temáticos.

Identidad natural: (mes, dia, titulo) — dos efemérides el mismo
día son posibles (ej. 8/3 = Día de la Mujer + otras).
`anio_unico` distingue las recurrentes (NULL) de los aniversarios
puntuales (50° del Golpe en 2026).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260614_0001"
down_revision = "20260607_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "efemeride",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mes", sa.SmallInteger(), nullable=False),
        sa.Column("dia", sa.SmallInteger(), nullable=False),
        sa.Column("titulo", sa.String(length=300), nullable=False),
        sa.Column("tipo", sa.String(length=30), nullable=False),
        sa.Column("relevancia", sa.String(length=10), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("fuente", sa.String(length=500), nullable=True),
        sa.Column(
            "areas_tematicas",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
        sa.Column("anio_unico", sa.Integer(), nullable=True),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # Unicidad por (mes, dia, titulo) — dos efemérides distintas
    # pueden coincidir mismo día (8/3 tiene varias).
    op.create_index(
        "uq_efemeride_fecha_titulo",
        "efemeride",
        ["mes", "dia", "titulo"],
        unique=True,
    )
    # Índices de búsqueda comunes: fecha (próximas N días) y filtros.
    op.create_index(
        "ix_efemeride_mes_dia",
        "efemeride",
        ["mes", "dia"],
    )
    op.create_index("ix_efemeride_tipo", "efemeride", ["tipo"])
    op.create_index("ix_efemeride_relevancia", "efemeride", ["relevancia"])
    # Sanidad de datos vía CHECK constraints. Más barato que validar
    # en cada INSERT desde Python.
    op.execute(
        "ALTER TABLE efemeride ADD CONSTRAINT chk_efemeride_mes "
        "CHECK (mes BETWEEN 1 AND 12)"
    )
    op.execute(
        "ALTER TABLE efemeride ADD CONSTRAINT chk_efemeride_dia "
        "CHECK (dia BETWEEN 1 AND 31)"
    )
    op.execute(
        "ALTER TABLE efemeride ADD CONSTRAINT chk_efemeride_anio_unico "
        "CHECK (anio_unico IS NULL OR anio_unico BETWEEN 1800 AND 2100)"
    )


def downgrade() -> None:
    op.drop_index("ix_efemeride_relevancia", table_name="efemeride")
    op.drop_index("ix_efemeride_tipo", table_name="efemeride")
    op.drop_index("ix_efemeride_mes_dia", table_name="efemeride")
    op.drop_index("uq_efemeride_fecha_titulo", table_name="efemeride")
    op.drop_table("efemeride")
