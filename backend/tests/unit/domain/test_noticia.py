"""Tests de dominio: noticias + menciones (feat-40.1).

Cubren las invariantes de las 6 entidades + helpers:
- canonicalizar_url, hash_url.
- FuenteNoticia: invariantes nombre/dominio, requerimiento de
  feed_url para RSS/sitemap, distrito requerido para DISTRITAL.
- Articulo: no se persiste texto (verificado por la ausencia del
  campo); bajada acotada a chars; hash auto-calculado o validado;
  frozen.
- ClasificacionArticulo: invariantes campos no-vacíos.
- ArticuloRelevante: score 0-100, razón no vacía.
- Mencion: snippet ≤200 chars, confianza_tono en [0,1].
- AlertaMencionEnviada: invariantes individual/agrupada.

Ver `docs/specs/16-briefing-noticias-y-menciones.md` y
`backend/praxis/domain/noticia.py`.
"""

from __future__ import annotations

from dataclasses import fields
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from praxis.domain import (
    MAX_BAJADA_PROPIA_CHARS,
    MAX_SNIPPET_CONTEXTO_CHARS,
    AlcanceMedio,
    AlertaMencionEnviada,
    AreaTematica,
    Articulo,
    ArticuloRelevante,
    ClasificacionArticulo,
    FuenteNoticia,
    Mencion,
    ModoAccesoFuente,
    TipoFuenteNoticia,
    TonoMencion,
    canonicalizar_url,
    hash_url,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# canonicalizar_url + hash_url
# ---------------------------------------------------------------------------


class TestCanonicalizarUrl:
    def test_strip_trailing_slash(self) -> None:
        assert (
            canonicalizar_url("https://lanacion.com.ar/path/")
            == "https://lanacion.com.ar/path"
        )

    def test_lowercase_scheme_y_host(self) -> None:
        assert (
            canonicalizar_url("HTTPS://LaNacion.com.ar/X")
            == "https://lanacion.com.ar/X"
        )

    def test_remueve_query_string(self) -> None:
        assert (
            canonicalizar_url("https://x.com/note?utm_source=a&utm_medium=b")
            == "https://x.com/note"
        )

    def test_remueve_fragment(self) -> None:
        assert (
            canonicalizar_url("https://x.com/note#section-1")
            == "https://x.com/note"
        )

    def test_path_se_preserva_case(self) -> None:
        """Algunos medios usan slugs case-sensitive."""
        assert (
            canonicalizar_url("https://x.com/Slug-CaseSensitive")
            == "https://x.com/Slug-CaseSensitive"
        )


class TestHashUrl:
    def test_es_sha256_hex_de_64_chars(self) -> None:
        h = hash_url("https://x.com/abc")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_es_deterministico_post_canonicalizacion(self) -> None:
        a = hash_url("https://x.com/abc")
        b = hash_url("HTTPS://X.COM/abc?utm=1")
        c = hash_url("https://x.com/abc/")
        assert a == b == c


# ---------------------------------------------------------------------------
# FuenteNoticia
# ---------------------------------------------------------------------------


def _fuente_kwargs(**over):  # type: ignore[no-untyped-def]
    base = {
        "id": uuid4(),
        "nombre": "La Nación",
        "dominio": "lanacion.com.ar",
        "tipo": TipoFuenteNoticia.NACIONAL,
        "alcance": AlcanceMedio.NACIONAL,
        "modo_acceso": ModoAccesoFuente.RSS,
        "feed_url": "https://lanacion.com.ar/feed.xml",
    }
    base.update(over)
    return base


class TestFuenteNoticia:
    def test_construccion_valida_con_rss(self) -> None:
        f = FuenteNoticia(**_fuente_kwargs())
        assert f.tipo == TipoFuenteNoticia.NACIONAL

    def test_nombre_vacio_levanta(self) -> None:
        with pytest.raises(ValueError, match="nombre"):
            FuenteNoticia(**_fuente_kwargs(nombre="   "))

    def test_dominio_vacio_levanta(self) -> None:
        with pytest.raises(ValueError, match="dominio"):
            FuenteNoticia(**_fuente_kwargs(dominio="  "))

    def test_rss_sin_feed_url_levanta(self) -> None:
        with pytest.raises(ValueError, match="feed_url"):
            FuenteNoticia(**_fuente_kwargs(feed_url=None))

    def test_sitemap_sin_feed_url_levanta(self) -> None:
        with pytest.raises(ValueError, match="feed_url"):
            FuenteNoticia(
                **_fuente_kwargs(
                    modo_acceso=ModoAccesoFuente.SITEMAP, feed_url=None,
                ),
            )

    def test_scraping_no_requiere_feed_url(self) -> None:
        """Modo scraping no necesita feed."""
        f = FuenteNoticia(
            **_fuente_kwargs(
                modo_acceso=ModoAccesoFuente.SCRAPING, feed_url=None,
            ),
        )
        assert f.modo_acceso == ModoAccesoFuente.SCRAPING

    def test_distrital_sin_distrito_levanta(self) -> None:
        with pytest.raises(ValueError, match="distrito"):
            FuenteNoticia(
                **_fuente_kwargs(
                    tipo=TipoFuenteNoticia.DISTRITAL,
                    distrito=None,
                ),
            )

    def test_distrital_con_distrito_es_valida(self) -> None:
        f = FuenteNoticia(
            **_fuente_kwargs(
                tipo=TipoFuenteNoticia.DISTRITAL,
                alcance=AlcanceMedio.PROVINCIAL,
                distrito="Buenos Aires",
            ),
        )
        assert f.distrito == "Buenos Aires"


# ---------------------------------------------------------------------------
# Articulo
# ---------------------------------------------------------------------------


def _articulo(**over):  # type: ignore[no-untyped-def]
    base = {
        "id": None,
        "fuente_id": uuid4(),
        "url": "https://lanacion.com.ar/politica/articulo-1",
        "titulo": "Un debate en Congreso",
    }
    base.update(over)
    return Articulo(**base)


class TestArticulo:
    def test_no_tiene_campo_texto_completo(self) -> None:
        """Verificación estructural: el campo NO existe en el dominio
        (regla legal materializada en el esquema, ADR 0006)."""
        nombres = {f.name for f in fields(Articulo)}
        assert "texto" not in nombres
        assert "texto_completo" not in nombres
        assert "cuerpo" not in nombres

    def test_hash_dedup_se_autocalcula(self) -> None:
        a = _articulo()
        assert len(a.hash_dedup) == 64
        assert a.hash_dedup == hash_url(a.url)

    def test_hash_dedup_canonicaliza(self) -> None:
        """Dos artículos con URLs equivalentes tras canonicalización
        tienen el mismo hash → dedup automático."""
        a = _articulo(url="https://x.com/note/")
        b = _articulo(url="HTTPS://x.com/note?utm_source=yyy")
        assert a.hash_dedup == b.hash_dedup

    def test_url_vacia_levanta(self) -> None:
        with pytest.raises(ValueError, match="url"):
            _articulo(url="  ")

    def test_titulo_vacio_levanta(self) -> None:
        with pytest.raises(ValueError, match="titulo"):
            _articulo(titulo="   ")

    def test_bajada_propia_excede_chars_levanta(self) -> None:
        with pytest.raises(ValueError, match="bajada_propia"):
            _articulo(bajada_propia="x" * (MAX_BAJADA_PROPIA_CHARS + 1))

    def test_bajada_exacta_al_limite_es_valida(self) -> None:
        a = _articulo(bajada_propia="x" * MAX_BAJADA_PROPIA_CHARS)
        assert len(a.bajada_propia or "") == MAX_BAJADA_PROPIA_CHARS

    def test_es_frozen(self) -> None:
        a = _articulo()
        with pytest.raises(AttributeError):
            a.titulo = "Otro"  # type: ignore[misc]

    def test_hash_dedup_explicito_invalido_levanta(self) -> None:
        with pytest.raises(ValueError, match="hash_dedup"):
            _articulo(hash_dedup="abc")


# ---------------------------------------------------------------------------
# ClasificacionArticulo
# ---------------------------------------------------------------------------


class TestClasificacionArticulo:
    def test_construccion_valida(self) -> None:
        c = ClasificacionArticulo(
            id=None,
            articulo_id=uuid4(),
            area_tematica=AreaTematica.EDUCACION,
            palabras_clave=["docente", "universidad"],
            modelo="fake-keywords",
        )
        assert c.area_tematica == AreaTematica.EDUCACION

    def test_modelo_vacio_levanta(self) -> None:
        with pytest.raises(ValueError, match="modelo"):
            ClasificacionArticulo(
                id=None,
                articulo_id=uuid4(),
                area_tematica=AreaTematica.OTROS,
                modelo=" ",
            )


# ---------------------------------------------------------------------------
# ArticuloRelevante
# ---------------------------------------------------------------------------


class TestArticuloRelevante:
    def test_construccion_valida(self) -> None:
        r = ArticuloRelevante(
            articulo_id=uuid4(),
            despacho_id=uuid4(),
            score=70,
            razon="Toca área educación.",
        )
        assert r.score == 70

    @pytest.mark.parametrize("score", [-1, 101, 200])
    def test_score_fuera_de_rango(self, score: int) -> None:
        with pytest.raises(ValueError, match=r"\[0, 100\]"):
            ArticuloRelevante(
                articulo_id=uuid4(),
                despacho_id=uuid4(),
                score=score,
                razon="x",
            )

    def test_razon_vacia_levanta(self) -> None:
        with pytest.raises(ValueError, match="razon"):
            ArticuloRelevante(
                articulo_id=uuid4(),
                despacho_id=uuid4(),
                score=50,
                razon="   ",
            )


# ---------------------------------------------------------------------------
# Mencion
# ---------------------------------------------------------------------------


def _mencion(**over):  # type: ignore[no-untyped-def]
    base = {
        "id": None,
        "articulo_id": uuid4(),
        "legislador_id": uuid4(),
        "despacho_id": uuid4(),
        "snippet_contexto": "...el diputado Juliano dijo que...",
        "tono": TonoMencion.NEUTRO,
        "confianza_tono": 0.85,
        "alcance_medio": AlcanceMedio.NACIONAL,
    }
    base.update(over)
    return Mencion(**base)


class TestMencion:
    def test_construccion_valida(self) -> None:
        m = _mencion()
        assert m.tono == TonoMencion.NEUTRO

    def test_snippet_vacio_levanta(self) -> None:
        with pytest.raises(ValueError, match="snippet_contexto"):
            _mencion(snippet_contexto="    ")

    def test_snippet_excede_chars_levanta(self) -> None:
        with pytest.raises(ValueError, match="snippet_contexto"):
            _mencion(
                snippet_contexto="x" * (MAX_SNIPPET_CONTEXTO_CHARS + 1),
            )

    def test_snippet_exacto_al_limite_es_valido(self) -> None:
        m = _mencion(
            snippet_contexto="x" * MAX_SNIPPET_CONTEXTO_CHARS,
        )
        assert len(m.snippet_contexto) == MAX_SNIPPET_CONTEXTO_CHARS

    @pytest.mark.parametrize("conf", [-0.1, 1.1, 2.0])
    def test_confianza_fuera_de_rango(self, conf: float) -> None:
        with pytest.raises(ValueError, match="confianza_tono"):
            _mencion(confianza_tono=conf)

    def test_confianza_en_bordes_es_valida(self) -> None:
        assert _mencion(confianza_tono=0.0).confianza_tono == 0.0
        assert _mencion(confianza_tono=1.0).confianza_tono == 1.0


# ---------------------------------------------------------------------------
# AlertaMencionEnviada
# ---------------------------------------------------------------------------


class TestAlertaMencionEnviada:
    def test_individual_con_1_mencion(self) -> None:
        a = AlertaMencionEnviada(
            id=None,
            destinatario_id=uuid4(),
            tipo="individual",
            menciones_ids=[uuid4()],
            plantilla_meta="praxis_mencion_individual_v1",
            enviado_en=datetime.now(UTC),
            estado="enviado",
        )
        assert a.tipo == "individual"

    def test_individual_con_2_levanta(self) -> None:
        with pytest.raises(ValueError, match="individual"):
            AlertaMencionEnviada(
                id=None,
                destinatario_id=uuid4(),
                tipo="individual",
                menciones_ids=[uuid4(), uuid4()],
                plantilla_meta="x",
                enviado_en=datetime.now(UTC),
                estado="enviado",
            )

    def test_agrupada_con_2_o_mas(self) -> None:
        a = AlertaMencionEnviada(
            id=None,
            destinatario_id=uuid4(),
            tipo="agrupada",
            menciones_ids=[uuid4(), uuid4(), uuid4()],
            plantilla_meta="praxis_mencion_agrupada_v1",
            enviado_en=datetime.now(UTC),
            estado="enviado",
        )
        assert len(a.menciones_ids) == 3

    def test_agrupada_con_1_levanta(self) -> None:
        with pytest.raises(ValueError, match="agrupada"):
            AlertaMencionEnviada(
                id=None,
                destinatario_id=uuid4(),
                tipo="agrupada",
                menciones_ids=[uuid4()],
                plantilla_meta="x",
                enviado_en=datetime.now(UTC),
                estado="enviado",
            )

    def test_menciones_ids_vacia_levanta(self) -> None:
        with pytest.raises(ValueError, match="menciones_ids"):
            AlertaMencionEnviada(
                id=None,
                destinatario_id=uuid4(),
                tipo="individual",
                menciones_ids=[],
                plantilla_meta="x",
                enviado_en=datetime.now(UTC),
                estado="enviado",
            )
