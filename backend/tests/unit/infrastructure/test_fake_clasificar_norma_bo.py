"""Tests del `FakeLlmProvider.clasificar_norma_bo`.

Cubren:
- Clasificación por keywords sobre sumario + organismo.
- `area_tematica = OTROS` cuando no hay match.
- Palabras clave deduplicadas y limitadas a 5.
- Detección de referencias legales (Ley NNN, Decreto NNN/AAAA,
  Resolución NNN/AAAA).
- `afecta_expedientes_hcdn` derivado de referencias o mención de
  "expediente".
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from praxis.domain import (
    AreaTematica,
    ClasificacionNormaBOResult,
    NormaBO,
    SeccionBO,
    hash_sumario,
)
from praxis.infrastructure.llm.fake import FakeLlmProvider

pytestmark = pytest.mark.unit


def _norma(
    *,
    sumario: str = "Modifica régimen jubilatorio docente",
    organismo: str = "Poder Ejecutivo Nacional",
    tipo: str = "Decreto",
    numero: str = "412/2026",
) -> NormaBO:
    return NormaBO(
        id=None,
        fecha_publicacion=date(2026, 6, 1),
        seccion=SeccionBO.LEGISLACION,
        tipo_norma=tipo,
        numero_norma=numero,
        organismo_emisor=organismo,
        sumario=sumario,
        url_oficial="https://www.boletinoficial.gob.ar/det/x",
        hash_sumario=hash_sumario(sumario),
        capturado_en=datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# Áreas temáticas por keywords
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sumario, organismo, area_esperada",
    [
        (
            "Modifica obras sociales para personas con discapacidad",
            "MINISTERIO DE SALUD",
            AreaTematica.SALUD,
        ),
        (
            "Aprueba reglamentación de docentes universitarios",
            "MINISTERIO DE EDUCACION",
            AreaTematica.EDUCACION,
        ),
        (
            "Modifica régimen jubilatorio de trabajadores autónomos",
            "MINISTERIO DE TRABAJO",
            AreaTematica.TRABAJO,
        ),
        (
            "Aprueba protocolo policial",
            "MINISTERIO DE SEGURIDAD",
            AreaTematica.SEGURIDAD,
        ),
        (
            "Convenio internacional con Brasil",
            "CANCILLERIA",
            AreaTematica.RELACIONES_EXTERIORES,
        ),
        (
            "Reglamenta tributario para exportación de granos",
            "MINISTERIO DE ECONOMIA",
            AreaTematica.ECONOMIA,
        ),
    ],
)
async def test_clasifica_por_keywords(
    sumario: str, organismo: str, area_esperada: AreaTematica,
) -> None:
    provider = FakeLlmProvider()
    norma = _norma(sumario=sumario, organismo=organismo)
    resultado = await provider.clasificar_norma_bo(norma)
    assert resultado.area_tematica == area_esperada


async def test_devuelve_otros_si_no_matchea_nada() -> None:
    provider = FakeLlmProvider()
    norma = _norma(
        sumario="Aprueba registro de marca XYZ",
        organismo="INPI",
    )
    resultado = await provider.clasificar_norma_bo(norma)
    assert resultado.area_tematica == AreaTematica.OTROS


# ---------------------------------------------------------------------------
# Palabras clave
# ---------------------------------------------------------------------------


async def test_palabras_clave_se_deduplican_y_limitan_a_5() -> None:
    provider = FakeLlmProvider()
    # Sumario denso en términos de salud para forzar muchos matches.
    norma = _norma(
        sumario=(
            "Hospital público otorga medicación. Sistema sanitario "
            "atiende enfermedades. Profesionales hospital atienden "
            "pacientes con discapacidad."
        ),
        organismo="MINISTERIO DE SALUD",
    )
    resultado = await provider.clasificar_norma_bo(norma)
    assert resultado.area_tematica == AreaTematica.SALUD
    assert len(resultado.palabras_clave) <= 5
    assert len(set(resultado.palabras_clave)) == len(resultado.palabras_clave)


# ---------------------------------------------------------------------------
# Referencias legales
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "texto, esperadas",
    [
        (
            "Modifica el artículo 12 de la Ley 27.812",
            ["Ley 27.812"],
        ),
        (
            "Deroga el Decreto 412/2026 y modifica la Resolución 88/2026",
            ["Decreto 412/2026", "Resolución 88/2026"],
        ),
        (
            "Sin referencias legales en este texto.",
            [],
        ),
        (
            "Ley N° 24660 sobre ejecución penal",
            ["Ley 24660"],
        ),
    ],
)
async def test_detecta_referencias_legales(
    texto: str, esperadas: list[str],
) -> None:
    provider = FakeLlmProvider()
    norma = _norma(sumario=texto)
    resultado = await provider.clasificar_norma_bo(norma)
    assert resultado.referencias_legales == esperadas


async def test_referencias_legales_deduplican() -> None:
    provider = FakeLlmProvider()
    norma = _norma(
        sumario=(
            "Modifica Ley 27.812. Y también modifica Ley 27.812 en su "
            "artículo 3. Ver Ley 27.812 párrafo final."
        ),
    )
    resultado = await provider.clasificar_norma_bo(norma)
    assert resultado.referencias_legales == ["Ley 27.812"]


# ---------------------------------------------------------------------------
# afecta_expedientes_hcdn
# ---------------------------------------------------------------------------


async def test_afecta_hcdn_true_cuando_hay_referencias() -> None:
    provider = FakeLlmProvider()
    norma = _norma(
        sumario="Modifica el artículo 12 de la Ley 27.812",
    )
    resultado = await provider.clasificar_norma_bo(norma)
    assert resultado.afecta_expedientes_hcdn is True


async def test_afecta_hcdn_true_cuando_menciona_expediente() -> None:
    provider = FakeLlmProvider()
    norma = _norma(
        sumario="Resuelve sobre el expediente N° 1247-D-2025",
    )
    resultado = await provider.clasificar_norma_bo(norma)
    assert resultado.afecta_expedientes_hcdn is True


async def test_afecta_hcdn_false_por_default() -> None:
    provider = FakeLlmProvider()
    norma = _norma(
        sumario="Aprueba designación de subsecretario",
    )
    resultado = await provider.clasificar_norma_bo(norma)
    assert resultado.afecta_expedientes_hcdn is False


# ---------------------------------------------------------------------------
# Tipo de retorno
# ---------------------------------------------------------------------------


async def test_devuelve_clasificacion_norma_bo_result() -> None:
    provider = FakeLlmProvider()
    resultado = await provider.clasificar_norma_bo(_norma())
    assert isinstance(resultado, ClasificacionNormaBOResult)
