"""add calendar_token to despacho

Revision ID: 20260614_0002
Revises: 20260614_0001
Create Date: 2026-06-14

Feat-54.2: cada despacho tiene un token único de 32-64 chars que
sirve como autorización del feed iCal. La URL del calendar es
`https://app.../calendar/{token}.ics` — sin auth Clerk, el token
ES la auth. Si se filtra, el despacho lo regenera y el viejo deja
de funcionar.

NULL = el despacho no generó su URL todavía (se crea al primer
acceso a la página /configuracion/calendario).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260614_0002"
down_revision = "20260614_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "despacho",
        sa.Column("calendar_token", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "uq_despacho_calendar_token",
        "despacho",
        ["calendar_token"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_despacho_calendar_token", table_name="despacho")
    op.drop_column("despacho", "calendar_token")
