"""Capa Domain — entidades puras, value objects, reglas de negocio.

Ver `README.md` en esta carpeta para responsabilidades y restricciones.

Re-exporta los símbolos principales para imports cómodos desde casos de uso
e infraestructura. La regla es: si una entidad o value object es parte del
contrato público del dominio, vive en este __init__.
"""

from praxis.domain.comision import Comision, TipoComision
from praxis.domain.exceptions import (
    DomainError,
    ExpedienteNoEncontrado,
    FuenteNoDisponible,
)
from praxis.domain.expediente import (
    Expediente,
    Firmante,
    Giro,
    TramiteEvento,
)
from praxis.domain.value_objects import (
    Camara,
    EstadoExpediente,
    NumeroExpediente,
    OrigenExpediente,
    TipoExpediente,
)

__all__ = [
    "Camara",
    "Comision",
    "DomainError",
    "EstadoExpediente",
    "Expediente",
    "ExpedienteNoEncontrado",
    "Firmante",
    "FuenteNoDisponible",
    "Giro",
    "NumeroExpediente",
    "OrigenExpediente",
    "TipoComision",
    "TipoExpediente",
    "TramiteEvento",
]
