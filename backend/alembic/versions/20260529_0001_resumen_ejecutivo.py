"""create resumen_ejecutivo table

Revision ID: 20260529_0001
Revises: 20260528_0004
Create Date: 2026-05-29

Cache de outputs de LLM (resumen ejecutivo) por expediente. UNIQUE en
`expediente_id` para que haya a lo sumo uno; regenerar = delete+insert.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260529_0001"
down_revision: str | None = "20260528_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "resumen_ejecutivo",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("expediente_id", sa.Uuid(), nullable=False),
        sa.Column("contenido_md", sa.Text(), nullable=False),
        sa.Column("modelo", sa.String(length=80), nullable=False),
        sa.Column(
            "prompt_version",
            sa.String(length=20),
            nullable=False,
            server_default="v1",
        ),
        sa.Column(
            "generado_en",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["expediente_id"], ["expediente.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("expediente_id", name="uq_resumen_expediente_id"),
    )
    op.create_index(
        "ix_resumen_expediente_id",
        "resumen_ejecutivo",
        ["expediente_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_resumen_expediente_id", table_name="resumen_ejecutivo")
    op.drop_table("resumen_ejecutivo")
