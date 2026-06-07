"""add texto_completo to expediente

Revision ID: 20260607_0004
Revises: 20260607_0003
Create Date: 2026-06-07

Feat-48.4: para poder hacer embeddings sobre el cuerpo completo del
proyecto (no solo el sumario) y para que el asistente de redacción
pueda citar extractos exactos, persistimos el texto del PDF parseado
en una columna TEXT. Se llena con `scripts/bajar_textos_completos.py`.

NULL = aún no se intentó descargar, o el PDF no existe en el portal.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260607_0004"
down_revision = "20260607_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "expediente",
        sa.Column("texto_completo", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("expediente", "texto_completo")
