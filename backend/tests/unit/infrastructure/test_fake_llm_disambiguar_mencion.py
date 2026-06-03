"""Tests del `FakeLlmProvider.disambiguar_mencion`.

Heurística sin red. Cubre:

- Match por nombre completo → es_el_legislador=True.
- Señales negativas de identidad ("S.A.", "actor", "futbolista") sin
  señales políticas → es_el_legislador=False.
- Señales políticas explícitas ("diputado", bloque, distrito) sin
  señales negativas → es_el_legislador=True.
- Tono positivo por verbos ("impulsa", "destaca") → POSITIVO + 0.8.
- Tono negativo por verbos ("critica", "denuncia") → NEGATIVO + 0.8.
- Sin verbos → NEUTRO + 0.5.
"""

from __future__ import annotations

from datetime import date

import pytest

from praxis.domain import Bloque, Camara, Legislador, TonoMencion
from praxis.infrastructure.llm.fake import FakeLlmProvider

pytestmark = pytest.mark.unit


def _legislador() -> Legislador:
    return Legislador(
        slug="pjuliano",
        apellido="Juliano",
        nombre="Pablo",
        camara=Camara.HCDN,
        distrito="BUENOS AIRES",
        bloque=Bloque(nombre="DEMOCRACIA PARA SIEMPRE", camara=Camara.HCDN),
        periodo_mandato="2023-2027",
        fecha_inicio_mandato=date(2023, 12, 10),
        fecha_fin_mandato=date(2027, 12, 9),
    )


@pytest.fixture
def llm() -> FakeLlmProvider:
    return FakeLlmProvider()


# ---------------------------------------------------------------------------
# Identidad
# ---------------------------------------------------------------------------


async def test_match_nombre_completo_es_el_legislador(
    llm: FakeLlmProvider,
) -> None:
    r = await llm.disambiguar_mencion(
        legislador=_legislador(),
        alias_matcheado="Pablo Juliano",
        snippet="Pablo Juliano dijo algo neutral.",
        titulo_articulo="Nota cualquiera",
    )
    assert r.es_el_legislador is True


async def test_senales_negativas_descartan(llm: FakeLlmProvider) -> None:
    r = await llm.disambiguar_mencion(
        legislador=_legislador(),
        alias_matcheado="Juliano",
        snippet="La empresa Juliano S.A. anunció una expansión.",
        titulo_articulo="Negocios y empresas",
    )
    assert r.es_el_legislador is False


async def test_contexto_politico_confirma(llm: FakeLlmProvider) -> None:
    r = await llm.disambiguar_mencion(
        legislador=_legislador(),
        alias_matcheado="Juliano",
        snippet="El diputado Juliano rechazó la propuesta del oficialismo.",
        titulo_articulo="Sesión en Diputados",
    )
    assert r.es_el_legislador is True


async def test_distrito_en_snippet_confirma(llm: FakeLlmProvider) -> None:
    r = await llm.disambiguar_mencion(
        legislador=_legislador(),
        alias_matcheado="Juliano",
        snippet="Juliano, referente bonaerense, opinó sobre el caso.",
        titulo_articulo="BUENOS AIRES tras la sesión",
    )
    assert r.es_el_legislador is True


# ---------------------------------------------------------------------------
# Tono
# ---------------------------------------------------------------------------


async def test_tono_positivo_por_verbo(llm: FakeLlmProvider) -> None:
    r = await llm.disambiguar_mencion(
        legislador=_legislador(),
        alias_matcheado="Pablo Juliano",
        snippet="Pablo Juliano impulsa una nueva ley de educación.",
        titulo_articulo="Educación",
    )
    assert r.tono == TonoMencion.POSITIVO
    assert r.confianza_tono == 0.8


async def test_tono_negativo_por_verbo(llm: FakeLlmProvider) -> None:
    r = await llm.disambiguar_mencion(
        legislador=_legislador(),
        alias_matcheado="Pablo Juliano",
        snippet="Pablo Juliano critica al ministro por la inflación.",
        titulo_articulo="Política",
    )
    assert r.tono == TonoMencion.NEGATIVO
    assert r.confianza_tono == 0.8


async def test_tono_neutro_sin_senales(llm: FakeLlmProvider) -> None:
    r = await llm.disambiguar_mencion(
        legislador=_legislador(),
        alias_matcheado="Pablo Juliano",
        snippet="Pablo Juliano participó del encuentro junto a otros legisladores.",
        titulo_articulo="Encuentro político",
    )
    assert r.tono == TonoMencion.NEUTRO
    assert r.confianza_tono == 0.5


async def test_razon_no_excede_200_chars(llm: FakeLlmProvider) -> None:
    r = await llm.disambiguar_mencion(
        legislador=_legislador(),
        alias_matcheado="Juliano",
        snippet="x" * 500,
        titulo_articulo="y" * 500,
    )
    assert len(r.razon) <= 200
