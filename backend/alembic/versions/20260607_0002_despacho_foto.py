"""add legislador_foto_url to despacho

Revision ID: 20260607_0002
Revises: 20260607_0001
Create Date: 2026-06-07

Feat-46: el panel de huella del legislador necesita mostrar la foto
del titular. Lo guardamos como URL pública (el asesor la setea en
/configuracion). Si está NULL, la UI renderiza un placeholder con
iniciales.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260607_0002"
down_revision = "20260607_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "despacho",
        sa.Column("legislador_foto_url", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("despacho", "legislador_foto_url")
