"""Tests del caso de uso `EnviarBriefingDiario` (feat-41.4).

Cubre:
- Sin destinatarios activos / elegibles → no manda.
- Sin contenido (0 BO + 0 noticias) → no manda, devuelve
  sin_contenido=True.
- Con contenido y destinatarios elegibles → manda + marca enviado.
- Sender devuelve rechazado opt-out (131026) → marca envío rechazado
  + marca destinatario opt_out_en + activo=False.
- Sender devuelve fallido transitorio → marca envío fallido sin
  tocar al destinatario.
- Resumen corto se compone bien con N BO + M noticias.
- _primer_nombre extrae solo la primera palabra.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from praxis.application.ports import ResultadoEnvioWhatsApp
from praxis.application.use_cases import EnviarBriefingDiario
from praxis.application.use_cases.enviar_briefing_diario import (
    META_CODE_OPT_OUT,
    _componer_resumen,
    _primer_nombre,
)
from praxis.domain import (
    ArticuloRelevante,
    Destinatario,
    EnvioWhatsApp,
    EstadoEnvio,
    NormaBOAccionable,
    PrioridadAccionabilidad,
    RolDestinatario,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeDestinatarioRepo:
    def __init__(self, dests: list[Destinatario]) -> None:
        self._dests = list(dests)
        self.actualizados: list[Destinatario] = []

    async def crear(self, dest: Destinatario) -> Destinatario:
        raise NotImplementedError

    async def actualizar(self, dest: Destinatario) -> Destinatario:
        self.actualizados.append(dest)
        # Replace in-place.
        for i, d in enumerate(self._dests):
            if d.id == dest.id:
                self._dests[i] = dest
                break
        return dest

    async def buscar_por_id(self, **_: Any) -> Destinatario | None:
        raise NotImplementedError

    async def buscar_por_telefono(self, **_: Any) -> Destinatario | None:
        raise NotImplementedError

    async def listar_por_despacho(
        self, despacho_id: UUID, *, solo_activos: bool = False,
    ) -> list[Destinatario]:
        result = [d for d in self._dests if d.despacho_id == despacho_id]
        if solo_activos:
            result = [d for d in result if d.activo]
        return result

    async def eliminar(self, **_: Any) -> bool:
        raise NotImplementedError


class FakeEnvioRepo:
    def __init__(self) -> None:
        self.creados: list[EnvioWhatsApp] = []
        self.marcado_enviado: list[tuple[UUID, str]] = []
        self.marcado_fallido: list[tuple[UUID, str, bool]] = []
        self._next_id_count = 0

    async def crear(self, envio: EnvioWhatsApp) -> EnvioWhatsApp:
        self._next_id_count += 1
        nuevo = EnvioWhatsApp(
            id=uuid4(),
            destinatario_id=envio.destinatario_id,
            despacho_id=envio.despacho_id,
            plantilla_name=envio.plantilla_name,
            tipo=envio.tipo,
            payload_params=envio.payload_params,
            correlativo_id=envio.correlativo_id,
        )
        self.creados.append(nuevo)
        return nuevo

    async def marcar_enviado(
        self, *, envio_id: UUID, message_id_meta: str, enviado_en: datetime,
    ) -> EnvioWhatsApp:
        self.marcado_enviado.append((envio_id, message_id_meta))
        return EnvioWhatsApp(
            id=envio_id,
            destinatario_id=uuid4(),
            despacho_id=uuid4(),
            plantilla_name="x",
            tipo=__import__(
                "praxis.domain", fromlist=["TipoEnvio"],
            ).TipoEnvio.BRIEFING_DIARIO,
            estado=EstadoEnvio.ENVIADO,
            message_id_meta=message_id_meta,
        )

    async def marcar_fallido(
        self, *, envio_id: UUID, error: str, rechazado: bool = False,
    ) -> EnvioWhatsApp:
        self.marcado_fallido.append((envio_id, error, rechazado))
        estado = (
            EstadoEnvio.RECHAZADO if rechazado else EstadoEnvio.FALLIDO
        )
        return EnvioWhatsApp(
            id=envio_id,
            destinatario_id=uuid4(),
            despacho_id=uuid4(),
            plantilla_name="x",
            tipo=__import__(
                "praxis.domain", fromlist=["TipoEnvio"],
            ).TipoEnvio.BRIEFING_DIARIO,
            estado=estado,
            error=error,
        )

    async def actualizar_por_message_id(self, **_: Any) -> EnvioWhatsApp | None:
        raise NotImplementedError

    async def listar_por_despacho(self, **_: Any) -> list[EnvioWhatsApp]:
        raise NotImplementedError


class FakeAccionablesRepo:
    def __init__(self, items: list[NormaBOAccionable]) -> None:
        self._items = items

    async def upsert(self, _: Any) -> Any:
        raise NotImplementedError

    async def listar_por_despacho_y_fecha(
        self, *, despacho_id: UUID, fecha: date, top_n: int | None = None,
    ) -> list[NormaBOAccionable]:
        # NormaBOAccionable no guarda fecha_publicacion — se infiere de la
        # NormaBO original. Para el test, devolvemos todos los del despacho.
        del fecha
        result = [i for i in self._items if i.despacho_id == despacho_id]
        return result[: top_n or len(result)]

    async def borrar_por_despacho_y_fecha(self, **_: Any) -> int:
        raise NotImplementedError


class FakeRelevantesRepo:
    def __init__(self, items: list[ArticuloRelevante]) -> None:
        self._items = items

    async def upsert(self, _: Any) -> Any:
        raise NotImplementedError

    async def listar_por_despacho_24h(
        self, *, despacho_id: UUID, hasta: datetime, top_n: int | None = None,
    ) -> list[ArticuloRelevante]:
        result = [i for i in self._items if i.despacho_id == despacho_id]
        return result[: top_n or len(result)]

    async def borrar_por_despacho_y_ventana(self, **_: Any) -> int:
        raise NotImplementedError


class FakeSender:
    def __init__(self, resultado: ResultadoEnvioWhatsApp) -> None:
        self.resultado = resultado
        self.llamadas: list[dict[str, Any]] = []

    async def enviar(
        self,
        *,
        telefono_e164: str,
        plantilla_name: str,
        idioma: str,
        body_params_ordered: list[str],
    ) -> ResultadoEnvioWhatsApp:
        self.llamadas.append({
            "telefono": telefono_e164,
            "plantilla": plantilla_name,
            "idioma": idioma,
            "params": list(body_params_ordered),
        })
        return self.resultado


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def _dest_activo(despacho_id: UUID, *, telefono: str) -> Destinatario:
    return Destinatario(
        id=uuid4(),
        despacho_id=despacho_id,
        nombre="Pablo Juliano Otro",
        rol_interno=RolDestinatario.LEGISLADOR,
        telefono_e164=telefono,
        opt_in_en=datetime(2026, 5, 1, tzinfo=UTC),
        activo=True,
    )


def _accionable(despacho_id: UUID, fecha: date) -> NormaBOAccionable:
    # `fecha` se usa solo del lado del fake repo para filtrar; la entidad
    # no la guarda (vive en la NormaBO original).
    del fecha
    return NormaBOAccionable(
        norma_id=uuid4(),
        despacho_id=despacho_id,
        score=80,
        prioridad=PrioridadAccionabilidad.ALTA,
        razon="match perfil",
        expedientes_tocados=[],
    )


def _articulo_relevante(despacho_id: UUID) -> ArticuloRelevante:
    return ArticuloRelevante(
        articulo_id=uuid4(),
        despacho_id=despacho_id,
        score=70,
        razon="área educación",
    )


# ---------------------------------------------------------------------------
# Helpers puros
# ---------------------------------------------------------------------------


class TestHelpersPuros:
    def test_primer_nombre(self) -> None:
        assert _primer_nombre("Pablo Juliano Otro") == "Pablo"
        assert _primer_nombre("Pablo") == "Pablo"
        assert _primer_nombre("   ") == "Despacho"

    def test_componer_resumen_solo_bo(self) -> None:
        r = _componer_resumen(n_bo=2, n_noticias=0)
        assert "2 normas accionables" in r
        assert "noticia" not in r

    def test_componer_resumen_solo_noticias(self) -> None:
        r = _componer_resumen(n_bo=0, n_noticias=1)
        assert "1 noticia" in r
        assert "norma" not in r

    def test_componer_resumen_ambos(self) -> None:
        r = _componer_resumen(n_bo=3, n_noticias=5)
        assert "3 normas accionables" in r
        assert "5 noticias" in r
        assert " y " in r

    def test_componer_resumen_singular(self) -> None:
        r = _componer_resumen(n_bo=1, n_noticias=1)
        assert "1 norma accionable" in r
        assert "1 noticia" in r
        # Sin "s" extra.
        assert "1 normas" not in r


# ---------------------------------------------------------------------------
# Caso de uso
# ---------------------------------------------------------------------------


def _make_uc(
    destinatarios_repo: FakeDestinatarioRepo,
    envios_repo: FakeEnvioRepo,
    bo_repo: FakeAccionablesRepo,
    noticias_repo: FakeRelevantesRepo,
    sender: FakeSender,
) -> EnviarBriefingDiario:
    return EnviarBriefingDiario(
        destinatarios=destinatarios_repo,  # type: ignore[arg-type]
        envios=envios_repo,  # type: ignore[arg-type]
        accionables_bo=bo_repo,  # type: ignore[arg-type]
        relevantes_noticias=noticias_repo,  # type: ignore[arg-type]
        sender=sender,  # type: ignore[arg-type]
    )


async def test_sin_destinatarios_devuelve_cero() -> None:
    despacho_id = uuid4()
    uc = _make_uc(
        FakeDestinatarioRepo([]),
        FakeEnvioRepo(),
        FakeAccionablesRepo([]),
        FakeRelevantesRepo([]),
        FakeSender(ResultadoEnvioWhatsApp(exitoso=True)),
    )
    r = await uc.ejecutar(despacho_id=despacho_id, fecha=date(2026, 6, 1))
    assert r.destinatarios_objetivo == 0
    assert r.enviados_ok == 0
    assert r.sin_contenido is False  # short-circuit antes de chequear contenido


async def test_sin_contenido_no_manda_y_marca_sin_contenido() -> None:
    despacho_id = uuid4()
    dest = _dest_activo(despacho_id, telefono="+5491155551234")
    sender = FakeSender(ResultadoEnvioWhatsApp(exitoso=True))
    uc = _make_uc(
        FakeDestinatarioRepo([dest]),
        FakeEnvioRepo(),
        FakeAccionablesRepo([]),  # 0 BO
        FakeRelevantesRepo([]),   # 0 noticias
        sender,
    )
    r = await uc.ejecutar(despacho_id=despacho_id, fecha=date(2026, 6, 1))
    assert r.sin_contenido is True
    assert r.destinatarios_objetivo == 1
    assert r.enviados_ok == 0
    assert sender.llamadas == []


async def test_envio_exitoso() -> None:
    despacho_id = uuid4()
    fecha = date(2026, 6, 1)
    dest = _dest_activo(despacho_id, telefono="+5491155551234")
    sender = FakeSender(
        ResultadoEnvioWhatsApp(exitoso=True, message_id_meta="wamid.X"),
    )
    envios = FakeEnvioRepo()
    uc = _make_uc(
        FakeDestinatarioRepo([dest]),
        envios,
        FakeAccionablesRepo([_accionable(despacho_id, fecha)]),
        FakeRelevantesRepo([]),
        sender,
    )
    r = await uc.ejecutar(despacho_id=despacho_id, fecha=fecha)
    assert r.enviados_ok == 1
    assert r.fallidos_transitorios == 0
    assert r.rechazados == 0
    # Verifica payload del sender.
    assert len(sender.llamadas) == 1
    call = sender.llamadas[0]
    assert call["plantilla"] == "briefing_diario"
    assert call["params"][0] == "Pablo"  # primer nombre
    assert call["params"][1] == "2026-06-01"
    assert "norma" in call["params"][2]
    # Envio fue creado + marcado enviado.
    assert len(envios.creados) == 1
    assert len(envios.marcado_enviado) == 1


async def test_envio_rechazado_opt_out_marca_destinatario() -> None:
    despacho_id = uuid4()
    fecha = date(2026, 6, 1)
    dest = _dest_activo(despacho_id, telefono="+5491155551234")
    destinatarios = FakeDestinatarioRepo([dest])
    sender = FakeSender(
        ResultadoEnvioWhatsApp(
            exitoso=False,
            error="Recipient opted out",
            rechazado=True,
            error_meta_code=META_CODE_OPT_OUT,
        ),
    )
    envios = FakeEnvioRepo()
    uc = _make_uc(
        destinatarios,
        envios,
        FakeAccionablesRepo([_accionable(despacho_id, fecha)]),
        FakeRelevantesRepo([]),
        sender,
    )
    r = await uc.ejecutar(despacho_id=despacho_id, fecha=fecha)
    assert r.rechazados == 1
    assert r.enviados_ok == 0
    # Marcamos al destinatario opt_out.
    assert len(destinatarios.actualizados) == 1
    actualizado = destinatarios.actualizados[0]
    assert actualizado.opt_out_en is not None
    assert actualizado.activo is False


async def test_envio_fallido_transitorio_no_toca_destinatario() -> None:
    despacho_id = uuid4()
    fecha = date(2026, 6, 1)
    dest = _dest_activo(despacho_id, telefono="+5491155551234")
    destinatarios = FakeDestinatarioRepo([dest])
    sender = FakeSender(
        ResultadoEnvioWhatsApp(
            exitoso=False,
            error="timeout",
            rechazado=False,
        ),
    )
    uc = _make_uc(
        destinatarios,
        FakeEnvioRepo(),
        FakeAccionablesRepo([_accionable(despacho_id, fecha)]),
        FakeRelevantesRepo([]),
        sender,
    )
    r = await uc.ejecutar(despacho_id=despacho_id, fecha=fecha)
    assert r.fallidos_transitorios == 1
    # NO se marca destinatario.
    assert destinatarios.actualizados == []


async def test_destinatario_sin_flag_de_briefing_se_excluye() -> None:
    despacho_id = uuid4()
    fecha = date(2026, 6, 1)
    dest = _dest_activo(despacho_id, telefono="+5491155551234")
    dest_sin_briefing = Destinatario(
        id=uuid4(),
        despacho_id=despacho_id,
        nombre="Otro Asesor",
        rol_interno=RolDestinatario.ASESOR,
        telefono_e164="+5491155559999",
        opt_in_en=datetime(2026, 5, 1, tzinfo=UTC),
        activo=True,
        recibe_briefing_diario=False,
        recibe_alertas_menciones=True,
    )
    sender = FakeSender(
        ResultadoEnvioWhatsApp(exitoso=True, message_id_meta="wamid.X"),
    )
    uc = _make_uc(
        FakeDestinatarioRepo([dest, dest_sin_briefing]),
        FakeEnvioRepo(),
        FakeAccionablesRepo([_accionable(despacho_id, fecha)]),
        FakeRelevantesRepo([]),
        sender,
    )
    r = await uc.ejecutar(despacho_id=despacho_id, fecha=fecha)
    assert r.destinatarios_objetivo == 1  # solo dest, no el otro
    assert r.enviados_ok == 1
