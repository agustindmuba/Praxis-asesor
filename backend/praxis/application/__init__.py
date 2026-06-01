"""Capa Application — casos de uso y puertos.

Ver `README.md` en esta carpeta para responsabilidades y restricciones.
"""

from praxis.application.ports import (
    AuthProvider,
    BriefingRepository,
    CatalogoComisiones,
    CatalogoLegisladores,
    DespachoRepository,
    ExpedienteAreaTematicaRepository,
    ExpedienteRepository,
    FuenteExpedientes,
    LlmProvider,
    MembresiaDespachoRepository,
    OrdenDelDiaRepository,
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
    GenerarBriefing,
    GenerarResumenEjecutivo,
    ResolverContextoRequest,
    SincronizarUsuarioDesdeClerk,
    SugerirCofirmantes,
)

__all__ = [
    "AuthProvider",
    "BriefingRepository",
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
    "GenerarBriefing",
    "GenerarResumenEjecutivo",
    "LlmProvider",
    "MembresiaDespachoRepository",
    "OrdenDelDiaRepository",
    "ResolverContextoRequest",
    "ResumenEjecutivoRepository",
    "SeguimientoExpedienteRepository",
    "SincronizarUsuarioDesdeClerk",
    "SugerirCofirmantes",
    "UsuarioRepository",
]
