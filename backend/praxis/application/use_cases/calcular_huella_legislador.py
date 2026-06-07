"""Caso de uso: calcular la huella parlamentaria del legislador titular
del despacho (feat-46).

Devuelve:
- Identidad: nombre, bloque dominante, distrito dominante, foto_url, total
  de proyectos firmados.
- Distribución por estado (% sobre el total de firmados): ingresado /
  en_comision / con_dictamen / media_sancion_hcdn / media_sancion_hsn /
  sancionado / caduco / archivado / desconocido. Cada estado tiene su
  % calculado para que el panel pueda renderizar barra apilada 100%.
- Distribución por tipo de expediente.
- Distribución por área temática (top 6).

NO modifica nada — solo agrega para visualización.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class CategoriaConPct:
    """Item de cualquier distribución (estado/tipo/area)."""

    key: str
    total: int
    pct: float        # 0-1 sobre el total general


@dataclass(frozen=True, slots=True)
class HuellaLegislador:
    nombre: str | None
    slug: str | None
    bloque_dominante: str | None
    distrito_dominante: str | None
    foto_url: str | None
    total_firmados: int
    por_estado: list[CategoriaConPct] = field(default_factory=list)
    por_tipo: list[CategoriaConPct] = field(default_factory=list)
    por_area: list[CategoriaConPct] = field(default_factory=list)


# Orden lógico de avance del trámite (para barra apilada).
ORDEN_ESTADOS = [
    "ingresado",
    "en_comision",
    "con_dictamen",
    "media_sancion_hcdn",
    "media_sancion_hsn",
    "sancionado",
    "caduco",
    "archivado",
    "desconocido",
]


class CalcularHuellaLegisladorTitular:
    """Use case principal de feat-46."""

    def __init__(self, *, session: AsyncSession) -> None:
        self._session = session

    async def ejecutar(
        self,
        *,
        despacho_id: UUID,
        slug: str | None,
        foto_url: str | None,
    ) -> HuellaLegislador:
        if not slug:
            return HuellaLegislador(
                nombre=None,
                slug=None,
                bloque_dominante=None,
                distrito_dominante=None,
                foto_url=foto_url,
                total_firmados=0,
            )

        # Match laxo: tomamos primera palabra del slug (apellido), bajamos
        # a lowercase. Maneja "JULIANO, PABLO" → "juliano".
        apellido = slug.strip().split(",")[0].strip().lower()
        like = f"%{apellido}%"

        identidad = await self._identidad(like)
        nombre = identidad["nombre"]
        bloque_dom = identidad["bloque"]
        distrito_dom = identidad["distrito"]
        total = identidad["total"]

        por_estado = await self._distribucion_estado(like, total)
        por_tipo = await self._distribucion_tipo(like, total)
        por_area = await self._distribucion_area(like, total)

        return HuellaLegislador(
            nombre=nombre,
            slug=slug,
            bloque_dominante=bloque_dom,
            distrito_dominante=distrito_dom,
            foto_url=foto_url,
            total_firmados=total,
            por_estado=por_estado,
            por_tipo=por_tipo,
            por_area=por_area,
        )

    # ------------------------------------------------------------------

    async def _identidad(self, like: str) -> dict:
        r = await self._session.execute(
            text("""
                SELECT
                    MAX(nombre) AS nombre,                  -- nombre canónico (any)
                    MODE() WITHIN GROUP (ORDER BY bloque)   AS bloque_dom,
                    MODE() WITHIN GROUP (ORDER BY distrito) AS distrito_dom,
                    COUNT(DISTINCT expediente_id)           AS total
                FROM firmante
                WHERE LOWER(nombre) LIKE :like
            """),
            {"like": like},
        )
        row = r.one_or_none()
        if row is None:
            return {"nombre": None, "bloque": None, "distrito": None, "total": 0}
        return {
            "nombre": row[0],
            "bloque": row[1],
            "distrito": row[2],
            "total": int(row[3] or 0),
        }

    async def _distribucion_estado(
        self, like: str, total: int,
    ) -> list[CategoriaConPct]:
        r = await self._session.execute(
            text("""
                SELECT e.estado, COUNT(DISTINCT e.id) c
                FROM expediente e
                JOIN firmante f ON f.expediente_id = e.id
                WHERE LOWER(f.nombre) LIKE :like
                GROUP BY e.estado
            """),
            {"like": like},
        )
        crudo = {row[0]: int(row[1]) for row in r.all()}
        # Devolver en orden lógico de avance, incluyendo ceros para
        # estados sin proyectos (la barra apilada queda completa).
        return [
            CategoriaConPct(
                key=estado,
                total=crudo.get(estado, 0),
                pct=(crudo.get(estado, 0) / total) if total else 0.0,
            )
            for estado in ORDEN_ESTADOS
            if crudo.get(estado, 0) > 0       # solo los que tienen al menos 1
        ]

    async def _distribucion_tipo(
        self, like: str, total: int,
    ) -> list[CategoriaConPct]:
        r = await self._session.execute(
            text("""
                SELECT e.tipo, COUNT(DISTINCT e.id) c
                FROM expediente e
                JOIN firmante f ON f.expediente_id = e.id
                WHERE LOWER(f.nombre) LIKE :like
                GROUP BY e.tipo ORDER BY c DESC
            """),
            {"like": like},
        )
        return [
            CategoriaConPct(
                key=row[0],
                total=int(row[1]),
                pct=(int(row[1]) / total) if total else 0.0,
            )
            for row in r.all()
        ]

    async def _distribucion_area(
        self, like: str, total: int,
    ) -> list[CategoriaConPct]:
        r = await self._session.execute(
            text("""
                SELECT eat.area, COUNT(DISTINCT e.id) c
                FROM expediente e
                JOIN firmante f ON f.expediente_id = e.id
                JOIN expediente_area_tematica eat ON eat.expediente_id = e.id
                WHERE LOWER(f.nombre) LIKE :like
                GROUP BY eat.area
                ORDER BY c DESC LIMIT 6
            """),
            {"like": like},
        )
        return [
            CategoriaConPct(
                key=row[0],
                total=int(row[1]),
                pct=(int(row[1]) / total) if total else 0.0,
            )
            for row in r.all()
        ]
