"""Repositorios SQLAlchemy async.

Cada repo implementa un puerto definido en `praxis.application.ports`.
Convención: una clase por agregado raíz.
"""

from praxis.infrastructure.persistence.repositories.despacho import (
    SqlAlchemyDespachoRepository,
)

__all__ = ["SqlAlchemyDespachoRepository"]
