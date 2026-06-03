"""Tests integración del router /noticias, /menciones, /fuentes.

SQLite in-memory + FakeAuth + overrides. Cubre:

- GET /noticias: tenant-scoped, ordenado por score desc, hidrata
  artículo + fuente + clasificación.
- GET /noticias/{id}: detalle con menciones del despacho asociadas.
- GET /noticias/{id} 404.
- GET /menciones: histórico con filtros (tono, fuente_id).
- GET /menciones/{id}: tenant-scoped (otro despacho → 404).
- GET /fuentes: globales + DISTRITALES suscriptas via puente.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
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
    AlcanceMedio,
    AreaTematica,
    Articulo,
    ArticuloRelevante,
    AuthClaims,
    AuthError,
    AuthErrorCode,
    ClasificacionArticulo,
    Despacho,
    FuenteNoticia,
    MembresiaDespacho,
    Mencion,
    ModoAccesoFuente,
    Rol,
    TipoFuenteNoticia,
    TonoMencion,
    Usuario,
)
from praxis.infrastructure.persistence.base import Base
from praxis.infrastructure.persistence.models import FuenteNoticiaDespachoOrm
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyArticuloRelevanteRepository,
    SqlAlchemyArticuloRepository,
    SqlAlchemyClasificacionArticuloRepository,
    SqlAlchemyDespachoRepository,
    SqlAlchemyFuenteNoticiaRepository,
    SqlAlchemyMembresiaDespachoRepository,
    SqlAlchemyMencionRepository,
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
    """Seed: 1 despacho + 1 usuario + 2 fuentes (1 nac + 1 distrital
    suscripta) + 1 fuente DISTRITAL ajena + 2 artículos + 1 clasif +
    1 ArticuloRelevante + 2 menciones (1 positiva, 1 negativa)."""
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

    fuentes_repo = SqlAlchemyFuenteNoticiaRepository(session)
    f_nac = await fuentes_repo.crear(
        FuenteNoticia(
            id=None,
            nombre="La Nación",
            dominio="lanacion.com.ar",
            tipo=TipoFuenteNoticia.NACIONAL,
            alcance=AlcanceMedio.NACIONAL,
            modo_acceso=ModoAccesoFuente.RSS,
            feed_url="https://lanacion.com.ar/rss",
        ),
    )
    f_dist_suya = await fuentes_repo.crear(
        FuenteNoticia(
            id=None,
            nombre="Medio Bonaerense",
            dominio="medio-bonaerense.com",
            tipo=TipoFuenteNoticia.DISTRITAL,
            alcance=AlcanceMedio.PROVINCIAL,
            modo_acceso=ModoAccesoFuente.RSS,
            feed_url="https://medio-bonaerense.com/rss",
            distrito="BUENOS AIRES",
        ),
    )
    f_dist_ajena = await fuentes_repo.crear(
        FuenteNoticia(
            id=None,
            nombre="Medio Cordobés",
            dominio="medio-cordobes.com",
            tipo=TipoFuenteNoticia.DISTRITAL,
            alcance=AlcanceMedio.PROVINCIAL,
            modo_acceso=ModoAccesoFuente.RSS,
            feed_url="https://medio-cordobes.com/rss",
            distrito="CORDOBA",
        ),
    )
    # Asociamos la fuente distrital suya al despacho via puente.
    session.add(
        FuenteNoticiaDespachoOrm(
            fuente_id=f_dist_suya.id, despacho_id=d.id,
        ),
    )

    arts_repo = SqlAlchemyArticuloRepository(session)
    a1, = await arts_repo.upsert_lote([
        Articulo(
            id=None,
            fuente_id=f_nac.id,
            url="https://lanacion.com.ar/educacion-1",
            titulo="Diputados aprobó reforma educativa",
            bajada_propia="Una sola oración resumen del artículo.",
            publicado_en=datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
            capturado_en=datetime(2026, 6, 1, 10, 5, tzinfo=UTC),
        ),
    ])
    a2, = await arts_repo.upsert_lote([
        Articulo(
            id=None,
            fuente_id=f_nac.id,
            url="https://lanacion.com.ar/economia-1",
            titulo="Inflación de mayo",
            publicado_en=datetime(2026, 6, 1, 11, 0, tzinfo=UTC),
            capturado_en=datetime(2026, 6, 1, 11, 5, tzinfo=UTC),
        ),
    ])

    clasifs_repo = SqlAlchemyClasificacionArticuloRepository(session)
    await clasifs_repo.crear(
        ClasificacionArticulo(
            id=None,
            articulo_id=a1.id,
            area_tematica=AreaTematica.EDUCACION,
            palabras_clave=["jornada", "escuela"],
            modelo="fake-test",
        ),
    )

    relevantes_repo = SqlAlchemyArticuloRelevanteRepository(session)
    await relevantes_repo.upsert(
        ArticuloRelevante(
            articulo_id=a1.id,
            despacho_id=d.id,
            score=85,
            razon="área educación + menciona al legislador",
        ),
    )

    menciones_repo = SqlAlchemyMencionRepository(session)
    persistidas = await menciones_repo.crear_lote([
        Mencion(
            id=None,
            articulo_id=a1.id,
            legislador_id=uuid4(),
            despacho_id=d.id,
            snippet_contexto="El diputado Pablo Juliano impulsó la ley...",
            tono=TonoMencion.POSITIVO,
            confianza_tono=0.9,
            alcance_medio=AlcanceMedio.NACIONAL,
            detectado_en=datetime(2026, 6, 1, 10, 10, tzinfo=UTC),
        ),
        Mencion(
            id=None,
            articulo_id=a2.id,
            legislador_id=uuid4(),
            despacho_id=d.id,
            snippet_contexto="Juliano criticó al ministro...",
            tono=TonoMencion.NEGATIVO,
            confianza_tono=0.8,
            alcance_medio=AlcanceMedio.NACIONAL,
            detectado_en=datetime(2026, 6, 1, 11, 10, tzinfo=UTC),
        ),
    ])
    m_pos, m_neg = persistidas[0], persistidas[1]

    await session.commit()
    return {
        "despacho_id": d.id,
        "usuario_id": u.id,
        "fuente_nac_id": f_nac.id,
        "fuente_dist_suya_id": f_dist_suya.id,
        "fuente_dist_ajena_id": f_dist_ajena.id,
        "articulo_relevante_id": a1.id,
        "articulo_no_relevante_id": a2.id,
        "mencion_pos_id": m_pos.id,
        "mencion_neg_id": m_neg.id,
        "token": "tok-ana",
    }


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
# GET /noticias
# ---------------------------------------------------------------------------


async def test_listar_noticias_devuelve_solo_relevantes_del_despacho(
    session: AsyncSession, seed: dict[str, Any],
) -> None:
    client = _setup_client(session, seed)
    try:
        resp = client.get("/api/v1/noticias", headers=_headers(seed))
        assert resp.status_code == 200
        items = resp.json()
        # Solo el a1 tiene ArticuloRelevante en el seed.
        assert len(items) == 1
        item = items[0]
        assert item["relevante"]["score"] == 85
        assert item["articulo"]["titulo"].startswith("Diputados")
        assert item["fuente"]["dominio"] == "lanacion.com.ar"
        assert item["clasificacion"]["area_tematica"] == "educacion"
    finally:
        real_app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /noticias/{id}
# ---------------------------------------------------------------------------


async def test_detalle_articulo_con_menciones(
    session: AsyncSession, seed: dict[str, Any],
) -> None:
    client = _setup_client(session, seed)
    try:
        resp = client.get(
            f"/api/v1/noticias/{seed['articulo_relevante_id']}",
            headers=_headers(seed),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["articulo"]["titulo"].startswith("Diputados")
        assert data["clasificacion"]["area_tematica"] == "educacion"
        assert data["relevante"]["score"] == 85
        # 1 mención asociada (la positiva).
        assert len(data["menciones"]) == 1
        assert data["menciones"][0]["tono"] == "positivo"
    finally:
        real_app.dependency_overrides.clear()


async def test_detalle_articulo_404(
    session: AsyncSession, seed: dict[str, Any],
) -> None:
    client = _setup_client(session, seed)
    try:
        resp = client.get(
            f"/api/v1/noticias/{uuid4()}", headers=_headers(seed),
        )
        assert resp.status_code == 404
    finally:
        real_app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /menciones
# ---------------------------------------------------------------------------


def _ventana_seed_params() -> dict[str, str]:
    """Ventana amplia para asegurar que la seed entra. Usa `params=`
    para que httpx URL-encodee el `+` del isoformat correctamente."""
    return {
        "desde": datetime(2026, 6, 1, 0, 0, tzinfo=UTC).isoformat(),
        "hasta": datetime(2026, 6, 2, 0, 0, tzinfo=UTC).isoformat(),
    }


async def test_listar_menciones_historico(
    session: AsyncSession, seed: dict[str, Any],
) -> None:
    client = _setup_client(session, seed)
    try:
        resp = client.get(
            "/api/v1/menciones",
            headers=_headers(seed),
            params=_ventana_seed_params(),
        )
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 2
        tonos = {m["mencion"]["tono"] for m in items}
        assert tonos == {"positivo", "negativo"}
    finally:
        real_app.dependency_overrides.clear()


async def test_listar_menciones_filtra_por_tono(
    session: AsyncSession, seed: dict[str, Any],
) -> None:
    client = _setup_client(session, seed)
    try:
        params = _ventana_seed_params() | {"tono": "negativo"}
        resp = client.get(
            "/api/v1/menciones",
            headers=_headers(seed),
            params=params,
        )
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["mencion"]["tono"] == "negativo"
    finally:
        real_app.dependency_overrides.clear()


async def test_listar_menciones_filtra_por_fuente(
    session: AsyncSession, seed: dict[str, Any],
) -> None:
    client = _setup_client(session, seed)
    try:
        # Ambas menciones están en `fuente_nac_id`; filtrando por la
        # distrital ajena → 0 resultados.
        params = _ventana_seed_params() | {
            "fuente_id": str(seed["fuente_dist_ajena_id"]),
        }
        resp = client.get(
            "/api/v1/menciones",
            headers=_headers(seed),
            params=params,
        )
        assert resp.status_code == 200
        assert resp.json() == []
    finally:
        real_app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /menciones/{id}
# ---------------------------------------------------------------------------


async def test_detalle_mencion(
    session: AsyncSession, seed: dict[str, Any],
) -> None:
    client = _setup_client(session, seed)
    try:
        resp = client.get(
            f"/api/v1/menciones/{seed['mencion_pos_id']}",
            headers=_headers(seed),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["mencion"]["tono"] == "positivo"
        assert data["articulo"]["titulo"].startswith("Diputados")
    finally:
        real_app.dependency_overrides.clear()


async def test_detalle_mencion_inexistente_404(
    session: AsyncSession, seed: dict[str, Any],
) -> None:
    client = _setup_client(session, seed)
    try:
        resp = client.get(
            f"/api/v1/menciones/{uuid4()}", headers=_headers(seed),
        )
        assert resp.status_code == 404
    finally:
        real_app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /fuentes
# ---------------------------------------------------------------------------


async def test_listar_fuentes_globales_y_distritales_suscriptas(
    session: AsyncSession, seed: dict[str, Any],
) -> None:
    client = _setup_client(session, seed)
    try:
        resp = client.get("/api/v1/fuentes", headers=_headers(seed))
        assert resp.status_code == 200
        items = resp.json()
        dominios = {f["dominio"] for f in items}
        # Global (nacional) → visible.
        assert "lanacion.com.ar" in dominios
        # Distrital suscripta → visible.
        assert "medio-bonaerense.com" in dominios
        # Distrital de otro despacho → NO visible.
        assert "medio-cordobes.com" not in dominios
    finally:
        real_app.dependency_overrides.clear()
