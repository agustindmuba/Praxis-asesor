"""Caso de uso: detectar Órdenes del Día nuevas en el portal HCDN y
persistirlas (feat-45.3).

Pipeline:
1. Llama al scraper `HcdnOrdenDelDiaScraper.listar_sesiones()` →
   N sesiones disponibles en el plt.html del portal.
2. Compara cada `id_sesion` con DB. Si ya tenemos un `OrdenDelDia`
   con ese `id_sesion_externa`, se skipea (idempotencia).
3. Para las nuevas, baja el temario completo y resuelve cada N°
   expediente del PDF a `Expediente.id` en la DB local.
4. Crea el `OrdenDelDia` con los UUIDs encontrados + el resumen del
   scraper (fecha, tipo sesión, id externo).

No genera el briefing acá — eso lo dispara el caller (en producción,
la Celery task de feat-45.4 corre esto y después un GenerarBriefing
por despacho con perfil_opositor cargado).

Diseño: read-only contra HCDN + write only-new contra DB. Idempotente,
re-corre sin riesgo (no duplica).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from praxis.application.ports import OrdenDelDiaRepository
from praxis.domain import Camara, OrdenDelDia
from praxis.infrastructure.scrapers.hcdn.orden_del_dia import (
    HcdnOrdenDelDiaScraper,
)

log = logging.getLogger(__name__)


# Formato N° expediente desde el PDF: NNNN-X-AAAA (ya normalizado por
# el parser). El UNIQUE en DB es (numero, origen, anio) pero usa
# `letra` opcional en algunos casos.
_NUM_EXP_RE = re.compile(r"(\d{4})-([A-Z]{1,4})-(\d{2,4})")


@dataclass(frozen=True, slots=True)
class ResultadoDetectarOD:
    sesiones_disponibles_total: int
    sesiones_nuevas: int
    ods_creados: int
    expedientes_resueltos_total: int
    expedientes_no_encontrados_total: int
    detalle_por_sesion: list[dict] = field(default_factory=list)


class DetectarNuevoOd:
    """Use case principal de feat-45.3."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        ordenes_repo: OrdenDelDiaRepository,
        scraper: HcdnOrdenDelDiaScraper | None = None,
    ) -> None:
        self._session = session
        self._ordenes_repo = ordenes_repo
        self._scraper = scraper or HcdnOrdenDelDiaScraper()

    async def ejecutar(
        self, *, max_nuevas: int = 5,
    ) -> ResultadoDetectarOD:
        sesiones = await self._scraper.listar_sesiones()
        log.info("detectar_nuevo_od: %d sesiones listadas", len(sesiones))

        # Sesiones ya importadas
        existentes = await self._ids_externas_existentes()

        nuevas = [s for s in sesiones if s.id_sesion not in existentes]
        nuevas_limitadas = nuevas[:max_nuevas]
        log.info(
            "detectar_nuevo_od: %d nuevas (de %d), procesando hasta %d",
            len(nuevas), len(sesiones), max_nuevas,
        )

        creados = 0
        expedientes_resueltos = 0
        expedientes_no_encontrados = 0
        detalles: list[dict] = []
        for sesion in nuevas_limitadas:
            try:
                temario = await self._scraper.obtener_temario(sesion.id_sesion)
            except Exception as exc:
                log.warning(
                    "obtener_temario id=%d falló: %s", sesion.id_sesion, exc,
                )
                detalles.append({
                    "id_sesion": sesion.id_sesion,
                    "error": str(exc)[:120],
                    "creado": False,
                })
                continue

            # Resolver N° expediente → UUID en DB
            uuids: list[UUID] = []
            no_encontrados: list[str] = []
            for it in temario.items:
                eid = await self._resolver_numero_a_uuid(it.numero_expediente)
                if eid is None:
                    no_encontrados.append(it.numero_expediente)
                else:
                    uuids.append(eid)
            expedientes_resueltos += len(uuids)
            expedientes_no_encontrados += len(no_encontrados)

            # Construir + persistir el OD
            try:
                od = OrdenDelDia(
                    camara=Camara.HCDN,
                    fecha_sesion=temario.fecha_sesion or date.today(),
                    hora_sesion=None,
                    titulo=self._titular(temario.tipo_sesion, sesion.id_sesion),
                    fuente="scraping_hcdn",
                    expedientes_ids=uuids,
                    id_sesion_externa=sesion.id_sesion,
                )
            except ValueError as exc:
                log.warning(
                    "construir OD id=%d falló: %s", sesion.id_sesion, exc,
                )
                detalles.append({
                    "id_sesion": sesion.id_sesion,
                    "error": str(exc)[:120],
                    "creado": False,
                })
                continue

            await self._ordenes_repo.crear(od)
            creados += 1
            detalles.append({
                "id_sesion": sesion.id_sesion,
                "fecha_sesion": str(od.fecha_sesion),
                "tipo_sesion": temario.tipo_sesion,
                "items_total": len(temario.items),
                "resueltos": len(uuids),
                "no_encontrados": len(no_encontrados),
                "creado": True,
            })

        await self._session.commit()
        return ResultadoDetectarOD(
            sesiones_disponibles_total=len(sesiones),
            sesiones_nuevas=len(nuevas),
            ods_creados=creados,
            expedientes_resueltos_total=expedientes_resueltos,
            expedientes_no_encontrados_total=expedientes_no_encontrados,
            detalle_por_sesion=detalles,
        )

    # ------------------------------------------------------------------

    async def _ids_externas_existentes(self) -> set[int]:
        r = await self._session.execute(text(
            "SELECT DISTINCT id_sesion_externa FROM orden_del_dia "
            "WHERE id_sesion_externa IS NOT NULL"
        ))
        return {int(row[0]) for row in r.all()}

    async def _resolver_numero_a_uuid(self, numero: str) -> UUID | None:
        m = _NUM_EXP_RE.match(numero)
        if not m:
            return None
        num = int(m.group(1))
        origen = m.group(2)
        anio = int(m.group(3))
        if anio < 100:
            anio += 2000
        r = await self._session.execute(text("""
            SELECT id FROM expediente
            WHERE numero = :n AND origen = :o AND anio = :a
            LIMIT 1
        """), {"n": num, "o": origen, "a": anio})
        row = r.one_or_none()
        return UUID(str(row[0])) if row else None

    def _titular(self, tipo_sesion: str | None, id_sesion: int) -> str:
        if tipo_sesion:
            return f"Sesión {tipo_sesion} HCDN (id {id_sesion})"
        return f"Sesión HCDN (id {id_sesion})"
