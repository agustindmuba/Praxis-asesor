"""Repositorio de Votacion (con sus VotoLegislador) sobre SQLAlchemy async.

Sin puerto explícito por ahora — el caso de uso del scraper lo usa
directo (ver ADR 0001 §"Puertos solo cuando hay 2+ adaptadores").

Si en el futuro se agrega un `FuenteVotaciones` para HSN o terceros,
se extrae el puerto sin romper consumers.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from praxis.domain import Camara, Votacion, VotoLegislador
from praxis.infrastructure.persistence.mappers import (
    from_votacion,
    to_votacion,
    to_voto_legislador,
)
from praxis.infrastructure.persistence.models import VotacionOrm


class SqlAlchemyVotacionRepository:
    """Persistencia de votaciones nominales + sus votos individuales."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Mutaciones
    # ------------------------------------------------------------------

    async def crear(
        self,
        votacion: Votacion,
        votos: list[VotoLegislador],
    ) -> Votacion:
        """Inserta votación + cascada de votos. Devuelve la Votacion hidratada."""
        orm = from_votacion(votacion, votos)
        self._session.add(orm)
        await self._session.flush()
        await self._session.refresh(orm, ["votos"])
        return to_votacion(orm)

    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------

    async def buscar_por_acta_id_hcdn(self, acta_id: int) -> Votacion | None:
        """Devuelve la Votacion identificada por su `acta_id_hcdn` (UNIQUE)."""
        stmt = (
            select(VotacionOrm)
            .where(VotacionOrm.acta_id_hcdn == acta_id)
            .options(selectinload(VotacionOrm.votos))
        )
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        return to_votacion(orm) if orm is not None else None

    async def buscar_por_id(self, id_: UUID) -> Votacion | None:
        stmt = (
            select(VotacionOrm)
            .where(VotacionOrm.id == id_)
            .options(selectinload(VotacionOrm.votos))
        )
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        return to_votacion(orm) if orm is not None else None

    async def listar_votos_de(self, votacion_id: UUID) -> list[VotoLegislador]:
        """Devuelve la lista de votos individuales para una Votacion."""
        stmt = (
            select(VotacionOrm)
            .where(VotacionOrm.id == votacion_id)
            .options(selectinload(VotacionOrm.votos))
        )
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        if orm is None:
            return []
        return [to_voto_legislador(v) for v in orm.votos]

    async def listar_recientes(
        self,
        *,
        camara: Camara | None = None,
        desde: date | None = None,
        hasta: date | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Votacion]:
        """Lista de votaciones ordenada por fecha desc.

        Sin cargar votos individuales (eso es buscar_por_id para ahorrar
        memoria cuando solo se muestran headers).
        """
        stmt = select(VotacionOrm).order_by(VotacionOrm.fecha.desc(), VotacionOrm.id.desc())
        if camara is not None:
            stmt = stmt.where(VotacionOrm.camara == camara.value)
        if desde is not None:
            stmt = stmt.where(VotacionOrm.fecha >= desde)
        if hasta is not None:
            stmt = stmt.where(VotacionOrm.fecha <= hasta)
        stmt = stmt.limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return [to_votacion(orm) for orm in result.scalars()]
