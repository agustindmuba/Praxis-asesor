"""Puertos (interfaces) de la capa Application.

Cada puerto declara un contrato que la capa Infrastructure debe implementar.
Las implementaciones concretas (adaptadores) viven en `praxis.infrastructure`
y se inyectan en los casos de uso.

Regla hexagonal (ver `docs/adr/0001-stack-inicial.md`):
- `praxis.application` define los puertos pero NO conoce las implementaciones.
- `praxis.infrastructure` implementa los puertos.
- Los casos de uso reciben puertos por DI, nunca importan adaptadores
  directamente.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from praxis.domain import Expediente, NumeroExpediente


class FuenteExpedientes(ABC):
    """Puerto: una fuente desde la que se pueden obtener expedientes.

    Implementaciones esperadas:
    - `praxis.infrastructure.scrapers.hcdn.HcdnScraper`
    - `praxis.infrastructure.scrapers.hsn.HsnScraper` (futuro)
    - Eventualmente: cache, persistencia local, otras fuentes públicas.

    Convención de errores:
    - `ExpedienteNoEncontrado` si el número no existe en la fuente.
    - `FuenteNoDisponible` si la fuente está caída o devuelve errores
      no-recuperables. Errores transitorios deben manejarse internamente
      con retries antes de propagar.
    """

    @abstractmethod
    async def buscar_por_numero(self, numero: NumeroExpediente) -> Expediente:
        """Devuelve el expediente identificado por `numero`.

        Args:
            numero: Identificador del expediente.

        Returns:
            Snapshot completo del expediente con todos los campos que la
            fuente pueda proveer.

        Raises:
            ExpedienteNoEncontrado: si la fuente no encuentra el expediente.
            FuenteNoDisponible: si la fuente falla por motivos externos.
            ValueError: si `numero.camara` no es compatible con la fuente
                (ej. pedirle HSN a un HcdnScraper).
        """
        raise NotImplementedError
