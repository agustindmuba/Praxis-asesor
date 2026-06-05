"""Tests del caso de uso `GenerarAccionableConPerfil` (feat-42.2).

Cubre:
- Cache hit: si ya hay accionable para (despacho, tipo, evento_id) y
  regenerar=False, devuelve el cacheado SIN llamar al LLM.
- Cache miss: si no hay cacheado, llama al LLM y persiste.
- regenerar=True: pisa el cache incluso si existe.
- Despacho sin perfil opositor → ValueError explícito.
- Mapeo del JSON del LLM a `AccionableEvento`:
  - acción fuera del catálogo → `AccionSugerida.OTRO`.
  - confianza fuera del catálogo → `ConfianzaAccionable.MEDIA`.
  - tweets vacíos / con texto vacío → se descartan, no se rompen.
  - tweet > 280 chars → se trunca a 280.
- JSON envuelto en ```json ... ``` → se parsea bien.

Usa fakes in-memory de todos los puertos. Sin red, sin DB.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from praxis.application.ports import (
    AccionableEventoRepository,
    LlmProvider,
    PerfilOpositorRepository,
)
from praxis.application.use_cases.generar_accionable_con_perfil import (
    GenerarAccionableConPerfil,
    PayloadEvento,
)
from praxis.domain import (
    ACCIONABLE_PROMPT_VERSION,
    AccionableEvento,
    AccionSugerida,
    ConfianzaAccionable,
    ConfianzaGlobal,
    FiguraReferida,
    PerfilOpositorDespacho,
    TipoEvento,
    TonoComunicacional,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeAccionableRepo(AccionableEventoRepository):
    """In-memory: dict keyed por (despacho_id, tipo, evento_id)."""

    def __init__(self) -> None:
        self._store: dict[
            tuple[UUID, TipoEvento, UUID], AccionableEvento,
        ] = {}
        self.upsert_calls = 0

    async def buscar_por_evento(
        self,
        *,
        despacho_id: UUID,
        tipo_evento: TipoEvento,
        evento_id: UUID,
    ) -> AccionableEvento | None:
        return self._store.get((despacho_id, tipo_evento, evento_id))

    async def upsert(
        self, accionable: AccionableEvento,
    ) -> AccionableEvento:
        self.upsert_calls += 1
        key = (
            accionable.despacho_id,
            accionable.tipo_evento,
            accionable.evento_id,
        )
        self._store[key] = accionable
        return accionable

    async def listar_por_despacho_y_tipo(
        self,
        *,
        despacho_id: UUID,
        tipo_evento: TipoEvento,
    ) -> list[AccionableEvento]:
        return [
            a for a in self._store.values()
            if a.despacho_id == despacho_id and a.tipo_evento == tipo_evento
        ]


class FakePerfilOpositorRepo(PerfilOpositorRepository):
    def __init__(self, perfil: PerfilOpositorDespacho | None = None) -> None:
        self._perfil = perfil

    async def buscar_por_despacho(
        self, despacho_id: UUID,
    ) -> PerfilOpositorDespacho | None:
        if self._perfil and self._perfil.despacho_id == despacho_id:
            return self._perfil
        return None

    async def upsert(
        self, perfil: PerfilOpositorDespacho,
    ) -> PerfilOpositorDespacho:
        self._perfil = perfil
        return perfil


class FakeLlmRespondedor(LlmProvider):
    """LLM que devuelve un JSON predeterminado por `razonar_libre`.

    Solo implementa `razonar_libre` y `nombre_modelo` — los otros
    métodos del puerto no se usan en este caso de uso. Si se invocan,
    fallan ruidosamente.
    """

    def __init__(self, payload_json: str) -> None:
        self._payload = payload_json
        self.razonar_calls = 0
        self.last_system: str = ""
        self.last_user: str = ""

    @property
    def nombre_modelo(self) -> str:
        return "fake-test"

    async def razonar_libre(
        self, *, system: str, user: str, max_tokens: int = 2000,
    ) -> tuple[str, str]:
        self.razonar_calls += 1
        self.last_system = system
        self.last_user = user
        return self._payload, "fake-test"

    async def generar_resumen_ejecutivo(self, expediente):  # pragma: no cover
        raise NotImplementedError

    async def clasificar_area_tematica(self, expediente):  # pragma: no cover
        raise NotImplementedError

    async def generar_argumentos(self, expediente, *, contraargumentos=False):  # pragma: no cover
        raise NotImplementedError

    async def clasificar_norma_bo(self, norma, *, texto=None):  # pragma: no cover
        raise NotImplementedError

    async def disambiguar_mencion(self, **kwargs):  # pragma: no cover
        raise NotImplementedError

    async def generar_bajada_propia(self, articulo, *, texto_articulo):  # pragma: no cover
        raise NotImplementedError

    async def clasificar_articulo(self, articulo, *, texto_articulo):  # pragma: no cover
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _perfil_minimo(despacho_id: UUID) -> PerfilOpositorDespacho:
    return PerfilOpositorDespacho(
        despacho_id=despacho_id,
        bandera_principal="Defensa del federalismo fiscal",
        banderas_secundarias=["Transparencia", "Salud pública"],
        temas_de_cuidado=["Aborto"],
        tono_comunicacional=TonoComunicacional.TECNICO_JURIDICO,
        adversarios=[FiguraReferida(nombre="Caputo", razon="Cuestiona pacto fiscal")],
        aliados=[FiguraReferida(nombre="UCR", razon="Coincide en federalismo")],
        linea_de_bloque="oposición dialogal",
        justificacion_evidencia="20 proyectos firmados sobre federalismo",
        confianza_global=ConfianzaGlobal.ALTA,
    )


def _payload(tipo: TipoEvento = TipoEvento.NORMA_BO) -> PayloadEvento:
    return PayloadEvento(
        titulo="Decreto 123/2026 — Reforma del sistema previsional",
        resumen="Modifica la fórmula de movilidad jubilatoria por DNU.",
        tipo=tipo,
        evento_id=uuid4(),
        metadata_extra={"organismo": "PEN", "fecha": "2026-06-05"},
    )


def _payload_llm_ok() -> str:
    return json.dumps({
        "razon_para_despacho": "Toca federalismo: PEN avanza sobre Anses",
        "accion_sugerida": "pedido_informes",
        "explicacion_accion": "Solicitar informe sobre el impacto provincial",
        "tweets_sugeridos": [
            {"tono": "frontal", "texto": "El DNU avanza sobre los jubilados."},
            {"tono": "tecnico", "texto": "Pedimos al PEN explicar el cálculo."},
        ],
        "confianza": "alta",
    })


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_hit_no_llama_llm() -> None:
    """Si ya hay accionable cacheado y regenerar=False, no se llama al LLM."""
    despacho_id = uuid4()
    payload = _payload()

    accionable_cacheado = AccionableEvento(
        despacho_id=despacho_id,
        tipo_evento=payload.tipo,
        evento_id=payload.evento_id,
        razon_para_despacho="Cacheado",
        accion_sugerida=AccionSugerida.PEDIDO_INFORMES,
        explicacion_accion="Cacheado",
    )
    accionables = FakeAccionableRepo()
    await accionables.upsert(accionable_cacheado)
    accionables.upsert_calls = 0      # reseteo el contador post-seeding

    perfiles = FakePerfilOpositorRepo(_perfil_minimo(despacho_id))
    llm = FakeLlmRespondedor(_payload_llm_ok())

    uc = GenerarAccionableConPerfil(
        accionables=accionables, perfiles=perfiles, llm=llm,
    )
    result = await uc.ejecutar(despacho_id=despacho_id, payload=payload)

    assert result.razon_para_despacho == "Cacheado"
    assert llm.razonar_calls == 0
    assert accionables.upsert_calls == 0


@pytest.mark.asyncio
async def test_cache_miss_llama_llm_y_persiste() -> None:
    """Sin cache, invoca LLM, parsea, persiste y devuelve."""
    despacho_id = uuid4()
    payload = _payload()

    accionables = FakeAccionableRepo()
    perfiles = FakePerfilOpositorRepo(_perfil_minimo(despacho_id))
    llm = FakeLlmRespondedor(_payload_llm_ok())

    uc = GenerarAccionableConPerfil(
        accionables=accionables, perfiles=perfiles, llm=llm,
    )
    result = await uc.ejecutar(despacho_id=despacho_id, payload=payload)

    assert llm.razonar_calls == 1
    assert accionables.upsert_calls == 1
    assert result.accion_sugerida == AccionSugerida.PEDIDO_INFORMES
    assert result.confianza == ConfianzaAccionable.ALTA
    assert len(result.tweets_sugeridos) == 2
    assert result.modelo == "fake-test"
    assert result.prompt_version == ACCIONABLE_PROMPT_VERSION


@pytest.mark.asyncio
async def test_regenerar_true_ignora_cache() -> None:
    """regenerar=True llama al LLM aunque haya un accionable cacheado."""
    despacho_id = uuid4()
    payload = _payload()

    accionable_viejo = AccionableEvento(
        despacho_id=despacho_id,
        tipo_evento=payload.tipo,
        evento_id=payload.evento_id,
        razon_para_despacho="Viejo",
        accion_sugerida=AccionSugerida.SILENCIO_ESTRATEGICO,
        explicacion_accion="Viejo",
    )
    accionables = FakeAccionableRepo()
    await accionables.upsert(accionable_viejo)
    accionables.upsert_calls = 0

    perfiles = FakePerfilOpositorRepo(_perfil_minimo(despacho_id))
    llm = FakeLlmRespondedor(_payload_llm_ok())

    uc = GenerarAccionableConPerfil(
        accionables=accionables, perfiles=perfiles, llm=llm,
    )
    result = await uc.ejecutar(
        despacho_id=despacho_id, payload=payload, regenerar=True,
    )

    assert llm.razonar_calls == 1
    assert result.accion_sugerida == AccionSugerida.PEDIDO_INFORMES


@pytest.mark.asyncio
async def test_despacho_sin_perfil_lanza_value_error() -> None:
    """Si el despacho no tiene perfil opositor cargado, el use case
    explica al asesor que tiene que crearlo primero."""
    despacho_id = uuid4()
    payload = _payload()

    perfiles = FakePerfilOpositorRepo(perfil=None)
    llm = FakeLlmRespondedor(_payload_llm_ok())

    uc = GenerarAccionableConPerfil(
        accionables=FakeAccionableRepo(), perfiles=perfiles, llm=llm,
    )

    with pytest.raises(ValueError, match="no tiene perfil opositor"):
        await uc.ejecutar(despacho_id=despacho_id, payload=payload)
    assert llm.razonar_calls == 0


@pytest.mark.asyncio
async def test_accion_fuera_de_catalogo_cae_a_otro() -> None:
    """Si el LLM se inventa una acción no listada, cae a OTRO."""
    despacho_id = uuid4()
    payload = _payload()
    raw = json.dumps({
        "razon_para_despacho": "X",
        "accion_sugerida": "marcha_callejera",
        "explicacion_accion": "Y",
        "tweets_sugeridos": [],
        "confianza": "media",
    })
    llm = FakeLlmRespondedor(raw)
    uc = GenerarAccionableConPerfil(
        accionables=FakeAccionableRepo(),
        perfiles=FakePerfilOpositorRepo(_perfil_minimo(despacho_id)),
        llm=llm,
    )
    result = await uc.ejecutar(despacho_id=despacho_id, payload=payload)
    assert result.accion_sugerida == AccionSugerida.OTRO


@pytest.mark.asyncio
async def test_confianza_invalida_cae_a_media() -> None:
    despacho_id = uuid4()
    payload = _payload()
    raw = json.dumps({
        "razon_para_despacho": "X",
        "accion_sugerida": "pedido_informes",
        "explicacion_accion": "Y",
        "tweets_sugeridos": [],
        "confianza": "altísima",   # fuera del catálogo
    })
    llm = FakeLlmRespondedor(raw)
    uc = GenerarAccionableConPerfil(
        accionables=FakeAccionableRepo(),
        perfiles=FakePerfilOpositorRepo(_perfil_minimo(despacho_id)),
        llm=llm,
    )
    result = await uc.ejecutar(despacho_id=despacho_id, payload=payload)
    assert result.confianza == ConfianzaAccionable.MEDIA


@pytest.mark.asyncio
async def test_tweets_vacios_o_largos_se_higienizan() -> None:
    """Tweets sin texto se descartan; los > 280 chars se truncan."""
    despacho_id = uuid4()
    payload = _payload()
    tweet_largo = "A" * 400
    raw = json.dumps({
        "razon_para_despacho": "X",
        "accion_sugerida": "pedido_informes",
        "explicacion_accion": "Y",
        "tweets_sugeridos": [
            {"tono": "frontal", "texto": ""},
            {"tono": "frontal", "texto": "   "},
            {"tono": "tecnico", "texto": tweet_largo},
        ],
        "confianza": "media",
    })
    llm = FakeLlmRespondedor(raw)
    uc = GenerarAccionableConPerfil(
        accionables=FakeAccionableRepo(),
        perfiles=FakePerfilOpositorRepo(_perfil_minimo(despacho_id)),
        llm=llm,
    )
    result = await uc.ejecutar(despacho_id=despacho_id, payload=payload)
    assert len(result.tweets_sugeridos) == 1
    assert len(result.tweets_sugeridos[0].texto) == 280


@pytest.mark.asyncio
async def test_json_envuelto_en_fences_se_parsea() -> None:
    """LLM que responde con ```json ... ``` (común) se parsea bien."""
    despacho_id = uuid4()
    payload = _payload()
    raw = "```json\n" + _payload_llm_ok() + "\n```"
    llm = FakeLlmRespondedor(raw)
    uc = GenerarAccionableConPerfil(
        accionables=FakeAccionableRepo(),
        perfiles=FakePerfilOpositorRepo(_perfil_minimo(despacho_id)),
        llm=llm,
    )
    result = await uc.ejecutar(despacho_id=despacho_id, payload=payload)
    assert result.accion_sugerida == AccionSugerida.PEDIDO_INFORMES


@pytest.mark.asyncio
async def test_perfil_se_incluye_en_el_prompt() -> None:
    """El system+user del LLM debe contener la bandera principal del
    perfil, para que el LLM razone informado por la línea política."""
    despacho_id = uuid4()
    payload = _payload()
    perfil = _perfil_minimo(despacho_id)
    llm = FakeLlmRespondedor(_payload_llm_ok())

    uc = GenerarAccionableConPerfil(
        accionables=FakeAccionableRepo(),
        perfiles=FakePerfilOpositorRepo(perfil),
        llm=llm,
    )
    await uc.ejecutar(despacho_id=despacho_id, payload=payload)

    assert "Defensa del federalismo fiscal" in llm.last_user
    assert "Caputo" in llm.last_user          # adversario aparece
    assert "UCR" in llm.last_user             # aliado aparece
    assert payload.titulo in llm.last_user    # evento aparece
