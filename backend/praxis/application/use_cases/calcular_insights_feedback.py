"""Caso de uso: insights del feedback del asesor sobre accionables (feat-43.3).

Lee la columna `estado` de `accionable_evento` (feat-43.2) en una ventana
de tiempo y calcula:

- Distribución por tipo de acción (pedido_informes, retweet_critico, etc.):
  cuántos hechos / ignorados / adaptados / pendientes y % ignorado.
- Sugerencias automáticas:
  * Si un tipo de acción tiene ≥ 60% de "ignorado" sobre al menos 5
    accionables → sugerir bajar el tono de ese tipo en el perfil.
  * Si un tipo de acción tiene ≥ 60% de "adaptado" con notas similares,
    sugerir que el asesor lo revise (probable patrón).
  * Si hay ≥ 5 accionables pendientes con > 7 días → "acumulación de
    backlog".

NO modifica el perfil opositor — solo devuelve recomendaciones. El asesor
decide si las aplica desde la UI (`/configuracion/perfil-opositor`).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)


VENTANA_DIAS_DEFAULT = 28
UMBRAL_MIN_MUESTRAS = 5         # No sugerir sobre menos de N accionables.
UMBRAL_PCT_IGNORADO = 0.60      # 60% para gatillar "bajar tono".
UMBRAL_PCT_ADAPTADO = 0.60
UMBRAL_BACKLOG_DIAS = 7


@dataclass(frozen=True, slots=True)
class DistribucionAccion:
    accion: str
    total: int
    pendientes: int
    hechos: int
    ignorados: int
    adaptados: int

    @property
    def pct_ignorado(self) -> float:
        cerrados = self.hechos + self.ignorados + self.adaptados
        return self.ignorados / cerrados if cerrados else 0.0

    @property
    def pct_hecho(self) -> float:
        cerrados = self.hechos + self.ignorados + self.adaptados
        return self.hechos / cerrados if cerrados else 0.0

    @property
    def pct_adaptado(self) -> float:
        cerrados = self.hechos + self.ignorados + self.adaptados
        return self.adaptados / cerrados if cerrados else 0.0


@dataclass(frozen=True, slots=True)
class SugerenciaInsight:
    tipo: str         # "bajar_tono" | "revisar_patron_adaptado" | "backlog"
    accion_objetivo: str | None  # tipo de acción afectada (si aplica)
    mensaje: str
    severidad: str    # "alta" | "media" | "baja"


@dataclass(frozen=True, slots=True)
class InsightsFeedback:
    ventana_dias: int
    total_accionables: int
    total_con_feedback: int       # estados != pendiente
    distribucion: list[DistribucionAccion] = field(default_factory=list)
    sugerencias: list[SugerenciaInsight] = field(default_factory=list)


class CalcularInsightsFeedback:
    """Use case principal de feat-43.3."""

    def __init__(self, *, session: AsyncSession) -> None:
        self._session = session

    async def ejecutar(
        self,
        *,
        despacho_id: UUID,
        ventana_dias: int = VENTANA_DIAS_DEFAULT,
        ahora: datetime | None = None,
    ) -> InsightsFeedback:
        ahora = ahora or datetime.now(UTC)
        desde = ahora - timedelta(days=ventana_dias)

        distribucion = await self._distribucion(despacho_id, desde)
        total = sum(d.total for d in distribucion)
        con_feedback = sum(
            d.hechos + d.ignorados + d.adaptados for d in distribucion
        )
        backlog = await self._backlog_antiguo(despacho_id, ahora)

        sugerencias = self._sugerencias(distribucion, backlog_n=backlog)

        return InsightsFeedback(
            ventana_dias=ventana_dias,
            total_accionables=total,
            total_con_feedback=con_feedback,
            distribucion=distribucion,
            sugerencias=sugerencias,
        )

    # ------------------------------------------------------------------

    async def _distribucion(
        self, despacho_id: UUID, desde: datetime,
    ) -> list[DistribucionAccion]:
        """Distribución por acción dentro de la ventana.

        Cuenta los accionables generados dentro de la ventana. Para los
        que NO tienen marcado_en (pendientes), se cuentan en `pendientes`.
        Los que sí, en su `estado`.
        """
        r = await self._session.execute(
            text("""
                SELECT
                    accion_sugerida,
                    COUNT(*) AS total,
                    SUM(CASE WHEN estado = 'pendiente' THEN 1 ELSE 0 END) AS pendientes,
                    SUM(CASE WHEN estado = 'hecho'     THEN 1 ELSE 0 END) AS hechos,
                    SUM(CASE WHEN estado = 'ignorado'  THEN 1 ELSE 0 END) AS ignorados,
                    SUM(CASE WHEN estado = 'adaptado'  THEN 1 ELSE 0 END) AS adaptados
                FROM accionable_evento
                WHERE despacho_id = :did
                  AND COALESCE(generado_en, creado_en) >= :desde
                GROUP BY accion_sugerida
                ORDER BY total DESC
            """),
            {"did": despacho_id, "desde": desde},
        )
        return [
            DistribucionAccion(
                accion=row[0],
                total=int(row[1]),
                pendientes=int(row[2] or 0),
                hechos=int(row[3] or 0),
                ignorados=int(row[4] or 0),
                adaptados=int(row[5] or 0),
            )
            for row in r.all()
        ]

    async def _backlog_antiguo(
        self, despacho_id: UUID, ahora: datetime,
    ) -> int:
        """Cuenta accionables que llevan más de N días pendientes."""
        umbral = ahora - timedelta(days=UMBRAL_BACKLOG_DIAS)
        r = await self._session.execute(
            text("""
                SELECT COUNT(*) FROM accionable_evento
                WHERE despacho_id = :did
                  AND estado = 'pendiente'
                  AND COALESCE(generado_en, creado_en) < :umbral
            """),
            {"did": despacho_id, "umbral": umbral},
        )
        return int(r.scalar() or 0)

    def _sugerencias(
        self,
        distribucion: list[DistribucionAccion],
        *,
        backlog_n: int,
    ) -> list[SugerenciaInsight]:
        sugerencias: list[SugerenciaInsight] = []

        for d in distribucion:
            cerrados = d.hechos + d.ignorados + d.adaptados
            if cerrados < UMBRAL_MIN_MUESTRAS:
                continue  # poca evidencia, no sugerir.
            if d.pct_ignorado >= UMBRAL_PCT_IGNORADO:
                sugerencias.append(SugerenciaInsight(
                    tipo="bajar_tono",
                    accion_objetivo=d.accion,
                    mensaje=(
                        f"De los últimos {cerrados} accionables tipo "
                        f"'{d.accion}', el {round(d.pct_ignorado*100)}% "
                        f"los dejaste pasar. El bot está sobre-sugiriendo "
                        f"esta acción — considerá bajar su tono en el perfil."
                    ),
                    severidad="alta" if d.pct_ignorado >= 0.80 else "media",
                ))
            elif d.pct_adaptado >= UMBRAL_PCT_ADAPTADO:
                sugerencias.append(SugerenciaInsight(
                    tipo="revisar_patron_adaptado",
                    accion_objetivo=d.accion,
                    mensaje=(
                        f"De los últimos {cerrados} accionables tipo "
                        f"'{d.accion}', el {round(d.pct_adaptado*100)}% "
                        f"los hiciste 'distinto'. Quizás conviene ajustar "
                        f"el prompt del bot para que sugiera más cerca de "
                        f"tu estilo."
                    ),
                    severidad="media",
                ))

        if backlog_n >= UMBRAL_MIN_MUESTRAS:
            sugerencias.append(SugerenciaInsight(
                tipo="backlog",
                accion_objetivo=None,
                mensaje=(
                    f"Tenés {backlog_n} accionables pendientes desde hace "
                    f"más de {UMBRAL_BACKLOG_DIAS} días. Marcalos como "
                    f"'hecho', 'ignorar' o 'distinto' para que el bot "
                    f"aprenda."
                ),
                severidad="baja" if backlog_n < 10 else "media",
            ))

        return sugerencias
