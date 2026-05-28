"""Scraper async del portal HSN (Senado de la Nación).

Implementa `FuenteExpedientes`. URL canónica:
    GET /parlamentario/comisiones/verExp/<NUM>.<YY>/<ORIGEN>/<TIPO>

donde ORIGEN ∈ {S, CD, PE} y TIPO ∈ {PL, PR, PD, PC}.

La lógica de parseo pura vive en `parser.py`; este archivo es solo I/O,
rate limit, retries.
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
    OrigenExpediente,
    TipoExpediente,
)
from praxis.infrastructure.scrapers.hsn.parser import parse_expediente_hsn

log = structlog.get_logger(__name__)

HSN_BASE = "https://www.senado.gob.ar"

# data-sources.md §"Reglas generales": 1 req/seg, UA identificable.
DEFAULT_USER_AGENT = "PraxisAsesor/0.1 (+contacto@dominio.com)"
DEFAULT_RATE_LIMIT_SECONDS = 1.0
DEFAULT_MAX_RETRIES = 3

# Mapeo TipoExpediente → código de URL. HSN expone los 4 tipos clásicos;
# tipos que no tienen URL canónica HSN (DECRETO, OTRO, MENSAJE_PE) no se
# soportan y lanzan ValueError al intentar buscar.
_TIPO_A_URL: dict[TipoExpediente, str] = {
    TipoExpediente.PROYECTO_LEY: "PL",
    TipoExpediente.PROYECTO_RESOLUCION: "PR",
    TipoExpediente.PROYECTO_DECLARACION: "PD",
    TipoExpediente.PROYECTO_COMUNICACION: "PC",
}

# Mapeo OrigenExpediente → código de URL HSN. Solo S/CD/PE son válidos
# en URLs HSN; el resto no aplica (un expediente con origen DIPUTADO
# directo no existe en HSN; sería CD si está en revisión allá).
_ORIGEN_A_URL: dict[OrigenExpediente, str] = {
    OrigenExpediente.SENADOR: "S",
    OrigenExpediente.REVISION_DIPUTADOS: "CD",
    OrigenExpediente.EJECUTIVO: "PE",
}


def _build_url(numero: NumeroExpediente, tipo: TipoExpediente) -> str:
    """Construye la URL canónica HSN del detalle del expediente.

    Raises:
        ValueError: si `tipo` u `origen` no tienen código de URL HSN válido.
    """
    if tipo not in _TIPO_A_URL:
        raise ValueError(
            f"TipoExpediente {tipo.value!r} no tiene URL HSN canónica "
            f"(soportados: PROYECTO_LEY, PROYECTO_RESOLUCION, "
            f"PROYECTO_DECLARACION, PROYECTO_COMUNICACION)"
        )
    if numero.origen not in _ORIGEN_A_URL:
        raise ValueError(
            f"OrigenExpediente {numero.origen.value!r} no es válido para HSN "
            f"(soportados: SENADOR, REVISION_DIPUTADOS, EJECUTIVO)"
        )
    anio_yy = numero.anio % 100
    return (
        f"{HSN_BASE}/parlamentario/comisiones/verExp"
        f"/{numero.numero}.{anio_yy:02d}"
        f"/{_ORIGEN_A_URL[numero.origen]}"
        f"/{_TIPO_A_URL[tipo]}"
    )


class HsnScraper(FuenteExpedientes):
    """Adaptador concreto: scraper de HSN sobre httpx async.

    Uso típico (composition root):
        async with httpx.AsyncClient() as client:
            scraper = HsnScraper(client)
            expediente = await scraper.buscar_por_numero(
                numero, tipo=TipoExpediente.PROYECTO_LEY
            )
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
        self._lock = asyncio.Lock()
        self._last_request_time: float = 0.0

    async def buscar_por_numero(
        self,
        numero: NumeroExpediente,
        tipo: TipoExpediente | None = None,
    ) -> Expediente:
        if numero.camara != Camara.HSN:
            raise ValueError(f"HsnScraper solo soporta Camara.HSN, recibió {numero.camara}")
        if tipo is None:
            raise ValueError(
                "HsnScraper requiere `tipo` (la URL HSN canónica lo incluye). "
                "Ver spec docs/specs/02-ingesta-hsn.md."
            )

        url = _build_url(numero, tipo)
        log.info("hsn.buscar_por_numero.inicio", numero=str(numero), url=url)

        html = await self._get_with_retries(url)

        try:
            expediente = parse_expediente_hsn(html, numero, tipo)
        except ValueError as exc:
            log.error("hsn.parse.error", numero=str(numero), error=str(exc))
            raise ExpedienteNoEncontrado(str(numero), fuente="HSN") from exc

        expediente.fuente_url = url
        log.info(
            "hsn.buscar_por_numero.ok",
            numero=str(numero),
            firmantes=len(expediente.firmantes),
            giros=len(expediente.giros),
            tramite_eventos=len(expediente.tramite),
        )
        return expediente

    # -------------------------------------------------------------------
    # Internos: rate limit + retries
    # -------------------------------------------------------------------

    async def _get_with_retries(self, url: str) -> str:
        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                response = await self._rate_limited_get(url)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_exc = exc
                log.warning("hsn.get.error_transitorio", attempt=attempt + 1, error=str(exc))
                await asyncio.sleep(2**attempt)
                continue

            if response.status_code == 200:
                return response.text
            if response.status_code == 404:
                raise ExpedienteNoEncontrado(url, fuente="HSN")
            if 500 <= response.status_code < 600:
                last_exc = httpx.HTTPStatusError(
                    f"HTTP {response.status_code}",
                    request=response.request,
                    response=response,
                )
                log.warning("hsn.get.5xx", attempt=attempt + 1, status=response.status_code)
                await asyncio.sleep(2**attempt)
                continue
            raise FuenteNoDisponible("HSN", f"HTTP {response.status_code}")

        raise FuenteNoDisponible("HSN", str(last_exc) if last_exc else "agotamiento de retries")

    async def _rate_limited_get(self, url: str) -> httpx.Response:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request_time
            if elapsed < self._rate_limit_seconds:
                await asyncio.sleep(self._rate_limit_seconds - elapsed)
            response = await self._client.get(
                url,
                headers={
                    "User-Agent": self._user_agent,
                    "Accept-Language": "es-AR,es;q=0.9",
                },
                timeout=20.0,
                follow_redirects=True,
            )
            self._last_request_time = time.monotonic()
            return response
