"""create despacho table

Revision ID: 20260528_0001
Revises: 20260527_0001
Create Date: 2026-05-28

Primera tabla real del bloque 2: `despacho` (el tenant). UUID v7 como PK,
timestamps automáticos, configuración como JSONB (Postgres) / JSON (SQLite).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260528_0001"
down_revision: str | None = "20260527_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "despacho",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("nombre", sa.String(length=200), nullable=False),
        sa.Column("legislador_titular_slug", sa.String(length=100), nullable=True),
        sa.Column("configuracion", sa.JSON(), nullable=False),
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
    op.create_index("ix_despacho_nombre", "despacho", ["nombre"])


def downgrade() -> None:
    op.drop_index("ix_despacho_nombre", table_name="despacho")
    op.drop_table("despacho")
