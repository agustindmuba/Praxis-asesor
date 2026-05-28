"""initial (vacía)

Migración placeholder para validar el pipeline de Alembic. No crea schema.
Las migraciones reales empiezan con la primera definición de modelos
(probablemente la entidad Camara o Legislador).

Revision ID: 20260527_0001
Revises:
Create Date: 2026-05-27

"""

from collections.abc import Sequence

revision: str = "20260527_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """No-op: primera migración."""
    pass


def downgrade() -> None:
    """No-op: primera migración."""
    pass
