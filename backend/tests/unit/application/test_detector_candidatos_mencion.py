"""Tests del detector regex de candidatos a mención (feat-40.3 pase 1).

Servicio puro sin I/O. Cubren:

- Match nombre completo → confianza 1.0.
- Match apellido + contexto político ≤80 chars → confianza 0.7.
- Match apellido sin contexto → confianza 0.4.
- Aliases extra (Twitter handles).
- Normalización de tildes / case.
- Dedup por posición.
- Snippet ≤200 chars con elipsis cuando hay recorte.
- Sin match si nombre/apellido no aparecen.
"""

from __future__ import annotations

import pytest

from praxis.application.services import (
    CandidatoMencion,
    detectar_candidatos,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Casos felices
# ---------------------------------------------------------------------------


class TestNombreCompleto:
    def test_match_de_nombre_completo_da_confianza_1(self) -> None:
        texto = "En el debate, Pablo Juliano dijo que la educación es prioridad."
        cs = detectar_candidatos(
            texto,
            nombre_completo="Pablo Juliano",
            apellido="Juliano",
        )
        assert len(cs) == 1
        assert cs[0].alias_matcheado == "Pablo Juliano"
        assert cs[0].confianza_regex == 1.0
        assert "Pablo Juliano" in cs[0].snippet

    def test_match_es_case_insensitive(self) -> None:
        texto = "Reportes indican que pablo juliano se opuso."
        cs = detectar_candidatos(
            texto,
            nombre_completo="Pablo Juliano",
            apellido="Juliano",
        )
        assert len(cs) == 1
        assert cs[0].alias_matcheado == "Pablo Juliano"

    def test_tildes_normalizadas(self) -> None:
        texto = "Pablo Juliano dijo que la cámara debate la ley."
        cs = detectar_candidatos(
            texto,
            nombre_completo="Pablo Juliano",
            apellido="Juliano",
        )
        assert len(cs) >= 1


# ---------------------------------------------------------------------------
# Apellido + contexto
# ---------------------------------------------------------------------------


class TestApellidoConContexto:
    def test_apellido_cerca_de_diputado_confianza_07(self) -> None:
        texto = "El diputado Juliano apuntó contra el oficialismo."
        cs = detectar_candidatos(
            texto,
            nombre_completo="Pablo Juliano",
            apellido="Juliano",
        )
        assert len(cs) == 1
        assert cs[0].alias_matcheado == "Juliano"
        assert cs[0].confianza_regex == 0.7

    def test_apellido_cerca_de_bloque_confianza_07(self) -> None:
        texto = "El bloque DPS, con Juliano a la cabeza, votará en contra."
        cs = detectar_candidatos(
            texto,
            nombre_completo="Pablo Juliano",
            apellido="Juliano",
        )
        assert len(cs) == 1
        assert cs[0].confianza_regex == 0.7

    def test_apellido_lejos_de_contexto_confianza_04(self) -> None:
        # Apellido sin ningún término político en su entorno.
        texto = (
            "El producto fabricado por Juliano S.A. genera empleo en la zona "
            "norte."
        )
        cs = detectar_candidatos(
            texto,
            nombre_completo="Pablo Juliano",
            apellido="Juliano",
        )
        assert len(cs) == 1
        assert cs[0].confianza_regex == 0.4


# ---------------------------------------------------------------------------
# Aliases extra
# ---------------------------------------------------------------------------


class TestAliasesExtra:
    def test_alias_twitter_se_detecta(self) -> None:
        texto = "Como dijo @PJuliano en X esta mañana, no acompañarán."
        cs = detectar_candidatos(
            texto,
            nombre_completo="Pablo Juliano",
            apellido="Juliano",
            aliases_extra=["@PJuliano"],
        )
        # @PJuliano matches; apellido "Juliano" también está adentro
        # del alias. Para el pase 1 ambos son válidos pero los
        # deduplicamos por posición.
        aliases = {c.alias_matcheado for c in cs}
        assert "@PJuliano" in aliases

    def test_alias_repetido_con_nombre_completo_no_se_duplica(self) -> None:
        texto = "Pablo Juliano y luego Pablo Juliano otra vez."
        cs = detectar_candidatos(
            texto,
            nombre_completo="Pablo Juliano",
            apellido="Juliano",
            aliases_extra=["Pablo Juliano"],   # mismo que nombre_completo
        )
        # 2 matches por posiciones distintas. Cada posición sólo 1
        # candidato. El alias_extra se ignora porque coincide con nombre.
        assert len(cs) == 2
        assert all(c.alias_matcheado == "Pablo Juliano" for c in cs)


# ---------------------------------------------------------------------------
# Dedup por posición
# ---------------------------------------------------------------------------


def test_match_nombre_completo_no_genera_match_extra_de_apellido() -> None:
    """Si nombre completo matchea en posición X, el apellido en la
    misma posición NO se duplica."""
    texto = "Pablo Juliano dijo... y más tarde el diputado Juliano respondió."
    cs = detectar_candidatos(
        texto,
        nombre_completo="Pablo Juliano",
        apellido="Juliano",
    )
    # Esperamos 2 matches: el primer "Pablo Juliano" + el "diputado Juliano".
    # El "Juliano" embebido en "Pablo Juliano" NO duplica.
    assert len(cs) == 2
    aliases = sorted(c.alias_matcheado for c in cs)
    assert aliases == ["Juliano", "Pablo Juliano"]


# ---------------------------------------------------------------------------
# Snippet
# ---------------------------------------------------------------------------


def test_snippet_con_elipsis_si_recorta() -> None:
    texto = "x" * 500 + " Pablo Juliano " + "y" * 500
    cs = detectar_candidatos(
        texto,
        nombre_completo="Pablo Juliano",
        apellido="Juliano",
    )
    assert len(cs) == 1
    snip = cs[0].snippet
    assert snip.startswith("…")
    assert snip.endswith("…")
    assert "Pablo Juliano" in snip


def test_snippet_sin_elipsis_si_texto_corto() -> None:
    texto = "Pablo Juliano dijo algo."
    cs = detectar_candidatos(
        texto,
        nombre_completo="Pablo Juliano",
        apellido="Juliano",
    )
    snip = cs[0].snippet
    assert not snip.startswith("…")
    assert not snip.endswith("…")


# ---------------------------------------------------------------------------
# Negativos
# ---------------------------------------------------------------------------


def test_texto_sin_mencion_devuelve_lista_vacia() -> None:
    cs = detectar_candidatos(
        "La inflación de mayo fue del 3,2% según el INDEC.",
        nombre_completo="Pablo Juliano",
        apellido="Juliano",
    )
    assert cs == []


def test_texto_vacio_devuelve_lista_vacia() -> None:
    assert (
        detectar_candidatos(
            "", nombre_completo="Pablo Juliano", apellido="Juliano",
        )
        == []
    )


def test_apellido_como_parte_de_otra_palabra_no_matchea() -> None:
    """Word boundary: 'Julianos' no debe matchear 'Juliano'."""
    texto = "Los julianos del cumple anual celebraron en Boedo."
    cs = detectar_candidatos(
        texto,
        nombre_completo="Pablo Juliano",
        apellido="Juliano",
    )
    assert cs == []


def test_estructura_candidato() -> None:
    """Sanity de la dataclass."""
    cs = detectar_candidatos(
        "Pablo Juliano",
        nombre_completo="Pablo Juliano",
        apellido="Juliano",
    )
    assert isinstance(cs[0], CandidatoMencion)
    assert cs[0].posicion_inicio == 0
