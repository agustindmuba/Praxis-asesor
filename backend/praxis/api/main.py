"""Punto de entrada HTTP del backend Praxis Asesor.

Define la instancia de FastAPI, monta routers y expone health checks.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import redis.asyncio as aioredis
import structlog
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from praxis import __version__
from praxis.config import get_settings
from praxis.infrastructure.db.engine import engine

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Hooks de arranque/apagado del proceso."""
    settings = get_settings()
    log.info("praxis.startup", env=settings.env, version=__version__)
    yield
    log.info("praxis.shutdown")


app = FastAPI(
    title="Praxis Asesor — Backend",
    version=__version__,
    description=(
        "API HTTP del backend de Praxis Asesor. Documentación interactiva en "
        "`/docs` (Swagger) y `/redoc`."
    ),
    lifespan=lifespan,
)


# -----------------------------------------------------------------------------
# CORS
# -----------------------------------------------------------------------------
# Necesario para que el frontend (Next.js en :3000 en dev, dominio real en
# prod) pueda hablarle al backend. Lista permitida en `Settings.cors_origins`.
#
# Si la lista está vacía, no agregamos el middleware → todas las requests
# cross-origin fallan en el navegador (comportamiento esperado para tests
# unitarios y para entornos donde no hay frontend separado).
_cors_origins = get_settings().cors_origins
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Despacho-Id",
            # Headers que Clerk puede mandar en algunos flows:
            "Svix-Id",
            "Svix-Timestamp",
            "Svix-Signature",
        ],
        expose_headers=["X-Despacho-Id"],
        max_age=600,  # cachea preflight 10 min.
    )


# -----------------------------------------------------------------------------
# Health checks
# -----------------------------------------------------------------------------


@app.get("/health", tags=["health"], summary="Liveness probe")
async def health() -> dict[str, str]:
    """Liveness: el proceso está vivo y respondiendo HTTP.

    No chequea dependencias externas; pensado para que el orquestador
    (Railway, Kubernetes, etc.) decida si reiniciar el contenedor.
    """
    return {"status": "ok", "version": __version__}


@app.get("/ready", tags=["health"], summary="Readiness probe")
async def ready() -> JSONResponse:
    """Readiness: la app puede atender requests reales.

    Verifica conectividad con Postgres y Redis. Si alguno falla, devuelve
    503 con detalle por componente. Pensado para que el LB no rutee tráfico
    a una réplica que todavía no está lista.
    """
    settings = get_settings()
    checks: dict[str, dict[str, str]] = {}

    # Postgres.
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = {"status": "ok"}
    except Exception as exc:
        checks["database"] = {"status": "error", "detail": str(exc)}

    # Redis.
    redis_client = aioredis.from_url(str(settings.redis_url))  # type: ignore[no-untyped-call]
    try:
        pong = await redis_client.ping()
        checks["redis"] = {
            "status": "ok" if pong else "error",
            "detail": "" if pong else "ping=false",
        }
    except Exception as exc:
        checks["redis"] = {"status": "error", "detail": str(exc)}
    finally:
        await redis_client.aclose()

    all_ok = all(c["status"] == "ok" for c in checks.values())
    return JSONResponse(
        status_code=status.HTTP_200_OK if all_ok else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "status": "ok" if all_ok else "degraded",
            "version": __version__,
            "checks": checks,
        },
    )


# -----------------------------------------------------------------------------
# Routers de feature
# -----------------------------------------------------------------------------

from praxis.api.routers import auth as auth_router  # noqa: E402
from praxis.api.routers import bo as bo_router  # noqa: E402
from praxis.api.routers import briefings as briefings_router  # noqa: E402
from praxis.api.routers import expedientes as expedientes_router  # noqa: E402
from praxis.api.routers import noticias as noticias_router  # noqa: E402
from praxis.api.routers import seguimientos as seguimientos_router  # noqa: E402
from praxis.api.routers import webhooks as webhooks_router  # noqa: E402
from praxis.api.routers import webhooks_whatsapp as webhooks_whatsapp_router  # noqa: E402
from praxis.api.routers import whatsapp as whatsapp_router  # noqa: E402
from praxis.api.routers import perfil_opositor as perfil_opositor_router  # noqa: E402
from praxis.api.routers import accionables as accionables_router  # noqa: E402
from praxis.api.routers import briefing_diario as briefing_diario_router  # noqa: E402
from praxis.api.routers import hub_diario as hub_diario_router  # noqa: E402
from praxis.api.routers import proyectos_redaccion as proyectos_redaccion_router  # noqa: E402
from praxis.api.routers import normativa as normativa_router  # noqa: E402
from praxis.api.routers import legislador_titular as legislador_titular_router  # noqa: E402
from praxis.api.routers import onboarding as onboarding_router  # noqa: E402

API_V1 = "/api/v1"
app.include_router(auth_router.router, prefix=API_V1)
app.include_router(expedientes_router.router, prefix=API_V1)
app.include_router(seguimientos_router.router, prefix=API_V1)
app.include_router(webhooks_router.router, prefix=API_V1)
app.include_router(briefings_router.router_ordenes, prefix=API_V1)
app.include_router(briefings_router.router_briefings, prefix=API_V1)
app.include_router(bo_router.router, prefix=API_V1)
app.include_router(noticias_router.router_noticias, prefix=API_V1)
app.include_router(noticias_router.router_menciones, prefix=API_V1)
app.include_router(noticias_router.router_fuentes, prefix=API_V1)
app.include_router(webhooks_whatsapp_router.router, prefix=API_V1)
app.include_router(whatsapp_router.router_destinatarios, prefix=API_V1)
app.include_router(whatsapp_router.router_envios, prefix=API_V1)
app.include_router(whatsapp_router.router_plantillas, prefix=API_V1)
app.include_router(perfil_opositor_router.router, prefix=API_V1)
app.include_router(accionables_router.router, prefix=API_V1)
app.include_router(briefing_diario_router.router, prefix=API_V1)
app.include_router(hub_diario_router.router, prefix=API_V1)
app.include_router(proyectos_redaccion_router.router, prefix=API_V1)
app.include_router(normativa_router.router, prefix=API_V1)
app.include_router(normativa_router.router_validar, prefix=API_V1)
app.include_router(legislador_titular_router.router, prefix=API_V1)
app.include_router(onboarding_router.router, prefix=API_V1)


# -----------------------------------------------------------------------------
# CLI helper: levantar dev server sin invocar uvicorn directo.
# -----------------------------------------------------------------------------


def run_dev() -> Any:
    """Atajo para `uv run python -m praxis.api.main` durante desarrollo."""
    import uvicorn

    uvicorn.run(
        "praxis.api.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level=get_settings().log_level.lower(),
    )


if __name__ == "__main__":
    run_dev()

