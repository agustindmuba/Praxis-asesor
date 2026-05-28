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
    MembresiaDespachoRepository,
    SeguimientoExpedienteRepository,
    UsuarioRepository,
)
from praxis.application.use_cases import (
    BuscarExpediente,
    EnriquecerExpediente,
    ResolverContextoRequest,
)

__all__ = [
    "AuthProvider",
    "BuscarExpediente",
    "CatalogoComisiones",
    "CatalogoLegisladores",
    "DespachoRepository",
    "EnriquecerExpediente",
    "ExpedienteRepository",
    "FuenteExpedientes",
    "MembresiaDespachoRepository",
    "ResolverContextoRequest",
    "SeguimientoExpedienteRepository",
    "UsuarioRepository",
]
