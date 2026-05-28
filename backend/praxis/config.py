"""Configuración tipada de la aplicación (pydantic-settings v2).

Lee variables de entorno y un archivo `.env` (no versionado).
La instancia se obtiene vía `get_settings()`, cacheada por proceso.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings de Praxis Asesor backend.

    Carga, en orden de precedencia:
      1. Variables de entorno del proceso.
      2. Archivo `.env` en el directorio de trabajo.
      3. Defaults definidos abajo.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="forbid",
    )

    # --- Entorno ---
    env: Literal["dev", "staging", "prod"] = Field(
        default="dev",
        description="Entorno de ejecución; gobierna defaults de logging, debug, etc.",
    )

    # --- Persistencia ---
    database_url: PostgresDsn = Field(
        description=(
            "DSN Postgres async. Ejemplo: postgresql+asyncpg://praxis:praxis@localhost:5432/praxis"
        ),
    )

    # --- Cola / broker ---
    redis_url: RedisDsn = Field(
        description="DSN Redis usado por Celery (broker + result backend) y cache.",
    )

    # --- IA ---
    anthropic_api_key: str | None = Field(
        default=None,
        description="API key de Anthropic. Requerida solo para features de IA (v3+).",
    )

    # --- Auth (Clerk) ---
    # Ver docs/specs/09-auth-multitenancy.md. Si está vacío, la app arranca pero
    # los endpoints protegidos van a fallar; útil para tests o flows internos.
    clerk_issuer: str | None = Field(
        default=None,
        description="Issuer esperado del JWT (Clerk frontend API URL).",
    )
    clerk_jwks_url: str | None = Field(
        default=None,
        description="URL del JWKS de Clerk (.well-known/jwks.json).",
    )
    clerk_audience: str | None = Field(
        default=None,
        description="`aud` esperado, si Clerk lo configura.",
    )

    # --- Logging ---
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Nivel de logging global.",
    )

    @property
    def is_dev(self) -> bool:
        return self.env == "dev"

    @property
    def is_prod(self) -> bool:
        return self.env == "prod"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Devuelve la instancia única de Settings.

    Cacheada con `lru_cache` para evitar releer `.env` en cada acceso.
    En tests, usar `get_settings.cache_clear()` antes de override.
    """
    return Settings()  # type: ignore[call-arg]  # los campos requeridos vienen del env
