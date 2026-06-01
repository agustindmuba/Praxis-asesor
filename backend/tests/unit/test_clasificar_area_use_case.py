"""Test del caso de uso ClasificarExpedienteTematicamente.

Mocks de los puertos. Verifica cache hit / cache miss / 404.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from praxis.application.use_cases import ClasificarExpedienteTematicamente
from praxis.domain import (
    AreaTematica,
    Camara,
    Expediente,
    ExpedienteAreaTematica,
    ExpedienteNoEncontrado,
    NumeroExpediente,
    OrigenExpediente,
    TipoExpediente,
)


def _expediente() -> Expediente:
    return Expediente(
        id=uuid4(),
        numero=NumeroExpediente(
            numero=1, origen=OrigenExpediente.DIPUTADO, anio=2025, camara=Camara.HCDN
        ),
        tipo=TipoExpediente.PROYECTO_LEY,
        titulo="Educacion",
    )


async def test_cache_hit_no_llama_al_llm() -> None:
    exp = _expediente()
    assert exp.id is not None
    cacheado = ExpedienteAreaTematica(
        id=uuid4(),
        expediente_id=exp.id,
        area=AreaTematica.EDUCACION,
        modelo="fake-keywords",
        generado_en=datetime.now(),
    )
    expedientes = AsyncMock()
    clasificaciones = AsyncMock()
    clasificaciones.buscar_por_expediente.return_value = cacheado
    llm = AsyncMock()
    llm.nombre_modelo = "fake-keywords"

    uc = ClasificarExpedienteTematicamente(
        expedientes=expedientes, clasificaciones=clasificaciones, llm=llm,
    )
    result = await uc.execute(exp.id)

    assert result is cacheado
    llm.clasificar_area_tematica.assert_not_called()
    expedientes.buscar_por_id.assert_not_called()
    clasificaciones.crear.assert_not_called()


async def test_cache_miss_llama_y_persiste() -> None:
    exp = _expediente()
    assert exp.id is not None
    expedientes = AsyncMock()
    expedientes.buscar_por_id.return_value = exp
    clasificaciones = AsyncMock()
    clasificaciones.buscar_por_expediente.return_value = None
    # Para hacer transparente lo que devuelve `crear`, devolvemos el mismo
    # objeto que recibe.
    clasificaciones.crear.side_effect = lambda c: c
    llm = AsyncMock()
    llm.nombre_modelo = "fake-keywords"
    llm.clasificar_area_tematica.return_value = AreaTematica.EDUCACION

    uc = ClasificarExpedienteTematicamente(
        expedientes=expedientes, clasificaciones=clasificaciones, llm=llm,
    )
    result = await uc.execute(exp.id)

    assert result.area == AreaTematica.EDUCACION
    assert result.modelo == "fake-keywords"
    assert result.expediente_id == exp.id
    llm.clasificar_area_tematica.assert_awaited_once_with(exp)
    clasificaciones.crear.assert_awaited_once()


async def test_expediente_inexistente_levanta() -> None:
    expedientes = AsyncMock()
    expedientes.buscar_por_id.return_value = None
    clasificaciones = AsyncMock()
    clasificaciones.buscar_por_expediente.return_value = None
    llm = AsyncMock()
    llm.nombre_modelo = "fake-keywords"

    uc = ClasificarExpedienteTematicamente(
        expedientes=expedientes, clasificaciones=clasificaciones, llm=llm,
    )
    with pytest.raises(ExpedienteNoEncontrado):
        await uc.execute(uuid4())
