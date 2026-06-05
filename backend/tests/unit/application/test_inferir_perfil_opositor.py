"""Tests de `InferirPerfilOpositor` (feat-42.0/42.1).

El use case tiene 2 partes claramente separables:
- `_fetch_huella` ejecuta queries SQL crudas → eso es trabajo de
  integración (cubierto por el script `perfilar_legislador.py`).
- `_llamar_llm` parsea el JSON del LLM y construye la entidad → eso
  es lógica pura, fácilmente unit testeable.

Estos tests cubren la lógica pura subclaseando el use case para
inyectar una huella fake (saltearse la DB) y luego verificar:

- Huella vacía → ValueError (no llama al LLM).
- LLM con JSON válido → entidad bien construida.
- Tono fuera del catálogo → cae a MIXTO.
- Confianza fuera del catálogo → cae a MEDIA.
- Adversarios y aliados se mapean a `FiguraReferida`.
- JSON envuelto en fences ```json ... ``` se parsea.
- El upsert se invoca con el perfil final.
"""

from __future__ import annotations

import json
from uuid import UUID, uuid4

import pytest

from praxis.application.ports import LlmProvider, PerfilOpositorRepository
from praxis.application.use_cases.inferir_perfil_opositor import (
    HuellaParlamentaria,
    InferirPerfilOpositor,
)
from praxis.domain import (
    PERFIL_OPOSITOR_PROMPT_VERSION,
    ConfianzaGlobal,
    PerfilOpositorDespacho,
    TonoComunicacional,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakePerfilRepo(PerfilOpositorRepository):
    def __init__(self) -> None:
        self.upserted: PerfilOpositorDespacho | None = None
        self.upsert_calls = 0

    async def buscar_por_despacho(self, despacho_id: UUID):
        return self.upserted

    async def upsert(
        self, perfil: PerfilOpositorDespacho,
    ) -> PerfilOpositorDespacho:
        self.upsert_calls += 1
        self.upserted = perfil
        return perfil


class FakeLlmRespondedor(LlmProvider):
    def __init__(self, payload: str, modelo: str = "fake-test") -> None:
        self._payload = payload
        self._modelo = modelo
        self.calls = 0

    @property
    def nombre_modelo(self) -> str:
        return self._modelo

    async def razonar_libre(
        self, *, system: str, user: str, max_tokens: int = 2000,
    ) -> tuple[str, str]:
        self.calls += 1
        return self._payload, self._modelo

    async def generar_resumen_ejecutivo(self, e):  # pragma: no cover
        raise NotImplementedError

    async def clasificar_area_tematica(self, e):  # pragma: no cover
        raise NotImplementedError

    async def generar_argumentos(self, e, *, contraargumentos=False):  # pragma: no cover
        raise NotImplementedError

    async def clasificar_norma_bo(self, n, *, texto=None):  # pragma: no cover
        raise NotImplementedError

    async def disambiguar_mencion(self, **k):  # pragma: no cover
        raise NotImplementedError

    async def generar_bajada_propia(self, a, *, texto_articulo):  # pragma: no cover
        raise NotImplementedError

    async def clasificar_articulo(self, a, *, texto_articulo):  # pragma: no cover
        raise NotImplementedError


class UseCaseConHuellaInyectada(InferirPerfilOpositor):
    """Subclase que evita la DB: devuelve la huella precargada."""

    def __init__(self, huella: HuellaParlamentaria, **kw) -> None:
        super().__init__(**kw)
        self._huella_precargada = huella

    async def _fetch_huella(
        self, nombre_legislador: str, max_vot: int,
    ) -> HuellaParlamentaria:
        return self._huella_precargada


def _huella_con_evidencia() -> HuellaParlamentaria:
    return HuellaParlamentaria(
        nombre_buscado="JULIANO, PABLO",
        identidades=[
            {"nombre": "JULIANO, PABLO", "bloque": "DPS",
             "distrito": "Buenos Aires", "proyectos": 20},
        ],
        expedientes_firmados=[
            {"tipo": "ley", "titulo": "Cobertura medicamentos",
             "anio": 2025, "numero": 100, "origen": "HCDN",
             "area": "salud", "orden_firma": 1, "bloque_al_firmar": "DPS"},
        ],
        areas_dominantes=[{"area": "salud", "n_proyectos": 10}],
        cofirmantes_recurrentes=[
            {"nombre": "Lopez, Juan", "bloque": "UCR",
             "proyectos_compartidos": 5},
        ],
        votaciones=[
            {"fecha": "2025-09-15", "asunto": "Reforma jubilatoria",
             "voto": "NEGATIVO", "bloque_en_ese_momento": "DPS",
             "ley_aprobada": True, "afirmativos_totales": 130,
             "negativos_totales": 100, "que_dijo": None},
        ],
    )


def _huella_vacia() -> HuellaParlamentaria:
    return HuellaParlamentaria(
        nombre_buscado="UNKNOWN, PERSON",
        identidades=[],
        expedientes_firmados=[],
        areas_dominantes=[],
        cofirmantes_recurrentes=[],
        votaciones=[],
    )


def _payload_llm_completo() -> str:
    return json.dumps({
        "bandera_principal": "Salud pública y federalismo",
        "banderas_secundarias": ["Cobertura universal", "Medicamentos"],
        "temas_de_cuidado": ["Aborto", "Política exterior"],
        "tono_comunicacional": "tecnico-juridico",
        "adversarios_inferidos": [
            {"nombre": "Caputo", "razon": "Votó contra reforma jubilatoria"},
        ],
        "aliados_inferidos": [
            {"nombre": "Lopez (UCR)", "razon": "5 proyectos compartidos"},
        ],
        "linea_de_bloque": "oposición dialogal",
        "justificacion_evidencia": "20 firmas + voto negativo a reforma jubilatoria",
        "confianza_global": "alta",
        "advertencias": ["Cofirmantes con UCR no implica alianza estable"],
    })


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_huella_vacia_lanza_value_error() -> None:
    """Si el legislador no tiene actividad documentada, no se llama al LLM."""
    despacho_id = uuid4()
    perfiles = FakePerfilRepo()
    llm = FakeLlmRespondedor(_payload_llm_completo())

    uc = UseCaseConHuellaInyectada(
        huella=_huella_vacia(),
        session=object(),    # sentinel — no se usa porque _fetch_huella está override
        perfiles=perfiles,
        llm=llm,
    )
    with pytest.raises(ValueError, match="No encontré actividad parlamentaria"):
        await uc.ejecutar(
            despacho_id=despacho_id, nombre_legislador="UNKNOWN, PERSON",
        )
    assert llm.calls == 0
    assert perfiles.upsert_calls == 0


@pytest.mark.asyncio
async def test_perfil_completo_se_construye_y_upsertea() -> None:
    despacho_id = uuid4()
    perfiles = FakePerfilRepo()
    llm = FakeLlmRespondedor(_payload_llm_completo())

    uc = UseCaseConHuellaInyectada(
        huella=_huella_con_evidencia(),
        session=object(),
        perfiles=perfiles,
        llm=llm,
    )
    perfil = await uc.ejecutar(
        despacho_id=despacho_id, nombre_legislador="JULIANO, PABLO",
    )

    assert perfiles.upsert_calls == 1
    assert perfil.despacho_id == despacho_id
    assert perfil.bandera_principal == "Salud pública y federalismo"
    assert perfil.tono_comunicacional == TonoComunicacional.TECNICO_JURIDICO
    assert perfil.confianza_global == ConfianzaGlobal.ALTA
    assert len(perfil.adversarios) == 1
    assert perfil.adversarios[0].nombre == "Caputo"
    assert "reforma jubilatoria" in perfil.adversarios[0].razon
    assert len(perfil.aliados) == 1
    assert perfil.aliados[0].nombre == "Lopez (UCR)"
    assert perfil.modelo_inferencia == "fake-test"
    assert perfil.prompt_version == PERFIL_OPOSITOR_PROMPT_VERSION
    assert perfil.inferido_en is not None


@pytest.mark.asyncio
async def test_tono_invalido_cae_a_mixto() -> None:
    despacho_id = uuid4()
    raw = json.dumps({
        "bandera_principal": "X",
        "banderas_secundarias": [],
        "temas_de_cuidado": [],
        "tono_comunicacional": "papal-bíblico",   # fuera del catálogo
        "adversarios_inferidos": [],
        "aliados_inferidos": [],
        "linea_de_bloque": "",
        "justificacion_evidencia": "",
        "confianza_global": "media",
        "advertencias": [],
    })
    uc = UseCaseConHuellaInyectada(
        huella=_huella_con_evidencia(),
        session=object(),
        perfiles=FakePerfilRepo(),
        llm=FakeLlmRespondedor(raw),
    )
    perfil = await uc.ejecutar(
        despacho_id=despacho_id, nombre_legislador="X",
    )
    assert perfil.tono_comunicacional == TonoComunicacional.MIXTO


@pytest.mark.asyncio
async def test_confianza_invalida_cae_a_media() -> None:
    despacho_id = uuid4()
    raw = json.dumps({
        "bandera_principal": "X",
        "banderas_secundarias": [],
        "temas_de_cuidado": [],
        "tono_comunicacional": "mixto",
        "adversarios_inferidos": [],
        "aliados_inferidos": [],
        "linea_de_bloque": "",
        "justificacion_evidencia": "",
        "confianza_global": "altísima",   # fuera del catálogo
        "advertencias": [],
    })
    uc = UseCaseConHuellaInyectada(
        huella=_huella_con_evidencia(),
        session=object(),
        perfiles=FakePerfilRepo(),
        llm=FakeLlmRespondedor(raw),
    )
    perfil = await uc.ejecutar(
        despacho_id=despacho_id, nombre_legislador="X",
    )
    assert perfil.confianza_global == ConfianzaGlobal.MEDIA


@pytest.mark.asyncio
async def test_json_envuelto_en_fences_se_parsea() -> None:
    despacho_id = uuid4()
    raw = "```json\n" + _payload_llm_completo() + "\n```"
    uc = UseCaseConHuellaInyectada(
        huella=_huella_con_evidencia(),
        session=object(),
        perfiles=FakePerfilRepo(),
        llm=FakeLlmRespondedor(raw),
    )
    perfil = await uc.ejecutar(
        despacho_id=despacho_id, nombre_legislador="X",
    )
    assert perfil.bandera_principal == "Salud pública y federalismo"


@pytest.mark.asyncio
async def test_huella_total_evidencia_cuenta_correcto() -> None:
    """La huella suma expedientes + votaciones + cofirmantes."""
    huella = _huella_con_evidencia()
    assert huella.total_evidencia() == 3   # 1+1+1


@pytest.mark.asyncio
async def test_huella_vacia_total_evidencia_es_cero() -> None:
    assert _huella_vacia().total_evidencia() == 0
