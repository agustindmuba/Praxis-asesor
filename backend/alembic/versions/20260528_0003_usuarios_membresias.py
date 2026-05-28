"""create usuario and membresia_despacho tables

Revision ID: 20260528_0003
Revises: 20260528_0002
Create Date: 2026-05-28

Usuarios humanos + sus membresías en despachos. Roles del MVP:
jefe_asesores, asesor, lector.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260528_0003"
down_revision: str | None = "20260528_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Usuario.
    op.create_table(
        "usuario",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False, unique=True),
        sa.Column("nombre", sa.String(length=200), nullable=False),
        sa.Column(
            "auth_provider_id",
            sa.String(length=200),
            nullable=True,
            unique=True,
        ),
        sa.Column(
            "activo",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
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
    op.create_index("ix_usuario_email", "usuario", ["email"])
    op.create_index(
        "ix_usuario_auth_provider_id",
        "usuario",
        ["auth_provider_id"],
        unique=False,
    )

    # MembresiaDespacho (PK compuesto).
    op.create_table(
        "membresia_despacho",
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("despacho_id", sa.Uuid(), nullable=False),
        sa.Column("rol", sa.String(length=30), nullable=False),
        sa.Column(
            "activo",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("usuario_id", "despacho_id"),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["despacho_id"], ["despacho.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_membresia_despacho_despacho_id",
        "membresia_despacho",
        ["despacho_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_membresia_despacho_despacho_id", table_name="membresia_despacho")
    op.drop_table("membresia_despacho")
    op.drop_index("ix_usuario_auth_provider_id", table_name="usuario")
    op.drop_index("ix_usuario_email", table_name="usuario")
    op.drop_table("usuario")
