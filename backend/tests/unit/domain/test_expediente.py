"""Tests unitarios de entidades de dominio: Expediente, Firmante, Giro, TramiteEvento."""

from __future__ import annotations

from datetime import date

import pytest

from praxis.domain.expediente import Expediente, Firmante, Giro, TramiteEvento
from praxis.domain.value_objects import (
    Camara,
    EstadoExpediente,
    NumeroExpediente,
    TipoExpediente,
)

pytestmark = pytest.mark.unit


# --- Firmante ----------------------------------------------------------------


def test_firmante_minimo() -> None:
    f = Firmante(nombre="PROPATO, AGUSTINA LUCRECIA")
    assert f.nombre == "PROPATO, AGUSTINA LUCRECIA"
    assert f.orden == 1


def test_firmante_completo() -> None:
    f = Firmante(
        nombre="PROPATO, AGUSTINA LUCRECIA",
        distrito="BUENOS AIRES",
        bloque="UNIÓN POR LA PATRIA",
        orden=2,
    )
    assert f.distrito == "BUENOS AIRES"
    assert f.orden == 2


def test_firmante_nombre_vacio_lanza() -> None:
    with pytest.raises(ValueError, match="nombre"):
        Firmante(nombre="   ")


def test_firmante_orden_invalido_lanza() -> None:
    with pytest.raises(ValueError, match="orden"):
        Firmante(nombre="X", orden=0)


def test_firmante_es_inmutable() -> None:
    f = Firmante(nombre="X")
    with pytest.raises((AttributeError, TypeError)):
        f.nombre = "Y"  # type: ignore[misc]


# --- Giro --------------------------------------------------------------------


def test_giro_minimo() -> None:
    g = Giro(comision="ASUNTOS CONSTITUCIONALES")
    assert g.comision == "ASUNTOS CONSTITUCIONALES"
    assert g.fecha_ingreso is None


def test_giro_con_fechas_validas() -> None:
    g = Giro(
        comision="DE SALUD",
        fecha_ingreso=date(2024, 3, 21),
        fecha_egreso=date(2024, 5, 10),
        orden=1,
    )
    assert g.fecha_egreso == date(2024, 5, 10)


def test_giro_fecha_egreso_anterior_a_ingreso_lanza() -> None:
    with pytest.raises(ValueError, match="fecha_egreso"):
        Giro(
            comision="X",
            fecha_ingreso=date(2024, 5, 10),
            fecha_egreso=date(2024, 3, 1),
        )


def test_giro_comision_vacia_lanza() -> None:
    with pytest.raises(ValueError, match="comision"):
        Giro(comision="")


# --- TramiteEvento -----------------------------------------------------------


def test_tramite_evento_minimo() -> None:
    t = TramiteEvento(
        fecha=date(2024, 4, 1),
        camara=Camara.HCDN,
        evento="GIRO A COMISION",
    )
    assert t.evento == "GIRO A COMISION"
    assert t.detalle is None


def test_tramite_evento_sin_fecha() -> None:
    # Algunos eventos antiguos no tienen fecha registrada.
    t = TramiteEvento(fecha=None, camara=Camara.HSN, evento="ARCHIVADO")
    assert t.fecha is None


def test_tramite_evento_con_fuente_traza() -> None:
    t = TramiteEvento(
        fecha=date(2024, 3, 12),
        camara=Camara.HSN,
        evento="INGRESO A MESA DE ENTRADAS",
        fuente="derived:hsn-stages",
    )
    assert t.fuente == "derived:hsn-stages"


def test_tramite_evento_vacio_lanza() -> None:
    with pytest.raises(ValueError, match="evento"):
        TramiteEvento(fecha=None, camara=Camara.HCDN, evento="")


# --- Expediente --------------------------------------------------------------


def _make_num(camara: Camara = Camara.HCDN) -> NumeroExpediente:
    if camara == Camara.HCDN:
        return NumeroExpediente.parse_hcdn("1497-D-2024")
    return NumeroExpediente.parse_hsn("239/24")


def test_expediente_minimo() -> None:
    e = Expediente(
        numero=_make_num(),
        tipo=TipoExpediente.PROYECTO_LEY,
        titulo="Modificación Ley 25.326",
    )
    assert e.camara == Camara.HCDN
    assert e.estado == EstadoExpediente.DESCONOCIDO
    assert e.firmantes == []
    assert e.autor_principal is None


def test_expediente_camara_es_atajo_de_numero() -> None:
    e_h = Expediente(
        numero=_make_num(Camara.HCDN),
        tipo=TipoExpediente.PROYECTO_LEY,
        titulo="X",
    )
    e_s = Expediente(
        numero=_make_num(Camara.HSN),
        tipo=TipoExpediente.PROYECTO_LEY,
        titulo="Y",
    )
    assert e_h.camara == Camara.HCDN
    assert e_s.camara == Camara.HSN


def test_expediente_titulo_vacio_lanza() -> None:
    with pytest.raises(ValueError, match="titulo"):
        Expediente(numero=_make_num(), tipo=TipoExpediente.PROYECTO_LEY, titulo="  ")


def test_expediente_autor_principal_por_orden() -> None:
    e = Expediente(
        numero=_make_num(),
        tipo=TipoExpediente.PROYECTO_LEY,
        titulo="Algo",
        firmantes=[
            Firmante(nombre="B", orden=2),
            Firmante(nombre="A", orden=1),
            Firmante(nombre="C", orden=3),
        ],
    )
    autor = e.autor_principal
    assert autor is not None
    assert autor.nombre == "A"


def test_expediente_tramite_ordenado_asc_con_sin_fecha_al_final() -> None:
    t1 = TramiteEvento(fecha=date(2024, 5, 1), camara=Camara.HCDN, evento="A")
    t2 = TramiteEvento(fecha=date(2024, 3, 1), camara=Camara.HCDN, evento="B")
    t3 = TramiteEvento(fecha=None, camara=Camara.HCDN, evento="C")
    e = Expediente(
        numero=_make_num(),
        tipo=TipoExpediente.PROYECTO_LEY,
        titulo="X",
        tramite=[t1, t2, t3],
    )
    ordenado = e.tramite_ordenado()
    assert [t.evento for t in ordenado] == ["B", "A", "C"]


def test_expediente_es_mutable() -> None:
    # A propósito mutable (ADR 0002): los casos de uso enriquecen.
    e = Expediente(numero=_make_num(), tipo=TipoExpediente.PROYECTO_LEY, titulo="X")
    e.estado = EstadoExpediente.EN_COMISION
    assert e.estado == EstadoExpediente.EN_COMISION


def test_expediente_lista_firmantes_independiente_entre_instancias() -> None:
    """Regression guard: que `field(default_factory=list)` esté bien (no shared)."""
    e1 = Expediente(numero=_make_num(), tipo=TipoExpediente.PROYECTO_LEY, titulo="X")
    e2 = Expediente(numero=_make_num(), tipo=TipoExpediente.PROYECTO_LEY, titulo="Y")
    e1.firmantes.append(Firmante(nombre="Z"))
    assert e2.firmantes == []


# --- Amendment 1 ADR 0002: expediente_relacionado --------------------------


def test_expediente_expediente_relacionado_default_none() -> None:
    e = Expediente(numero=_make_num(), tipo=TipoExpediente.PROYECTO_LEY, titulo="X")
    assert e.expediente_relacionado is None


def test_expediente_expediente_relacionado_se_puede_setear() -> None:
    # Caso típico: un expediente HCDN vinculado a su contraparte HSN.
    e = Expediente(
        numero=NumeroExpediente.parse_hcdn("100-D-2024"),
        tipo=TipoExpediente.PROYECTO_LEY,
        titulo="Proyecto X",
    )
    e.expediente_relacionado = NumeroExpediente.parse_hsn("50/24")
    assert e.expediente_relacionado is not None
    assert e.expediente_relacionado.camara == Camara.HSN
    assert e.expediente_relacionado.numero == 50


# --- Amendment 1 ADR 0002: caducidad ---------------------------------------


def test_expediente_caducidad_defaults() -> None:
    """Defaults razonables: sin fechas y no prorrogado."""
    e = Expediente(numero=_make_num(), tipo=TipoExpediente.PROYECTO_LEY, titulo="X")
    assert e.fecha_caducidad is None
    assert e.fecha_caducidad_original is None
    assert e.prorrogado is False


def test_expediente_caducidad_setear_con_prorroga() -> None:
    """Caso real: prorrogado una vez por aplicación del 114 bis."""
    e = Expediente(numero=_make_num(), tipo=TipoExpediente.PROYECTO_LEY, titulo="X")
    e.fecha_caducidad_original = date(2025, 2, 28)
    e.fecha_caducidad = date(2027, 2, 28)
    e.prorrogado = True
    assert e.fecha_caducidad_original == date(2025, 2, 28)
    assert e.fecha_caducidad == date(2027, 2, 28)
    assert e.prorrogado is True
