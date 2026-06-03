"""Tests de los parsers JSON del AnthropicLlmProvider para artículos.

NO llaman a la API. Verifican que:

- `_limpiar_y_cap_bajada` saca prefijos "Bajada:" / comillas
  envolventes y capa a `max_chars` con elipsis si recorta.
- `_parsear_clasificacion_articulo` parsea JSON válido, sobrevive a
  JSON malformado (→ fallback OTROS), normaliza el área temática y
  capa palabras_clave a 5.
"""

from __future__ import annotations

import pytest

from praxis.domain import MAX_BAJADA_PROPIA_CHARS, AreaTematica
from praxis.infrastructure.llm.anthropic_provider import (
    _limpiar_y_cap_bajada,
    _parsear_clasificacion_articulo,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# _limpiar_y_cap_bajada
# ---------------------------------------------------------------------------


class TestLimpiarYCapBajada:
    def test_corto_pasa_intacto(self) -> None:
        assert _limpiar_y_cap_bajada("Una bajada normal.", 240) == (
            "Una bajada normal."
        )

    def test_saca_prefijo_bajada(self) -> None:
        out = _limpiar_y_cap_bajada("Bajada: una oración informativa.", 240)
        assert out == "una oración informativa."

    def test_saca_prefijo_resumen_case_insensitive(self) -> None:
        out = _limpiar_y_cap_bajada("RESUMEN: cosa cualquiera", 240)
        assert out == "cosa cualquiera"

    def test_saca_comillas_envolventes_rectas(self) -> None:
        out = _limpiar_y_cap_bajada('"Texto entre comillas."', 240)
        assert out == "Texto entre comillas."

    def test_saca_comillas_tipograficas(self) -> None:
        out = _limpiar_y_cap_bajada("“Texto.”", 240)
        assert out == "Texto."

    def test_colapsa_whitespace_multiple(self) -> None:
        out = _limpiar_y_cap_bajada("Una   bajada\ncon\tquiebres.", 240)
        assert out == "Una bajada con quiebres."

    def test_capa_a_max_chars_con_elipsis(self) -> None:
        largo = "x" * 500
        out = _limpiar_y_cap_bajada(largo, MAX_BAJADA_PROPIA_CHARS)
        assert len(out) <= MAX_BAJADA_PROPIA_CHARS
        assert out.endswith("…")

    def test_corta_en_word_boundary_si_hay_cerca(self) -> None:
        # 250 chars, debería cortar antes del último espacio.
        out = _limpiar_y_cap_bajada(" ".join(["palabra"] * 50), 50)
        # No debe cortar a la mitad de "palabra".
        assert "palabr…" not in out
        assert out.endswith("…")


# ---------------------------------------------------------------------------
# _parsear_clasificacion_articulo
# ---------------------------------------------------------------------------


class TestParsearClasificacionArticulo:
    def test_json_valido_devuelve_resultado(self) -> None:
        respuesta = (
            '{"area_tematica": "educacion", '
            '"palabras_clave": ["jornada", "escuela", "ley"]}'
        )
        r = _parsear_clasificacion_articulo(respuesta)
        assert r.area_tematica == AreaTematica.EDUCACION
        assert r.palabras_clave == ["jornada", "escuela", "ley"]

    def test_fences_se_sacan(self) -> None:
        respuesta = (
            "```json\n"
            '{"area_tematica": "salud", "palabras_clave": []}\n'
            "```"
        )
        r = _parsear_clasificacion_articulo(respuesta)
        assert r.area_tematica == AreaTematica.SALUD

    def test_json_malformado_devuelve_otros(self) -> None:
        r = _parsear_clasificacion_articulo("no es json")
        assert r.area_tematica == AreaTematica.OTROS
        assert r.palabras_clave == []

    def test_area_invalida_cae_a_otros(self) -> None:
        respuesta = '{"area_tematica": "futbol", "palabras_clave": []}'
        r = _parsear_clasificacion_articulo(respuesta)
        assert r.area_tematica == AreaTematica.OTROS

    def test_palabras_capadas_a_5(self) -> None:
        respuesta = (
            '{"area_tematica": "economia", '
            '"palabras_clave": ["a","b","c","d","e","f","g"]}'
        )
        r = _parsear_clasificacion_articulo(respuesta)
        assert len(r.palabras_clave) == 5
        assert r.palabras_clave == ["a", "b", "c", "d", "e"]

    def test_palabras_no_lista_se_normaliza_a_vacio(self) -> None:
        respuesta = (
            '{"area_tematica": "economia", "palabras_clave": "no es lista"}'
        )
        r = _parsear_clasificacion_articulo(respuesta)
        assert r.palabras_clave == []

    def test_top_level_no_objeto_devuelve_otros(self) -> None:
        # Una lista, no un dict — el parser debe devolver fallback.
        r = _parsear_clasificacion_articulo('["no", "es", "dict"]')
        assert r.area_tematica == AreaTematica.OTROS
