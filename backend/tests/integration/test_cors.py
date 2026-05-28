"""Tests del CORSMiddleware.

CORS se configura via `Settings.cors_origins`. Si está vacía, no se agrega
el middleware y los preflights fallan (comportamiento default seguro).

Estos tests no chequean Settings (que se cachea por proceso vía lru_cache);
chequean que cuando el middleware está agregado, responde bien.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


def _build_app_con_cors(origins: list[str]) -> FastAPI:
    """App de prueba que monta el middleware con los orígenes dados."""
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Despacho-Id"],
    )

    @app.get("/ping")
    async def ping() -> dict[str, str]:
        return {"ok": "true"}

    return app


def test_cors_preflight_permite_origen_listado() -> None:
    """OPTIONS preflight desde un origen listado → 200 con headers correctos."""
    app = _build_app_con_cors(["http://localhost:3000"])
    client = TestClient(app)
    response = client.options(
        "/ping",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization,x-despacho-id",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
    allow_headers = response.headers.get("access-control-allow-headers", "").lower()
    assert "authorization" in allow_headers
    assert "x-despacho-id" in allow_headers


def test_cors_preflight_rechaza_origen_no_listado() -> None:
    """Origen no listado → no devuelve allow-origin (browser bloquea)."""
    app = _build_app_con_cors(["http://localhost:3000"])
    client = TestClient(app)
    response = client.options(
        "/ping",
        headers={
            "Origin": "http://evil.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    # FastAPI/Starlette devuelve 400 cuando el origen no matchea.
    # Lo crítico: no devuelve `access-control-allow-origin: evil.com`.
    assert response.headers.get("access-control-allow-origin") != "http://evil.com"


def test_cors_request_real_incluye_allow_origin() -> None:
    """Una GET cross-origin desde un origen listado debe traer el header
    `access-control-allow-origin` en la respuesta."""
    app = _build_app_con_cors(["http://localhost:3000"])
    client = TestClient(app)
    response = client.get("/ping", headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
