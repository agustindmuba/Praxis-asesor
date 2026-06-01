"""Capa Application — casos de uso y puertos.

Ver `README.md` en esta carpeta para responsabilidades y restricciones.
"""

from praxis.application.ports import (
    AuthProvider,
    CatalogoComisiones,
    CatalogoLegisladores,
    DespachoRepository,
    ExpedienteAreaTematicaRepository,
    ExpedienteRepository,
    FuenteExpedientes,
    LlmProvider,
    MembresiaDespachoRepository,
    ResumenEjecutivoRepository,
    SeguimientoExpedienteRepository,
    UsuarioRepository,
)
from praxis.application.use_cases import (
    BuscarAntecedenteParecido,
    BuscarExpediente,
    CalcularInteligenciaExpediente,
    ClasificarExpedienteTematicamente,
    EnriquecerExpediente,
    GenerarResumenEjecutivo,
    ResolverContextoRequest,
    SincronizarUsuarioDesdeClerk,
    SugerirCofirmantes,
)

__all__ = [
    "AuthProvider",
    "BuscarAntecedenteParecido",
    "BuscarExpediente",
    "CalcularInteligenciaExpediente",
    "CatalogoComisiones",
    "CatalogoLegisladores",
    "ClasificarExpedienteTematicamente",
    "DespachoRepository",
    "EnriquecerExpediente",
    "ExpedienteAreaTematicaRepository",
    "ExpedienteRepository",
    "FuenteExpedientes",
    "GenerarResumenEjecutivo",
    "LlmProvider",
    "MembresiaDespachoRepository",
    "ResolverContextoRequest",
    "ResumenEjecutivoRepository",
    "SeguimientoExpedienteRepository",
    "SincronizarUsuarioDesdeClerk",
    "SugerirCofirmantes",
    "UsuarioRepository",
]
