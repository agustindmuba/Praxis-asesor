"""Tests del scraper async de votaciones HCDN.

Usan `httpx.MockTransport` — sin HTTP real. El parser se testea aparte
en `test_hcdn_votaciones_parser.py`.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from praxis.domain import FuenteNoDisponible
from praxis.infrastructure.scrapers.hcdn.votaciones import (
    VOTACIONES_BASE,
    VOTACIONES_INDEX_URL,
    VotacionesHcdnScraper,
)

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "hcdn"


def _load(filename: str) -> str:
    return (FIXTURES / filename).read_text(encoding="utf-8")


def _make_transport(
    handler: Callable[[httpx.Request], httpx.Response],
) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


# ---------------------------------------------------------------------------
# Camino feliz
# ---------------------------------------------------------------------------


async def test_listar_indice_devuelve_los_items_del_portal() -> None:
    """GET / con params correctos y parsea las 500 votaciones."""
    html = _load("votaciones_index_home.html")
    capturado: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert str(request.url).startswith(VOTACIONES_INDEX_URL)
        capturado["anoSearch"] = request.url.params.get("anoSearch")
        capturado["txtSearch"] = request.url.params.get("txtSearch")
        return httpx.Response(200, text=html)

    async with httpx.AsyncClient(transport=_make_transport(handler)) as client:
        scraper = VotacionesHcdnScraper(client, rate_limit_seconds=0.0)
        items = await scraper.listar_indice(anio=2025, texto="zona")

    assert len(items) == 500
    assert items[0].acta_id == 5937
    assert capturado["anoSearch"] == "2025"
    assert capturado["txtSearch"] == "zona"


async def test_listar_indice_sin_filtros_no_pasa_params() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params.get("anoSearch") is None
        assert request.url.params.get("txtSearch") is None
        return httpx.Response(200, text=_load("votaciones_index_home.html"))

    async with httpx.AsyncClient(transport=_make_transport(handler)) as client:
        scraper = VotacionesHcdnScraper(client, rate_limit_seconds=0.0)
        items = await scraper.listar_indice()
    assert len(items) == 500


async def test_obtener_acta_devuelve_votacion_y_votos() -> None:
    html = _load("votacion_5937.html")

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == f"{VOTACIONES_BASE}/votacion/5937"
        return httpx.Response(200, text=html)

    async with httpx.AsyncClient(transport=_make_transport(handler)) as client:
        scraper = VotacionesHcdnScraper(client, rate_limit_seconds=0.0)
        votacion, votos = await scraper.obtener_acta(5937)

    assert votacion.acta_id_hcdn == 5937
    assert votacion.titulo_od == "O.D. 84"
    assert votacion.fuente_url == f"{VOTACIONES_BASE}/votacion/5937"
    assert len(votos) == 257


async def test_obtener_acta_setea_user_agent_correcto() -> None:
    captured_ua: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_ua.append(request.headers.get("user-agent", ""))
        return httpx.Response(200, text=_load("votacion_5937.html"))

    async with httpx.AsyncClient(transport=_make_transport(handler)) as client:
        scraper = VotacionesHcdnScraper(client, rate_limit_seconds=0.0)
        await scraper.obtener_acta(5937)

    assert len(captured_ua) == 1
    assert "PraxisAsesor" in captured_ua[0]
    assert "Scrapy" not in captured_ua[0]


# ---------------------------------------------------------------------------
# Errores
# ---------------------------------------------------------------------------


async def test_obtener_acta_4xx_lanza_fuente_no_disponible() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    async with httpx.AsyncClient(transport=_make_transport(handler)) as client:
        scraper = VotacionesHcdnScraper(
            client, rate_limit_seconds=0.0, max_retries=2
        )
        with pytest.raises(FuenteNoDisponible):
            await scraper.obtener_acta(99999)


async def test_obtener_acta_5xx_persistente_agota_retries() -> None:
    call_count = [0]

    def handler(_: httpx.Request) -> httpx.Response:
        call_count[0] += 1
        return httpx.Response(500, text="server error")

    async with httpx.AsyncClient(transport=_make_transport(handler)) as client:
        scraper = VotacionesHcdnScraper(
            client, rate_limit_seconds=0.0, max_retries=3
        )
        with pytest.raises(FuenteNoDisponible):
            await scraper.obtener_acta(5937)

    assert call_count[0] == 3


async def test_obtener_acta_5xx_transitorio_y_luego_ok() -> None:
    calls = [0]
    html_ok = _load("votacion_5937.html")

    def handler(_: httpx.Request) -> httpx.Response:
        calls[0] += 1
        if calls[0] == 1:
            return httpx.Response(500, text="server error")
        return httpx.Response(200, text=html_ok)

    async with httpx.AsyncClient(transport=_make_transport(handler)) as client:
        scraper = VotacionesHcdnScraper(
            client, rate_limit_seconds=0.0, max_retries=3
        )
        votacion, votos = await scraper.obtener_acta(5937)

    assert calls[0] == 2
    assert votacion.acta_id_hcdn == 5937
    assert len(votos) == 257


async def test_obtener_acta_html_no_parseable_lanza_fuente_no_disponible() -> None:
    """HTML que no es de votación → ValueError del parser → FuenteNoDisponible."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html><body>otra cosa</body></html>")

    async with httpx.AsyncClient(transport=_make_transport(handler)) as client:
        scraper = VotacionesHcdnScraper(client, rate_limit_seconds=0.0)
        with pytest.raises(FuenteNoDisponible):
            await scraper.obtener_acta(5937)
