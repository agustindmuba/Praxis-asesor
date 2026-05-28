"""Casos de uso de la aplicación.

Cada caso de uso es una unidad de orquestación entre puertos. NO contiene
lógica de negocio (eso es dominio), NI conoce implementaciones concretas
(eso es infrastructure).
"""

from praxis.application.use_cases.buscar_expediente import BuscarExpediente

__all__ = ["BuscarExpediente"]
