"""Tests integración de los routers /destinatarios + /envios-whatsapp
+ /plantillas (feat-41.5).

Cubre:
- POST /destinatarios crea OK, normaliza E.164.
- POST con teléfono mal-formado → 422.
- POST con teléfono duplicado en el despacho → 409.
- GET lista con `solo_activos`.
- PATCH actualiza flags.
- DELETE 204 + 404.
- Tenant isolation: otro despacho no ve los del despacho A.
- GET /envios-whatsapp filtra por tipo + ventana.
- GET /plantillas con solo_aprobadas.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from praxis.api.deps import get_auth_provider, get_session
from praxis.api.main import app as real_app
from praxis.application.ports import AuthProvider
from praxis.domain import (
    AuthClaims,
    AuthError,
    AuthErrorCode,
    CategoriaPlantilla,
    Despacho,
    Destinatario,
    EnvioWhatsApp,
    EstadoMetaPlantilla,
    MembresiaDespacho,
    PlantillaWhatsApp,
    Rol,
    RolDestinatario,
    TipoEnvio,
    Usuario,
)
from praxis.infrastructure.persistence.base import Base
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyDespachoRepository,
    SqlAlchemyDestinatarioRepository,
    SqlAlchemyEnvioWhatsAppRepository,
    SqlAlchemyMembresiaDespachoRepository,
    SqlAlchemyPlantillaWhatsAppRepository,
    SqlAlchemyUsuarioRepository,
)

pytestmark = pytest.mark.integration


class FakeAuth(AuthProvider):
    def __init__(self, tokens: dict[str, AuthClaims]) -> None:
        self._tokens = tokens

    async def verificar_token(self, token: str) -> AuthClaims:
        c = self._tokens.get(token)
        if c is None:
            raise AuthError(AuthErrorCode.INVALID_TOKEN, "unknown")
        return c


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_fk(dbapi_conn, _record) -> None:  # type: ignore[no-untyped-def]
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as s:
        yield s
    await engine.dispose()


@pytest_asyncio.fixture
async def seed(session: AsyncSession) -> dict[str, Any]:
    d = await SqlAlchemyDespachoRepository(session).crear(
        Despacho(id=uuid4(), nombre="Despacho A"),
    )
    u = await SqlAlchemyUsuarioRepository(session).crear(
        Usuario(
            id=uuid4(),
            email="ana@x.com",
            nombre="Ana",
            auth_provider_id="clerk_ana",
        ),
    )
    await SqlAlchemyMembresiaDespachoRepository(session).agregar(
        MembresiaDespacho(
            usuario_id=u.id, despacho_id=d.id, rol=Rol.JEFE_ASESORES,
        ),
    )
    # Plantilla aprobada + plantilla pendiente.
    await SqlAlchemyPlantillaWhatsAppRepository(session).upsert(
        PlantillaWhatsApp(
            name="briefing_diario",
            categoria=CategoriaPlantilla.UTILITY,
            body_params=["n", "f", "r"],
            contenido_referencia="Hola {{1}} del {{2}}: {{3}}",
            estado_meta=EstadoMetaPlantilla.APROBADA,
        ),
    )
    await SqlAlchemyPlantillaWhatsAppRepository(session).upsert(
        PlantillaWhatsApp(
            name="alerta_x",
            categoria=CategoriaPlantilla.UTILITY,
            body_params=[],
            contenido_referencia="Alerta",
            estado_meta=EstadoMetaPlantilla.PENDIENTE_APROBACION,
        ),
    )
    await session.commit()
    return {"despacho_id": d.id, "token": "tok-ana"}


def _setup_client(session: AsyncSession, seed: dict[str, Any]) -> TestClient:
    auth = FakeAuth(
        {seed["token"]: AuthClaims(sub="clerk_ana", email="ana@x.com")},
    )

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield session

    real_app.dependency_overrides[get_session] = _session_override
    real_app.dependency_overrides[get_auth_provider] = lambda: auth
    return TestClient(real_app)


def _headers(seed: dict[str, Any]) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {seed['token']}",
        "X-Despacho-Id": str(seed["despacho_id"]),
    }


# ---------------------------------------------------------------------------
# /destinatarios
# ---------------------------------------------------------------------------


async def test_post_crear_destinatario(
    session: AsyncSession, seed: dict[str, Any],
) -> None:
    client = _setup_client(session, seed)
    try:
        resp = client.post(
            "/api/v1/destinatarios",
            headers=_headers(seed),
            json={
                "nombre": "Pablo Juliano",
                "rol_interno": "legislador",
                "telefono_e164": "+54 9 11 5555-1234",  # con espacios + guiones
                "recibe_briefing_diario": True,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["telefono_e164"] == "+5491155551234"
        assert data["activo"] is False  # opt_in pending
    finally:
        real_app.dependency_overrides.clear()


async def test_post_telefono_invalido_422(
    session: AsyncSession, seed: dict[str, Any],
) -> None:
    client = _setup_client(session, seed)
    try:
        resp = client.post(
            "/api/v1/destinatarios",
            headers=_headers(seed),
            json={
                "nombre": "X",
                "rol_interno": "asesor",
                "telefono_e164": "555-1234",  # sin +
            },
        )
        assert resp.status_code == 422
    finally:
        real_app.dependency_overrides.clear()


async def test_post_telefono_duplicado_409(
    session: AsyncSession, seed: dict[str, Any],
) -> None:
    await SqlAlchemyDestinatarioRepository(session).crear(
        Destinatario(
            id=None,
            despacho_id=seed["despacho_id"],
            nombre="Pre-existente",
            rol_interno=RolDestinatario.ASESOR,
            telefono_e164="+5491155551234",
        ),
    )
    await session.commit()

    client = _setup_client(session, seed)
    try:
        resp = client.post(
            "/api/v1/destinatarios",
            headers=_headers(seed),
            json={
                "nombre": "Otro",
                "rol_interno": "legislador",
                "telefono_e164": "+5491155551234",
            },
        )
        assert resp.status_code == 409
    finally:
        real_app.dependency_overrides.clear()


async def test_get_lista_y_filtro_activos(
    session: AsyncSession, seed: dict[str, Any],
) -> None:
    repo = SqlAlchemyDestinatarioRepository(session)
    await repo.crear(
        Destinatario(
            id=None,
            despacho_id=seed["despacho_id"],
            nombre="A",
            rol_interno=RolDestinatario.ASESOR,
            telefono_e164="+5491155551111",
        ),
    )
    activo = await repo.crear(
        Destinatario(
            id=None,
            despacho_id=seed["despacho_id"],
            nombre="B",
            rol_interno=RolDestinatario.LEGISLADOR,
            telefono_e164="+5491155552222",
        ),
    )
    await repo.actualizar(
        Destinatario(
            id=activo.id,
            despacho_id=activo.despacho_id,
            nombre=activo.nombre,
            rol_interno=activo.rol_interno,
            telefono_e164=activo.telefono_e164,
            opt_in_en=datetime(2026, 5, 1, tzinfo=UTC),
            activo=True,
        ),
    )
    await session.commit()

    client = _setup_client(session, seed)
    try:
        todos = client.get(
            "/api/v1/destinatarios", headers=_headers(seed),
        )
        activos = client.get(
            "/api/v1/destinatarios?solo_activos=true",
            headers=_headers(seed),
        )
        assert todos.status_code == 200
        assert activos.status_code == 200
        assert len(todos.json()) == 2
        assert len(activos.json()) == 1
        assert activos.json()[0]["telefono_e164"] == "+5491155552222"
    finally:
        real_app.dependency_overrides.clear()


async def test_patch_actualiza_flags(
    session: AsyncSession, seed: dict[str, Any],
) -> None:
    dest = await SqlAlchemyDestinatarioRepository(session).crear(
        Destinatario(
            id=None,
            despacho_id=seed["despacho_id"],
            nombre="A",
            rol_interno=RolDestinatario.ASESOR,
            telefono_e164="+5491155551111",
            recibe_briefing_diario=True,
            recibe_alertas_menciones=False,
        ),
    )
    await session.commit()

    client = _setup_client(session, seed)
    try:
        resp = client.patch(
            f"/api/v1/destinatarios/{dest.id}",
            headers=_headers(seed),
            json={"recibe_alertas_menciones": True, "nombre": "A actualizado"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["nombre"] == "A actualizado"
        assert data["recibe_alertas_menciones"] is True
        assert data["recibe_briefing_diario"] is True  # no cambió
    finally:
        real_app.dependency_overrides.clear()


async def test_delete_destinatario(
    session: AsyncSession, seed: dict[str, Any],
) -> None:
    dest = await SqlAlchemyDestinatarioRepository(session).crear(
        Destinatario(
            id=None,
            despacho_id=seed["despacho_id"],
            nombre="A",
            rol_interno=RolDestinatario.ASESOR,
            telefono_e164="+5491155551111",
        ),
    )
    await session.commit()

    client = _setup_client(session, seed)
    try:
        resp = client.delete(
            f"/api/v1/destinatarios/{dest.id}",
            headers=_headers(seed),
        )
        assert resp.status_code == 204
        # Segundo DELETE → 404.
        resp2 = client.delete(
            f"/api/v1/destinatarios/{dest.id}",
            headers=_headers(seed),
        )
        assert resp2.status_code == 404
    finally:
        real_app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# /envios-whatsapp
# ---------------------------------------------------------------------------


async def test_get_envios_filtra_por_tipo(
    session: AsyncSession, seed: dict[str, Any],
) -> None:
    dest = await SqlAlchemyDestinatarioRepository(session).crear(
        Destinatario(
            id=None,
            despacho_id=seed["despacho_id"],
            nombre="A",
            rol_interno=RolDestinatario.ASESOR,
            telefono_e164="+5491155551111",
        ),
    )
    envio_repo = SqlAlchemyEnvioWhatsAppRepository(session)
    ahora = datetime(2026, 6, 1, 10, 0, tzinfo=UTC)
    e1 = await envio_repo.crear(
        EnvioWhatsApp(
            id=None,
            destinatario_id=dest.id,  # type: ignore[arg-type]
            despacho_id=seed["despacho_id"],
            plantilla_name="briefing_diario",
            tipo=TipoEnvio.BRIEFING_DIARIO,
        ),
    )
    await envio_repo.marcar_enviado(
        envio_id=e1.id,  # type: ignore[arg-type]
        message_id_meta="m1",
        enviado_en=ahora,
    )
    e2 = await envio_repo.crear(
        EnvioWhatsApp(
            id=None,
            destinatario_id=dest.id,  # type: ignore[arg-type]
            despacho_id=seed["despacho_id"],
            plantilla_name="alerta_x",
            tipo=TipoEnvio.ALERTA_MENCION,
        ),
    )
    await envio_repo.marcar_enviado(
        envio_id=e2.id,  # type: ignore[arg-type]
        message_id_meta="m2",
        enviado_en=ahora + timedelta(hours=1),
    )
    await session.commit()

    client = _setup_client(session, seed)
    try:
        params = {
            "desde": (ahora - timedelta(hours=1)).isoformat(),
            "hasta": (ahora + timedelta(days=1)).isoformat(),
        }
        todos = client.get(
            "/api/v1/envios-whatsapp",
            headers=_headers(seed),
            params=params,
        )
        assert todos.status_code == 200
        assert len(todos.json()) == 2

        solo_briefing = client.get(
            "/api/v1/envios-whatsapp",
            headers=_headers(seed),
            params=params | {"tipo": "briefing_diario"},
        )
        assert solo_briefing.status_code == 200
        assert len(solo_briefing.json()) == 1
        assert solo_briefing.json()[0]["tipo"] == "briefing_diario"
    finally:
        real_app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# /plantillas
# ---------------------------------------------------------------------------


async def test_get_plantillas_con_filtro_aprobadas(
    session: AsyncSession, seed: dict[str, Any],
) -> None:
    client = _setup_client(session, seed)
    try:
        todas = client.get("/api/v1/plantillas", headers=_headers(seed))
        solo_ap = client.get(
            "/api/v1/plantillas?solo_aprobadas=true",
            headers=_headers(seed),
        )
        assert todas.status_code == 200
        assert solo_ap.status_code == 200
        # seed: 1 APROBADA + 1 PENDIENTE.
        assert len(todas.json()) == 2
        assert len(solo_ap.json()) == 1
        assert solo_ap.json()[0]["name"] == "briefing_diario"
    finally:
        real_app.dependency_overrides.clear()
