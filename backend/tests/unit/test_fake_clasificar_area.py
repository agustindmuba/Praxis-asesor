"""Tests unitarios del clasificador temático del FakeLlmProvider.

Sin DB, sin red — son pruebas de keywords sobre título/sumario.
"""

from __future__ import annotations

import pytest

from praxis.domain import (
    AreaTematica,
    Camara,
    Expediente,
    NumeroExpediente,
    OrigenExpediente,
    TipoExpediente,
)
from praxis.infrastructure.llm.fake import FakeLlmProvider


def _exp(titulo: str, sumario: str | None = None) -> Expediente:
    """Construye un Expediente mínimo para alimentar el clasificador."""
    return Expediente(
        numero=NumeroExpediente(
            numero=1,
            origen=OrigenExpediente.DIPUTADO,
            anio=2025,
            camara=Camara.HCDN,
        ),
        tipo=TipoExpediente.PROYECTO_LEY,
        titulo=titulo,
        sumario=sumario,
    )


@pytest.fixture
def provider() -> FakeLlmProvider:
    return FakeLlmProvider()


async def test_salud(provider: FakeLlmProvider) -> None:
    exp = _exp("LEY DE EMERGENCIA SANITARIA EN HOSPITALES PUBLICOS")
    assert await provider.clasificar_area_tematica(exp) == AreaTematica.SALUD


async def test_educacion(provider: FakeLlmProvider) -> None:
    exp = _exp(
        "DECLARAR LA EDUCACION COMO SERVICIO ESTRATEGICO",
        sumario="Sistema educativo nacional",
    )
    assert await provider.clasificar_area_tematica(exp) == AreaTematica.EDUCACION


async def test_ambiente(provider: FakeLlmProvider) -> None:
    exp = _exp("LEY DE PROTECCION DE HUMEDALES Y BOSQUES NATIVOS")
    assert await provider.clasificar_area_tematica(exp) == AreaTematica.AMBIENTE


async def test_trabajo(provider: FakeLlmProvider) -> None:
    exp = _exp("MOVILIDAD JUBILATORIA Y ASIGNACION FAMILIAR")
    assert await provider.clasificar_area_tematica(exp) == AreaTematica.TRABAJO


async def test_seguridad(provider: FakeLlmProvider) -> None:
    exp = _exp(
        "MODIFICACION DEL CODIGO PENAL - DELITOS VINCULADOS AL NARCOTRAFICO",
    )
    assert await provider.clasificar_area_tematica(exp) == AreaTematica.SEGURIDAD


async def test_derechos_humanos(provider: FakeLlmProvider) -> None:
    exp = _exp("LEY INTEGRAL DE PREVENCION DE FEMICIDIOS Y VIOLENCIA DE GENERO")
    # "femicidio" gana antes que "violencia" porque DDHH está más arriba
    # que seguridad en el orden de buckets para feminicidio.
    assert await provider.clasificar_area_tematica(exp) == AreaTematica.DERECHOS_HUMANOS


async def test_transporte(provider: FakeLlmProvider) -> None:
    exp = _exp("RECUPERACION DE LA RED FERROVIARIA DE PASAJEROS")
    assert await provider.clasificar_area_tematica(exp) == AreaTematica.TRANSPORTE


async def test_infraestructura(provider: FakeLlmProvider) -> None:
    exp = _exp(
        "PROGRAMA DE VIVIENDAS SOCIALES Y CONEXION A AGUA POTABLE",
    )
    assert await provider.clasificar_area_tematica(exp) == AreaTematica.INFRAESTRUCTURA


async def test_justicia(provider: FakeLlmProvider) -> None:
    exp = _exp(
        "REFORMA DEL CODIGO PROCESAL PENAL DE LA NACION",
    )
    assert await provider.clasificar_area_tematica(exp) == AreaTematica.JUSTICIA


async def test_relaciones_exteriores(provider: FakeLlmProvider) -> None:
    exp = _exp(
        "APRUEBASE EL TRATADO DE COOPERACION INTERNACIONAL CON CHILE",
    )
    assert await provider.clasificar_area_tematica(exp) == AreaTematica.RELACIONES_EXTERIORES


async def test_economia(provider: FakeLlmProvider) -> None:
    exp = _exp("MODIFICACION DEL REGIMEN TARIFARIO DE ZONA FRIA")
    assert await provider.clasificar_area_tematica(exp) == AreaTematica.ECONOMIA


async def test_otros_cuando_no_matchea(provider: FakeLlmProvider) -> None:
    exp = _exp("HOMENAJE A LA BIBLIOTECA NACIONAL EN SU ANIVERSARIO")
    assert await provider.clasificar_area_tematica(exp) == AreaTematica.OTROS


async def test_usa_sumario_no_solo_titulo(provider: FakeLlmProvider) -> None:
    """El sumario también pesa, no solo el título."""
    exp = _exp(
        "PROYECTO MISCELANEO",
        sumario="Establece el plan nacional de vacunacion obligatoria",
    )
    assert await provider.clasificar_area_tematica(exp) == AreaTematica.SALUD


async def test_es_case_insensitive_y_sin_tildes(provider: FakeLlmProvider) -> None:
    """El portal usa mayúsculas sin tildes; el clasificador acepta ambos."""
    exp1 = _exp("Régimen de Educación Inicial")
    exp2 = _exp("REGIMEN DE EDUCACION INICIAL")
    assert (
        await provider.clasificar_area_tematica(exp1)
        == await provider.clasificar_area_tematica(exp2)
        == AreaTematica.EDUCACION
    )
