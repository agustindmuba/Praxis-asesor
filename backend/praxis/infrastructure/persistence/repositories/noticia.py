"""Repositorios SQLAlchemy para Noticias (spec 16, feat-40.5).

Seis repos en un archivo porque pertenecen al mismo agregado y se
escriben/leen juntos en el pipeline de Celery (fuente → adapter →
artículo → bajada + clasificación + menciones).

- `SqlAlchemyFuenteNoticiaRepository`: catálogo de medios. `crear` +
  lookups + `listar_para_despacho` (globales + DISTRITALes del puente)
  + `marcar_revisada` (timestamp del polling).
- `SqlAlchemyArticuloRepository`: snapshots. UPSERT idempotente por
  `hash_dedup`. `actualizar_bajada_propia` muta el campo post-LLM.
- `SqlAlchemyArticuloHashRepository`: dedup forever, sobrevive a la
  purga del artículo a los 12 meses (D10).
- `SqlAlchemyClasificacionArticuloRepository`: UNIQUE en `articulo_id`,
  reclasificar = delete + insert.
- `SqlAlchemyArticuloRelevanteRepository`: tenant-scoped por
  `despacho_id`. Análogo a NormaBOAccionable.
- `SqlAlchemyMencionRepository`: tenant-scoped. `crear_lote` idempotente
  por `(articulo_id, legislador_id, despacho_id)`. `marcar_notificadas`
  + `listar_recientes_por_despacho` habilitan el anti-flood de
  feat-40.5C.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from praxis.application.ports import (
    ArticuloHashRepository,
    ArticuloRelevanteRepository,
    ArticuloRepository,
    ClasificacionArticuloRepository,
    FuenteNoticiaRepository,
    MencionRepository,
)
from praxis.domain import (
    MAX_BAJADA_PROPIA_CHARS,
    Articulo,
    ArticuloRelevante,
    ClasificacionArticulo,
    FuenteNoticia,
    Mencion,
    TipoFuenteNoticia,
)
from praxis.infrastructure.persistence.mappers import (
    from_articulo,
    from_articulo_relevante,
    from_clasificacion_articulo,
    from_fuente_noticia,
    from_mencion,
    to_articulo,
    to_articulo_relevante,
    to_clasificacion_articulo,
    to_fuente_noticia,
    to_mencion,
)
from praxis.infrastructure.persistence.models import (
    ArticuloHashOrm,
    ArticuloOrm,
    ArticuloRelevanteOrm,
    ClasificacionArticuloOrm,
    FuenteNoticiaDespachoOrm,
    FuenteNoticiaOrm,
    MencionOrm,
)

# ---------------------------------------------------------------------------
# FuenteNoticia
# ---------------------------------------------------------------------------


class SqlAlchemyFuenteNoticiaRepository(FuenteNoticiaRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def crear(self, fuente: FuenteNoticia) -> FuenteNoticia:
        """Inserta una fuente nueva. El UNIQUE en `dominio` aborta el
        flush si el dominio ya estaba; el caller debe chequear con
        `buscar_por_dominio` antes."""
        orm = from_fuente_noticia(fuente)
        self._session.add(orm)
        await self._session.flush()
        return to_fuente_noticia(orm)

    async def buscar_por_id(self, fuente_id: UUID) -> FuenteNoticia | None:
        stmt = select(FuenteNoticiaOrm).where(FuenteNoticiaOrm.id == fuente_id)
        orm = (await self._session.execute(stmt)).scalar_one_or_none()
        return to_fuente_noticia(orm) if orm else None

    async def buscar_por_dominio(self, dominio: str) -> FuenteNoticia | None:
        stmt = select(FuenteNoticiaOrm).where(
            FuenteNoticiaOrm.dominio == dominio.lower(),
        )
        orm = (await self._session.execute(stmt)).scalar_one_or_none()
        return to_fuente_noticia(orm) if orm else None

    async def listar_activas(self) -> list[FuenteNoticia]:
        stmt = (
            select(FuenteNoticiaOrm)
            .where(FuenteNoticiaOrm.activa.is_(True))
            .order_by(FuenteNoticiaOrm.nombre)
        )
        result = await self._session.execute(stmt)
        return [to_fuente_noticia(r) for r in result.scalars().all()]

    async def listar_para_despacho(
        self, despacho_id: UUID,
    ) -> list[FuenteNoticia]:
        """Globales (tipo NACIONAL + POLITICO, activas) + DISTRITALES
        asociadas a este despacho via puente."""
        join_subq = (
            select(FuenteNoticiaDespachoOrm.fuente_id)
            .where(FuenteNoticiaDespachoOrm.despacho_id == despacho_id)
        )
        stmt = (
            select(FuenteNoticiaOrm)
            .where(
                FuenteNoticiaOrm.activa.is_(True),
                or_(
                    FuenteNoticiaOrm.tipo.in_(
                        [TipoFuenteNoticia.NACIONAL.value,
                         TipoFuenteNoticia.POLITICO.value],
                    ),
                    FuenteNoticiaOrm.id.in_(join_subq),
                ),
            )
            .order_by(FuenteNoticiaOrm.nombre)
        )
        result = await self._session.execute(stmt)
        return [to_fuente_noticia(r) for r in result.scalars().all()]

    async def marcar_revisada(
        self, fuente_id: UUID, *, momento: datetime,
    ) -> None:
        stmt = (
            update(FuenteNoticiaOrm)
            .where(FuenteNoticiaOrm.id == fuente_id)
            .values(ultima_revision=momento)
        )
        await self._session.execute(stmt)


# ---------------------------------------------------------------------------
# Articulo
# ---------------------------------------------------------------------------


class SqlAlchemyArticuloRepository(ArticuloRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_lote(self, articulos: list[Articulo]) -> list[Articulo]:
        """Idempotente por `hash_dedup` UNIQUE.

        Para cada artículo: si `hash_dedup` ya existe, devuelve el
        existente sin tocar. Si no, inserta. Esto preserva
        `bajada_propia` y `capturado_en` de la versión original.
        """
        if not articulos:
            return []
        resultado: list[Articulo] = []
        for art in articulos:
            existente = await self.buscar_por_hash(art.hash_dedup)
            if existente is not None:
                resultado.append(existente)
                continue
            orm = from_articulo(art)
            self._session.add(orm)
            await self._session.flush()
            resultado.append(to_articulo(orm))
        return resultado

    async def buscar_por_id(self, articulo_id: UUID) -> Articulo | None:
        stmt = select(ArticuloOrm).where(ArticuloOrm.id == articulo_id)
        orm = (await self._session.execute(stmt)).scalar_one_or_none()
        return to_articulo(orm) if orm else None

    async def buscar_por_hash(self, hash_dedup: str) -> Articulo | None:
        stmt = select(ArticuloOrm).where(ArticuloOrm.hash_dedup == hash_dedup)
        orm = (await self._session.execute(stmt)).scalar_one_or_none()
        return to_articulo(orm) if orm else None

    async def listar_por_fuente(
        self, fuente_id: UUID, *, desde: datetime,
    ) -> list[Articulo]:
        stmt = (
            select(ArticuloOrm)
            .where(
                ArticuloOrm.fuente_id == fuente_id,
                ArticuloOrm.capturado_en >= desde,
            )
            .order_by(ArticuloOrm.capturado_en.desc())
        )
        result = await self._session.execute(stmt)
        return [to_articulo(r) for r in result.scalars().all()]

    async def actualizar_bajada_propia(
        self, articulo_id: UUID, *, bajada: str,
    ) -> Articulo:
        if len(bajada) > MAX_BAJADA_PROPIA_CHARS:
            raise ValueError(
                f"bajada excede {MAX_BAJADA_PROPIA_CHARS} chars "
                f"(recibido {len(bajada)})",
            )
        stmt = (
            update(ArticuloOrm)
            .where(ArticuloOrm.id == articulo_id)
            .values(bajada_propia=bajada)
        )
        result = await self._session.execute(stmt)
        if result.rowcount == 0:  # type: ignore[attr-defined]
            raise ValueError(f"Articulo {articulo_id} no existe")
        actualizado = await self.buscar_por_id(articulo_id)
        assert actualizado is not None
        return actualizado


# ---------------------------------------------------------------------------
# ArticuloHash (dedup forever)
# ---------------------------------------------------------------------------


class SqlAlchemyArticuloHashRepository(ArticuloHashRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def registrar(self, hash_dedup: str) -> bool:
        """True si era nuevo; False si ya estaba (chequeo previo
        explícito para no levantar IntegrityError)."""
        if await self.existe(hash_dedup):
            return False
        self._session.add(ArticuloHashOrm(hash_dedup=hash_dedup))
        await self._session.flush()
        return True

    async def existe(self, hash_dedup: str) -> bool:
        stmt = select(ArticuloHashOrm.hash_dedup).where(
            ArticuloHashOrm.hash_dedup == hash_dedup,
        )
        return (
            await self._session.execute(stmt)
        ).scalar_one_or_none() is not None


# ---------------------------------------------------------------------------
# ClasificacionArticulo
# ---------------------------------------------------------------------------


class SqlAlchemyClasificacionArticuloRepository(
    ClasificacionArticuloRepository,
):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def buscar_por_articulo(
        self, articulo_id: UUID,
    ) -> ClasificacionArticulo | None:
        stmt = select(ClasificacionArticuloOrm).where(
            ClasificacionArticuloOrm.articulo_id == articulo_id,
        )
        orm = (await self._session.execute(stmt)).scalar_one_or_none()
        return to_clasificacion_articulo(orm) if orm else None

    async def crear(
        self, clasif: ClasificacionArticulo,
    ) -> ClasificacionArticulo:
        orm = from_clasificacion_articulo(clasif)
        self._session.add(orm)
        await self._session.flush()
        return to_clasificacion_articulo(orm)

    async def eliminar(self, articulo_id: UUID) -> bool:
        stmt = delete(ClasificacionArticuloOrm).where(
            ClasificacionArticuloOrm.articulo_id == articulo_id,
        )
        result = await self._session.execute(stmt)
        return result.rowcount > 0  # type: ignore[attr-defined,no-any-return]


# ---------------------------------------------------------------------------
# ArticuloRelevante (tenant-scoped)
# ---------------------------------------------------------------------------


class SqlAlchemyArticuloRelevanteRepository(ArticuloRelevanteRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self, relevante: ArticuloRelevante,
    ) -> ArticuloRelevante:
        """UPSERT por PK compuesta `(articulo_id, despacho_id)`. Si
        existe, actualiza score/razon/expedientes. Si no, inserta."""
        existente = await self._buscar(
            relevante.articulo_id, relevante.despacho_id,
        )
        if existente is not None:
            stmt_upd = (
                update(ArticuloRelevanteOrm)
                .where(
                    ArticuloRelevanteOrm.articulo_id == relevante.articulo_id,
                    ArticuloRelevanteOrm.despacho_id == relevante.despacho_id,
                )
                .values(
                    score=relevante.score,
                    razon=relevante.razon,
                    expedientes_tocados=[
                        str(eid) for eid in relevante.expedientes_tocados
                    ],
                )
            )
            await self._session.execute(stmt_upd)
        else:
            self._session.add(from_articulo_relevante(relevante))
        await self._session.flush()
        actualizado = await self._buscar(
            relevante.articulo_id, relevante.despacho_id,
        )
        assert actualizado is not None
        return actualizado

    async def _buscar(
        self, articulo_id: UUID, despacho_id: UUID,
    ) -> ArticuloRelevante | None:
        stmt = select(ArticuloRelevanteOrm).where(
            ArticuloRelevanteOrm.articulo_id == articulo_id,
            ArticuloRelevanteOrm.despacho_id == despacho_id,
        )
        orm = (await self._session.execute(stmt)).scalar_one_or_none()
        return to_articulo_relevante(orm) if orm else None

    async def listar_por_despacho_24h(
        self,
        *,
        despacho_id: UUID,
        hasta: datetime,
        top_n: int | None = None,
    ) -> list[ArticuloRelevante]:
        desde = hasta - timedelta(hours=24)
        stmt = (
            select(ArticuloRelevanteOrm)
            .where(
                ArticuloRelevanteOrm.despacho_id == despacho_id,
                ArticuloRelevanteOrm.generado_en >= desde,
                ArticuloRelevanteOrm.generado_en <= hasta,
            )
            .order_by(ArticuloRelevanteOrm.score.desc())
        )
        if top_n is not None:
            stmt = stmt.limit(top_n)
        result = await self._session.execute(stmt)
        return [to_articulo_relevante(r) for r in result.scalars().all()]

    async def borrar_por_despacho_y_ventana(
        self,
        *,
        despacho_id: UUID,
        desde: datetime,
        hasta: datetime,
    ) -> int:
        stmt = delete(ArticuloRelevanteOrm).where(
            ArticuloRelevanteOrm.despacho_id == despacho_id,
            ArticuloRelevanteOrm.generado_en >= desde,
            ArticuloRelevanteOrm.generado_en <= hasta,
        )
        result = await self._session.execute(stmt)
        return int(result.rowcount or 0)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Mencion (tenant-scoped)
# ---------------------------------------------------------------------------


class SqlAlchemyMencionRepository(MencionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def crear_lote(self, menciones: list[Mencion]) -> list[Mencion]:
        if not menciones:
            return []
        resultado: list[Mencion] = []
        for m in menciones:
            existente = await self._buscar_natural(
                m.articulo_id, m.legislador_id, m.despacho_id,
            )
            if existente is not None:
                resultado.append(existente)
                continue
            orm = from_mencion(m)
            self._session.add(orm)
            await self._session.flush()
            resultado.append(to_mencion(orm))
        return resultado

    async def _buscar_natural(
        self, articulo_id: UUID, legislador_id: UUID, despacho_id: UUID,
    ) -> Mencion | None:
        stmt = select(MencionOrm).where(
            MencionOrm.articulo_id == articulo_id,
            MencionOrm.legislador_id == legislador_id,
            MencionOrm.despacho_id == despacho_id,
        )
        orm = (await self._session.execute(stmt)).scalar_one_or_none()
        return to_mencion(orm) if orm else None

    async def listar_historico(
        self,
        *,
        despacho_id: UUID,
        desde: datetime,
        hasta: datetime,
        tono: str | None = None,
        fuente_id: UUID | None = None,
    ) -> list[Mencion]:
        stmt = (
            select(MencionOrm)
            .where(
                MencionOrm.despacho_id == despacho_id,
                MencionOrm.detectado_en >= desde,
                MencionOrm.detectado_en <= hasta,
            )
            .order_by(MencionOrm.detectado_en.desc())
        )
        if tono is not None:
            stmt = stmt.where(MencionOrm.tono == tono)
        if fuente_id is not None:
            # JOIN sobre articulo para filtrar por fuente del medio.
            stmt = stmt.join(
                ArticuloOrm, ArticuloOrm.id == MencionOrm.articulo_id,
            ).where(ArticuloOrm.fuente_id == fuente_id)
        result = await self._session.execute(stmt)
        return [to_mencion(r) for r in result.scalars().all()]

    async def buscar_por_id(
        self, *, despacho_id: UUID, mencion_id: UUID,
    ) -> Mencion | None:
        stmt = select(MencionOrm).where(
            MencionOrm.id == mencion_id,
            MencionOrm.despacho_id == despacho_id,
        )
        orm = (await self._session.execute(stmt)).scalar_one_or_none()
        return to_mencion(orm) if orm else None

    async def listar_por_despacho_no_notificadas(
        self, despacho_id: UUID, *, limite: int = 100,
    ) -> list[Mencion]:
        stmt = (
            select(MencionOrm)
            .where(
                MencionOrm.despacho_id == despacho_id,
                MencionOrm.notificada.is_(False),
            )
            .order_by(MencionOrm.detectado_en.desc())
            .limit(limite)
        )
        result = await self._session.execute(stmt)
        return [to_mencion(r) for r in result.scalars().all()]

    async def listar_recientes_por_despacho(
        self,
        despacho_id: UUID,
        *,
        desde: datetime,
        hasta: datetime,
    ) -> list[Mencion]:
        stmt = (
            select(MencionOrm)
            .where(
                MencionOrm.despacho_id == despacho_id,
                MencionOrm.detectado_en >= desde,
                MencionOrm.detectado_en <= hasta,
            )
            .order_by(MencionOrm.detectado_en.desc())
        )
        result = await self._session.execute(stmt)
        return [to_mencion(r) for r in result.scalars().all()]

    async def marcar_notificadas(self, mencion_ids: list[UUID]) -> int:
        if not mencion_ids:
            return 0
        stmt = (
            update(MencionOrm)
            .where(MencionOrm.id.in_(mencion_ids))
            .values(notificada=True)
        )
        result = await self._session.execute(stmt)
        return int(result.rowcount or 0)  # type: ignore[attr-defined]
