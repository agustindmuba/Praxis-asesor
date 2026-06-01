"""create expediente_area_tematica table

Revision ID: 20260601_0001
Revises: 20260531_0001
Create Date: 2026-06-01

Cache de clasificación temática por expediente (feat/27 — spec 14).
UNIQUE en expediente_id para que haya a lo sumo una clasificación por
expediente; reclasificar = delete+insert.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260601_0001"
down_revision: str | None = "20260531_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "expediente_area_tematica",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("expediente_id", sa.Uuid(), nullable=False),
        sa.Column("area", sa.String(length=40), nullable=False),
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
            ["expediente_id"], ["expediente.id"], ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "expediente_id", name="uq_area_tematica_expediente_id",
        ),
    )
    op.create_index(
        "ix_area_tematica_expediente_id",
        "expediente_area_tematica",
        ["expediente_id"],
    )
    op.create_index(
        "ix_area_tematica_area",
        "expediente_area_tematica",
        ["area"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_area_tematica_area",
        table_name="expediente_area_tematica",
    )
    op.drop_index(
        "ix_area_tematica_expediente_id",
        table_name="expediente_area_tematica",
    )
    op.drop_table("expediente_area_tematica")
