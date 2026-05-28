"""Tests integración de los routers /me, /expedientes y /seguimientos.

Estrategia (igual que test_auth_dep.py):
- SQLite in-memory.
- App de prueba con `app.dependency_overrides[get_session]` y
  `app.dependency_overrides[get_auth_provider]` para no necesitar Postgres
  ni Clerk reales.
- Cada test seed-ea lo que necesita.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from praxis.api.deps import get_auth_provider, get_session
from praxis.api.main import app as real_app
from praxis.application.ports import AuthProvider
from praxis.domain import (
    AuthClaims,
    AuthError,
    AuthErrorCode,
    Camara,
    Despacho,
    EstadoExpediente,
    Expediente,
    Firmante,
    Giro,
    MembresiaDespacho,
    NumeroExpediente,
    Prioridad,
    Rol,
    SeguimientoExpediente,
    TipoExpediente,
    TramiteEvento,
    Usuario,
)
from praxis.infrastructure.persistence.base import Base
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyDespachoRepository,
    SqlAlchemyExpedienteRepository,
    SqlAlchemyMembresiaDespachoRepository,
    SqlAlchemySeguimientoExpedienteRepository,
    SqlAlchemyUsuarioRepository,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fake auth provider
# ---------------------------------------------------------------------------


class FakeAuth(AuthProvider):
    def __init__(self, tokens: dict[str, AuthClaims]) -> None:
        self._tokens = tokens

    async def verificar_token(self, token: str) -> AuthClaims:
        c = self._tokens.get(token)
        if c is None:
            raise AuthError(AuthErrorCode.INVALID_TOKEN, "unknown token")
        return c


# ---------------------------------------------------------------------------
# Fixtures de DB + app
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    # Habilitar FKs en SQLite (necesario para que el FK del seguimiento valide).
    from sqlalchemy import event

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
    """Crea usuarios A/B, despachos A/B, membresías, un expediente compartido,
    y devuelve los UUIDs útiles + tokens para cada usuario.
    """
    d_a = await SqlAlchemyDespachoRepository(session).crear(
        Despacho(id=uuid4(), nombre="Despacho A")
    )
    d_b = await SqlAlchemyDespachoRepository(session).crear(
        Despacho(id=uuid4(), nombre="Despacho B")
    )
    u_a = await SqlAlchemyUsuarioRepository(session).crear(
        Usuario(
            id=uuid4(),
            email="ana@x.com",
            nombre="Ana",
            auth_provider_id="clerk_ana",
        )
    )
    u_b = await SqlAlchemyUsuarioRepository(session).crear(
        Usuario(
            id=uuid4(),
            email="beto@x.com",
            nombre="Beto",
            auth_provider_id="clerk_beto",
        )
    )
    mem_repo = SqlAlchemyMembresiaDespachoRepository(session)
    await mem_repo.agregar(
        MembresiaDespacho(usuario_id=u_a.id, despacho_id=d_a.id, rol=Rol.JEFE_ASESORES)
    )
    await mem_repo.agregar(MembresiaDespacho(usuario_id=u_b.id, despacho_id=d_b.id, rol=Rol.ASESOR))

    exp_repo = SqlAlchemyExpedienteRepository(session)
    exp = await exp_repo.crear(
        Expediente(
            numero=NumeroExpediente.parse_hcdn("100-D-2024"),
            tipo=TipoExpediente.PROYECTO_LEY,
            titulo="Reforma de Salud",
            sumario="Modificacion del sistema sanitario",
            fecha_ingreso=date(2024, 3, 15),
            estado=EstadoExpediente.EN_COMISION,
            firmantes=[
                Firmante(nombre="MASSOT, NICOLAS", orden=1, bloque="X"),
            ],
            giros=[Giro(comision="ACCION SOCIAL Y SALUD PUBLICA")],
            tramite=[
                TramiteEvento(
                    fecha=date(2024, 3, 20),
                    camara=Camara.HCDN,
                    evento="GIRO A COMISION",
                    detalle="ACCION SOCIAL Y SALUD PUBLICA",
                    fuente="scraper:hcdn",
                ),
            ],
        )
    )
    # Un segundo expediente para testear filtros.
    exp2 = await exp_repo.crear(
        Expediente(
            numero=NumeroExpediente.parse_hcdn("200-D-2025"),
            tipo=TipoExpediente.PROYECTO_RESOLUCION,
            titulo="Declaracion sobre cultura",
            fecha_ingreso=date(2025, 1, 10),
            estado=EstadoExpediente.INGRESADO,
            firmantes=[Firmante(nombre="GARCIA, JUAN", orden=1)],
            giros=[Giro(comision="CULTURA")],
        )
    )

    await session.commit()
    return {
        "despacho_a_id": d_a.id,
        "despacho_b_id": d_b.id,
        "usuario_a_id": u_a.id,
        "usuario_b_id": u_b.id,
        "expediente_id": exp.id,
        "expediente2_id": exp2.id,
        "token_a": "tok-ana",
        "token_b": "tok-beto",
    }


def _setup_overrides(session: AsyncSession, seed: dict[str, Any]) -> TestClient:
    """Override las deps + arma un TestClient sobre la app real."""
    auth = FakeAuth(
        {
            seed["token_a"]: AuthClaims(sub="clerk_ana", email="ana@x.com"),
            seed["token_b"]: AuthClaims(sub="clerk_beto", email="beto@x.com"),
        }
    )

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield session

    real_app.dependency_overrides[get_session] = _session_override
    real_app.dependency_overrides[get_auth_provider] = lambda: auth
    return TestClient(real_app)


def _h(seed: dict[str, Any], *, who: str = "a", despacho: str = "a") -> dict[str, str]:
    """Helper para armar headers Authorization + X-Despacho-Id."""
    return {
        "Authorization": f"Bearer {seed['token_' + who]}",
        "X-Despacho-Id": str(seed[f"despacho_{despacho}_id"]),
    }


# ---------------------------------------------------------------------------
# /me
# ---------------------------------------------------------------------------


def test_me_devuelve_usuario_despacho_y_rol(session: AsyncSession, seed: dict[str, Any]) -> None:
    client = _setup_overrides(session, seed)
    response = client.get("/api/v1/me", headers=_h(seed))
    assert response.status_code == 200
    body = response.json()
    assert body["usuario"]["email"] == "ana@x.com"
    assert body["despacho"]["nombre"] == "Despacho A"
    assert body["rol"] == "jefe_asesores"


# ---------------------------------------------------------------------------
# GET /expedientes (búsqueda)
# ---------------------------------------------------------------------------


def test_listar_expedientes_sin_filtros(session: AsyncSession, seed: dict[str, Any]) -> None:
    client = _setup_overrides(session, seed)
    response = client.get("/api/v1/expedientes", headers=_h(seed))
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2
    # Verificar que el resumen NO incluye firmantes/giros/tramite.
    assert "firmantes" not in body["items"][0]
    assert "tramite" not in body["items"][0]


def test_listar_expedientes_filtra_por_texto(session: AsyncSession, seed: dict[str, Any]) -> None:
    client = _setup_overrides(session, seed)
    response = client.get(
        "/api/v1/expedientes",
        headers=_h(seed),
        params={"texto": "salud"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["titulo"] == "Reforma de Salud"


def test_listar_expedientes_filtra_por_comision(
    session: AsyncSession, seed: dict[str, Any]
) -> None:
    client = _setup_overrides(session, seed)
    response = client.get(
        "/api/v1/expedientes",
        headers=_h(seed),
        params={"comision": "cultura"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["titulo"] == "Declaracion sobre cultura"


def test_listar_expedientes_pagina(session: AsyncSession, seed: dict[str, Any]) -> None:
    client = _setup_overrides(session, seed)
    response = client.get(
        "/api/v1/expedientes",
        headers=_h(seed),
        params={"limit": 1, "offset": 0},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert len(body["items"]) == 1
    assert body["limit"] == 1


def test_listar_expedientes_rechaza_filtros_invalidos(
    session: AsyncSession, seed: dict[str, Any]
) -> None:
    client = _setup_overrides(session, seed)
    # limit fuera de rango.
    response = client.get(
        "/api/v1/expedientes",
        headers=_h(seed),
        params={"limit": 9999},
    )
    assert response.status_code == 422


def test_listar_expedientes_requiere_auth(session: AsyncSession, seed: dict[str, Any]) -> None:
    client = _setup_overrides(session, seed)
    response = client.get("/api/v1/expedientes")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /expedientes/{id}
# ---------------------------------------------------------------------------


def test_ficha_devuelve_relaciones_y_sin_seguimiento_si_no_marca(
    session: AsyncSession, seed: dict[str, Any]
) -> None:
    client = _setup_overrides(session, seed)
    response = client.get(
        f"/api/v1/expedientes/{seed['expediente_id']}",
        headers=_h(seed),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["titulo"] == "Reforma de Salud"
    assert len(body["firmantes"]) == 1
    assert body["firmantes"][0]["nombre"] == "MASSOT, NICOLAS"
    assert len(body["giros"]) == 1
    assert len(body["tramite"]) == 1
    assert body["seguimiento"] is None


def test_ficha_embebe_seguimiento_si_despacho_lo_marca(
    session: AsyncSession, seed: dict[str, Any]
) -> None:
    """Sembramos un seguimiento de despacho A sobre el expediente, y consultamos
    la ficha con auth de A. Debe venir embebido."""
    import asyncio

    async def _seed_seguimiento() -> None:
        repo = SqlAlchemySeguimientoExpedienteRepository(session)
        await repo.crear(
            SeguimientoExpediente(
                id=uuid4(),
                despacho_id=seed["despacho_a_id"],
                expediente_id=seed["expediente_id"],
                prioridad=Prioridad.ALTA,
            )
        )
        await session.commit()

    asyncio.get_event_loop().run_until_complete(_seed_seguimiento())

    client = _setup_overrides(session, seed)
    response = client.get(
        f"/api/v1/expedientes/{seed['expediente_id']}",
        headers=_h(seed, who="a", despacho="a"),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["seguimiento"] is not None
    assert body["seguimiento"]["prioridad"] == "alta"


def test_ficha_no_embebe_seguimiento_de_otro_despacho(
    session: AsyncSession, seed: dict[str, Any]
) -> None:
    """Despacho A marcó el expediente. Despacho B consulta la ficha del mismo
    expediente: el campo `seguimiento` debe venir null (es de A, no de B)."""
    import asyncio

    async def _seed_seguimiento() -> None:
        repo = SqlAlchemySeguimientoExpedienteRepository(session)
        await repo.crear(
            SeguimientoExpediente(
                id=uuid4(),
                despacho_id=seed["despacho_a_id"],
                expediente_id=seed["expediente_id"],
            )
        )
        await session.commit()

    asyncio.get_event_loop().run_until_complete(_seed_seguimiento())

    client = _setup_overrides(session, seed)
    response = client.get(
        f"/api/v1/expedientes/{seed['expediente_id']}",
        headers=_h(seed, who="b", despacho="b"),
    )
    assert response.status_code == 200
    assert response.json()["seguimiento"] is None


def test_ficha_inexistente_devuelve_404(session: AsyncSession, seed: dict[str, Any]) -> None:
    client = _setup_overrides(session, seed)
    response = client.get(
        f"/api/v1/expedientes/{uuid4()}",
        headers=_h(seed),
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /seguimientos
# ---------------------------------------------------------------------------


def test_crear_seguimiento(session: AsyncSession, seed: dict[str, Any]) -> None:
    client = _setup_overrides(session, seed)
    response = client.post(
        "/api/v1/seguimientos",
        headers=_h(seed),
        json={
            "expediente_id": str(seed["expediente_id"]),
            "prioridad": "alta",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["expediente_id"] == str(seed["expediente_id"])
    assert body["prioridad"] == "alta"
    assert body["archivado"] is False


def test_crear_seguimiento_falla_si_expediente_no_existe(
    session: AsyncSession, seed: dict[str, Any]
) -> None:
    client = _setup_overrides(session, seed)
    response = client.post(
        "/api/v1/seguimientos",
        headers=_h(seed),
        json={"expediente_id": str(uuid4())},
    )
    assert response.status_code == 404


def test_crear_seguimiento_duplicado_devuelve_409(
    session: AsyncSession, seed: dict[str, Any]
) -> None:
    client = _setup_overrides(session, seed)
    payload = {"expediente_id": str(seed["expediente_id"])}
    r1 = client.post("/api/v1/seguimientos", headers=_h(seed), json=payload)
    r2 = client.post("/api/v1/seguimientos", headers=_h(seed), json=payload)
    assert r1.status_code == 201
    assert r2.status_code == 409


# ---------------------------------------------------------------------------
# PATCH /seguimientos/{id}
# ---------------------------------------------------------------------------


def test_actualizar_seguimiento_asigna_responsable(
    session: AsyncSession, seed: dict[str, Any]
) -> None:
    client = _setup_overrides(session, seed)
    creado = client.post(
        "/api/v1/seguimientos",
        headers=_h(seed),
        json={"expediente_id": str(seed["expediente_id"])},
    ).json()
    sid = creado["id"]

    response = client.patch(
        f"/api/v1/seguimientos/{sid}",
        headers=_h(seed),
        json={"responsable_id": str(seed["usuario_a_id"])},
    )
    assert response.status_code == 200
    assert response.json()["responsable_id"] == str(seed["usuario_a_id"])


def test_actualizar_seguimiento_archiva(session: AsyncSession, seed: dict[str, Any]) -> None:
    client = _setup_overrides(session, seed)
    creado = client.post(
        "/api/v1/seguimientos",
        headers=_h(seed),
        json={"expediente_id": str(seed["expediente_id"])},
    ).json()
    sid = creado["id"]

    response = client.patch(
        f"/api/v1/seguimientos/{sid}",
        headers=_h(seed),
        json={"archivado": True},
    )
    assert response.status_code == 200
    assert response.json()["archivado"] is True


def test_actualizar_seguimiento_de_otro_despacho_devuelve_404(
    session: AsyncSession, seed: dict[str, Any]
) -> None:
    """Tenant isolation: despacho A crea, despacho B intenta updatear."""
    client = _setup_overrides(session, seed)
    creado = client.post(
        "/api/v1/seguimientos",
        headers=_h(seed, who="a", despacho="a"),
        json={"expediente_id": str(seed["expediente_id"])},
    ).json()
    sid = creado["id"]

    response = client.patch(
        f"/api/v1/seguimientos/{sid}",
        headers=_h(seed, who="b", despacho="b"),
        json={"responsable_id": str(seed["usuario_b_id"])},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /seguimientos/{id}
# ---------------------------------------------------------------------------


def test_delete_seguimiento_archiva(session: AsyncSession, seed: dict[str, Any]) -> None:
    client = _setup_overrides(session, seed)
    creado = client.post(
        "/api/v1/seguimientos",
        headers=_h(seed),
        json={"expediente_id": str(seed["expediente_id"])},
    ).json()
    sid = creado["id"]

    response = client.delete(f"/api/v1/seguimientos/{sid}", headers=_h(seed))
    assert response.status_code == 204

    # Verificamos vía PATCH que ya está archivado.
    response_patch = client.patch(
        f"/api/v1/seguimientos/{sid}",
        headers=_h(seed),
        json={},  # body vacío: solo lee
    )
    assert response_patch.status_code == 200
    assert response_patch.json()["archivado"] is True


def test_delete_seguimiento_otro_despacho_devuelve_404(
    session: AsyncSession, seed: dict[str, Any]
) -> None:
    client = _setup_overrides(session, seed)
    creado = client.post(
        "/api/v1/seguimientos",
        headers=_h(seed, who="a", despacho="a"),
        json={"expediente_id": str(seed["expediente_id"])},
    ).json()
    sid = creado["id"]

    response = client.delete(
        f"/api/v1/seguimientos/{sid}",
        headers=_h(seed, who="b", despacho="b"),
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /seguimientos (listar del despacho activo)
# ---------------------------------------------------------------------------


def test_listar_seguimientos_vacio(session: AsyncSession, seed: dict[str, Any]) -> None:
    """Sin seguimientos creados, devuelve lista vacía."""
    client = _setup_overrides(session, seed)
    response = client.get("/api/v1/seguimientos", headers=_h(seed))
    assert response.status_code == 200
    assert response.json() == []


def test_listar_seguimientos_devuelve_solo_del_despacho_activo(
    session: AsyncSession, seed: dict[str, Any]
) -> None:
    """Tenant isolation: despacho A NO ve los seguimientos de despacho B."""
    client = _setup_overrides(session, seed)

    # Despacho A marca exp1, despacho B marca exp1 también.
    r_a = client.post(
        "/api/v1/seguimientos",
        headers=_h(seed, who="a", despacho="a"),
        json={"expediente_id": str(seed["expediente_id"]), "prioridad": "alta"},
    )
    r_b = client.post(
        "/api/v1/seguimientos",
        headers=_h(seed, who="b", despacho="b"),
        json={"expediente_id": str(seed["expediente_id"]), "prioridad": "baja"},
    )
    assert r_a.status_code == 201
    assert r_b.status_code == 201

    # Despacho A ve solo el suyo.
    resp_a = client.get("/api/v1/seguimientos", headers=_h(seed, who="a", despacho="a"))
    items_a = resp_a.json()
    assert len(items_a) == 1
    assert items_a[0]["prioridad"] == "alta"

    # Despacho B ve solo el suyo.
    resp_b = client.get("/api/v1/seguimientos", headers=_h(seed, who="b", despacho="b"))
    items_b = resp_b.json()
    assert len(items_b) == 1
    assert items_b[0]["prioridad"] == "baja"


def test_listar_seguimientos_default_oculta_archivados(
    session: AsyncSession, seed: dict[str, Any]
) -> None:
    client = _setup_overrides(session, seed)
    creado = client.post(
        "/api/v1/seguimientos",
        headers=_h(seed),
        json={"expediente_id": str(seed["expediente_id"])},
    ).json()
    client.delete(f"/api/v1/seguimientos/{creado['id']}", headers=_h(seed))

    # Default: no ver archivados.
    resp = client.get("/api/v1/seguimientos", headers=_h(seed))
    assert resp.json() == []

    # Con flag: ver todo.
    resp_all = client.get("/api/v1/seguimientos?incluir_archivados=true", headers=_h(seed))
    assert len(resp_all.json()) == 1
    assert resp_all.json()[0]["archivado"] is True


def test_listar_seguimientos_requiere_auth(session: AsyncSession, seed: dict[str, Any]) -> None:
    client = _setup_overrides(session, seed)
    response = client.get("/api/v1/seguimientos")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Cleanup global (los overrides en `app` persisten entre tests)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_overrides_at_end() -> Any:
    """Limpia los overrides después de cada test para no contaminar el siguiente."""
    yield
    real_app.dependency_overrides.clear()
