"""Tests del caso de uso `DetectarMencionesEnArticulo`.

Orquestador puro entre detector regex (pase 1) y LLM disambiguator
(pase 2). Verifica:

- Si regex no encuentra candidatos → lista vacía, LLM no se llama.
- Si LLM dice `es_el_legislador=False` → se descarta esa mención.
- Si regex encuentra varios candidatos del MISMO legislador → 1 sola
  Mencion, la de mejor score (`confianza_regex * confianza_tono`).
- Varios legisladores en el mismo artículo → 1 Mencion por cada uno.
- Snippet cap a `MAX_SNIPPET_CONTEXTO_CHARS`.
- `Mencion` lleva `articulo_id`, `legislador_id`, `despacho_id`,
  `alcance_medio`, `detectado_en` correctos.
- Si articulo.id es None → ValueError.
- Texto vacío → lista vacía, LLM no se llama.

NO toca DB. Usa un `LlmProvider` stub que registra llamadas.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from praxis.application.use_cases import (
    DetectarMencionesEnArticulo,
    LegisladorAMonitorear,
)
from praxis.domain import (
    AlcanceMedio,
    Articulo,
    Bloque,
    Camara,
    DisambiguacionMencion,
    Legislador,
    TonoMencion,
)
from praxis.infrastructure.llm.fake import FakeLlmProvider

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _legislador(
    *,
    nombre: str = "Pablo",
    apellido: str = "Juliano",
    slug: str = "pjuliano",
    distrito: str = "BUENOS AIRES",
    bloque: str = "DEMOCRACIA PARA SIEMPRE",
) -> Legislador:
    return Legislador(
        slug=slug,
        apellido=apellido,
        nombre=nombre,
        camara=Camara.HCDN,
        distrito=distrito,
        bloque=Bloque(nombre=bloque, camara=Camara.HCDN),
        periodo_mandato="2023-2027",
        fecha_inicio_mandato=date(2023, 12, 10),
        fecha_fin_mandato=date(2027, 12, 9),
    )


def _articulo(*, titulo: str = "Sesión en Diputados") -> Articulo:
    return Articulo(
        id=uuid4(),
        fuente_id=uuid4(),
        url="https://medio.com.ar/nota-1",
        titulo=titulo,
        publicado_en=datetime(2026, 6, 1, 9, 0, tzinfo=UTC),
        capturado_en=datetime(2026, 6, 1, 9, 5, tzinfo=UTC),
    )


class _LlmStub:
    """Stub controlable que registra llamadas y devuelve un resultado fijo."""

    def __init__(self, *, resultado: DisambiguacionMencion) -> None:
        self._resultado = resultado
        self.llamadas: list[tuple[str, str, str]] = []

    @property
    def nombre_modelo(self) -> str:
        return "stub"

    async def disambiguar_mencion(
        self, *, legislador, alias_matcheado, snippet, titulo_articulo,
    ) -> DisambiguacionMencion:
        self.llamadas.append((alias_matcheado, snippet, titulo_articulo))
        _ = legislador
        return self._resultado


# ---------------------------------------------------------------------------
# Casos felices
# ---------------------------------------------------------------------------


async def test_un_match_un_legislador_devuelve_una_mencion() -> None:
    art = _articulo()
    leg = _legislador()
    despacho_id = uuid4()
    legislador_id = uuid4()
    llm = _LlmStub(
        resultado=DisambiguacionMencion(
            es_el_legislador=True,
            tono=TonoMencion.POSITIVO,
            confianza_tono=0.9,
            razon="Verbo positivo.",
        ),
    )
    uc = DetectarMencionesEnArticulo(llm=llm)  # type: ignore[arg-type]

    menciones = await uc.ejecutar(
        articulo=art,
        texto_articulo=(
            "El diputado Pablo Juliano impulsó hoy una nueva ley educativa."
        ),
        legisladores=[
            LegisladorAMonitorear(
                legislador=leg,
                legislador_id=legislador_id,
                despacho_id=despacho_id,
            ),
        ],
        alcance_medio=AlcanceMedio.NACIONAL,
    )

    assert len(menciones) == 1
    m = menciones[0]
    assert m.legislador_id == legislador_id
    assert m.despacho_id == despacho_id
    assert m.articulo_id == art.id
    assert m.tono == TonoMencion.POSITIVO
    assert m.confianza_tono == 0.9
    assert m.alcance_medio == AlcanceMedio.NACIONAL
    assert "Pablo Juliano" in m.snippet_contexto
    assert m.notificada is False
    assert m.detectado_en is not None


async def test_si_llm_descarta_no_se_construye_mencion() -> None:
    art = _articulo()
    leg = _legislador()
    llm = _LlmStub(
        resultado=DisambiguacionMencion(
            es_el_legislador=False,
            tono=TonoMencion.NEUTRO,
            confianza_tono=0.5,
            razon="Homónimo.",
        ),
    )
    uc = DetectarMencionesEnArticulo(llm=llm)  # type: ignore[arg-type]

    menciones = await uc.ejecutar(
        articulo=art,
        texto_articulo="La empresa Juliano S.A. anuncia inversión.",
        legisladores=[
            LegisladorAMonitorear(
                legislador=leg,
                legislador_id=uuid4(),
                despacho_id=uuid4(),
            ),
        ],
        alcance_medio=AlcanceMedio.NACIONAL,
    )

    assert menciones == []
    # El LLM SÍ fue llamado (es la única manera de saber que descarta).
    assert len(llm.llamadas) >= 1


async def test_multiples_matches_del_mismo_legislador_devuelve_una_sola() -> None:
    """Si el regex encuentra al legislador en varias posiciones, el
    caso de uso devuelve 1 sola Mencion (la de mayor score)."""
    art = _articulo()
    leg = _legislador()
    despacho_id = uuid4()
    legislador_id = uuid4()
    llm = _LlmStub(
        resultado=DisambiguacionMencion(
            es_el_legislador=True,
            tono=TonoMencion.NEUTRO,
            confianza_tono=0.7,
            razon="",
        ),
    )
    uc = DetectarMencionesEnArticulo(llm=llm)  # type: ignore[arg-type]

    texto = (
        "Pablo Juliano dijo X. Más tarde el diputado Juliano agregó Y. "
        "Pablo Juliano cerró la conferencia."
    )
    menciones = await uc.ejecutar(
        articulo=art,
        texto_articulo=texto,
        legisladores=[
            LegisladorAMonitorear(
                legislador=leg,
                legislador_id=legislador_id,
                despacho_id=despacho_id,
            ),
        ],
        alcance_medio=AlcanceMedio.PROVINCIAL,
    )

    assert len(menciones) == 1
    # Se llama al LLM una vez por candidato (3 candidatos).
    assert len(llm.llamadas) == 3


async def test_dos_legisladores_distintos_dos_menciones() -> None:
    art = _articulo()
    leg1 = _legislador()
    leg2 = _legislador(
        nombre="Cristina",
        apellido="Fernandez",
        slug="cfernandez",
        distrito="BUENOS AIRES",
        bloque="UNION POR LA PATRIA",
    )
    llm = _LlmStub(
        resultado=DisambiguacionMencion(
            es_el_legislador=True,
            tono=TonoMencion.NEUTRO,
            confianza_tono=0.7,
            razon="",
        ),
    )
    uc = DetectarMencionesEnArticulo(llm=llm)  # type: ignore[arg-type]

    menciones = await uc.ejecutar(
        articulo=art,
        texto_articulo=(
            "El diputado Pablo Juliano respondió en el recinto a "
            "Cristina Fernandez sobre el proyecto previsional."
        ),
        legisladores=[
            LegisladorAMonitorear(
                legislador=leg1,
                legislador_id=uuid4(),
                despacho_id=uuid4(),
            ),
            LegisladorAMonitorear(
                legislador=leg2,
                legislador_id=uuid4(),
                despacho_id=uuid4(),
            ),
        ],
        alcance_medio=AlcanceMedio.NACIONAL,
    )

    assert len(menciones) == 2
    apellidos = sorted(
        m.legislador_id for m in menciones
    )
    assert len(set(apellidos)) == 2


# ---------------------------------------------------------------------------
# Snippet
# ---------------------------------------------------------------------------


async def test_snippet_capado_a_max_chars() -> None:
    from praxis.domain import MAX_SNIPPET_CONTEXTO_CHARS

    art = _articulo()
    leg = _legislador()
    llm = _LlmStub(
        resultado=DisambiguacionMencion(
            es_el_legislador=True,
            tono=TonoMencion.NEUTRO,
            confianza_tono=0.6,
            razon="",
        ),
    )
    uc = DetectarMencionesEnArticulo(llm=llm)  # type: ignore[arg-type]

    texto = "x" * 500 + " Pablo Juliano " + "y" * 500
    menciones = await uc.ejecutar(
        articulo=art,
        texto_articulo=texto,
        legisladores=[
            LegisladorAMonitorear(
                legislador=leg,
                legislador_id=uuid4(),
                despacho_id=uuid4(),
            ),
        ],
        alcance_medio=AlcanceMedio.NACIONAL,
    )

    assert len(menciones) == 1
    assert len(menciones[0].snippet_contexto) <= MAX_SNIPPET_CONTEXTO_CHARS


# ---------------------------------------------------------------------------
# Negativos
# ---------------------------------------------------------------------------


async def test_texto_vacio_no_llama_llm() -> None:
    art = _articulo()
    leg = _legislador()
    llm = _LlmStub(
        resultado=DisambiguacionMencion(
            es_el_legislador=True,
            tono=TonoMencion.NEUTRO,
            confianza_tono=0.5,
            razon="",
        ),
    )
    uc = DetectarMencionesEnArticulo(llm=llm)  # type: ignore[arg-type]

    menciones = await uc.ejecutar(
        articulo=art,
        texto_articulo="",
        legisladores=[
            LegisladorAMonitorear(
                legislador=leg,
                legislador_id=uuid4(),
                despacho_id=uuid4(),
            ),
        ],
        alcance_medio=AlcanceMedio.NACIONAL,
    )

    assert menciones == []
    assert llm.llamadas == []


async def test_articulo_sin_id_lanza() -> None:
    art = Articulo(
        id=None,  # no persistido
        fuente_id=uuid4(),
        url="https://medio.com.ar/x",
        titulo="x",
    )
    leg = _legislador()
    llm = FakeLlmProvider()
    uc = DetectarMencionesEnArticulo(llm=llm)

    with pytest.raises(ValueError, match=r"articulo\.id"):
        await uc.ejecutar(
            articulo=art,
            texto_articulo="Pablo Juliano dijo algo.",
            legisladores=[
                LegisladorAMonitorear(
                    legislador=leg,
                    legislador_id=uuid4(),
                    despacho_id=uuid4(),
                ),
            ],
            alcance_medio=AlcanceMedio.NACIONAL,
        )


async def test_texto_sin_mencion_devuelve_vacio_sin_llamar_llm() -> None:
    art = _articulo()
    leg = _legislador()
    llm = _LlmStub(
        resultado=DisambiguacionMencion(
            es_el_legislador=True,
            tono=TonoMencion.NEUTRO,
            confianza_tono=0.5,
            razon="",
        ),
    )
    uc = DetectarMencionesEnArticulo(llm=llm)  # type: ignore[arg-type]

    menciones = await uc.ejecutar(
        articulo=art,
        texto_articulo="La inflación de mayo según el INDEC.",
        legisladores=[
            LegisladorAMonitorear(
                legislador=leg,
                legislador_id=uuid4(),
                despacho_id=uuid4(),
            ),
        ],
        alcance_medio=AlcanceMedio.NACIONAL,
    )

    assert menciones == []
    assert llm.llamadas == []


# ---------------------------------------------------------------------------
# Integración Fake completo (regex + Fake LLM end-to-end)
# ---------------------------------------------------------------------------


async def test_integracion_con_fake_llm_real() -> None:
    """Usa el FakeLlmProvider real para verificar la cadena entera."""
    art = _articulo(titulo="Política y Congreso")
    leg = _legislador()
    llm = FakeLlmProvider()
    uc = DetectarMencionesEnArticulo(llm=llm)

    menciones = await uc.ejecutar(
        articulo=art,
        texto_articulo=(
            "El diputado Pablo Juliano impulsa un proyecto de ley con "
            "su bloque para mejorar la educación pública."
        ),
        legisladores=[
            LegisladorAMonitorear(
                legislador=leg,
                legislador_id=uuid4(),
                despacho_id=uuid4(),
            ),
        ],
        alcance_medio=AlcanceMedio.NACIONAL,
    )

    assert len(menciones) == 1
    # Fake LLM debería leer "impulsa" como positivo.
    assert menciones[0].tono == TonoMencion.POSITIVO
