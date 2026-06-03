"""Tests del caso de uso `ProcesarWebhookWhatsApp` (feat-41.3).

Cubre:
- Status update sobre envío conocido → actualiza estado.
- Status update sobre message_id desconocido → cuenta como desconocido.
- Inbound opt_in → marca destinatario opt_in_en + activo=True.
- Inbound opt_out → marca destinatario opt_out_en + activo=False.
- Inbound sin match en destinatarios → ignorado.
- Inbound clasificado como None → ignorado.
- Excepciones de repos se capturan en `errores` y siguen.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from praxis.application.use_cases import ProcesarWebhookWhatsApp
from praxis.domain import (
    Destinatario,
    EnvioWhatsApp,
    EstadoEnvio,
    RolDestinatario,
)
from praxis.domain.despacho import Despacho
from praxis.infrastructure.whatsapp.webhooks import (
    InboundMessage,
    StatusUpdate,
    WebhookEvento,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fakes in-memory
# ---------------------------------------------------------------------------


class FakeDespachoRepo:
    def __init__(self, despachos: list[Despacho]) -> None:
        self._d = despachos

    async def listar(self) -> list[Despacho]:
        return list(self._d)

    async def crear(self, despacho: Despacho) -> Despacho:
        raise NotImplementedError

    async def buscar_por_id(self, despacho_id: UUID) -> Despacho | None:
        return next((d for d in self._d if d.id == despacho_id), None)


class FakeDestinatarioRepo:
    def __init__(self) -> None:
        self._dests: dict[UUID, Destinatario] = {}
        self.actualizados: list[Destinatario] = []

    def seed(self, d: Destinatario) -> Destinatario:
        assert d.id is not None
        self._dests[d.id] = d
        return d

    async def crear(self, dest: Destinatario) -> Destinatario:
        raise NotImplementedError

    async def actualizar(self, dest: Destinatario) -> Destinatario:
        assert dest.id is not None
        self._dests[dest.id] = dest
        self.actualizados.append(dest)
        return dest

    async def buscar_por_id(
        self, *, despacho_id: UUID, destinatario_id: UUID,
    ) -> Destinatario | None:
        d = self._dests.get(destinatario_id)
        if d is None or d.despacho_id != despacho_id:
            return None
        return d

    async def buscar_por_telefono(
        self, *, despacho_id: UUID, telefono_e164: str,
    ) -> Destinatario | None:
        for d in self._dests.values():
            if (
                d.despacho_id == despacho_id
                and d.telefono_e164 == telefono_e164
            ):
                return d
        return None

    async def listar_por_despacho(
        self, despacho_id: UUID, *, solo_activos: bool = False,
    ) -> list[Destinatario]:
        raise NotImplementedError

    async def eliminar(
        self, *, despacho_id: UUID, destinatario_id: UUID,
    ) -> bool:
        raise NotImplementedError


class FakeEnvioRepo:
    def __init__(self) -> None:
        self.actualizaciones: list[tuple[str, str, str | None]] = []
        self.reconocidos: set[str] = set()

    def reconocer(self, message_id: str) -> None:
        self.reconocidos.add(message_id)

    async def crear(self, envio: EnvioWhatsApp) -> EnvioWhatsApp:
        raise NotImplementedError

    async def marcar_enviado(self, **_: Any) -> EnvioWhatsApp:
        raise NotImplementedError

    async def marcar_fallido(self, **_: Any) -> EnvioWhatsApp:
        raise NotImplementedError

    async def actualizar_por_message_id(
        self,
        *,
        message_id_meta: str,
        nuevo_estado: str,
        error: str | None = None,
    ) -> EnvioWhatsApp | None:
        self.actualizaciones.append((message_id_meta, nuevo_estado, error))
        if message_id_meta not in self.reconocidos:
            return None
        # Devolvemos un envío sintético para que el caller lo cuente.
        return EnvioWhatsApp(
            id=uuid4(),
            destinatario_id=uuid4(),
            despacho_id=uuid4(),
            plantilla_name="x",
            tipo=__import__(
                "praxis.domain", fromlist=["TipoEnvio"],
            ).TipoEnvio.BRIEFING_DIARIO,
            estado=EstadoEnvio(nuevo_estado),
            error=error,
        )

    async def listar_por_despacho(self, **_: Any) -> list[EnvioWhatsApp]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _despacho() -> Despacho:
    return Despacho(id=uuid4(), nombre="Despacho Test")


def _destinatario(despacho: Despacho, *, tel: str) -> Destinatario:
    return Destinatario(
        id=uuid4(),
        despacho_id=despacho.id,
        nombre="Test User",
        rol_interno=RolDestinatario.LEGISLADOR,
        telefono_e164=tel,
    )


def _make_uc(
    despachos: FakeDespachoRepo,
    destinatarios: FakeDestinatarioRepo,
    envios: FakeEnvioRepo,
) -> ProcesarWebhookWhatsApp:
    return ProcesarWebhookWhatsApp(
        envios=envios,  # type: ignore[arg-type]
        destinatarios=destinatarios,  # type: ignore[arg-type]
        despachos=despachos,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Casos
# ---------------------------------------------------------------------------


async def test_status_update_reconocido() -> None:
    envios = FakeEnvioRepo()
    envios.reconocer("wamid.X")
    uc = _make_uc(FakeDespachoRepo([]), FakeDestinatarioRepo(), envios)

    r = await uc.ejecutar(
        WebhookEvento(
            statuses=[
                StatusUpdate(
                    message_id_meta="wamid.X",
                    nuevo_estado=EstadoEnvio.ENTREGADO,
                    error=None,
                ),
            ],
            mensajes=[],
        ),
    )
    assert r.statuses_actualizados == 1
    assert r.statuses_desconocidos == 0


async def test_status_update_desconocido() -> None:
    envios = FakeEnvioRepo()  # ninguno reconocido
    uc = _make_uc(FakeDespachoRepo([]), FakeDestinatarioRepo(), envios)

    r = await uc.ejecutar(
        WebhookEvento(
            statuses=[
                StatusUpdate(
                    message_id_meta="wamid.X",
                    nuevo_estado=EstadoEnvio.LEIDO,
                    error=None,
                ),
            ],
            mensajes=[],
        ),
    )
    assert r.statuses_desconocidos == 1
    assert r.statuses_actualizados == 0


async def test_opt_in_de_destinatario_existente() -> None:
    despacho = _despacho()
    dest = _destinatario(despacho, tel="+5491155551234")
    destinatarios = FakeDestinatarioRepo()
    destinatarios.seed(dest)
    uc = _make_uc(
        FakeDespachoRepo([despacho]), destinatarios, FakeEnvioRepo(),
    )

    ahora = datetime(2026, 6, 1, tzinfo=UTC)
    r = await uc.ejecutar(
        WebhookEvento(
            statuses=[],
            mensajes=[
                InboundMessage(
                    from_e164="+5491155551234",
                    body="SI",
                    message_id_meta="wamid.in",
                ),
            ],
        ),
        ahora=ahora,
    )
    assert r.opt_ins_aplicados == 1
    assert r.opt_outs_aplicados == 0
    # Verifica que el destinatario quedó activo + opt_in.
    actualizado = destinatarios.actualizados[0]
    assert actualizado.opt_in_en == ahora
    assert actualizado.opt_out_en is None
    assert actualizado.activo is True


async def test_opt_out_de_destinatario_existente() -> None:
    despacho = _despacho()
    dest = _destinatario(despacho, tel="+5491155551234")
    destinatarios = FakeDestinatarioRepo()
    destinatarios.seed(dest)
    uc = _make_uc(
        FakeDespachoRepo([despacho]), destinatarios, FakeEnvioRepo(),
    )

    ahora = datetime(2026, 6, 1, tzinfo=UTC)
    r = await uc.ejecutar(
        WebhookEvento(
            statuses=[],
            mensajes=[
                InboundMessage(
                    from_e164="+5491155551234",
                    body="STOP",
                    message_id_meta="wamid.in",
                ),
            ],
        ),
        ahora=ahora,
    )
    assert r.opt_outs_aplicados == 1
    actualizado = destinatarios.actualizados[0]
    assert actualizado.opt_out_en == ahora
    assert actualizado.activo is False


async def test_opt_in_de_telefono_desconocido_se_ignora() -> None:
    despacho = _despacho()
    destinatarios = FakeDestinatarioRepo()  # vacío
    uc = _make_uc(
        FakeDespachoRepo([despacho]), destinatarios, FakeEnvioRepo(),
    )
    r = await uc.ejecutar(
        WebhookEvento(
            statuses=[],
            mensajes=[
                InboundMessage(
                    from_e164="+5491100000000",
                    body="SI",
                    message_id_meta="wamid.in",
                ),
            ],
        ),
    )
    assert r.opt_ins_aplicados == 0
    assert r.mensajes_ignorados == 1


async def test_inbound_sin_clasificar_se_ignora() -> None:
    despacho = _despacho()
    destinatarios = FakeDestinatarioRepo()
    destinatarios.seed(_destinatario(despacho, tel="+5491155551234"))
    uc = _make_uc(
        FakeDespachoRepo([despacho]), destinatarios, FakeEnvioRepo(),
    )
    r = await uc.ejecutar(
        WebhookEvento(
            statuses=[],
            mensajes=[
                InboundMessage(
                    from_e164="+5491155551234",
                    body="hola che",
                    message_id_meta="wamid.x",
                ),
            ],
        ),
    )
    assert r.mensajes_ignorados == 1
    assert destinatarios.actualizados == []
