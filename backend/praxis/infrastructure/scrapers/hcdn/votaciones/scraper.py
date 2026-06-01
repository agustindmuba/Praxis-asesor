"""Scraper async del portal de votaciones HCDN.

I/O contra `https://votaciones.hcdn.gob.ar/` con rate limit + retries.
Reutiliza el mismo User-Agent y el patrón de backoff exponencial que
`HcdnScraper` para que el portal vea a Praxis como un cliente consistente.

Hay dos operaciones:

- `listar_indice(*, anio, texto)`: devuelve hasta 500 items (limite del
  portal) — usar `anio` para paginar por año si se necesita ir más atrás.
- `obtener_acta(acta_id)`: devuelve el detalle parseado.

El parsing puro vive en `parser.py`. Este archivo solo se ocupa de I/O.
"""

from __future__ import annotations

import asyncio
import time

import httpx
import structlog

from praxis.domain import (
    FuenteNoDisponible,
    Votacion,
    VotoLegislador,
)
from praxis.infrastructure.scrapers.hcdn.votaciones.parser import (
    IndiceItem,
    parse_acta_votacion,
    parse_indice_votaciones,
)

log = structlog.get_logger(__name__)

VOTACIONES_BASE = "https://votaciones.hcdn.gob.ar"
VOTACIONES_INDEX_URL = f"{VOTACIONES_BASE}/votaciones/search"
VOTACIONES_DETALLE_URL_TMPL = f"{VOTACIONES_BASE}/votacion/{{acta_id}}"

# Mismo UA que HcdnScraper (data-sources.md §"Reglas generales").
DEFAULT_USER_AGENT = "PraxisAsesor/0.1 (+contacto@dominio.com)"
DEFAULT_RATE_LIMIT_SECONDS = 1.0
DEFAULT_MAX_RETRIES = 3


class VotacionesHcdnScraper:
    """Adaptador concreto del portal de votaciones HCDN."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        user_agent: str = DEFAULT_USER_AGENT,
        rate_limit_seconds: float = DEFAULT_RATE_LIMIT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        self._client = client
        self._user_agent = user_agent
        self._rate_limit_seconds = rate_limit_seconds
        self._max_retries = max_retries
        self._lock = asyncio.Lock()
        self._last_request_time: float = 0.0

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    async def listar_indice(
        self,
        *,
        anio: int | None = None,
        texto: str | None = None,
    ) -> list[IndiceItem]:
        """Devuelve el listado de votaciones del portal.

        Sin parámetros: las 500 más recientes.
        Con `anio`: filtra por año (1993..2026 según verificó el spike).
        Con `texto`: búsqueda libre en el título.

        Si la combinación no devuelve resultados, lista vacía.
        """
        params: dict[str, str] = {}
        if anio is not None:
            params["anoSearch"] = str(anio)
        if texto is not None:
            params["txtSearch"] = texto
        log.info("votaciones.listar.inicio", anio=anio, texto=texto)
        html = await self._get_with_retries(VOTACIONES_INDEX_URL, params=params)
        items = parse_indice_votaciones(html)
        log.info(
            "votaciones.listar.ok",
            anio=anio,
            texto=texto,
            total=len(items),
        )
        return items

    async def obtener_acta(
        self,
        acta_id: int,
    ) -> tuple[Votacion, list[VotoLegislador]]:
        """Devuelve `(Votacion, list[VotoLegislador])` para un acta_id.

        Levanta `FuenteNoDisponible` si el portal devuelve 4xx/5xx o si
        el HTML no es parseable.
        """
        url = VOTACIONES_DETALLE_URL_TMPL.format(acta_id=acta_id)
        log.info("votaciones.obtener_acta.inicio", acta_id=acta_id)
        html = await self._get_with_retries(url)
        try:
            votacion, votos = parse_acta_votacion(
                html,
                acta_id=acta_id,
                fuente_url=url,
            )
        except ValueError as exc:
            log.error(
                "votaciones.obtener_acta.parse_error",
                acta_id=acta_id,
                error=str(exc),
            )
            raise FuenteNoDisponible("HCDN-votaciones", str(exc)) from exc
        log.info(
            "votaciones.obtener_acta.ok",
            acta_id=acta_id,
            asunto=votacion.asunto[:60],
            votos=len(votos),
        )
        return votacion, votos

    # ------------------------------------------------------------------
    # Internos: rate limit + retries (copia del patrón de HcdnScraper)
    # ------------------------------------------------------------------

    async def _get_with_retries(
        self,
        url: str,
        params: dict[str, str] | None = None,
    ) -> str:
        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                response = await self._rate_limited_get(url, params)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_exc = exc
                log.warning(
                    "votaciones.get.error_transitorio",
                    attempt=attempt + 1,
                    error=str(exc),
                )
                await asyncio.sleep(2**attempt)
                continue

            if response.status_code == 200:
                return response.text
            if 500 <= response.status_code < 600:
                last_exc = httpx.HTTPStatusError(
                    f"HTTP {response.status_code}",
                    request=response.request,
                    response=response,
                )
                log.warning(
                    "votaciones.get.5xx",
                    attempt=attempt + 1,
                    status=response.status_code,
                )
                await asyncio.sleep(2**attempt)
                continue
            # 4xx no recuperable.
            raise FuenteNoDisponible(
                "HCDN-votaciones",
                f"HTTP {response.status_code}",
            )

        raise FuenteNoDisponible(
            "HCDN-votaciones",
            str(last_exc) if last_exc else "agotamiento de retries",
        )

    async def _rate_limited_get(
        self,
        url: str,
        params: dict[str, str] | None,
    ) -> httpx.Response:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request_time
            if elapsed < self._rate_limit_seconds:
                await asyncio.sleep(self._rate_limit_seconds - elapsed)
            response = await self._client.get(
                url,
                params=params or {},
                headers={
                    "User-Agent": self._user_agent,
                    "Accept-Language": "es-AR,es;q=0.9",
                    "Referer": f"{VOTACIONES_BASE}/",
                },
                timeout=20.0,
                follow_redirects=True,
            )
            self._last_request_time = time.monotonic()
            return response
