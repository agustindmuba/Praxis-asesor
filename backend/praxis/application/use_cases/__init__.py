"""Casos de uso de la aplicación.

Cada caso de uso es una unidad de orquestación entre puertos. NO contiene
lógica de negocio (eso es dominio), NI conoce implementaciones concretas
(eso es infrastructure).
"""

from praxis.application.use_cases.buscar_expediente import BuscarExpediente
from praxis.application.use_cases.enriquecer_expediente import EnriquecerExpediente
from praxis.application.use_cases.resolver_contexto import ResolverContextoRequest
from praxis.application.use_cases.sincronizar_usuario_clerk import (
    SincronizarUsuarioDesdeClerk,
)

__all__ = [
    "BuscarExpediente",
    "EnriquecerExpediente",
    "ResolverContextoRequest",
    "SincronizarUsuarioDesdeClerk",
]
