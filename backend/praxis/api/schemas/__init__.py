"""DTOs Pydantic v2 que la API expone al cliente.

Separados de los dataclasses del dominio para mantener el dominio puro
(sin pydantic) y para que cambios en el contrato HTTP no acoplen al modelo.

Convención: `from_attributes=True` en cada schema que se construya desde
una entidad del dominio.
"""

from praxis.api.schemas.auth import MeResponse
from praxis.api.schemas.busqueda import FiltrosExpediente, ResultadoBusquedaDTO
from praxis.api.schemas.expediente import (
    ExpedienteFicha,
    ExpedienteResumen,
    FirmanteDTO,
    GiroDTO,
    NumeroExpedienteDTO,
    TramiteEventoDTO,
)
from praxis.api.schemas.inteligencia import (
    ComparacionPeersDTO,
    EtapaProgresoDTO,
    InteligenciaExpedienteDTO,
    ProgresoTramiteDTO,
)
from praxis.api.schemas.resumen import ResumenEjecutivoDTO
from praxis.api.schemas.seguimiento import (
    ActualizarSeguimientoBody,
    CrearSeguimientoBody,
    SeguimientoDTO,
)

__all__ = [
    "ActualizarSeguimientoBody",
    "ComparacionPeersDTO",
    "CrearSeguimientoBody",
    "EtapaProgresoDTO",
    "ExpedienteFicha",
    "ExpedienteResumen",
    "FiltrosExpediente",
    "FirmanteDTO",
    "GiroDTO",
    "InteligenciaExpedienteDTO",
    "MeResponse",
    "NumeroExpedienteDTO",
    "ProgresoTramiteDTO",
    "ResultadoBusquedaDTO",
    "ResumenEjecutivoDTO",
    "SeguimientoDTO",
    "TramiteEventoDTO",
]
