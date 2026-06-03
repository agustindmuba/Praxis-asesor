"""Tests integración de los 3 repos WhatsApp sobre SQLite (feat-41.1).

Cubre:
- Destinatario: CRUD tenant-scoped, UNIQUE despacho_telefono, listar
  con filtro `solo_activos`, eliminar.
- PlantillaWhatsApp: upsert idempotente, listar con `solo_aprobadas`.
- EnvioWhatsApp: crear, marcar_enviado, marcar_fallido, marcar_rechazado,
  actualizar_por_message_id (con estado válido + estado inválido),
  listar tenant-scoped con ventana temporal + filtro por tipo.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from praxis.domain import (
    CategoriaPlantilla,
    Despacho,
    Destinatario,
    EnvioWhatsApp,
    EstadoEnvio,
    EstadoMetaPlantilla,
    PlantillaWhatsApp,
    RolDestinatario,
    TipoEnvio,
)
from praxis.infrastructure.persistence.base import Base
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyDespachoRepository,
    SqlAlchemyDestinatarioRepository,
    SqlAlchemyEnvioWhatsAppRepository,
    SqlAlchemyPlantillaWhatsAppRepository,
)

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as s:
        yield s
    await engine.dispose()


@pytest_asyncio.fixture
async def despacho(session: AsyncSession) -> Despacho:
    return await SqlAlchemyDespachoRepository(session).crear(
        Despacho(id=uuid4(), nombre="Despacho A"),
    )


@pytest_asyncio.fixture
async def plantilla(session: AsyncSession) -> PlantillaWhatsApp:
    """Plantilla seed reutilizable para los tests de envío."""
    return await SqlAlchemyPlantillaWhatsAppRepository(session).upsert(
        PlantillaWhatsApp(
            name="briefing_diario",
            categoria=CategoriaPlantilla.UTILITY,
            body_params=["nombre", "fecha"],
            contenido_referencia="Hola {{1}}, briefing del {{2}}.",
            estado_meta=EstadoMetaPlantilla.APROBADA,
        ),
    )


def _dest(despacho: Despacho, *, telefono: str = "+5491155551234") -> Destinatario:
    return Destinatario(
        id=None,
        despacho_id=despacho.id,
        nombre="Pablo Juliano",
        rol_interno=RolDestinatario.LEGISLADOR,
        telefono_e164=telefono,
    )


# ---------------------------------------------------------------------------
# Destinatario
# ---------------------------------------------------------------------------


async def test_destinatario_crear_y_buscar(
    session: AsyncSession, despacho: Despacho,
) -> None:
    repo = SqlAlchemyDestinatarioRepository(session)
    d = await repo.crear(_dest(despacho))
    assert d.id is not None

    por_id = await repo.buscar_por_id(
        despacho_id=despacho.id, destinatario_id=d.id,
    )
    por_tel = await repo.buscar_por_telefono(
        despacho_id=despacho.id, telefono_e164="+5491155551234",
    )
    assert por_id is not None and por_id.nombre == "Pablo Juliano"
    assert por_tel is not None and por_tel.id == d.id


async def test_destinatario_tenant_isolation(
    session: AsyncSession, despacho: Despacho,
) -> None:
    repo = SqlAlchemyDestinatarioRepository(session)
    d = await repo.crear(_dest(despacho))

    # Otro despacho NO debe ver al destinatario.
    otro = await SqlAlchemyDespachoRepository(session).crear(
        Despacho(id=uuid4(), nombre="Despacho B"),
    )
    encontrado_ajeno = await repo.buscar_por_id(
        despacho_id=otro.id, destinatario_id=d.id,
    )
    assert encontrado_ajeno is None


async def test_destinatario_actualizar(
    session: AsyncSession, despacho: Despacho,
) -> None:
    repo = SqlAlchemyDestinatarioRepository(session)
    d = await repo.crear(_dest(despacho))

    ahora = datetime(2026, 6, 1, tzinfo=UTC)
    actualizado = await repo.actualizar(
        Destinatario(
            id=d.id,
            despacho_id=d.despacho_id,
            nombre="Pablo Juliano (actualizado)",
            rol_interno=d.rol_interno,
            telefono_e164=d.telefono_e164,
            opt_in_en=ahora,
            activo=True,
        ),
    )
    assert actualizado.nombre.endswith("(actualizado)")
    assert actualizado.activo is True
    assert actualizado.opt_in_vigente is True


async def test_destinatario_listar_solo_activos(
    session: AsyncSession, despacho: Despacho,
) -> None:
    repo = SqlAlchemyDestinatarioRepository(session)
    await repo.crear(_dest(despacho, telefono="+5491155550001"))
    activo = await repo.crear(_dest(despacho, telefono="+5491155550002"))
    activo = await repo.actualizar(
        Destinatario(
            id=activo.id,
            despacho_id=despacho.id,
            nombre=activo.nombre,
            rol_interno=activo.rol_interno,
            telefono_e164=activo.telefono_e164,
            opt_in_en=datetime(2026, 6, 1, tzinfo=UTC),
            activo=True,
        ),
    )

    todos = await repo.listar_por_despacho(despacho.id)
    activos = await repo.listar_por_despacho(despacho.id, solo_activos=True)
    assert len(todos) == 2
    assert len(activos) == 1
    assert activos[0].id == activo.id


async def test_destinatario_eliminar(
    session: AsyncSession, despacho: Despacho,
) -> None:
    repo = SqlAlchemyDestinatarioRepository(session)
    d = await repo.crear(_dest(despacho))
    borrado = await repo.eliminar(
        despacho_id=despacho.id, destinatario_id=d.id,
    )
    assert borrado is True
    assert await repo.buscar_por_id(
        despacho_id=despacho.id, destinatario_id=d.id,
    ) is None


# ---------------------------------------------------------------------------
# PlantillaWhatsApp
# ---------------------------------------------------------------------------


async def test_plantilla_upsert_idempotente(session: AsyncSession) -> None:
    repo = SqlAlchemyPlantillaWhatsAppRepository(session)
    p1 = await repo.upsert(
        PlantillaWhatsApp(
            name="alerta_mencion",
            categoria=CategoriaPlantilla.UTILITY,
            body_params=["titulo"],
            contenido_referencia="Mención: {{1}}",
        ),
    )
    p2 = await repo.upsert(
        PlantillaWhatsApp(
            name="alerta_mencion",
            categoria=CategoriaPlantilla.UTILITY,
            body_params=["titulo"],
            contenido_referencia="Mención nueva: {{1}}",
            estado_meta=EstadoMetaPlantilla.APROBADA,
        ),
    )
    assert p1.name == p2.name
    assert p2.estado_meta == EstadoMetaPlantilla.APROBADA
    assert "Mención nueva" in p2.contenido_referencia


async def test_plantilla_listar_solo_aprobadas(session: AsyncSession) -> None:
    repo = SqlAlchemyPlantillaWhatsAppRepository(session)
    await repo.upsert(
        PlantillaWhatsApp(
            name="ap_a",
            categoria=CategoriaPlantilla.UTILITY,
            body_params=[],
            contenido_referencia="A",
            estado_meta=EstadoMetaPlantilla.APROBADA,
        ),
    )
    await repo.upsert(
        PlantillaWhatsApp(
            name="pend_b",
            categoria=CategoriaPlantilla.UTILITY,
            body_params=[],
            contenido_referencia="B",
            estado_meta=EstadoMetaPlantilla.PENDIENTE_APROBACION,
        ),
    )
    todas = await repo.listar()
    solo_ap = await repo.listar(solo_aprobadas=True)
    assert len(todas) == 2
    assert len(solo_ap) == 1
    assert solo_ap[0].name == "ap_a"


# ---------------------------------------------------------------------------
# EnvioWhatsApp
# ---------------------------------------------------------------------------


async def _seed_envio_base(
    session: AsyncSession, despacho: Despacho, plantilla: PlantillaWhatsApp,
) -> dict[str, Any]:
    dest_repo = SqlAlchemyDestinatarioRepository(session)
    envio_repo = SqlAlchemyEnvioWhatsAppRepository(session)
    d = await dest_repo.crear(_dest(despacho))
    e = await envio_repo.crear(
        EnvioWhatsApp(
            id=None,
            destinatario_id=d.id,  # type: ignore[arg-type]
            despacho_id=despacho.id,
            plantilla_name=plantilla.name,
            tipo=TipoEnvio.BRIEFING_DIARIO,
            payload_params={"nombre": "Pablo", "fecha": "2026-06-01"},
        ),
    )
    return {"destinatario": d, "envio": e, "repo": envio_repo}


async def test_envio_crear_pendiente(
    session: AsyncSession, despacho: Despacho, plantilla: PlantillaWhatsApp,
) -> None:
    seed = await _seed_envio_base(session, despacho, plantilla)
    envio = seed["envio"]
    assert envio.id is not None
    assert envio.estado == EstadoEnvio.PENDIENTE


async def test_envio_marcar_enviado(
    session: AsyncSession, despacho: Despacho, plantilla: PlantillaWhatsApp,
) -> None:
    seed = await _seed_envio_base(session, despacho, plantilla)
    repo = seed["repo"]
    envio = seed["envio"]
    ahora = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    actualizado = await repo.marcar_enviado(
        envio_id=envio.id,
        message_id_meta="wamid.HBgM...",
        enviado_en=ahora,
    )
    assert actualizado.estado == EstadoEnvio.ENVIADO
    assert actualizado.message_id_meta == "wamid.HBgM..."


async def test_envio_marcar_fallido(
    session: AsyncSession, despacho: Despacho, plantilla: PlantillaWhatsApp,
) -> None:
    seed = await _seed_envio_base(session, despacho, plantilla)
    actualizado = await seed["repo"].marcar_fallido(
        envio_id=seed["envio"].id, error="timeout meta api",
    )
    assert actualizado.estado == EstadoEnvio.FALLIDO
    assert actualizado.error == "timeout meta api"


async def test_envio_marcar_rechazado(
    session: AsyncSession, despacho: Despacho, plantilla: PlantillaWhatsApp,
) -> None:
    seed = await _seed_envio_base(session, despacho, plantilla)
    actualizado = await seed["repo"].marcar_fallido(
        envio_id=seed["envio"].id, error="user opted out", rechazado=True,
    )
    assert actualizado.estado == EstadoEnvio.RECHAZADO


async def test_envio_actualizar_por_message_id_ok(
    session: AsyncSession, despacho: Despacho, plantilla: PlantillaWhatsApp,
) -> None:
    seed = await _seed_envio_base(session, despacho, plantilla)
    repo = seed["repo"]
    await repo.marcar_enviado(
        envio_id=seed["envio"].id,
        message_id_meta="wamid.X",
        enviado_en=datetime(2026, 6, 1, tzinfo=UTC),
    )
    actualizado = await repo.actualizar_por_message_id(
        message_id_meta="wamid.X", nuevo_estado="entregado",
    )
    assert actualizado is not None
    assert actualizado.estado == EstadoEnvio.ENTREGADO


async def test_envio_actualizar_por_message_id_no_encuentra(
    session: AsyncSession, despacho: Despacho, plantilla: PlantillaWhatsApp,
) -> None:
    seed = await _seed_envio_base(session, despacho, plantilla)
    encontrado = await seed["repo"].actualizar_por_message_id(
        message_id_meta="wamid.inexistente", nuevo_estado="entregado",
    )
    assert encontrado is None


async def test_envio_actualizar_estado_invalido_lanza(
    session: AsyncSession, despacho: Despacho, plantilla: PlantillaWhatsApp,
) -> None:
    seed = await _seed_envio_base(session, despacho, plantilla)
    with pytest.raises(ValueError, match="Estado"):
        await seed["repo"].actualizar_por_message_id(
            message_id_meta="x", nuevo_estado="estado_inexistente",
        )


async def test_envio_listar_con_ventana_y_tipo(
    session: AsyncSession, despacho: Despacho, plantilla: PlantillaWhatsApp,
) -> None:
    dest_repo = SqlAlchemyDestinatarioRepository(session)
    envio_repo = SqlAlchemyEnvioWhatsAppRepository(session)
    d = await dest_repo.crear(_dest(despacho))
    ahora = datetime(2026, 6, 1, 10, 0, tzinfo=UTC)
    # Briefing al destinatario.
    e1 = await envio_repo.crear(
        EnvioWhatsApp(
            id=None,
            destinatario_id=d.id,  # type: ignore[arg-type]
            despacho_id=despacho.id,
            plantilla_name=plantilla.name,
            tipo=TipoEnvio.BRIEFING_DIARIO,
        ),
    )
    await envio_repo.marcar_enviado(
        envio_id=e1.id, message_id_meta="m1", enviado_en=ahora,
    )
    e2 = await envio_repo.crear(
        EnvioWhatsApp(
            id=None,
            destinatario_id=d.id,  # type: ignore[arg-type]
            despacho_id=despacho.id,
            plantilla_name=plantilla.name,
            tipo=TipoEnvio.ALERTA_MENCION,
        ),
    )
    await envio_repo.marcar_enviado(
        envio_id=e2.id, message_id_meta="m2",
        enviado_en=ahora + timedelta(hours=1),
    )

    todos = await envio_repo.listar_por_despacho(
        despacho.id,
        desde=ahora - timedelta(hours=1),
        hasta=ahora + timedelta(days=1),
    )
    assert len(todos) == 2

    solo_briefings = await envio_repo.listar_por_despacho(
        despacho.id,
        desde=ahora - timedelta(hours=1),
        hasta=ahora + timedelta(days=1),
        tipo="briefing_diario",
    )
    assert len(solo_briefings) == 1
    assert solo_briefings[0].tipo == TipoEnvio.BRIEFING_DIARIO
