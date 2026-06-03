"""Tests integración del router /webhooks/whatsapp (feat-41.3).

SQLite in-memory + TestClient. Cubre:
- GET handshake: token correcto → devuelve challenge.
- GET handshake: token incorrecto → 403.
- POST sin firma → 401.
- POST firma inválida → 401.
- POST con firma válida + payload de status update + envío previamente
  persistido → actualiza estado en DB.
- POST con firma válida + payload inbound opt-in → marca destinatario.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from praxis.api.deps import get_session
from praxis.api.main import app as real_app
from praxis.config import get_settings
from praxis.domain import (
    CategoriaPlantilla,
    Despacho,
    Destinatario,
    EnvioWhatsApp,
    EstadoEnvio,
    EstadoMetaPlantilla,
    PlantillaWhatsApp,
    RolDestinatario,
    TipoEnvio,
)
from praxis.infrastructure.persistence.base import Base
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyDespachoRepository,
    SqlAlchemyDestinatarioRepository,
    SqlAlchemyEnvioWhatsAppRepository,
    SqlAlchemyPlantillaWhatsAppRepository,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Settings overrides + fixtures
# ---------------------------------------------------------------------------


WEBHOOK_VERIFY_TOKEN = "test_verify_token"
APP_SECRET = "test_app_secret"


@pytest.fixture(autouse=True)
def _set_webhook_settings() -> None:
    """Inyecta los settings de webhook en el cache de Settings.

    Pydantic Settings carga del env al construir; para tests
    sobrescribimos directamente el cache de get_settings.
    """
    get_settings.cache_clear()
    settings = get_settings()
    settings.meta_whatsapp_webhook_verify_token = WEBHOOK_VERIFY_TOKEN
    settings.meta_whatsapp_webhook_app_secret = APP_SECRET
    yield
    settings.meta_whatsapp_webhook_verify_token = None
    settings.meta_whatsapp_webhook_app_secret = None


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as s:
        yield s
    await engine.dispose()


def _setup_client(session: AsyncSession) -> TestClient:
    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield session

    real_app.dependency_overrides[get_session] = _session_override
    return TestClient(real_app)


def _firmar(body: bytes) -> str:
    return "sha256=" + hmac.new(
        APP_SECRET.encode("utf-8"), body, hashlib.sha256,
    ).hexdigest()


# ---------------------------------------------------------------------------
# GET handshake
# ---------------------------------------------------------------------------


async def test_handshake_token_correcto_devuelve_challenge(
    session: AsyncSession,
) -> None:
    client = _setup_client(session)
    try:
        resp = client.get(
            "/api/v1/webhooks/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": WEBHOOK_VERIFY_TOKEN,
                "hub.challenge": "12345",
            },
        )
        assert resp.status_code == 200
        assert resp.json() == 12345
    finally:
        real_app.dependency_overrides.clear()


async def test_handshake_token_incorrecto_403(
    session: AsyncSession,
) -> None:
    client = _setup_client(session)
    try:
        resp = client.get(
            "/api/v1/webhooks/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong",
                "hub.challenge": "12345",
            },
        )
        assert resp.status_code == 403
    finally:
        real_app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# POST eventos
# ---------------------------------------------------------------------------


async def test_post_sin_firma_401(session: AsyncSession) -> None:
    client = _setup_client(session)
    try:
        resp = client.post(
            "/api/v1/webhooks/whatsapp",
            json={"entry": []},
        )
        assert resp.status_code == 401
    finally:
        real_app.dependency_overrides.clear()


async def test_post_firma_invalida_401(session: AsyncSession) -> None:
    client = _setup_client(session)
    try:
        body = b'{"entry":[]}'
        resp = client.post(
            "/api/v1/webhooks/whatsapp",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": "sha256=" + "0" * 64,
            },
        )
        assert resp.status_code == 401
    finally:
        real_app.dependency_overrides.clear()


async def test_post_status_update_actualiza_envio(
    session: AsyncSession,
) -> None:
    # Seed: 1 despacho + 1 plantilla + 1 destinatario + 1 envío.
    despacho = await SqlAlchemyDespachoRepository(session).crear(
        Despacho(id=uuid4(), nombre="Despacho A"),
    )
    await SqlAlchemyPlantillaWhatsAppRepository(session).upsert(
        PlantillaWhatsApp(
            name="briefing_diario",
            categoria=CategoriaPlantilla.UTILITY,
            body_params=["n", "f", "r"],
            contenido_referencia="Hola {{1}} del {{2}}: {{3}}",
            estado_meta=EstadoMetaPlantilla.APROBADA,
        ),
    )
    dest = await SqlAlchemyDestinatarioRepository(session).crear(
        Destinatario(
            id=None,
            despacho_id=despacho.id,
            nombre="Pablo",
            rol_interno=RolDestinatario.LEGISLADOR,
            telefono_e164="+5491155551234",
        ),
    )
    envios_repo = SqlAlchemyEnvioWhatsAppRepository(session)
    envio = await envios_repo.crear(
        EnvioWhatsApp(
            id=None,
            destinatario_id=dest.id,  # type: ignore[arg-type]
            despacho_id=despacho.id,
            plantilla_name="briefing_diario",
            tipo=TipoEnvio.BRIEFING_DIARIO,
        ),
    )
    await envios_repo.marcar_enviado(
        envio_id=envio.id,  # type: ignore[arg-type]
        message_id_meta="wamid.test.XYZ",
        enviado_en=datetime.now(UTC),
    )
    await session.commit()

    client = _setup_client(session)
    try:
        payload = {
            "entry": [{
                "changes": [{
                    "value": {
                        "statuses": [{
                            "id": "wamid.test.XYZ",
                            "status": "delivered",
                        }],
                    },
                }],
            }],
        }
        body = json.dumps(payload).encode("utf-8")
        resp = client.post(
            "/api/v1/webhooks/whatsapp",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": _firmar(body),
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["statuses_actualizados"] == 1
        assert data["statuses_desconocidos"] == 0

        # Verifica que el envío quedó como ENTREGADO.
        refresco = await envios_repo._fetch_or_raise(envio.id)  # type: ignore[arg-type,attr-defined]
        assert refresco.estado == EstadoEnvio.ENTREGADO
    finally:
        real_app.dependency_overrides.clear()


async def test_post_inbound_opt_in_marca_destinatario(
    session: AsyncSession,
) -> None:
    despacho = await SqlAlchemyDespachoRepository(session).crear(
        Despacho(id=uuid4(), nombre="Despacho A"),
    )
    dest_repo = SqlAlchemyDestinatarioRepository(session)
    dest = await dest_repo.crear(
        Destinatario(
            id=None,
            despacho_id=despacho.id,
            nombre="Pablo",
            rol_interno=RolDestinatario.LEGISLADOR,
            telefono_e164="+5491155551234",
        ),
    )
    await session.commit()

    client = _setup_client(session)
    try:
        payload = {
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "from": "5491155551234",
                            "id": "wamid.in.1",
                            "type": "text",
                            "text": {"body": "SI"},
                        }],
                    },
                }],
            }],
        }
        body = json.dumps(payload).encode("utf-8")
        resp = client.post(
            "/api/v1/webhooks/whatsapp",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": _firmar(body),
            },
        )
        assert resp.status_code == 200
        assert resp.json()["opt_ins_aplicados"] == 1

        refresco = await dest_repo.buscar_por_id(
            despacho_id=despacho.id,  # type: ignore[arg-type]
            destinatario_id=dest.id,  # type: ignore[arg-type]
        )
        assert refresco is not None
        assert refresco.activo is True
        assert refresco.opt_in_en is not None
    finally:
        real_app.dependency_overrides.clear()
