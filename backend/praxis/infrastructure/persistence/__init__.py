"""Capa de persistencia con SQLAlchemy 2.0 async.

Implementa los puertos de repositorio definidos en `praxis.application.ports`.
Ver `docs/adr/0003-persistencia.md`.
"""

from praxis.infrastructure.persistence.base import Base, TenantScopedMixin, uuid7

__all__ = ["Base", "TenantScopedMixin", "uuid7"]
