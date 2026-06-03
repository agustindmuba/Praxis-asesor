"""Tests de dominio: `PerfilInteresDespacho`.

Cubren las invariantes del __post_init__: normalización (strip + dedup),
validación de áreas contra el enum conocido, y la lógica de
`fue_editado_despues_de_sembrar`.

Ver `docs/specs/15-resumen-bo-accionable.md` §D1 y
`backend/praxis/domain/perfil_interes_despacho.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from praxis.domain import AreaTematica, PerfilInteresDespacho


class TestPerfilInteresDespachoConstruccion:
    def test_perfil_vacio_es_valido(self) -> None:
        """Un despacho sin sembrar ni editar es un estado válido."""
        perfil = PerfilInteresDespacho(despacho_id=uuid4())
        assert perfil.areas_tematicas == []
        assert perfil.comisiones_legislador == []
        assert perfil.distritos_observados == []
        assert perfil.aliases_legislador == []
        assert perfil.sembrado_at is None
        assert perfil.editado_at is None

    def test_areas_se_strippean(self) -> None:
        """Espacios y vacíos se sanean."""
        perfil = PerfilInteresDespacho(
            despacho_id=uuid4(),
            areas_tematicas=["  educacion  ", "", "salud", "   "],
        )
        assert perfil.areas_tematicas == ["educacion", "salud"]

    def test_listas_dedupean_conservando_orden(self) -> None:
        """Aliases repetidos se reducen al primero, manteniendo orden."""
        perfil = PerfilInteresDespacho(
            despacho_id=uuid4(),
            aliases_legislador=[
                "Pablo Juliano",
                "Juliano",
                "Pablo Juliano",   # repetido — descartar
                "@PJuliano",
            ],
        )
        assert perfil.aliases_legislador == [
            "Pablo Juliano",
            "Juliano",
            "@PJuliano",
        ]

    def test_area_desconocida_levanta_value_error(self) -> None:
        """Si entra una área que no es del enum, el dominio lo rechaza."""
        with pytest.raises(ValueError, match="áreas desconocidas"):
            PerfilInteresDespacho(
                despacho_id=uuid4(),
                areas_tematicas=["educacion", "cibernetica"],
            )

    def test_todas_las_areas_del_enum_son_aceptadas(self) -> None:
        """Smoke: cualquier valor del enum AreaTematica es válido."""
        todas = [a.value for a in AreaTematica]
        perfil = PerfilInteresDespacho(
            despacho_id=uuid4(),
            areas_tematicas=todas,
        )
        assert sorted(perfil.areas_tematicas) == sorted(todas)


class TestFueEditadoDespuesDeSembrar:
    def test_sin_edicion_es_false(self) -> None:
        perfil = PerfilInteresDespacho(
            despacho_id=uuid4(),
            sembrado_at=datetime.now(UTC),
        )
        assert perfil.fue_editado_despues_de_sembrar is False

    def test_edicion_posterior_a_sembrado_es_true(self) -> None:
        sembrado = datetime.now(UTC)
        editado = sembrado + timedelta(minutes=10)
        perfil = PerfilInteresDespacho(
            despacho_id=uuid4(),
            sembrado_at=sembrado,
            editado_at=editado,
        )
        assert perfil.fue_editado_despues_de_sembrar is True

    def test_edicion_anterior_a_sembrado_es_false(self) -> None:
        """Si re-sembramos después de la edición, vuelve a ser False."""
        editado = datetime.now(UTC)
        sembrado_despues = editado + timedelta(minutes=1)
        perfil = PerfilInteresDespacho(
            despacho_id=uuid4(),
            sembrado_at=sembrado_despues,
            editado_at=editado,
        )
        assert perfil.fue_editado_despues_de_sembrar is False

    def test_edicion_sin_sembrado_es_true(self) -> None:
        """Edición existente sin sembrado previo → respetar la edición."""
        perfil = PerfilInteresDespacho(
            despacho_id=uuid4(),
            sembrado_at=None,
            editado_at=datetime.now(UTC),
        )
        assert perfil.fue_editado_despues_de_sembrar is True
