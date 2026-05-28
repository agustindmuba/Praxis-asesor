"""create seguimiento_expediente table

Revision ID: 20260528_0004
Revises: 20260528_0003
Create Date: 2026-05-28

Entidad tenant-scoped central: cada despacho marca expedientes que sigue,
con prioridad y responsable opcional.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260528_0004"
down_revision: str | None = "20260528_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "seguimiento_expediente",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("despacho_id", sa.Uuid(), nullable=False),
        sa.Column("expediente_id", sa.Uuid(), nullable=False),
        sa.Column("responsable_id", sa.Uuid(), nullable=True),
        sa.Column("prioridad", sa.String(length=10), nullable=False, server_default="media"),
        sa.Column(
            "archivado",
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
        sa.ForeignKeyConstraint(["despacho_id"], ["despacho.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["expediente_id"], ["expediente.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["responsable_id"], ["usuario.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "uq_seguimiento_despacho_expediente",
        "seguimiento_expediente",
        ["despacho_id", "expediente_id"],
        unique=True,
    )
    op.create_index(
        "ix_seguimiento_despacho_id",
        "seguimiento_expediente",
        ["despacho_id"],
    )
    op.create_index(
        "ix_seguimiento_expediente_id",
        "seguimiento_expediente",
        ["expediente_id"],
    )
    op.create_index(
        "ix_seguimiento_responsable_id",
        "seguimiento_expediente",
        ["responsable_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_seguimiento_responsable_id", table_name="seguimiento_expediente")
    op.drop_index("ix_seguimiento_expediente_id", table_name="seguimiento_expediente")
    op.drop_index("ix_seguimiento_despacho_id", table_name="seguimiento_expediente")
    op.drop_index("uq_seguimiento_despacho_expediente", table_name="seguimiento_expediente")
    op.drop_table("seguimiento_expediente")
