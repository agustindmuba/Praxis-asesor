"""Repositorio de Usuario sobre SQLAlchemy async."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from praxis.application.ports import UsuarioRepository
from praxis.domain import Usuario
from praxis.infrastructure.persistence.mappers import from_usuario, to_usuario
from praxis.infrastructure.persistence.models import UsuarioOrm


class SqlAlchemyUsuarioRepository(UsuarioRepository):
    """Persistencia de Usuario."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def crear(self, usuario: Usuario) -> Usuario:
        orm = from_usuario(usuario)
        self._session.add(orm)
        await self._session.flush()
        return to_usuario(orm)

    async def buscar_por_id(self, usuario_id: UUID) -> Usuario | None:
        orm = await self._session.get(UsuarioOrm, usuario_id)
        return to_usuario(orm) if orm is not None else None

    async def buscar_por_email(self, email: str) -> Usuario | None:
        stmt = select(UsuarioOrm).where(UsuarioOrm.email == email.strip().lower())
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        return to_usuario(orm) if orm is not None else None

    async def buscar_por_auth_provider_id(self, auth_provider_id: str) -> Usuario | None:
        stmt = select(UsuarioOrm).where(UsuarioOrm.auth_provider_id == auth_provider_id)
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        return to_usuario(orm) if orm is not None else None

    async def listar(self) -> list[Usuario]:
        result = await self._session.execute(select(UsuarioOrm).order_by(UsuarioOrm.email))
        return [to_usuario(orm) for orm in result.scalars()]

    async def actualizar(self, usuario: Usuario) -> Usuario:
        """Actualiza email/nombre/auth_provider_id/activo por id.

        No usa `merge()` para que sea explícito qué campos pisamos. El email
        se normaliza igual que en crear (strip + lower).
        """
        # Usamos select() en lugar de session.get() porque este último
        # tiene comportamiento problemático con aiosqlite cuando la session
        # se reusa entre requests del mismo test (load_on_pk_identity rompe
        # el contexto greenlet).
        stmt = select(UsuarioOrm).where(UsuarioOrm.id == usuario.id)
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        if orm is None:
            raise ValueError(f"Usuario {usuario.id} no existe")
        orm.email = usuario.email.strip().lower()
        orm.nombre = usuario.nombre
        orm.auth_provider_id = usuario.auth_provider_id
        orm.activo = usuario.activo
        await self._session.flush()
        return to_usuario(orm)
