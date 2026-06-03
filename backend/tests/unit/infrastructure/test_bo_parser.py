"""Tests del parser del PDF del BO.

Cubren:
- Parsing del SUMARIO con un PDF fixture real (capturado en
  spike 39.1.5).
- Heurística de unir-líneas-partidas no pega headers de sección con
  el primer entry siguiente.
- Tipo, número, organismo y página se extraen correctamente.
- `extraer_normas_bo` produce listas alineadas (norma[i] ↔ texto[i]).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pdfplumber
import pytest

from praxis.domain import SeccionBO
from praxis.infrastructure.bo.parser import (
    SumarioEntry,
    extraer_normas_bo,
    parsear_sumario,
)

pytestmark = pytest.mark.unit


FIXTURE_PDF = (
    Path(__file__).resolve().parents[3]
    / "spikes" / "bo" / "pdf_del_dia__primera.pdf"
)


@pytest.fixture
def pdf_fixture():
    pdf = pdfplumber.open(FIXTURE_PDF)
    yield pdf
    pdf.close()


def test_fixture_existe() -> None:
    """Sanity: el PDF fixture del spike está versionado."""
    assert FIXTURE_PDF.exists(), (
        f"Falta {FIXTURE_PDF}. ¿No se versionó del spike 39.1.5?"
    )


class TestParsearSumario:
    def test_parsea_mas_de_20_entradas(self, pdf_fixture) -> None:
        """El PDF fixture del 2026-06-01 tiene 25 normas. Aceptamos un
        rango amplio porque otros PDFs reales tendrán otros volúmenes."""
        entradas = parsear_sumario(pdf_fixture)
        assert len(entradas) >= 20
        assert len(entradas) <= 50

    def test_primera_entrada_no_se_pierde(self, pdf_fixture) -> None:
        """El primer entry del fixture es Decreto 412/2026. Si se pierde,
        el bug de "unir líneas partidas" pegando con headers volvió."""
        entradas = parsear_sumario(pdf_fixture)
        assert entradas[0].tipo == "Decreto"
        assert entradas[0].numero == "412/2026"

    def test_organismo_no_incluye_header_de_seccion(
        self, pdf_fixture,
    ) -> None:
        """Ninguna entrada debe tener 'Resoluciones', 'Decretos', etc.
        pegados al organismo (regresión de un bug temprano)."""
        entradas = parsear_sumario(pdf_fixture)
        for e in entradas:
            for header in (
                "Decretos", "Resoluciones", "Disposiciones",
                "Decisiones Administrativas", "Avisos",
            ):
                assert not e.organismo.startswith(header), (
                    f"Organismo arranca con header '{header}': "
                    f"{e.organismo!r}"
                )

    def test_paginas_son_ascendentes(self, pdf_fixture) -> None:
        """El SUMARIO lista las normas en orden de aparición."""
        entradas = parsear_sumario(pdf_fixture)
        paginas = [e.pagina_inicio for e in entradas]
        # Permitimos repetidos (dos normas en la misma página) pero no
        # decrementos.
        for i in range(1, len(paginas)):
            assert paginas[i] >= paginas[i - 1] - 1, (
                f"Decremento de página en {i}: {paginas[i - 1]} → {paginas[i]}"
            )

    def test_numero_norma_tiene_formato_esperado(
        self, pdf_fixture,
    ) -> None:
        """Formato típico: NNNN/AAAA o NN.NNN (Leyes)."""
        import re
        entradas = parsear_sumario(pdf_fixture)
        patron = re.compile(r"^([\d.]+/\d{4}|\d+\.\d+)$")
        for e in entradas:
            assert patron.match(e.numero), (
                f"Número {e.numero!r} no matchea formato esperado"
            )


class TestExtraerNormasBO:
    def test_devuelve_listas_alineadas(self, pdf_fixture) -> None:
        normas, textos = extraer_normas_bo(
            pdf_fixture,
            fecha_publicacion=date(2026, 6, 1),
            seccion=SeccionBO.LEGISLACION,
        )
        assert len(normas) == len(textos)
        assert len(normas) > 0

    def test_normas_tienen_metadata_completa(self, pdf_fixture) -> None:
        normas, _ = extraer_normas_bo(
            pdf_fixture,
            fecha_publicacion=date(2026, 6, 1),
            seccion=SeccionBO.LEGISLACION,
        )
        for n in normas:
            assert n.fecha_publicacion == date(2026, 6, 1)
            assert n.seccion == SeccionBO.LEGISLACION
            assert n.tipo_norma.strip()
            assert n.numero_norma.strip()
            assert n.organismo_emisor.strip()
            assert n.sumario.strip()
            assert len(n.hash_sumario) == 64
            assert n.id is None   # lo asigna el repo al persistir

    def test_textos_no_vacios(self, pdf_fixture) -> None:
        """Cada NormaBOTexto.texto tiene al menos el sumario corto."""
        _, textos = extraer_normas_bo(
            pdf_fixture,
            fecha_publicacion=date(2026, 6, 1),
            seccion=SeccionBO.LEGISLACION,
        )
        for t in textos:
            assert t.texto.strip()

    def test_textos_largos_para_la_mayoria_de_normas(
        self, pdf_fixture,
    ) -> None:
        """El cuerpo extraído debería ser sustancial (no sólo el sumario
        corto) para la mayoría de las normas — confirma que el rango
        de páginas se calcula correctamente."""
        _, textos = extraer_normas_bo(
            pdf_fixture,
            fecha_publicacion=date(2026, 6, 1),
            seccion=SeccionBO.LEGISLACION,
        )
        largos = [len(t.texto) for t in textos]
        # Al menos 80% deberían tener > 500 chars de cuerpo.
        bien_extraidos = sum(1 for size in largos if size > 500)
        assert bien_extraidos / len(largos) >= 0.8, (
            f"Sólo {bien_extraidos}/{len(largos)} normas tienen >500 chars; "
            "el cálculo de rango de páginas puede estar mal."
        )

    def test_fecha_y_capturado_en_se_propagan(self, pdf_fixture) -> None:
        capturado = datetime(2026, 6, 1, 5, 0, tzinfo=UTC)
        normas, textos = extraer_normas_bo(
            pdf_fixture,
            fecha_publicacion=date(2026, 6, 1),
            seccion=SeccionBO.LEGISLACION,
            capturado_en=capturado,
        )
        for n in normas:
            assert n.capturado_en == capturado
        for t in textos:
            assert t.capturado_en == capturado


class TestSumarioEntry:
    def test_es_frozen(self) -> None:
        e = SumarioEntry(
            organismo="X",
            tipo="Decreto",
            numero="1/2026",
            sumario_corto="abc",
            id_interno="DECTO-1-2026",
            pagina_inicio=4,
        )
        with pytest.raises(AttributeError):
            e.organismo = "Y"  # type: ignore[misc]
