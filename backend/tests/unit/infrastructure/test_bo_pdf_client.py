"""Tests del `BoletinOficialPdfClient`.

Usamos `httpx.MockTransport` para no agregar `respx` como dep. Mockeamos
el endpoint S3 retornando los bytes del PDF fixture del spike.

Cubren:
- Camino feliz: 200 + bytes %PDF → parsea + devuelve normas.
- Cache en memoria: segundo llamado a `listar_normas_del_dia` no re-baja.
- `obtener_texto_completo` devuelve el texto cacheado por hash_sumario.
- Sección no activa en v1 devuelve lista vacía.
- Fecha distinta a hoy devuelve lista vacía (S3 sólo sirve pdf-del-dia).
- 500 → FuenteNoDisponible.
- 200 con body que no es PDF → FuenteNoDisponible.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from praxis.domain import FuenteNoDisponible, SeccionBO
from praxis.infrastructure.bo.pdf_client import BoletinOficialPdfClient

pytestmark = pytest.mark.unit


FIXTURE_PDF = (
    Path(__file__).resolve().parents[3]
    / "spikes" / "bo" / "pdf_del_dia__primera.pdf"
)


def _client_con_mock(handler) -> BoletinOficialPdfClient:
    """Construye un client con MockTransport, manteniendo el UA Praxis
    como header default — replicamos lo que hace el cliente real."""
    from praxis.infrastructure.bo.pdf_client import DEFAULT_UA
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(
        transport=transport,
        timeout=30.0,
        headers={"User-Agent": DEFAULT_UA, "Accept": "application/pdf"},
    )
    return BoletinOficialPdfClient(client=http)


@pytest.fixture
def pdf_bytes() -> bytes:
    return FIXTURE_PDF.read_bytes()


# ---------------------------------------------------------------------------
# Camino feliz
# ---------------------------------------------------------------------------


async def test_devuelve_normas_del_pdf(pdf_bytes: bytes) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "pdf-del-dia/primera.pdf" in str(request.url)
        assert "PraxisAsesor" in request.headers["user-agent"]
        return httpx.Response(200, content=pdf_bytes)

    client = _client_con_mock(handler)
    try:
        fecha = datetime.now(UTC).date()
        normas = await client.listar_normas_del_dia(
            fecha, SeccionBO.LEGISLACION,
        )
        assert len(normas) > 0
        assert normas[0].seccion == SeccionBO.LEGISLACION
        assert normas[0].fecha_publicacion == fecha
    finally:
        await client.aclose()


async def test_segundo_llamado_usa_cache(pdf_bytes: bytes) -> None:
    """Cache en memoria: no se llama a HTTP por segunda vez."""
    llamadas = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        llamadas["count"] += 1
        return httpx.Response(200, content=pdf_bytes)

    client = _client_con_mock(handler)
    try:
        fecha = datetime.now(UTC).date()
        a = await client.listar_normas_del_dia(fecha, SeccionBO.LEGISLACION)
        b = await client.listar_normas_del_dia(fecha, SeccionBO.LEGISLACION)
        assert llamadas["count"] == 1
        # Las listas tienen los mismos numbres de norma (mismo objeto base).
        assert [n.numero_norma for n in a] == [n.numero_norma for n in b]
    finally:
        await client.aclose()


async def test_obtener_texto_completo_devuelve_texto_cacheado(
    pdf_bytes: bytes,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=pdf_bytes)

    client = _client_con_mock(handler)
    try:
        fecha = datetime.now(UTC).date()
        normas = await client.listar_normas_del_dia(
            fecha, SeccionBO.LEGISLACION,
        )
        texto = await client.obtener_texto_completo(normas[0])
        assert texto is not None
        assert len(texto) > 0
    finally:
        await client.aclose()


# ---------------------------------------------------------------------------
# Casos sin HTTP
# ---------------------------------------------------------------------------


async def test_seccion_no_activa_devuelve_vacio() -> None:
    """AVISOS_OFICIALES no está en SECCIONES_ACTIVAS_V1."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("No debería llamar a HTTP para sección inactiva")

    client = _client_con_mock(handler)
    try:
        fecha = datetime.now(UTC).date()
        normas = await client.listar_normas_del_dia(
            fecha, SeccionBO.AVISOS_OFICIALES,
        )
        assert normas == []
    finally:
        await client.aclose()


async def test_fecha_distinta_a_hoy_devuelve_vacio() -> None:
    """S3 sólo sirve `pdf-del-dia`. Otra fecha → vacío."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("No debería llamar a HTTP para fecha pasada")

    client = _client_con_mock(handler)
    try:
        from datetime import date as _date
        from datetime import timedelta
        ayer = _date.today() - timedelta(days=5)
        normas = await client.listar_normas_del_dia(
            ayer, SeccionBO.LEGISLACION,
        )
        assert normas == []
    finally:
        await client.aclose()


# ---------------------------------------------------------------------------
# Errores HTTP
# ---------------------------------------------------------------------------


async def test_status_500_levanta_fuente_no_disponible() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        # 500 no está en la lista de retries (502/503/504), así que falla
        # directo.
        return httpx.Response(500, content=b"server error")

    client = _client_con_mock(handler)
    try:
        fecha = datetime.now(UTC).date()
        with pytest.raises(FuenteNoDisponible):
            await client.listar_normas_del_dia(fecha, SeccionBO.LEGISLACION)
    finally:
        await client.aclose()


async def test_status_200_pero_no_pdf_levanta() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>not a pdf</html>")

    client = _client_con_mock(handler)
    try:
        fecha = datetime.now(UTC).date()
        with pytest.raises(FuenteNoDisponible, match="esperaba 200 con"):
            await client.listar_normas_del_dia(fecha, SeccionBO.LEGISLACION)
    finally:
        await client.aclose()
