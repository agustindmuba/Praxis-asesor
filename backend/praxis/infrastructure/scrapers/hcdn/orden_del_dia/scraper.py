"""Scraper async del Plan de Labor / Temario de HCDN (feat-45.2)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import httpx

from praxis.infrastructure.scrapers.hcdn.orden_del_dia.parser import (
    OrdenDelDiaParseado,
    extraer_pdf_base64,
    parsear_pdf_temario,
)

log = logging.getLogger(__name__)

HCDN_BASE = "https://www.hcdn.gob.ar"
PLT_URL = f"{HCDN_BASE}/secparl/dclp/plan_de_labor/plt.html"
PROCESAR_URL = f"{HCDN_BASE}/secparl/dclp/procesar.html"

DEFAULT_UA = "PraxisAsesor/0.1 (+contacto@dominio.com)"
DEFAULT_TIMEOUT = 60.0          # PDFs base64 son grandes (200-500KB)


@dataclass(frozen=True, slots=True)
class SesionDisponible:
    """Una entrada de la lista de sesiones del Plan de Labor."""

    id_sesion: int
    titulo: str                 # texto del link en el listado, sin formato canónico


class HcdnOrdenDelDiaScraper:
    """Encapsula la captura del temario de HCDN.

    Diseñado para uso en Celery task: cada método es independiente,
    re-corre desde cero si falla parcialmente.
    """

    def __init__(
        self,
        *,
        user_agent: str = DEFAULT_UA,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._headers = {"User-Agent": user_agent}
        self._timeout = timeout

    async def listar_sesiones(self) -> list[SesionDisponible]:
        """Devuelve los `id_sesion` listados en `plt.html`.

        El portal mantiene años atrás. El scraper devuelve TODO lo que
        encuentra; el caller filtra por fecha si necesita.
        """
        async with httpx.AsyncClient(
            headers=self._headers, timeout=self._timeout, follow_redirects=True,
        ) as client:
            r = await client.get(PLT_URL)
            r.raise_for_status()
            html = r.text

        sesiones: list[SesionDisponible] = []
        # Patron: href="/secparl/dclp/procesar.html?id_sesion=3581&tipo=temario"
        for m in re.finditer(
            r'href="/secparl/dclp/procesar\.html\?id_sesion=(\d+)&(?:amp;)?tipo=temario"[^>]*>([^<]*)',
            html,
        ):
            id_sesion = int(m.group(1))
            titulo = m.group(2).strip() if m.group(2) else ""
            sesiones.append(SesionDisponible(id_sesion=id_sesion, titulo=titulo))
        log.info("listar_sesiones: %d sesiones encontradas", len(sesiones))
        return sesiones

    async def obtener_temario(self, id_sesion: int) -> OrdenDelDiaParseado:
        """Descarga el HTML wrapper + decodifica el PDF + parsea."""
        url = f"{PROCESAR_URL}?id_sesion={id_sesion}&tipo=temario"
        async with httpx.AsyncClient(
            headers=self._headers, timeout=self._timeout, follow_redirects=True,
        ) as client:
            r = await client.get(url)
            r.raise_for_status()
            html = r.text

        pdf_bytes = extraer_pdf_base64(html)
        log.info(
            "obtener_temario: id_sesion=%d, pdf=%d bytes",
            id_sesion, len(pdf_bytes),
        )
        return parsear_pdf_temario(pdf_bytes)
