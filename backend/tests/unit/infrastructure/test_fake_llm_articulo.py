"""Tests del `FakeLlmProvider.generar_bajada_propia` y `clasificar_articulo`.

Heurísticas sin red. Verifican que:

- `generar_bajada_propia` reformula título + primera frase rica del
  cuerpo, capa a `MAX_BAJADA_PROPIA_CHARS` con elipsis, y devuelve sólo
  el título si no hay frase rica disponible.
- `clasificar_articulo` reusa los buckets de keywords del provider y
  devuelve el área correcta + palabras clave que efectivamente
  matchearon. Sin matches → OTROS + [].
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from praxis.domain import MAX_BAJADA_PROPIA_CHARS, AreaTematica, Articulo
from praxis.infrastructure.llm.fake import FakeLlmProvider

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _articulo(*, titulo: str = "Título de prueba") -> Articulo:
    return Articulo(
        id=uuid4(),
        fuente_id=uuid4(),
        url="https://medio.com.ar/articulo-1",
        titulo=titulo,
        publicado_en=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
        capturado_en=datetime(2026, 6, 1, 12, 5, tzinfo=UTC),
    )


@pytest.fixture
def llm() -> FakeLlmProvider:
    return FakeLlmProvider()


# ---------------------------------------------------------------------------
# generar_bajada_propia
# ---------------------------------------------------------------------------


async def test_bajada_combina_titulo_y_primera_frase(
    llm: FakeLlmProvider,
) -> None:
    art = _articulo(titulo="Diputados aprobó la ley educativa")
    texto = (
        "La cámara dio media sanción al proyecto con 130 votos a favor "
        "y 80 en contra. Ahora pasa al Senado para su discusión."
    )
    bajada = await llm.generar_bajada_propia(art, texto_articulo=texto)
    assert "Diputados aprobó la ley educativa" in bajada
    assert "130 votos" in bajada


async def test_bajada_se_capa_con_elipsis(llm: FakeLlmProvider) -> None:
    art = _articulo(titulo="Titulo")
    # Hacemos una primera frase larguísima que rompa el cap.
    texto = "x" * 1000 + ". y" * 100
    bajada = await llm.generar_bajada_propia(art, texto_articulo=texto)
    assert len(bajada) <= MAX_BAJADA_PROPIA_CHARS
    if len(bajada) == MAX_BAJADA_PROPIA_CHARS:
        # Si fue exactamente al cap, debería haber elipsis.
        assert bajada.endswith("…")


async def test_bajada_sin_cuerpo_devuelve_titulo(
    llm: FakeLlmProvider,
) -> None:
    art = _articulo(titulo="Solo título disponible")
    bajada = await llm.generar_bajada_propia(art, texto_articulo="")
    assert bajada == "Solo título disponible"


async def test_bajada_con_cuerpo_muy_corto_devuelve_titulo(
    llm: FakeLlmProvider,
) -> None:
    """Si el cuerpo no tiene ninguna frase ≥40 chars hasta el primer
    punto, el Fake conservador devuelve sólo el título."""
    art = _articulo(titulo="Sólo título")
    bajada = await llm.generar_bajada_propia(
        art, texto_articulo="Hola. Chau.",
    )
    assert bajada == "Sólo título"


# ---------------------------------------------------------------------------
# clasificar_articulo
# ---------------------------------------------------------------------------


async def test_clasifica_a_educacion_por_keyword(
    llm: FakeLlmProvider,
) -> None:
    art = _articulo(titulo="Avance del proyecto")
    texto = (
        "La nueva ley de educación pública busca extender la jornada "
        "escolar en escuelas primarias del país."
    )
    r = await llm.clasificar_articulo(art, texto_articulo=texto)
    assert r.area_tematica == AreaTematica.EDUCACION
    assert r.palabras_clave  # al menos 1


async def test_clasifica_a_salud_por_keyword(llm: FakeLlmProvider) -> None:
    art = _articulo(titulo="Atención médica")
    texto = (
        "El hospital público anunció nuevos turnos para atención "
        "primaria de salud en zonas vulnerables."
    )
    r = await llm.clasificar_articulo(art, texto_articulo=texto)
    assert r.area_tematica == AreaTematica.SALUD


async def test_clasifica_a_otros_sin_match(llm: FakeLlmProvider) -> None:
    art = _articulo(titulo="Nota breve")
    texto = "qwerty asdf zxcv plumbi xafargatos."
    r = await llm.clasificar_articulo(art, texto_articulo=texto)
    assert r.area_tematica == AreaTematica.OTROS
    assert r.palabras_clave == []


async def test_palabras_clave_dedup_y_max_5(llm: FakeLlmProvider) -> None:
    art = _articulo(titulo="Nota larga")
    # Repetimos la misma keyword muchas veces para asegurar dedup y cap.
    texto = " ".join(["educación pública escolar primaria docente "] * 20)
    r = await llm.clasificar_articulo(art, texto_articulo=texto)
    # Dedup conservando orden, cap 5.
    assert len(r.palabras_clave) <= 5
    assert len(r.palabras_clave) == len(set(r.palabras_clave))
