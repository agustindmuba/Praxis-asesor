"""Capa Domain — entidades puras, value objects, reglas de negocio.

Ver `README.md` en esta carpeta para responsabilidades y restricciones.

Re-exporta los símbolos principales para imports cómodos desde casos de uso
e infraestructura. La regla es: si una entidad o value object es parte del
contrato público del dominio, vive en este __init__.
"""

from praxis.domain.comision import Comision, TipoComision
from praxis.domain.despacho import Despacho
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
from praxis.domain.inferencia_estado import (
    InferenciaResult,
    inferir_caducidad,
    inferir_estado,
    inferir_estado_y_caducidad,
)
from praxis.domain.legislador import Bloque, Legislador
from praxis.domain.tramite_historico import (
    eventos_recientes,
    filter_by_camara,
    filter_by_rango,
    merge_tramite,
    validar_consistencia,
)
from praxis.domain.usuario import MembresiaDespacho, Rol, Usuario
from praxis.domain.value_objects import (
    Camara,
    EstadoExpediente,
    NumeroExpediente,
    OrigenExpediente,
    TipoExpediente,
)

__all__ = [
    "Bloque",
    "Camara",
    "Comision",
    "Despacho",
    "DomainError",
    "EstadoExpediente",
    "Expediente",
    "ExpedienteNoEncontrado",
    "Firmante",
    "FuenteNoDisponible",
    "Giro",
    "InferenciaResult",
    "Legislador",
    "MembresiaDespacho",
    "NumeroExpediente",
    "OrigenExpediente",
    "Rol",
    "TipoComision",
    "TipoExpediente",
    "TramiteEvento",
    "Usuario",
    "eventos_recientes",
    "filter_by_camara",
    "filter_by_rango",
    "inferir_caducidad",
    "inferir_estado",
    "inferir_estado_y_caducidad",
    "merge_tramite",
    "validar_consistencia",
]
