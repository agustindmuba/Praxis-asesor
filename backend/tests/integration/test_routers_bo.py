"""Tests integración del router /bo.

SQLite in-memory, FakeAuth, override de get_session + get_llm_provider.

Cubren:
- GET /bo/normas — lista no-tenant-scoped.
- GET /bo/normas/{id} — detalle con clasificación.
- GET /bo/normas/{id} 404 si no existe.
- GET /bo/accionables — tenant-scoped.
- POST /bo/normas/reclasificar-perfil — dispara recálculo.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from praxis.api.deps import (
    get_auth_provider,
    get_llm_provider,
    get_session,
)
from praxis.api.main import app as real_app
from praxis.application.ports import AuthProvider, LlmProvider
from praxis.domain import (
    AreaTematica,
    AuthClaims,
    AuthError,
    AuthErrorCode,
    ClasificacionNormaBO,
    ClasificacionNormaBOResult,
    Despacho,
    Expediente,
    MembresiaDespacho,
    NormaBO,
    PerfilInteresDespacho,
    Rol,
    SeccionBO,
    Usuario,
    hash_sumario,
)
from praxis.infrastructure.persistence.base import Base
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyClasificacionNormaBORepository,
    SqlAlchemyDespachoRepository,
    SqlAlchemyMembresiaDespachoRepository,
    SqlAlchemyNormaBORepository,
    SqlAlchemyPerfilInteresDespachoRepository,
    SqlAlchemyUsuarioRepository,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeAuth(AuthProvider):
    def __init__(self, tokens: dict[str, AuthClaims]) -> None:
        self._tokens = tokens

    async def verificar_token(self, token: str) -> AuthClaims:
        c = self._tokens.get(token)
        if c is None:
            raise AuthError(AuthErrorCode.INVALID_TOKEN, "unknown token")
        return c


class FakeLlmStub(LlmProvider):
    """LLM minimal que sirve para que el endpoint reclasificar-perfil
    funcione sin llamar a Anthropic."""

    @property
    def nombre_modelo(self) -> str:
        return "fake-stub"

    async def clasificar_norma_bo(
        self, norma: NormaBO, *, texto: str | None = None,
    ) -> ClasificacionNormaBOResult:
        return ClasificacionNormaBOResult(
            area_tematica=AreaTematica.JUSTICIA,
            palabras_clave=[],
            afecta_expedientes_hcdn=False,
            referencias_legales=[],
        )

    async def generar_resumen_ejecutivo(self, expediente: Expediente) -> str:
        raise NotImplementedError

    async def clasificar_area_tematica(
        self, expediente: Expediente,
    ) -> AreaTematica:
        raise NotImplementedError

    async def generar_argumentos(
        self, expediente: Expediente, *, contraargumentos: bool = False,
    ) -> list[str]:
        raise NotImplementedError

    async def disambiguar_mencion(self, **_: object) -> object:  # type: ignore[override]
        raise NotImplementedError

    async def generar_bajada_propia(self, *_: object, **__: object) -> str:  # type: ignore[override]
        raise NotImplementedError

    async def clasificar_articulo(self, *_: object, **__: object) -> object:  # type: ignore[override]
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
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
    """Despacho A con perfil + 2 normas BO + clasificación cacheada."""
    d_a = await SqlAlchemyDespachoRepository(session).crear(
        Despacho(id=uuid4(), nombre="Despacho A"),
    )
    u_a = await SqlAlchemyUsuarioRepository(session).crear(
        Usuario(
            id=uuid4(),
            email="ana@x.com",
            nombre="Ana",
            auth_provider_id="clerk_ana",
        ),
    )
    await SqlAlchemyMembresiaDespachoRepository(session).agregar(
        MembresiaDespacho(
            usuario_id=u_a.id, despacho_id=d_a.id, rol=Rol.JEFE_ASESORES,
        ),
    )

    await SqlAlchemyPerfilInteresDespachoRepository(session).upsert(
        PerfilInteresDespacho(
            despacho_id=d_a.id,
            areas_tematicas=["justicia"],
            distritos_observados=["Buenos Aires"],
            aliases_legislador=["Pablo Juliano"],
            sembrado_at=datetime.now(UTC),
        ),
    )

    fecha = date(2026, 6, 1)
    sumario_a = "Decreto sobre código procesal de justicia"
    sumario_b = "Decreto sobre transporte urbano"
    norma_a = NormaBO(
        id=None,
        fecha_publicacion=fecha,
        seccion=SeccionBO.LEGISLACION,
        tipo_norma="Decreto",
        numero_norma="100/2026",
        organismo_emisor="Poder Ejecutivo Nacional",
        sumario=sumario_a,
        url_oficial="https://www.boletinoficial.gob.ar/det/d-100",
        hash_sumario=hash_sumario(sumario_a),
        capturado_en=datetime.now(UTC),
    )
    norma_b = NormaBO(
        id=None,
        fecha_publicacion=fecha,
        seccion=SeccionBO.LEGISLACION,
        tipo_norma="Decreto",
        numero_norma="200/2026",
        organismo_emisor="Poder Ejecutivo Nacional",
        sumario=sumario_b,
        url_oficial="https://www.boletinoficial.gob.ar/det/d-200",
        hash_sumario=hash_sumario(sumario_b),
        capturado_en=datetime.now(UTC),
    )
    normas_repo = SqlAlchemyNormaBORepository(session)
    [persistida_a, persistida_b] = await normas_repo.upsert_lote(
        [norma_a, norma_b],
    )

    clasifs_repo = SqlAlchemyClasificacionNormaBORepository(session)
    await clasifs_repo.crear(
        ClasificacionNormaBO(
            id=uuid4(),
            norma_id=persistida_a.id,  # type: ignore[arg-type]
            area_tematica=AreaTematica.JUSTICIA,
            palabras_clave=["procesal"],
            afecta_expedientes_hcdn=False,
            referencias_legales=[],
            modelo="fake-test",
            prompt_version="v1",
        ),
    )
    await clasifs_repo.crear(
        ClasificacionNormaBO(
            id=uuid4(),
            norma_id=persistida_b.id,  # type: ignore[arg-type]
            area_tematica=AreaTematica.TRANSPORTE,
            palabras_clave=["urbano"],
            afecta_expedientes_hcdn=False,
            referencias_legales=[],
            modelo="fake-test",
            prompt_version="v1",
        ),
    )

    await session.commit()
    return {
        "despacho_id": d_a.id,
        "usuario_id": u_a.id,
        "norma_a_id": persistida_a.id,
        "norma_b_id": persistida_b.id,
        "fecha": fecha.isoformat(),
        "token": "tok-ana",
    }


def _setup_client(
    session: AsyncSession, seed: dict[str, Any],
) -> TestClient:
    auth = FakeAuth(
        {seed["token"]: AuthClaims(sub="clerk_ana", email="ana@x.com")},
    )

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield session

    real_app.dependency_overrides[get_session] = _session_override
    real_app.dependency_overrides[get_auth_provider] = lambda: auth
    real_app.dependency_overrides[get_llm_provider] = lambda: FakeLlmStub()
    return TestClient(real_app)


def _headers(seed: dict[str, Any]) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {seed['token']}",
        "X-Despacho-Id": str(seed["despacho_id"]),
    }


# ---------------------------------------------------------------------------
# GET /bo/normas
# ---------------------------------------------------------------------------


async def test_listar_normas_devuelve_las_del_dia(
    session: AsyncSession, seed: dict[str, Any],
) -> None:
    client = _setup_client(session, seed)
    try:
        resp = client.get(f"/api/v1/bo/normas?fecha={seed['fecha']}")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 2
        # No tenant scoping → no header X-Despacho-Id necesario.
    finally:
        real_app.dependency_overrides.clear()


async def test_listar_normas_filtra_por_seccion(
    session: AsyncSession, seed: dict[str, Any],
) -> None:
    client = _setup_client(session, seed)
    try:
        resp = client.get(
            f"/api/v1/bo/normas?fecha={seed['fecha']}&seccion=legislacion",
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 2
    finally:
        real_app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /bo/normas/{id}
# ---------------------------------------------------------------------------


async def test_detalle_norma_existe_devuelve_clasificacion(
    session: AsyncSession, seed: dict[str, Any],
) -> None:
    client = _setup_client(session, seed)
    try:
        resp = client.get(f"/api/v1/bo/normas/{seed['norma_a_id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["norma"]["numero_norma"] == "100/2026"
        assert data["clasificacion"] is not None
        assert data["clasificacion"]["area_tematica"] == "justicia"
    finally:
        real_app.dependency_overrides.clear()


async def test_detalle_norma_inexistente_404(
    session: AsyncSession, seed: dict[str, Any],
) -> None:
    client = _setup_client(session, seed)
    try:
        resp = client.get(f"/api/v1/bo/normas/{uuid4()}")
        assert resp.status_code == 404
    finally:
        real_app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /bo/accionables
# ---------------------------------------------------------------------------


async def test_accionables_vacios_por_default(
    session: AsyncSession, seed: dict[str, Any],
) -> None:
    """Sin reclasificar antes, no hay accionables persistidos."""
    client = _setup_client(session, seed)
    try:
        resp = client.get(
            f"/api/v1/bo/accionables?fecha={seed['fecha']}",
            headers=_headers(seed),
        )
        assert resp.status_code == 200
        assert resp.json() == []
    finally:
        real_app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# POST /bo/normas/reclasificar-perfil
# ---------------------------------------------------------------------------


async def test_reclasificar_perfil_genera_accionables(
    session: AsyncSession, seed: dict[str, Any],
) -> None:
    client = _setup_client(session, seed)
    try:
        # Dispara el recálculo: perfil tiene 'justicia', clasificación
        # de norma_a es JUSTICIA → score 30 → MEDIA → persistida.
        resp = client.post(
            f"/api/v1/bo/normas/reclasificar-perfil?fecha={seed['fecha']}",
            headers=_headers(seed),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["fecha"] == seed["fecha"]
        assert body["accionables_recalculadas"] == 1

        # Verificamos via GET /bo/accionables.
        resp2 = client.get(
            f"/api/v1/bo/accionables?fecha={seed['fecha']}",
            headers=_headers(seed),
        )
        assert resp2.status_code == 200
        items = resp2.json()
        assert len(items) == 1
        assert items[0]["accionable"]["prioridad"] == "media"
        assert items[0]["norma"]["numero_norma"] == "100/2026"
    finally:
        real_app.dependency_overrides.clear()


async def test_reclasificar_sin_auth_devuelve_401(
    session: AsyncSession, seed: dict[str, Any],
) -> None:
    client = _setup_client(session, seed)
    try:
        resp = client.post(
            f"/api/v1/bo/normas/reclasificar-perfil?fecha={seed['fecha']}",
        )
        assert resp.status_code == 401
    finally:
        real_app.dependency_overrides.clear()
