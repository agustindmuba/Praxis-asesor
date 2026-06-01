"""Unit tests de los helpers puros de similitud para el briefing."""

from __future__ import annotations

from praxis.domain import jaccard, tokenizar_titulo


def test_tokenizar_baja_a_minusculas_y_saca_tildes() -> None:
    out = tokenizar_titulo("EDUCACIÓN PÚBLICA SUPERIOR")
    assert "educacion" in out
    assert "publica" in out
    assert "superior" in out


def test_tokenizar_saca_puntuacion() -> None:
    out = tokenizar_titulo("RÉGIMEN DE JUBILACIONES, PENSIONES Y ASIGNACIONES.")
    assert "jubilaciones" in out
    assert "pensiones" in out
    assert "asignaciones" in out
    # "régimen" es stopword.
    assert "regimen" not in out


def test_tokenizar_descarta_stopwords_y_palabras_cortas() -> None:
    out = tokenizar_titulo("MODIFICACION DE LA LEY DE EDUCACION NACIONAL")
    # stopwords: modificacion, ley, de, la, nacional
    assert "modificacion" not in out
    assert "ley" not in out
    assert "nacional" not in out
    # "educacion" sí queda
    assert "educacion" in out


def test_tokenizar_conserva_anios_como_4_digitos() -> None:
    out = tokenizar_titulo("ASIGNACION UNIVERSAL POR HIJO - LEY 24.714 / 1996")
    assert "asignacion" in out
    assert "universal" in out
    assert "1996" in out


def test_jaccard_identica() -> None:
    s = {"a", "b", "c"}
    assert jaccard(s, s) == 1.0


def test_jaccard_disjunta() -> None:
    assert jaccard({"a"}, {"b"}) == 0.0


def test_jaccard_parcial() -> None:
    # 2 comunes de 4 totales = 0.5
    assert jaccard({"a", "b", "c"}, {"b", "c", "d"}) == 0.5


def test_jaccard_set_vacio_devuelve_cero() -> None:
    assert jaccard(set(), set()) == 0.0
    assert jaccard({"a"}, set()) == 0.0


def test_caso_real_dos_titulos_de_educacion() -> None:
    """Dos títulos del corpus real: deberían tener Jaccard > 0.2."""
    t1 = tokenizar_titulo("DECLARAR LA EDUCACION COMO SERVICIO ESTRATEGICO ESENCIAL")
    t2 = tokenizar_titulo("REGIMEN EDUCATIVO DE GARANTIAS Y SERVICIO ESENCIAL")
    score = jaccard(t1, t2)
    assert score > 0.15  # comparten "servicio" + "esencial"


def test_caso_real_titulos_no_relacionados() -> None:
    """Educación vs salud: Jaccard debería ser bajo."""
    t1 = tokenizar_titulo("DECLARAR LA EDUCACION COMO SERVICIO ESTRATEGICO ESENCIAL")
    t2 = tokenizar_titulo("REGIMEN DE OBRAS SOCIALES PARA TRABAJADORES")
    score = jaccard(t1, t2)
    assert score < 0.15
