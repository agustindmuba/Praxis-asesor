"""Tests unitarios de `BuscarExpediente`.

Usamos fakes explícitos del puerto `FuenteExpedientes` en lugar de `MagicMock`
para que los tests respeten el contrato y sean legibles.
"""

from __future__ import annotations

import pytest

from praxis.application.ports import FuenteExpedientes
from praxis.application.use_cases import BuscarExpediente
from praxis.domain import (
    Camara,
    Expediente,
    ExpedienteNoEncontrado,
    FuenteNoDisponible,
    NumeroExpediente,
    OrigenExpediente,
    TipoExpediente,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeFuente(FuenteExpedientes):
    """Doble del puerto: registra llamadas y devuelve lo configurado.

    Configurable con un `Expediente` a devolver, una excepción a lanzar,
    o ninguna (lo que dispara ExpedienteNoEncontrado por default).
    """

    def __init__(
        self,
        camara: Camara,
        devolver: Expediente | None = None,
        lanzar: Exception | None = None,
    ) -> None:
        self._camara = camara
        self._devolver = devolver
        self._lanzar = lanzar
        self.llamadas: list[tuple[NumeroExpediente, TipoExpediente | None]] = []

    async def buscar_por_numero(
        self,
        numero: NumeroExpediente,
        tipo: TipoExpediente | None = None,
    ) -> Expediente:
        self.llamadas.append((numero, tipo))
        if self._lanzar is not None:
            raise self._lanzar
        if numero.camara != self._camara:
            raise ValueError(
                f"FakeFuente({self._camara}) recibió número con cámara {numero.camara}"
            )
        if self._devolver is None:
            raise ExpedienteNoEncontrado(str(numero), fuente=str(self._camara))
        return self._devolver


def _expediente_dummy(numero: NumeroExpediente) -> Expediente:
    """Helper: arma un Expediente mínimo para devolver desde un fake."""
    return Expediente(
        numero=numero,
        tipo=TipoExpediente.PROYECTO_LEY,
        titulo="Dummy",
    )


def _numero_hcdn() -> NumeroExpediente:
    return NumeroExpediente.parse_hcdn("100-D-2024")


def _numero_hsn() -> NumeroExpediente:
    return NumeroExpediente(
        numero=50,
        origen=OrigenExpediente.SENADOR,
        anio=2024,
        camara=Camara.HSN,
    )


# ---------------------------------------------------------------------------
# Camino feliz: rutea correctamente
# ---------------------------------------------------------------------------


async def test_camara_hcdn_va_al_puerto_hcdn() -> None:
    numero = _numero_hcdn()
    hcdn = FakeFuente(Camara.HCDN, devolver=_expediente_dummy(numero))
    hsn = FakeFuente(Camara.HSN)
    use_case = BuscarExpediente(hcdn=hcdn, hsn=hsn)

    resultado = await use_case.execute(numero)

    assert resultado.numero == numero
    assert hcdn.llamadas == [(numero, None)]
    assert hsn.llamadas == []  # HSN no fue tocado.


async def test_camara_hsn_va_al_puerto_hsn() -> None:
    numero = _numero_hsn()
    hcdn = FakeFuente(Camara.HCDN)
    hsn = FakeFuente(Camara.HSN, devolver=_expediente_dummy(numero))
    use_case = BuscarExpediente(hcdn=hcdn, hsn=hsn)

    resultado = await use_case.execute(numero, tipo=TipoExpediente.PROYECTO_LEY)

    assert resultado.numero == numero
    assert hsn.llamadas == [(numero, TipoExpediente.PROYECTO_LEY)]
    assert hcdn.llamadas == []


async def test_tipo_se_propaga_al_puerto() -> None:
    """El parámetro `tipo` llega al puerto destino tal cual."""
    numero = _numero_hsn()
    hcdn = FakeFuente(Camara.HCDN)
    hsn = FakeFuente(Camara.HSN, devolver=_expediente_dummy(numero))
    use_case = BuscarExpediente(hcdn=hcdn, hsn=hsn)

    await use_case.execute(numero, tipo=TipoExpediente.PROYECTO_DECLARACION)

    assert hsn.llamadas[0][1] == TipoExpediente.PROYECTO_DECLARACION


async def test_tipo_default_none_pasa_none() -> None:
    """Si no se pasa `tipo`, llega None al puerto (útil para HCDN)."""
    numero = _numero_hcdn()
    hcdn = FakeFuente(Camara.HCDN, devolver=_expediente_dummy(numero))
    hsn = FakeFuente(Camara.HSN)
    use_case = BuscarExpediente(hcdn=hcdn, hsn=hsn)

    await use_case.execute(numero)

    assert hcdn.llamadas[0][1] is None


# ---------------------------------------------------------------------------
# Errores propagados sin reemplazo
# ---------------------------------------------------------------------------


async def test_expediente_no_encontrado_se_propaga() -> None:
    numero = _numero_hcdn()
    hcdn = FakeFuente(Camara.HCDN)  # devolver=None → lanza ExpedienteNoEncontrado.
    hsn = FakeFuente(Camara.HSN)
    use_case = BuscarExpediente(hcdn=hcdn, hsn=hsn)

    with pytest.raises(ExpedienteNoEncontrado):
        await use_case.execute(numero)


async def test_fuente_no_disponible_se_propaga() -> None:
    numero = _numero_hsn()
    hcdn = FakeFuente(Camara.HCDN)
    hsn = FakeFuente(Camara.HSN, lanzar=FuenteNoDisponible("HSN", "timeout persistente"))
    use_case = BuscarExpediente(hcdn=hcdn, hsn=hsn)

    with pytest.raises(FuenteNoDisponible):
        await use_case.execute(numero, tipo=TipoExpediente.PROYECTO_LEY)


async def test_value_error_del_puerto_se_propaga() -> None:
    """Si el puerto valida y lanza ValueError, llega tal cual."""
    numero = _numero_hsn()
    hcdn = FakeFuente(Camara.HCDN)
    hsn = FakeFuente(Camara.HSN, lanzar=ValueError("tipo requerido"))
    use_case = BuscarExpediente(hcdn=hcdn, hsn=hsn)

    with pytest.raises(ValueError, match="tipo"):
        await use_case.execute(numero)


# ---------------------------------------------------------------------------
# Composition root: los puertos van por nombre (kw-only)
# ---------------------------------------------------------------------------


def test_constructor_exige_keyword_args() -> None:
    """Garantía de que no se pueda invertir HCDN/HSN por accidente."""
    hcdn = FakeFuente(Camara.HCDN)
    hsn = FakeFuente(Camara.HSN)
    with pytest.raises(TypeError):
        BuscarExpediente(hcdn, hsn)  # type: ignore[misc]  # falta keyword
