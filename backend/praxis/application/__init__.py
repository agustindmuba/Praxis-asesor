"""Capa Application — casos de uso y puertos.

Ver `README.md` en esta carpeta para responsabilidades y restricciones.
"""

from praxis.application.ports import (
    CatalogoComisiones,
    CatalogoLegisladores,
    DespachoRepository,
    ExpedienteRepository,
    FuenteExpedientes,
    MembresiaDespachoRepository,
    UsuarioRepository,
)
from praxis.application.use_cases import BuscarExpediente, EnriquecerExpediente

__all__ = [
    "BuscarExpediente",
    "CatalogoComisiones",
    "CatalogoLegisladores",
    "DespachoRepository",
    "EnriquecerExpediente",
    "ExpedienteRepository",
    "FuenteExpedientes",
    "MembresiaDespachoRepository",
    "UsuarioRepository",
]
