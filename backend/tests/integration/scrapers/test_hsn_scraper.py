"""Tests del scraper HSN (I/O, rate limiting, retries, construcción de URL).

Usan `httpx.MockTransport` para no hacer HTTP real. El parser se testea
aparte en `test_hsn_parser.py`.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from praxis.domain import (
    Camara,
    ExpedienteNoEncontrado,
    FuenteNoDisponible,
    NumeroExpediente,
    OrigenExpediente,
    TipoExpediente,
)
from praxis.infrastructure.scrapers.hsn.scraper import HSN_BASE, HsnScraper

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "hsn"


def _load(filename: str) -> str:
    return (FIXTURES / filename).read_text(encoding="utf-8")


def _make_transport(handler):
    return httpx.MockTransport(handler)


def _numero_239() -> NumeroExpediente:
    return NumeroExpediente(
        numero=239,
        origen=OrigenExpediente.SENADOR,
        anio=2024,
        camara=Camara.HSN,
    )


# --- Camino feliz ------------------------------------------------------------


async def test_scraper_busca_y_devuelve_expediente() -> None:
    html = _load("hsn_239_24_S_PL.html")
    expected_url = f"{HSN_BASE}/parlamentario/comisiones/verExp/239.24/S/PL"
    captured_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_urls.append(str(request.url))
        assert request.method == "GET"
        return httpx.Response(200, text=html)

    async with httpx.AsyncClient(transport=_make_transport(handler)) as client:
        scraper = HsnScraper(client, rate_limit_seconds=0.0)
        expediente = await scraper.buscar_por_numero(
            _numero_239(), tipo=TipoExpediente.PROYECTO_LEY
        )

    assert captured_urls == [expected_url]
    assert expediente.fuente_url == expected_url
    assert "SAPAG" in (expediente.titulo or "")


async def test_scraper_construye_url_correcta_para_cd_origen() -> None:
    """ORIGEN=CD (revisión Diputados), año a 2 dígitos."""
    captured_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_urls.append(str(request.url))
        return httpx.Response(200, text=_load("hsn_1_24_CD_PL.html"))

    numero = NumeroExpediente(
        numero=1,
        origen=OrigenExpediente.REVISION_DIPUTADOS,
        anio=2024,
        camara=Camara.HSN,
    )
    async with httpx.AsyncClient(transport=_make_transport(handler)) as client:
        scraper = HsnScraper(client, rate_limit_seconds=0.0)
        await scraper.buscar_por_numero(numero, tipo=TipoExpediente.PROYECTO_LEY)

    assert captured_urls == [f"{HSN_BASE}/parlamentario/comisiones/verExp/1.24/CD/PL"]


async def test_scraper_setea_user_agent_correcto() -> None:
    captured_ua: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_ua.append(request.headers.get("user-agent", ""))
        return httpx.Response(200, text=_load("hsn_239_24_S_PL.html"))

    async with httpx.AsyncClient(transport=_make_transport(handler)) as client:
        scraper = HsnScraper(client, rate_limit_seconds=0.0)
        await scraper.buscar_por_numero(_numero_239(), tipo=TipoExpediente.PROYECTO_LEY)

    assert "PraxisAsesor" in captured_ua[0]


# --- Validaciones de input ---------------------------------------------------


async def test_scraper_camara_incompatible_lanza() -> None:
    """Si el número es de HCDN, HsnScraper lanza ValueError."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not called")

    numero_hcdn = NumeroExpediente.parse_hcdn("100-D-2024")
    async with httpx.AsyncClient(transport=_make_transport(handler)) as client:
        scraper = HsnScraper(client, rate_limit_seconds=0.0)
        with pytest.raises(ValueError, match="HSN"):
            await scraper.buscar_por_numero(numero_hcdn, tipo=TipoExpediente.PROYECTO_LEY)


async def test_scraper_sin_tipo_lanza() -> None:
    """HSN requiere `tipo`: si no se pasa, ValueError."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not called")

    async with httpx.AsyncClient(transport=_make_transport(handler)) as client:
        scraper = HsnScraper(client, rate_limit_seconds=0.0)
        with pytest.raises(ValueError, match="tipo"):
            await scraper.buscar_por_numero(_numero_239())


async def test_scraper_tipo_no_soportado_lanza() -> None:
    """MENSAJE_PE / DECRETO / OTRO no tienen URL HSN canónica."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not called")

    async with httpx.AsyncClient(transport=_make_transport(handler)) as client:
        scraper = HsnScraper(client, rate_limit_seconds=0.0)
        with pytest.raises(ValueError, match="URL HSN"):
            await scraper.buscar_por_numero(_numero_239(), tipo=TipoExpediente.MENSAJE_PE)


async def test_scraper_origen_no_soportado_lanza() -> None:
    """DIPUTADO / PARTICULAR / etc. no son orígenes válidos para HSN."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not called")

    # Construimos un número HSN pero con un origen no-HSN.
    numero = NumeroExpediente(
        numero=10,
        origen=OrigenExpediente.PARTICULAR,
        anio=2024,
        camara=Camara.HSN,
    )
    async with httpx.AsyncClient(transport=_make_transport(handler)) as client:
        scraper = HsnScraper(client, rate_limit_seconds=0.0)
        with pytest.raises(ValueError, match="HSN"):
            await scraper.buscar_por_numero(numero, tipo=TipoExpediente.PROYECTO_LEY)


# --- Errores HTTP ------------------------------------------------------------


async def test_scraper_404_lanza_no_encontrado() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    async with httpx.AsyncClient(transport=_make_transport(handler)) as client:
        scraper = HsnScraper(client, rate_limit_seconds=0.0)
        with pytest.raises(ExpedienteNoEncontrado):
            await scraper.buscar_por_numero(_numero_239(), tipo=TipoExpediente.PROYECTO_LEY)


async def test_scraper_5xx_persistente_lanza_fuente_no_disponible() -> None:
    calls = [0]

    def handler(_: httpx.Request) -> httpx.Response:
        calls[0] += 1
        return httpx.Response(500, text="server error")

    async with httpx.AsyncClient(transport=_make_transport(handler)) as client:
        scraper = HsnScraper(client, rate_limit_seconds=0.0, max_retries=3)
        with pytest.raises(FuenteNoDisponible):
            await scraper.buscar_por_numero(_numero_239(), tipo=TipoExpediente.PROYECTO_LEY)
    assert calls[0] == 3


async def test_scraper_5xx_transitorio_y_luego_ok() -> None:
    calls = [0]

    def handler(_: httpx.Request) -> httpx.Response:
        calls[0] += 1
        if calls[0] == 1:
            return httpx.Response(500, text="hiccup")
        return httpx.Response(200, text=_load("hsn_239_24_S_PL.html"))

    async with httpx.AsyncClient(transport=_make_transport(handler)) as client:
        scraper = HsnScraper(client, rate_limit_seconds=0.0, max_retries=3)
        expediente = await scraper.buscar_por_numero(
            _numero_239(), tipo=TipoExpediente.PROYECTO_LEY
        )

    assert calls[0] == 2
    assert "SAPAG" in (expediente.titulo or "")
