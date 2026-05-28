"""Repositorios SQLAlchemy async.

Cada repo implementa un puerto definido en `praxis.application.ports`.
Convención: una clase por agregado raíz.
"""

from praxis.infrastructure.persistence.repositories.despacho import (
    SqlAlchemyDespachoRepository,
)
from praxis.infrastructure.persistence.repositories.expediente import (
    SqlAlchemyExpedienteRepository,
)
from praxis.infrastructure.persistence.repositories.membresia_despacho import (
    SqlAlchemyMembresiaDespachoRepository,
)
from praxis.infrastructure.persistence.repositories.usuario import (
    SqlAlchemyUsuarioRepository,
)

__all__ = [
    "SqlAlchemyDespachoRepository",
    "SqlAlchemyExpedienteRepository",
    "SqlAlchemyMembresiaDespachoRepository",
    "SqlAlchemyUsuarioRepository",
]
