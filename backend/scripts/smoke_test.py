"""Smoke test end-to-end contra Postgres real.

Diferente a los tests de integración (que usan SQLite in-memory): este
script corre contra la DB Postgres del docker-compose, con la migration
schema ya aplicada por Alembic.

Lo que hace:
1. Conecta a la DB (settings de .env).
2. Hace seed idempotente: Despacho A + Usuario Ana + Membresía.
3. Inserta 2 expedientes de prueba directo en DB.
4. Override del AuthProvider con un fake (no necesita JWT real de Clerk).
5. Hits HTTP vía httpx.AsyncClient + ASGITransport.
6. Valida respuestas con asserts.
7. Limpia (deja todo seed para futuras corridas — idempotente).

Uso:
    # 1. levantar docker
    docker compose up -d
    # 2. correr migrations
    cd backend && uv run alembic upgrade head
    # 3. correr smoke test
    cd backend && uv run python -m scripts.smoke_test

Exit code 0 si todo pasa, 1 si algo falla. Útil para CI eventualmente.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from datetime import date
from uuid import UUID, uuid4

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from praxis.api.deps import get_auth_provider
from praxis.api.main import app as real_app
from praxis.application.ports import AuthProvider
from praxis.config import get_settings
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
    Rol,
    TipoExpediente,
    TramiteEvento,
    Usuario,
)
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyDespachoRepository,
    SqlAlchemyExpedienteRepository,
    SqlAlchemyMembresiaDespachoRepository,
    SqlAlchemyUsuarioRepository,
)


class _FakeAuth(AuthProvider):
    """AuthProvider de smoke test: lookup por token literal."""

    def __init__(self, tokens: dict[str, AuthClaims]) -> None:
        self._tokens = tokens

    async def verificar_token(self, token: str) -> AuthClaims:
        c = self._tokens.get(token)
        if c is None:
            raise AuthError(AuthErrorCode.INVALID_TOKEN, "unknown token (smoke fake)")
        return c


# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------


async def _seed_state(session: AsyncSession) -> dict[str, UUID]:
    """Idempotente: crea o reusa Despacho A + Usuario + Membresía + 2 expedientes."""
    despachos = SqlAlchemyDespachoRepository(session)
    usuarios = SqlAlchemyUsuarioRepository(session)
    membresias = SqlAlchemyMembresiaDespachoRepository(session)
    exp_repo = SqlAlchemyExpedienteRepository(session)

    # Despacho.
    todos = await despachos.listar()
    despacho = next((d for d in todos if d.nombre == "Smoke Test Despacho"), None)
    if despacho is None:
        despacho = await despachos.crear(Despacho(id=uuid4(), nombre="Smoke Test Despacho"))

    # Usuario.
    usuario = await usuarios.buscar_por_email("smoke@test.local")
    if usuario is None:
        usuario = await usuarios.crear(
            Usuario(
                id=uuid4(),
                email="smoke@test.local",
                nombre="Smoke Test User",
                auth_provider_id="user_smoke_test",
                activo=True,
            )
        )

    # Membresia.
    mem = await membresias.buscar(usuario_id=usuario.id, despacho_id=despacho.id)
    if mem is None:
        await membresias.agregar(
            MembresiaDespacho(
                usuario_id=usuario.id,
                despacho_id=despacho.id,
                rol=Rol.JEFE_ASESORES,
            )
        )

    # Expedientes: 2 si no existen.
    exp1 = await exp_repo.buscar_por_numero(NumeroExpediente.parse_hcdn("9001-D-2024"))
    if exp1 is None:
        exp1 = await exp_repo.crear(
            Expediente(
                numero=NumeroExpediente.parse_hcdn("9001-D-2024"),
                tipo=TipoExpediente.PROYECTO_LEY,
                titulo="Smoke Test Salud",
                sumario="Reforma sistema sanitario",
                fecha_ingreso=date(2024, 5, 1),
                estado=EstadoExpediente.EN_COMISION,
                firmantes=[Firmante(nombre="SMOKE TESTER", orden=1)],
                giros=[Giro(comision="ACCION SOCIAL Y SALUD PUBLICA")],
                tramite=[
                    TramiteEvento(
                        fecha=date(2024, 5, 5),
                        camara=Camara.HCDN,
                        evento="GIRO A COMISION",
                        fuente="smoke",
                    )
                ],
            )
        )

    exp2 = await exp_repo.buscar_por_numero(NumeroExpediente.parse_hcdn("9002-D-2024"))
    if exp2 is None:
        exp2 = await exp_repo.crear(
            Expediente(
                numero=NumeroExpediente.parse_hcdn("9002-D-2024"),
                tipo=TipoExpediente.PROYECTO_RESOLUCION,
                titulo="Smoke Test Cultura",
                estado=EstadoExpediente.INGRESADO,
            )
        )

    await session.commit()
    return {
        "despacho_id": despacho.id,
        "usuario_id": usuario.id,
        "expediente_1_id": exp1.id,
        "expediente_2_id": exp2.id,
    }


# ---------------------------------------------------------------------------
# Hits HTTP
# ---------------------------------------------------------------------------


async def _run_hits(state: dict[str, UUID]) -> int:
    """Hace los hits y devuelve cantidad de checks ejecutados.

    Lanza AssertionError si algo falla.
    """
    headers = {
        "Authorization": "Bearer smoke-token",
        "X-Despacho-Id": str(state["despacho_id"]),
    }

    transport = httpx.ASGITransport(app=real_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        checks = 0

        # 1) /me
        r = await client.get("/api/v1/me", headers=headers)
        assert r.status_code == 200, f"/me devolvió {r.status_code}: {r.text}"
        body = r.json()
        assert body["usuario"]["email"] == "smoke@test.local"
        assert body["despacho"]["nombre"] == "Smoke Test Despacho"
        assert body["rol"] == "jefe_asesores"
        print(
            f"  ✓ GET /me → {body['usuario']['nombre']} @ "
            f"{body['despacho']['nombre']} ({body['rol']})"
        )
        checks += 1

        # 2) GET /expedientes sin filtros
        r = await client.get("/api/v1/expedientes", headers=headers)
        assert r.status_code == 200, f"/expedientes devolvió {r.status_code}"
        body = r.json()
        assert body["total"] >= 2
        print(f"  ✓ GET /expedientes → {body['total']} expedientes")
        checks += 1

        # 3) GET /expedientes?texto=salud
        r = await client.get("/api/v1/expedientes", headers=headers, params={"texto": "salud"})
        assert r.status_code == 200
        body = r.json()
        assert body["total"] >= 1
        assert any("Salud" in e["titulo"] for e in body["items"])
        print(f"  ✓ GET /expedientes?texto=salud → {body['total']} matches")
        checks += 1

        # 4) GET /expedientes/{id}
        r = await client.get(f"/api/v1/expedientes/{state['expediente_1_id']}", headers=headers)
        assert r.status_code == 200, f"ficha devolvió {r.status_code}: {r.text}"
        body = r.json()
        assert body["titulo"] == "Smoke Test Salud"
        assert len(body["firmantes"]) == 1
        assert body["seguimiento"] is None  # todavía no marcamos
        print(f"  ✓ GET /expedientes/{{id}} → {body['titulo']}, sin seguimiento")
        checks += 1

        # 5) POST /seguimientos
        r = await client.post(
            "/api/v1/seguimientos",
            headers=headers,
            json={"expediente_id": str(state["expediente_1_id"]), "prioridad": "alta"},
        )
        assert r.status_code in (201, 409), f"POST seguimiento: {r.status_code}: {r.text}"
        if r.status_code == 201:
            seg_id = r.json()["id"]
            print(f"  ✓ POST /seguimientos → 201 (id={seg_id})")
        else:
            print("  ✓ POST /seguimientos → 409 (ya seguía, idempotente)")
        checks += 1

        # 6) GET ficha de nuevo: ahora con seguimiento embebido
        r = await client.get(f"/api/v1/expedientes/{state['expediente_1_id']}", headers=headers)
        body = r.json()
        assert body["seguimiento"] is not None
        assert body["seguimiento"]["prioridad"] == "alta"
        print(
            "  ✓ GET ficha re-check → seguimiento embebido con prioridad="
            f"{body['seguimiento']['prioridad']}"
        )
        checks += 1

        # 7) Auth: sin token
        r = await client.get("/api/v1/me")
        assert r.status_code == 401
        print("  ✓ Sin token → 401")
        checks += 1

        # 8) Auth: sin X-Despacho-Id
        r = await client.get("/api/v1/me", headers={"Authorization": "Bearer smoke-token"})
        assert r.status_code == 400
        print("  ✓ Sin X-Despacho-Id → 400")
        checks += 1

        # 9) Tenant isolation: despacho_id que no es membresía → 403
        otro_uuid = uuid4()
        r = await client.get(
            "/api/v1/me",
            headers={
                "Authorization": "Bearer smoke-token",
                "X-Despacho-Id": str(otro_uuid),
            },
        )
        assert r.status_code == 403
        print("  ✓ Despacho ajeno → 403 (tenant isolation)")
        checks += 1

        return checks


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> int:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url), echo=False)
    sm = async_sessionmaker(engine, expire_on_commit=False)

    print(f"[smoke] Conectando a {settings.database_url}")
    print()

    # 1. Seed.
    print("[smoke] Sembrando estado...")
    try:
        async with sm() as session:
            state = await _seed_state(session)
    except Exception as exc:
        print(f"  ✗ Seed falló: {exc!r}")
        await engine.dispose()
        return 1

    print(f"  → Despacho: {state['despacho_id']}")
    print(f"  → Usuario:  {state['usuario_id']}")
    print(f"  → Exp 1:    {state['expediente_1_id']}")
    print(f"  → Exp 2:    {state['expediente_2_id']}")
    print()

    # 2. Override del AuthProvider para no necesitar JWT real.
    real_app.dependency_overrides[get_auth_provider] = lambda: _FakeAuth(
        {"smoke-token": AuthClaims(sub="user_smoke_test", email="smoke@test.local")}
    )

    # 3. Hits.
    print("[smoke] Ejecutando hits HTTP...")
    try:
        checks = await _run_hits(state)
    except AssertionError as exc:
        print(f"  ✗ ASSERT FALLÓ: {exc}")
        return 1
    except Exception as exc:
        print(f"  ✗ EXCEPCIÓN: {exc!r}")
        return 1
    finally:
        real_app.dependency_overrides.clear()
        await engine.dispose()

    print()
    print("=" * 60)
    print(f"  ✓ Smoke test OK — {checks} checks pasaron")
    print("=" * 60)
    return 0


def _wrap_iterator() -> AsyncIterator[None]:  # pragma: no cover - solo silencia mypy
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
