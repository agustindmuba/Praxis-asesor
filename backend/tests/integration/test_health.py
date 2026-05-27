"""Tests de integración del endpoint /health.

`/health` (liveness) no toca DB ni Redis, así que se puede correr sin
servicios externos. `/ready` (readiness) sí los toca y debería testearse
contra un docker-compose levantado.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.integration
async def test_health_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "version" in body
