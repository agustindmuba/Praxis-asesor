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

from praxis.domain import (
    Camara,
    Comision,
    Expediente,
    NumeroExpediente,
    TipoExpediente,
)
from praxis.domain.legislador import Legislador


class FuenteExpedientes(ABC):
    """Puerto: una fuente desde la que se pueden obtener expedientes.

    Implementaciones esperadas:
    - `praxis.infrastructure.scrapers.hcdn.HcdnScraper`
    - `praxis.infrastructure.scrapers.hsn.HsnScraper`
    - Eventualmente: cache, persistencia local, otras fuentes públicas.

    Convención de errores:
    - `ExpedienteNoEncontrado` si el número no existe en la fuente.
    - `FuenteNoDisponible` si la fuente está caída o devuelve errores
      no-recuperables. Errores transitorios deben manejarse internamente
      con retries antes de propagar.
    """

    @abstractmethod
    async def buscar_por_numero(
        self,
        numero: NumeroExpediente,
        tipo: TipoExpediente | None = None,
    ) -> Expediente:
        """Devuelve el expediente identificado por `numero`.

        Args:
            numero: Identificador del expediente.
            tipo: Tipo del expediente. **Requerido para HSN** (la URL canónica
                lo incluye, ver spec `docs/specs/02-ingesta-hsn.md`). HCDN lo
                ignora (su búsqueda lo infiere del sumario). `None` para
                fuentes que no lo necesitan.

        Returns:
            Snapshot completo del expediente con todos los campos que la
            fuente pueda proveer.

        Raises:
            ExpedienteNoEncontrado: si la fuente no encuentra el expediente.
            FuenteNoDisponible: si la fuente falla por motivos externos.
            ValueError: si `numero.camara` no es compatible con la fuente,
                o si la fuente exige `tipo` y no se proveyó.
        """
        raise NotImplementedError


class CatalogoLegisladores(ABC):
    """Puerto: catálogo del padrón vigente de legisladores.

    Implementación esperada inicial: `praxis.infrastructure.padron.CsvPadronRepository`
    (lee de CSVs vendored del Observatorio). Futuras: DB, API oficial si existe.

    El padrón cambia con poca frecuencia (recambio bicameral, asunciones).
    Las implementaciones pueden cachear todo en memoria al inicio sin
    preocupación de staleness inmediata.
    """

    @abstractmethod
    def listar(self, camara: Camara) -> list[Legislador]:
        """Devuelve todos los legisladores vigentes de la cámara dada."""
        raise NotImplementedError

    @abstractmethod
    def buscar_por_slug(self, slug: str, camara: Camara) -> Legislador:
        """Devuelve el legislador identificado por su slug.

        Raises:
            KeyError: si no se encuentra el slug en esa cámara.
        """
        raise NotImplementedError

    @abstractmethod
    def buscar_por_nombre(self, query: str) -> list[Legislador]:
        """Devuelve legisladores cuyo apellido o nombre matche `query`
        (case-insensitive, substring). Busca en ambas cámaras.
        """
        raise NotImplementedError


class CatalogoComisiones(ABC):
    """Puerto: catálogo de comisiones legislativas.

    Implementación esperada inicial:
    `praxis.infrastructure.comisiones.LocalCatalogoComisiones` (lee CSV HCDN
    del Observatorio + JSON HSN oficial, ambos vendored).
    """

    @abstractmethod
    def listar(self, camara: Camara) -> list[Comision]:
        """Devuelve todas las comisiones registradas en la cámara dada."""
        raise NotImplementedError

    @abstractmethod
    def buscar_por_nombre(
        self,
        query: str,
        camara: Camara | None = None,
    ) -> list[Comision]:
        """Devuelve comisiones cuyo nombre contiene `query` (case-insensitive).

        Si `camara=None`, busca en ambas cámaras.
        """
        raise NotImplementedError
