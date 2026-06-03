"""Tests de dominio: `NormaBO`, `NormaBOTexto`, `ClasificacionNormaBO`,
`NormaBOAccionable` y helpers.

Cubren:
- Validaciones de campos no-vacíos.
- `hash_sumario` es determinístico y normaliza whitespace.
- Prioridad coherente con score; umbral mínimo respetado.
- Razón acotada en chars; score en [0,100].

Ver `docs/specs/15-resumen-bo-accionable.md` y
`backend/praxis/domain/norma_bo.py`.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from praxis.domain import (
    BO_PROMPT_VERSION,
    MAX_RAZON_ACCIONABILIDAD_CHARS,
    SCORE_MINIMO_ACCIONABLE,
    SECCIONES_ACTIVAS_V1,
    AreaTematica,
    ClasificacionNormaBO,
    NormaBO,
    NormaBOAccionable,
    NormaBOTexto,
    PrioridadAccionabilidad,
    SeccionBO,
    hash_sumario,
    prioridad_para_score,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _norma(**overrides):
    base = {
        "id": None,
        "fecha_publicacion": date(2026, 6, 1),
        "seccion": SeccionBO.LEGISLACION,
        "tipo_norma": "decreto",
        "numero_norma": "412/2026",
        "organismo_emisor": "Poder Ejecutivo Nacional",
        "sumario": "Modifica régimen jubilatorio docente",
        "url_oficial": "https://www.boletinoficial.gob.ar/det/decreto-412-2026",
        "hash_sumario": hash_sumario("Modifica régimen jubilatorio docente"),
        "capturado_en": datetime.now(UTC),
    }
    base.update(overrides)
    return NormaBO(**base)


# ---------------------------------------------------------------------------
# hash_sumario
# ---------------------------------------------------------------------------


class TestHashSumario:
    def test_es_determinístico(self) -> None:
        assert hash_sumario("foo") == hash_sumario("foo")

    def test_es_sha256_hex_de_64_chars(self) -> None:
        h = hash_sumario("hola")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_normaliza_whitespace(self) -> None:
        """`foo bar` y `foo   bar\n` deben dar el mismo hash."""
        a = hash_sumario("foo bar")
        b = hash_sumario("foo   bar\n")
        c = hash_sumario("  foo bar  ")
        assert a == b == c

    def test_distintos_textos_distintos_hashes(self) -> None:
        assert hash_sumario("foo") != hash_sumario("bar")


# ---------------------------------------------------------------------------
# SECCIONES_ACTIVAS_V1
# ---------------------------------------------------------------------------


class TestSeccionesActivasV1:
    def test_solo_legislacion(self) -> None:
        """Tras feat-39.3 descubrimos que la cuarta sección del BO no
        son "designaciones" (son "Registro de Dominios"); las
        designaciones se publican como decretos dentro de Primera. v1
        sólo procesa Primera = LEGISLACION."""
        assert frozenset({SeccionBO.LEGISLACION}) == SECCIONES_ACTIVAS_V1

    def test_designaciones_reservada_para_v2(self) -> None:
        """Valor enum existe; en runtime se ignora v1 (deja la puerta
        abierta para que la clasificación LLM distinga designaciones en
        v2 sin migración de datos)."""
        assert SeccionBO.DESIGNACIONES not in SECCIONES_ACTIVAS_V1

    def test_avisos_oficiales_reservada_para_v2(self) -> None:
        """Reservado para v2 (SAIJ). Ver decisión D19."""
        assert SeccionBO.AVISOS_OFICIALES not in SECCIONES_ACTIVAS_V1


# ---------------------------------------------------------------------------
# NormaBO
# ---------------------------------------------------------------------------


class TestNormaBO:
    def test_construccion_minima_valida(self) -> None:
        n = _norma()
        assert n.tipo_norma == "decreto"
        assert n.seccion == SeccionBO.LEGISLACION

    @pytest.mark.parametrize(
        "campo",
        [
            "tipo_norma",
            "numero_norma",
            "organismo_emisor",
            "sumario",
            "url_oficial",
        ],
    )
    def test_campo_vacio_levanta_value_error(self, campo: str) -> None:
        with pytest.raises(ValueError, match=campo):
            _norma(**{campo: "   "})

    def test_hash_distinto_a_64_chars_levanta(self) -> None:
        with pytest.raises(ValueError, match="hash_sumario"):
            _norma(hash_sumario="abc")

    def test_norma_es_frozen(self) -> None:
        """frozen=True ⇒ FrozenInstanceError (subclase de AttributeError)."""
        n = _norma()
        with pytest.raises(AttributeError):
            n.tipo_norma = "ley"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# NormaBOTexto
# ---------------------------------------------------------------------------


class TestNormaBOTexto:
    def test_construccion_valida(self) -> None:
        t = NormaBOTexto(
            norma_id=uuid4(),
            texto="ARTÍCULO 1 — Modifíquese...",
            capturado_en=datetime.now(UTC),
        )
        assert t.texto.startswith("ARTÍCULO")

    def test_texto_vacio_levanta(self) -> None:
        with pytest.raises(ValueError, match="texto"):
            NormaBOTexto(
                norma_id=uuid4(),
                texto="   ",
                capturado_en=datetime.now(UTC),
            )


# ---------------------------------------------------------------------------
# ClasificacionNormaBO
# ---------------------------------------------------------------------------


class TestClasificacionNormaBO:
    def test_construccion_valida(self) -> None:
        c = ClasificacionNormaBO(
            id=None,
            norma_id=uuid4(),
            area_tematica=AreaTematica.JUSTICIA,
            palabras_clave=["régimen", "jubilatorio"],
            afecta_expedientes_hcdn=False,
            referencias_legales=["Ley 24.660"],
            modelo="fake-keywords",
            prompt_version=BO_PROMPT_VERSION,
        )
        assert c.area_tematica == AreaTematica.JUSTICIA
        assert c.palabras_clave == ["régimen", "jubilatorio"]

    def test_palabras_clave_y_referencias_pueden_estar_vacias(self) -> None:
        """Una norma puede no tener referencias legales claras o sin
        palabras clave dominantes — listas vacías son válidas."""
        c = ClasificacionNormaBO(
            id=None,
            norma_id=uuid4(),
            area_tematica=AreaTematica.OTROS,
            palabras_clave=[],
            afecta_expedientes_hcdn=False,
            referencias_legales=[],
            modelo="fake-keywords",
            prompt_version=BO_PROMPT_VERSION,
        )
        assert c.palabras_clave == []

    def test_modelo_vacio_levanta(self) -> None:
        with pytest.raises(ValueError, match="modelo"):
            ClasificacionNormaBO(
                id=None,
                norma_id=uuid4(),
                area_tematica=AreaTematica.OTROS,
                palabras_clave=[],
                afecta_expedientes_hcdn=False,
                referencias_legales=[],
                modelo="   ",
                prompt_version=BO_PROMPT_VERSION,
            )


# ---------------------------------------------------------------------------
# Scoring → Prioridad
# ---------------------------------------------------------------------------


class TestPrioridadParaScore:
    @pytest.mark.parametrize(
        "score, esperada",
        [
            (15, PrioridadAccionabilidad.BAJA),
            (29, PrioridadAccionabilidad.BAJA),
            (30, PrioridadAccionabilidad.MEDIA),
            (59, PrioridadAccionabilidad.MEDIA),
            (60, PrioridadAccionabilidad.ALTA),
            (100, PrioridadAccionabilidad.ALTA),
        ],
    )
    def test_umbrales(
        self, score: int, esperada: PrioridadAccionabilidad,
    ) -> None:
        assert prioridad_para_score(score) == esperada

    def test_bajo_umbral_minimo_levanta(self) -> None:
        with pytest.raises(ValueError, match="bajo umbral"):
            prioridad_para_score(SCORE_MINIMO_ACCIONABLE - 1)

    @pytest.mark.parametrize("score", [-1, 101, 200, -10])
    def test_fuera_de_rango_levanta(self, score: int) -> None:
        with pytest.raises(ValueError, match=r"\[0, 100\]"):
            prioridad_para_score(score)


# ---------------------------------------------------------------------------
# NormaBOAccionable
# ---------------------------------------------------------------------------


def _accionable(
    *,
    score: int = 75,
    prioridad: PrioridadAccionabilidad | None = None,
    razon: str = "Toca tu proyecto 1247-D-2025 (educación).",
) -> NormaBOAccionable:
    return NormaBOAccionable(
        norma_id=uuid4(),
        despacho_id=uuid4(),
        score=score,
        prioridad=prioridad or prioridad_para_score(score),
        razon=razon,
        expedientes_tocados=[uuid4()],
    )


class TestNormaBOAccionable:
    def test_construccion_coherente_es_valida(self) -> None:
        a = _accionable(score=75)
        assert a.prioridad == PrioridadAccionabilidad.ALTA

    def test_score_fuera_de_rango_levanta(self) -> None:
        with pytest.raises(ValueError, match=r"\[0, 100\]"):
            _accionable(score=200)

    def test_score_bajo_minimo_levanta(self) -> None:
        with pytest.raises(ValueError, match="umbral mínimo"):
            _accionable(score=10)

    def test_score_y_prioridad_incoherentes_levanta(self) -> None:
        with pytest.raises(ValueError, match="coherente"):
            NormaBOAccionable(
                norma_id=uuid4(),
                despacho_id=uuid4(),
                score=75,
                prioridad=PrioridadAccionabilidad.BAJA,
                razon="x",
                expedientes_tocados=[],
            )

    def test_razon_vacia_levanta(self) -> None:
        with pytest.raises(ValueError, match="razon"):
            _accionable(razon="    ")

    def test_razon_excede_chars_levanta(self) -> None:
        with pytest.raises(ValueError, match="excede"):
            _accionable(razon="x" * (MAX_RAZON_ACCIONABILIDAD_CHARS + 1))

    def test_razon_exacta_al_limite_es_valida(self) -> None:
        a = _accionable(razon="x" * MAX_RAZON_ACCIONABILIDAD_CHARS)
        assert len(a.razon) == MAX_RAZON_ACCIONABILIDAD_CHARS

    def test_expedientes_tocados_vacios_son_validos(self) -> None:
        """Una norma puede ser accionable por área temática sin tocar
        un expediente concreto del despacho."""
        a = NormaBOAccionable(
            norma_id=uuid4(),
            despacho_id=uuid4(),
            score=35,
            prioridad=PrioridadAccionabilidad.MEDIA,
            razon="Área educación, sin expediente en trámite del despacho.",
            expedientes_tocados=[],
        )
        assert a.expedientes_tocados == []
