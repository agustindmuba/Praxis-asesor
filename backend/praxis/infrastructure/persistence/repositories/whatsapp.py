"""Repositorios SQLAlchemy para WhatsApp (spec 17, feat-41.1).

Tres repos en un archivo:

- `SqlAlchemyDestinatarioRepository`: tenant-scoped. CRUD por
  `(despacho_id, telefono_e164)` UNIQUE.
- `SqlAlchemyPlantillaWhatsAppRepository`: catálogo global por `name`
  PK. UPSERT idempotente (sync con Meta).
- `SqlAlchemyEnvioWhatsAppRepository`: registro auditable tenant-scoped.
  El sender (feat-41.2) crea con estado=PENDIENTE, después llama
  `marcar_enviado`/`marcar_fallido`. Webhooks de status (feat-41.3)
  usan `actualizar_por_message_id`.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from praxis.application.ports import (
    DestinatarioRepository,
    EnvioWhatsAppRepository,
    PlantillaWhatsAppRepository,
)
from praxis.domain import (
    Destinatario,
    EnvioWhatsApp,
    EstadoEnvio,
    PlantillaWhatsApp,
)
from praxis.infrastructure.persistence.mappers import (
    from_destinatario,
    from_envio_whatsapp,
    from_plantilla_whatsapp,
    to_destinatario,
    to_envio_whatsapp,
    to_plantilla_whatsapp,
)
from praxis.infrastructure.persistence.models import (
    DestinatarioOrm,
    EnvioWhatsAppOrm,
    PlantillaWhatsAppOrm,
)

# ---------------------------------------------------------------------------
# Destinatario
# ---------------------------------------------------------------------------


class SqlAlchemyDestinatarioRepository(DestinatarioRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def crear(self, dest: Destinatario) -> Destinatario:
        orm = from_destinatario(dest)
        self._session.add(orm)
        await self._session.flush()
        return to_destinatario(orm)

    async def actualizar(self, dest: Destinatario) -> Destinatario:
        if dest.id is None:
            raise ValueError("Destinatario.id requerido para actualizar")
        stmt = (
            update(DestinatarioOrm)
            .where(DestinatarioOrm.id == dest.id)
            .values(
                nombre=dest.nombre,
                rol_interno=dest.rol_interno.value,
                telefono_e164=dest.telefono_e164,
                usuario_id=dest.usuario_id,
                recibe_briefing_diario=dest.recibe_briefing_diario,
                recibe_alertas_menciones=dest.recibe_alertas_menciones,
                recibe_alertas_otras=dest.recibe_alertas_otras,
                opt_in_en=dest.opt_in_en,
                opt_out_en=dest.opt_out_en,
                activo=dest.activo,
            )
        )
        result = await self._session.execute(stmt)
        if result.rowcount == 0:  # type: ignore[attr-defined]
            raise ValueError(f"Destinatario {dest.id} no existe")
        await self._session.flush()
        actualizado = await self.buscar_por_id(
            despacho_id=dest.despacho_id, destinatario_id=dest.id,
        )
        assert actualizado is not None
        return actualizado

    async def buscar_por_id(
        self, *, despacho_id: UUID, destinatario_id: UUID,
    ) -> Destinatario | None:
        stmt = select(DestinatarioOrm).where(
            DestinatarioOrm.id == destinatario_id,
            DestinatarioOrm.despacho_id == despacho_id,
        )
        orm = (await self._session.execute(stmt)).scalar_one_or_none()
        return to_destinatario(orm) if orm else None

    async def buscar_por_telefono(
        self, *, despacho_id: UUID, telefono_e164: str,
    ) -> Destinatario | None:
        stmt = select(DestinatarioOrm).where(
            DestinatarioOrm.despacho_id == despacho_id,
            DestinatarioOrm.telefono_e164 == telefono_e164,
        )
        orm = (await self._session.execute(stmt)).scalar_one_or_none()
        return to_destinatario(orm) if orm else None

    async def listar_por_despacho(
        self,
        despacho_id: UUID,
        *,
        solo_activos: bool = False,
    ) -> list[Destinatario]:
        stmt = (
            select(DestinatarioOrm)
            .where(DestinatarioOrm.despacho_id == despacho_id)
            .order_by(DestinatarioOrm.nombre)
        )
        if solo_activos:
            stmt = stmt.where(DestinatarioOrm.activo.is_(True))
        result = await self._session.execute(stmt)
        return [to_destinatario(r) for r in result.scalars().all()]

    async def eliminar(
        self, *, despacho_id: UUID, destinatario_id: UUID,
    ) -> bool:
        from sqlalchemy import delete
        stmt = delete(DestinatarioOrm).where(
            DestinatarioOrm.id == destinatario_id,
            DestinatarioOrm.despacho_id == despacho_id,
        )
        result = await self._session.execute(stmt)
        return result.rowcount > 0  # type: ignore[attr-defined,no-any-return]


# ---------------------------------------------------------------------------
# PlantillaWhatsApp
# ---------------------------------------------------------------------------


class SqlAlchemyPlantillaWhatsAppRepository(PlantillaWhatsAppRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, plantilla: PlantillaWhatsApp) -> PlantillaWhatsApp:
        existente = await self.buscar_por_name(plantilla.name)
        if existente is None:
            orm = from_plantilla_whatsapp(plantilla)
            self._session.add(orm)
            await self._session.flush()
            return to_plantilla_whatsapp(orm)
        # Update mutable fields.
        stmt = (
            update(PlantillaWhatsAppOrm)
            .where(PlantillaWhatsAppOrm.name == plantilla.name)
            .values(
                idioma=plantilla.idioma,
                categoria=plantilla.categoria.value,
                body_params=list(plantilla.body_params),
                estado_meta=plantilla.estado_meta.value,
                aprobada_en=plantilla.aprobada_en,
                contenido_referencia=plantilla.contenido_referencia,
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()
        actualizada = await self.buscar_por_name(plantilla.name)
        assert actualizada is not None
        return actualizada

    async def buscar_por_name(self, name: str) -> PlantillaWhatsApp | None:
        stmt = select(PlantillaWhatsAppOrm).where(
            PlantillaWhatsAppOrm.name == name,
        )
        orm = (await self._session.execute(stmt)).scalar_one_or_none()
        return to_plantilla_whatsapp(orm) if orm else None

    async def listar(
        self, *, solo_aprobadas: bool = False,
    ) -> list[PlantillaWhatsApp]:
        stmt = select(PlantillaWhatsAppOrm).order_by(PlantillaWhatsAppOrm.name)
        if solo_aprobadas:
            stmt = stmt.where(PlantillaWhatsAppOrm.estado_meta == "aprobada")
        result = await self._session.execute(stmt)
        return [to_plantilla_whatsapp(r) for r in result.scalars().all()]


# ---------------------------------------------------------------------------
# EnvioWhatsApp
# ---------------------------------------------------------------------------


class SqlAlchemyEnvioWhatsAppRepository(EnvioWhatsAppRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def crear(self, envio: EnvioWhatsApp) -> EnvioWhatsApp:
        orm = from_envio_whatsapp(envio)
        self._session.add(orm)
        await self._session.flush()
        return to_envio_whatsapp(orm)

    async def marcar_enviado(
        self, *, envio_id: UUID, message_id_meta: str, enviado_en: datetime,
    ) -> EnvioWhatsApp:
        stmt = (
            update(EnvioWhatsAppOrm)
            .where(EnvioWhatsAppOrm.id == envio_id)
            .values(
                estado=EstadoEnvio.ENVIADO.value,
                message_id_meta=message_id_meta,
                enviado_en=enviado_en,
                error=None,
            )
        )
        result = await self._session.execute(stmt)
        if result.rowcount == 0:  # type: ignore[attr-defined]
            raise ValueError(f"Envio {envio_id} no existe")
        await self._session.flush()
        return await self._fetch_or_raise(envio_id)

    async def marcar_fallido(
        self, *, envio_id: UUID, error: str, rechazado: bool = False,
    ) -> EnvioWhatsApp:
        estado = EstadoEnvio.RECHAZADO if rechazado else EstadoEnvio.FALLIDO
        stmt = (
            update(EnvioWhatsAppOrm)
            .where(EnvioWhatsAppOrm.id == envio_id)
            .values(estado=estado.value, error=error)
        )
        result = await self._session.execute(stmt)
        if result.rowcount == 0:  # type: ignore[attr-defined]
            raise ValueError(f"Envio {envio_id} no existe")
        await self._session.flush()
        return await self._fetch_or_raise(envio_id)

    async def actualizar_por_message_id(
        self,
        *,
        message_id_meta: str,
        nuevo_estado: str,
        error: str | None = None,
    ) -> EnvioWhatsApp | None:
        # Validar contra el enum del dominio antes de tocar la DB.
        try:
            EstadoEnvio(nuevo_estado)
        except ValueError as exc:
            raise ValueError(
                f"Estado '{nuevo_estado}' no es válido. "
                f"Válidos: {[e.value for e in EstadoEnvio]}",
            ) from exc
        stmt = (
            update(EnvioWhatsAppOrm)
            .where(EnvioWhatsAppOrm.message_id_meta == message_id_meta)
            .values(estado=nuevo_estado, error=error)
        )
        result = await self._session.execute(stmt)
        if result.rowcount == 0:  # type: ignore[attr-defined]
            return None
        await self._session.flush()
        stmt_q = select(EnvioWhatsAppOrm).where(
            EnvioWhatsAppOrm.message_id_meta == message_id_meta,
        )
        orm = (await self._session.execute(stmt_q)).scalar_one_or_none()
        return to_envio_whatsapp(orm) if orm else None

    async def listar_por_despacho(
        self,
        despacho_id: UUID,
        *,
        desde: datetime,
        hasta: datetime,
        tipo: str | None = None,
    ) -> list[EnvioWhatsApp]:
        stmt = (
            select(EnvioWhatsAppOrm)
            .where(
                EnvioWhatsAppOrm.despacho_id == despacho_id,
                EnvioWhatsAppOrm.enviado_en >= desde,
                EnvioWhatsAppOrm.enviado_en <= hasta,
            )
            .order_by(EnvioWhatsAppOrm.enviado_en.desc())
        )
        if tipo is not None:
            stmt = stmt.where(EnvioWhatsAppOrm.tipo == tipo)
        result = await self._session.execute(stmt)
        return [to_envio_whatsapp(r) for r in result.scalars().all()]

    async def _fetch_or_raise(self, envio_id: UUID) -> EnvioWhatsApp:
        stmt = select(EnvioWhatsAppOrm).where(EnvioWhatsAppOrm.id == envio_id)
        orm = (await self._session.execute(stmt)).scalar_one_or_none()
        if orm is None:
            raise ValueError(f"Envio {envio_id} no existe")
        return to_envio_whatsapp(orm)
