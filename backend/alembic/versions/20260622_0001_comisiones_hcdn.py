"""create comisiones hcdn + integrantes + reuniones

Revision ID: 20260622_0001
Revises: 20260614_0002
Create Date: 2026-06-22

Feat-61: comisiones del portal HCDN persistidas, con integrantes
(diputados que la integran y su cargo) y agenda de reuniones
(fecha + título + PDF de citación).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260622_0001"
down_revision = "20260614_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "comision_hcdn",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("camara", sa.String(length=20), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("nombre", sa.String(length=300), nullable=False),
        sa.Column("tipo", sa.String(length=30), nullable=False),
        sa.Column("url_oficial", sa.String(length=500), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column(
            "capturado_en",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("camara", "slug", name="uq_comision_hcdn_camara_slug"),
    )
    op.create_index("ix_comision_hcdn_camara", "comision_hcdn", ["camara"])

    op.create_table(
        "integrante_comision",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("comision_id", sa.Uuid(), nullable=False),
        sa.Column("nombre_diputado", sa.String(length=200), nullable=False),
        sa.Column("cargo", sa.String(length=40), nullable=False),
        sa.Column("partido", sa.String(length=200), nullable=True),
        sa.Column("distrito", sa.String(length=80), nullable=True),
        sa.Column("legislador_id", sa.Uuid(), nullable=True),
        sa.Column(
            "capturado_en",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["comision_id"], ["comision_hcdn.id"], ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_integrante_comision_comision",
        "integrante_comision",
        ["comision_id"],
    )
    op.create_index(
        "ix_integrante_comision_legislador",
        "integrante_comision",
        ["legislador_id"],
    )

    op.create_table(
        "reunion_comision",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("comision_id", sa.Uuid(), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("titulo", sa.String(length=500), nullable=False),
        sa.Column("hora", sa.Time(), nullable=True),
        sa.Column("sala", sa.String(length=120), nullable=True),
        sa.Column("citacion_pdf_url", sa.String(length=500), nullable=True),
        sa.Column(
            "capturado_en",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["comision_id"], ["comision_hcdn.id"], ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "comision_id", "fecha", "titulo",
            name="uq_reunion_comision_fecha_titulo",
        ),
    )
    op.create_index("ix_reunion_comision_fecha", "reunion_comision", ["fecha"])


def downgrade() -> None:
    op.drop_index("ix_reunion_comision_fecha", table_name="reunion_comision")
    op.drop_table("reunion_comision")
    op.drop_index(
        "ix_integrante_comision_legislador", table_name="integrante_comision",
    )
    op.drop_index(
        "ix_integrante_comision_comision", table_name="integrante_comision",
    )
    op.drop_table("integrante_comision")
    op.drop_index("ix_comision_hcdn_camara", table_name="comision_hcdn")
    op.drop_table("comision_hcdn")
