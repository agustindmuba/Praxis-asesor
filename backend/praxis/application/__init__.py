"""Capa Application — casos de uso y puertos.

Ver `README.md` en esta carpeta para responsabilidades y restricciones.
"""

from praxis.application.ports import (
    AuthProvider,
    CatalogoComisiones,
    CatalogoLegisladores,
    DespachoRepository,
    ExpedienteRepository,
    FuenteExpedientes,
    LlmProvider,
    MembresiaDespachoRepository,
    ResumenEjecutivoRepository,
    SeguimientoExpedienteRepository,
    UsuarioRepository,
)
from praxis.application.use_cases import (
    BuscarExpediente,
    CalcularInteligenciaExpediente,
    EnriquecerExpediente,
    GenerarResumenEjecutivo,
    ResolverContextoRequest,
    SincronizarUsuarioDesdeClerk,
)

__all__ = [
    "AuthProvider",
    "BuscarExpediente",
    "CalcularInteligenciaExpediente",
    "CatalogoComisiones",
    "CatalogoLegisladores",
    "DespachoRepository",
    "EnriquecerExpediente",
    "ExpedienteRepository",
    "FuenteExpedientes",
    "GenerarResumenEjecutivo",
    "LlmProvider",
    "MembresiaDespachoRepository",
    "ResolverContextoRequest",
    "ResumenEjecutivoRepository",
    "SeguimientoExpedienteRepository",
    "SincronizarUsuarioDesdeClerk",
    "UsuarioRepository",
]
