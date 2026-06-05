"""Tests de los asistentes de redacción de proyectos (feat-42.3).

Cubre los 3 use cases:

- `GenerarArticuladoConLLM`: parsea JSON con artículos, devuelve
  `ArticuladoGenerado(articulado, modelo)`. Si el perfil del despacho
  existe, lo inyecta en el prompt para que el LLM alinee la voz.

- `GenerarFundamentosConLLM`: pasa articulado + tipo + perfil opcional,
  devuelve el Markdown crudo del LLM (no parsea — son fundamentos
  libres).

- `RefinarArticuloConLLM`: pasa texto + instrucción, devuelve el
  refinado strippeado.

Fakes in-memory para PerfilOpositorRepository y LlmProvider.
"""

from __future__ import annotations

import json
from uuid import UUID, uuid4

import pytest

from praxis.application.ports import LlmProvider, PerfilOpositorRepository
from praxis.application.use_cases.asistir_redaccion_proyecto import (
    ArticuladoGenerado,
    FundamentosGenerados,
    GenerarArticuladoConLLM,
    GenerarFundamentosConLLM,
    RefinarArticuloConLLM,
)
from praxis.domain import (
    ConfianzaGlobal,
    FiguraReferida,
    PerfilOpositorDespacho,
    TipoProyecto,
    TonoComunicacional,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakePerfilRepo(PerfilOpositorRepository):
    def __init__(self, perfil: PerfilOpositorDespacho | None = None) -> None:
        self._perfil = perfil

    async def buscar_por_despacho(
        self, despacho_id: UUID,
    ) -> PerfilOpositorDespacho | None:
        if self._perfil and self._perfil.despacho_id == despacho_id:
            return self._perfil
        return None

    async def upsert(self, perfil):
        self._perfil = perfil
        return perfil


class FakeLlmRespondedor(LlmProvider):
    """LLM stub que devuelve `payload` por `razonar_libre`.

    Captura los últimos system/user para que los tests inspeccionen el
    prompt sin tener que reverse-engineer texto del LLM.
    """

    def __init__(self, payload: str, modelo: str = "fake-test") -> None:
        self._payload = payload
        self._modelo = modelo
        self.calls = 0
        self.last_system = ""
        self.last_user = ""
        self.last_max_tokens = 0

    @property
    def nombre_modelo(self) -> str:
        return self._modelo

    async def razonar_libre(
        self, *, system: str, user: str, max_tokens: int = 2000,
    ) -> tuple[str, str]:
        self.calls += 1
        self.last_system = system
        self.last_user = user
        self.last_max_tokens = max_tokens
        return self._payload, self._modelo

    # Métodos no usados — fail loud si alguien los toca.
    async def generar_resumen_ejecutivo(self, e):  # pragma: no cover
        raise NotImplementedError

    async def clasificar_area_tematica(self, e):  # pragma: no cover
        raise NotImplementedError

    async def generar_argumentos(self, e, *, contraargumentos=False):  # pragma: no cover
        raise NotImplementedError

    async def clasificar_norma_bo(self, norma, *, texto=None):  # pragma: no cover
        raise NotImplementedError

    async def disambiguar_mencion(self, **kw):  # pragma: no cover
        raise NotImplementedError

    async def generar_bajada_propia(self, a, *, texto_articulo):  # pragma: no cover
        raise NotImplementedError

    async def clasificar_articulo(self, a, *, texto_articulo):  # pragma: no cover
        raise NotImplementedError


def _perfil(despacho_id: UUID) -> PerfilOpositorDespacho:
    return PerfilOpositorDespacho(
        despacho_id=despacho_id,
        bandera_principal="Defensa de la salud pública",
        banderas_secundarias=["Cobertura universal", "Medicamentos críticos"],
        tono_comunicacional=TonoComunicacional.TECNICO_JURIDICO,
        adversarios=[FiguraReferida(nombre="Ministerio X", razon="Recorta")],
        linea_de_bloque="oposición técnica",
        justificacion_evidencia="20 firmas en salud",
        confianza_global=ConfianzaGlobal.ALTA,
    )


# ---------------------------------------------------------------------------
# GenerarArticuladoConLLM
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_articulado_parsea_json_simple() -> None:
    despacho_id = uuid4()
    payload = json.dumps({
        "articulado": [
            "Artículo 1° — Créase el Registro Nacional de Medicamentos Críticos.",
            "Artículo 2° — La autoridad de aplicación es el Ministerio de Salud.",
            "Artículo 3° — Comuníquese al Poder Ejecutivo Nacional.",
        ],
    })
    llm = FakeLlmRespondedor(payload)
    uc = GenerarArticuladoConLLM(perfiles=FakePerfilRepo(), llm=llm)
    result = await uc.ejecutar(
        despacho_id=despacho_id,
        tipo=TipoProyecto.LEY,
        tema="Registro de medicamentos críticos",
    )
    assert isinstance(result, ArticuladoGenerado)
    assert len(result.articulado) == 3
    assert "Registro" in result.articulado[0]
    assert result.modelo == "fake-test"


@pytest.mark.asyncio
async def test_articulado_parsea_con_fences_json() -> None:
    despacho_id = uuid4()
    raw = (
        "```json\n"
        + json.dumps({"articulado": ["Artículo 1° — De forma."]})
        + "\n```"
    )
    llm = FakeLlmRespondedor(raw)
    uc = GenerarArticuladoConLLM(perfiles=FakePerfilRepo(), llm=llm)
    result = await uc.ejecutar(
        despacho_id=despacho_id, tipo=TipoProyecto.DECLARACION, tema="X",
    )
    assert result.articulado == ["Artículo 1° — De forma."]


@pytest.mark.asyncio
async def test_articulado_inyecta_perfil_en_prompt() -> None:
    """Si hay perfil, el prompt debe contener la bandera principal."""
    despacho_id = uuid4()
    llm = FakeLlmRespondedor(json.dumps({"articulado": ["Artículo 1° — X."]}))
    uc = GenerarArticuladoConLLM(
        perfiles=FakePerfilRepo(_perfil(despacho_id)), llm=llm,
    )
    await uc.ejecutar(
        despacho_id=despacho_id,
        tipo=TipoProyecto.LEY,
        tema="Cobertura medicamentos críticos",
    )
    assert "Defensa de la salud pública" in llm.last_user
    assert "tecnico-juridico" in llm.last_user
    assert "TIPO: Proyecto de Ley" in llm.last_user


@pytest.mark.asyncio
async def test_articulado_sin_perfil_no_referencia_perfil() -> None:
    """Sin perfil cargado, el prompt no debe mentir sobre uno."""
    llm = FakeLlmRespondedor(json.dumps({"articulado": ["Artículo 1° — X."]}))
    uc = GenerarArticuladoConLLM(perfiles=FakePerfilRepo(perfil=None), llm=llm)
    await uc.ejecutar(
        despacho_id=uuid4(), tipo=TipoProyecto.RESOLUCION, tema="X",
    )
    assert "PERFIL OPOSITOR" not in llm.last_user


@pytest.mark.asyncio
async def test_articulado_articulado_ausente_devuelve_lista_vacia() -> None:
    """Si el LLM devuelve JSON sin `articulado`, no rompe — devuelve []."""
    llm = FakeLlmRespondedor(json.dumps({"otra_cosa": "x"}))
    uc = GenerarArticuladoConLLM(perfiles=FakePerfilRepo(), llm=llm)
    result = await uc.ejecutar(
        despacho_id=uuid4(), tipo=TipoProyecto.LEY, tema="X",
    )
    assert result.articulado == []


# ---------------------------------------------------------------------------
# GenerarFundamentosConLLM
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fundamentos_devuelve_markdown_crudo() -> None:
    """Los fundamentos NO se parsean — el LLM devuelve markdown libre."""
    md = (
        "Sr. Presidente,\n\n"
        "El presente proyecto responde a una demanda concreta...\n\n"
        "Por todo lo expuesto, solicito a mis pares acompañar.\n"
    )
    llm = FakeLlmRespondedor(md)
    uc = GenerarFundamentosConLLM(perfiles=FakePerfilRepo(), llm=llm)
    result = await uc.ejecutar(
        despacho_id=uuid4(),
        tipo=TipoProyecto.LEY,
        tema="X",
        articulado=["Artículo 1° — Y."],
    )
    assert isinstance(result, FundamentosGenerados)
    assert result.fundamentos.startswith("Sr. Presidente,")
    assert "solicito a mis pares" in result.fundamentos


@pytest.mark.asyncio
async def test_fundamentos_articulado_aparece_en_prompt() -> None:
    """El articulado completo debe llegar al LLM."""
    llm = FakeLlmRespondedor("fundamentos ok")
    uc = GenerarFundamentosConLLM(perfiles=FakePerfilRepo(), llm=llm)
    await uc.ejecutar(
        despacho_id=uuid4(),
        tipo=TipoProyecto.COMUNICACION,
        tema="Reforma X",
        articulado=[
            "Artículo 1° — Solicítase al PEN informe sobre A.",
            "Artículo 2° — Solicítase informe sobre B.",
        ],
    )
    assert "Artículo 1° — Solicítase al PEN informe sobre A." in llm.last_user
    assert "Artículo 2° — Solicítase informe sobre B." in llm.last_user
    assert "TIPO: Proyecto de Comunicación" in llm.last_user


@pytest.mark.asyncio
async def test_fundamentos_strip_whitespace_externo() -> None:
    """Espacios en blanco al principio/final del Markdown se limpian."""
    llm = FakeLlmRespondedor("\n\n  Sr. Presidente, etc...  \n\n")
    uc = GenerarFundamentosConLLM(perfiles=FakePerfilRepo(), llm=llm)
    result = await uc.ejecutar(
        despacho_id=uuid4(),
        tipo=TipoProyecto.DECLARACION,
        tema="X",
        articulado=["Artículo 1° — Y."],
    )
    assert result.fundamentos == "Sr. Presidente, etc..."


# ---------------------------------------------------------------------------
# RefinarArticuloConLLM
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refinar_devuelve_texto_strippeado() -> None:
    llm = FakeLlmRespondedor("  Artículo 1° — Versión más técnica.  \n")
    uc = RefinarArticuloConLLM(llm=llm)
    texto, modelo = await uc.ejecutar(
        texto_actual="Artículo 1° — Texto original.",
        instruccion="Hacelo más técnico",
    )
    assert texto == "Artículo 1° — Versión más técnica."
    assert modelo == "fake-test"


@pytest.mark.asyncio
async def test_refinar_pasa_texto_e_instruccion_al_llm() -> None:
    """Tanto el texto como la instrucción del asesor llegan al prompt."""
    llm = FakeLlmRespondedor("Refinado.")
    uc = RefinarArticuloConLLM(llm=llm)
    await uc.ejecutar(
        texto_actual="Artículo original con palabra `clavada`.",
        instruccion="Reemplazá `clavada` por `prevista`",
    )
    assert "clavada" in llm.last_user
    assert "prevista" in llm.last_user
    assert "INSTRUCCIÓN DEL ASESOR" in llm.last_user
