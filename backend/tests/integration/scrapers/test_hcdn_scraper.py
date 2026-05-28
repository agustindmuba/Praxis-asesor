"""Tests del scraper HCDN (I/O, rate limiting, retries).

Usan `httpx.MockTransport` para no hacer HTTP real. El parser se testea
aparte en `test_hcdn_parser.py`.
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
)
from praxis.infrastructure.scrapers.hcdn.scraper import (
    HCDN_RESULTADO_URL,
    HcdnScraper,
)

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "hcdn"


def _load_fixture(filename: str) -> str:
    return (FIXTURES / filename).read_text(encoding="utf-8")


def _make_transport(handler):
    """Helper para crear un transport mock con un handler dado."""
    return httpx.MockTransport(handler)


# --- Camino feliz ------------------------------------------------------------


async def test_scraper_busca_y_devuelve_expediente() -> None:
    """Caso normal: el portal devuelve la ficha; el scraper la entrega parseada."""
    html = _load_fixture("hcdn_1497-D-2024.html")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url) == HCDN_RESULTADO_URL
        # Verificar que el form data tiene el número descompuesto.
        body = request.content.decode("utf-8")
        assert "strNumExp=1497" in body
        assert "strNumExpOrig=D" in body
        assert "strNumExpAnio=2024" in body
        return httpx.Response(200, text=html)

    async with httpx.AsyncClient(transport=_make_transport(handler)) as client:
        scraper = HcdnScraper(client, rate_limit_seconds=0.0)
        numero = NumeroExpediente.parse_hcdn("1497-D-2024")
        expediente = await scraper.buscar_por_numero(numero)

    assert expediente.numero == numero
    assert "PROTECCION DE DATOS" in (expediente.titulo or "")
    assert expediente.fuente_url == HCDN_RESULTADO_URL


async def test_scraper_setea_user_agent_correcto() -> None:
    captured_ua: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_ua.append(request.headers.get("user-agent", ""))
        return httpx.Response(200, text=_load_fixture("hcdn_1497-D-2024.html"))

    async with httpx.AsyncClient(transport=_make_transport(handler)) as client:
        scraper = HcdnScraper(client, rate_limit_seconds=0.0)
        await scraper.buscar_por_numero(NumeroExpediente.parse_hcdn("1497-D-2024"))

    assert len(captured_ua) == 1
    assert "PraxisAsesor" in captured_ua[0]
    # Que no sea Scrapy/HeadlessChrome (HCDN los bloquea explícitamente).
    assert "Scrapy" not in captured_ua[0]
    assert "HeadlessChrome" not in captured_ua[0]


# --- Errores -----------------------------------------------------------------


async def test_scraper_camara_incompatible_lanza_value_error() -> None:
    """Pedirle un expediente de HSN a un HcdnScraper es un error de programación."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="should not be called")

    async with httpx.AsyncClient(transport=_make_transport(handler)) as client:
        scraper = HcdnScraper(client, rate_limit_seconds=0.0)
        numero_hsn = NumeroExpediente(
            numero=239,
            origen=OrigenExpediente.SENADOR,
            anio=2024,
            camara=Camara.HSN,
        )
        with pytest.raises(ValueError, match="HCDN"):
            await scraper.buscar_por_numero(numero_hsn)


async def test_scraper_no_encontrado_lanza() -> None:
    """El portal devuelve 200 con HTML chico (sin ficha) → ExpedienteNoEncontrado."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html><body>no se encontró el expediente</body></html>")

    async with httpx.AsyncClient(transport=_make_transport(handler)) as client:
        scraper = HcdnScraper(client, rate_limit_seconds=0.0)
        with pytest.raises(ExpedienteNoEncontrado):
            await scraper.buscar_por_numero(NumeroExpediente.parse_hcdn("99999-D-2024"))


async def test_scraper_4xx_lanza_fuente_no_disponible() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="forbidden")

    async with httpx.AsyncClient(transport=_make_transport(handler)) as client:
        scraper = HcdnScraper(client, rate_limit_seconds=0.0, max_retries=2)
        with pytest.raises(FuenteNoDisponible):
            await scraper.buscar_por_numero(NumeroExpediente.parse_hcdn("1-D-2024"))


async def test_scraper_5xx_se_reintenta_y_falla() -> None:
    """500 persistente: agota retries y propaga FuenteNoDisponible."""
    call_count = [0]

    def handler(_: httpx.Request) -> httpx.Response:
        call_count[0] += 1
        return httpx.Response(500, text="server error")

    async with httpx.AsyncClient(transport=_make_transport(handler)) as client:
        scraper = HcdnScraper(client, rate_limit_seconds=0.0, max_retries=3)
        with pytest.raises(FuenteNoDisponible):
            await scraper.buscar_por_numero(NumeroExpediente.parse_hcdn("1-D-2024"))

    assert call_count[0] == 3  # se intentó 3 veces antes de rendirse.


async def test_scraper_5xx_transitorio_y_luego_ok() -> None:
    """500 una vez, después 200: el scraper devuelve el resultado correcto."""
    calls = [0]
    html_ok = _load_fixture("hcdn_1497-D-2024.html")

    def handler(_: httpx.Request) -> httpx.Response:
        calls[0] += 1
        if calls[0] == 1:
            return httpx.Response(500, text="server error")
        return httpx.Response(200, text=html_ok)

    async with httpx.AsyncClient(transport=_make_transport(handler)) as client:
        scraper = HcdnScraper(client, rate_limit_seconds=0.0, max_retries=3)
        # Para no tener que esperar el backoff exponencial real (2^1 = 2s).
        scraper._rate_limit_seconds = 0.0
        expediente = await scraper.buscar_por_numero(NumeroExpediente.parse_hcdn("1497-D-2024"))

    assert calls[0] == 2
    assert expediente.firmantes  # parseó OK al segundo intento.
