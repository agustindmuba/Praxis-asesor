"""Scraper async del portal HCDN.

Implementa `FuenteExpedientes` haciendo POST al buscador oficial. La lógica
de parseo pura vive en `parser.py`; este archivo se ocupa solo de I/O,
rate limiting, retries y conversión a/desde el dominio.
"""

from __future__ import annotations

import asyncio
import time

import httpx
import structlog

from praxis.application.ports import FuenteExpedientes
from praxis.domain import (
    Camara,
    Expediente,
    ExpedienteNoEncontrado,
    FuenteNoDisponible,
    NumeroExpediente,
    TipoExpediente,
)
from praxis.domain.inferencia_estado import inferir_estado_y_caducidad
from praxis.infrastructure.scrapers.hcdn.parser import parse_resultado_hcdn

log = structlog.get_logger(__name__)

HCDN_BASE = "https://www.diputados.gob.ar"
HCDN_RESULTADO_URL = f"{HCDN_BASE}/proyectos/resultado.html"

# User-Agent declarado en data-sources.md. Respetuoso: identifica al cliente
# y da un contacto en caso de problemas. El portal HCDN bloquea bots
# anónimos genéricos (Scrapy, HeadlessChrome) pero acepta este.
DEFAULT_USER_AGENT = "PraxisAsesor/0.1 (+contacto@dominio.com)"

# Rate limit por dominio. data-sources.md §"Reglas generales" pide 1 req/s.
DEFAULT_RATE_LIMIT_SECONDS = 1.0

# Reintentos para errores transitorios (5xx, timeouts). 4xx no se reintentan.
DEFAULT_MAX_RETRIES = 3


class HcdnScraper(FuenteExpedientes):
    """Adaptador concreto: scraper de HCDN sobre httpx async.

    Uso típico (composition root):
        async with httpx.AsyncClient() as client:
            scraper = HcdnScraper(client)
            expediente = await scraper.buscar_por_numero(numero)
    """

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
        # Para enforce del rate limit por instancia (no global; si en el futuro
        # se necesita global, mover a un servicio compartido).
        self._lock = asyncio.Lock()
        self._last_request_time: float = 0.0

    async def buscar_por_numero(
        self,
        numero: NumeroExpediente,
        tipo: TipoExpediente | None = None,
    ) -> Expediente:
        # `tipo` no se usa en HCDN: la búsqueda lo infiere del sumario.
        # Aceptamos el parámetro para cumplir la signature del puerto.
        del tipo
        if numero.camara != Camara.HCDN:
            raise ValueError(f"HcdnScraper solo soporta Camara.HCDN, recibió {numero.camara}")

        log.info("hcdn.buscar_por_numero.inicio", numero=str(numero))

        # Form data para el POST. Replica lo validado en el spike.
        data = {
            "zezion": "true",
            "strTipo": "",
            "strNumExp": str(numero.numero),
            "strNumExpOrig": numero.origen.value,
            "strNumExpAnio": str(numero.anio),
            "strCamIni": "",
            "strFirmante": "",
            "strTipoFirmante": "",
            "strComision": "",
            "strFechaInicio": "",
            "strFechaFin": "",
            "strPalabras": "",
            "strMostrarTramites": "on",
            "strMostrarDictamenes": "on",
            "strMostrarFirmantes": "on",
            "strMostrarComisiones": "on",
            "strCantPagina": "20",
        }

        html = await self._post_with_retries(HCDN_RESULTADO_URL, data)

        # El portal devuelve siempre 200; "no encontrado" se detecta por contenido.
        if "no se encontr" in html.lower() or len(html) < 5000:
            log.warning("hcdn.buscar_por_numero.no_encontrado", numero=str(numero))
            raise ExpedienteNoEncontrado(str(numero), fuente="HCDN")

        try:
            expediente = parse_resultado_hcdn(html, numero)
        except ValueError as exc:
            log.error("hcdn.parse.error", numero=str(numero), error=str(exc))
            raise ExpedienteNoEncontrado(str(numero), fuente="HCDN") from exc

        expediente.fuente_url = HCDN_RESULTADO_URL

        # El portal HCDN no expone el estado del expediente de forma estructurada:
        # se infiere a partir de los eventos del trámite y la fecha de ingreso.
        # Ver `domain/inferencia_estado.py` y `docs/specs/07-inferencia-estado.md`.
        inferencia = inferir_estado_y_caducidad(expediente)
        expediente.estado = inferencia.estado
        expediente.fecha_caducidad = inferencia.fecha_caducidad
        expediente.fecha_caducidad_original = inferencia.fecha_caducidad_original
        expediente.prorrogado = inferencia.prorrogado

        log.info(
            "hcdn.buscar_por_numero.ok",
            numero=str(numero),
            firmantes=len(expediente.firmantes),
            giros=len(expediente.giros),
            tramite_eventos=len(expediente.tramite),
            estado=expediente.estado.value,
        )
        return expediente

    # -------------------------------------------------------------------
    # Internos: rate limit + retries
    # -------------------------------------------------------------------

    async def _post_with_retries(self, url: str, data: dict[str, str]) -> str:
        """POST con rate limit + reintentos con backoff exponencial."""
        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                response = await self._rate_limited_post(url, data)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_exc = exc
                log.warning(
                    "hcdn.post.error_transitorio",
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
                    "hcdn.post.5xx",
                    attempt=attempt + 1,
                    status=response.status_code,
                )
                await asyncio.sleep(2**attempt)
                continue
            # 4xx: error no recuperable.
            raise FuenteNoDisponible("HCDN", f"HTTP {response.status_code}")

        raise FuenteNoDisponible("HCDN", str(last_exc) if last_exc else "agotamiento de retries")

    async def _rate_limited_post(self, url: str, data: dict[str, str]) -> httpx.Response:
        """POST respetando rate_limit_seconds entre llamadas consecutivas."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request_time
            if elapsed < self._rate_limit_seconds:
                wait = self._rate_limit_seconds - elapsed
                await asyncio.sleep(wait)
            response = await self._client.post(
                url,
                data=data,
                headers={
                    "User-Agent": self._user_agent,
                    "Accept-Language": "es-AR,es;q=0.9",
                    "Referer": f"{HCDN_BASE}/proyectos/",
                },
                timeout=20.0,
                follow_redirects=True,
            )
            self._last_request_time = time.monotonic()
            return response
