"""Tests de `ValidarConflictosNormativos` (feat-42.6 / RAG).

Cubre:
- Mapeo del JSON del LLM por par (artículo proyecto, chunk normativo):
  - severidad="conflicto" → se registra.
  - severidad="modificacion" → se registra.
  - severidad="complementa" → NO se registra (se omite).
  - severidad="ninguno" → NO se registra.
- Artículo vacío del proyecto se skipea (no llama al buscador).
- Fence ```json ... ``` se parsea bien.
- Si el LLM responde JSON inválido o tira excepción, el par se ignora
  silenciosamente (log warning) — no rompe la validación entera.

Estrategia: el use case orquesta `BuscarNormativaSimilar` que toca DB
y `embeber_textos` que carga PyTorch. Para no levantar nada de eso en
unit tests, parchamos `BuscarNormativaSimilar.ejecutar` con un stub
async via monkeypatch. La AsyncSession queda como sentinel — el use
case nunca la usa directamente, solo la pasa al buscador interno.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from praxis.application.ports import LlmProvider
from praxis.application.use_cases import validar_conflictos_normativos as vcn_mod
from praxis.application.use_cases.validar_conflictos_normativos import (
    ChunkSimilar,
    ValidarConflictosNormativos,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class StubLlm(LlmProvider):
    """LLM que responde con un payload distinto por cada llamada.

    Si `payloads` se agota, lanza IndexError (los tests deben preparar
    exactamente la cantidad esperada).
    """

    def __init__(self, payloads: list[str] | None = None) -> None:
        self._payloads = list(payloads or [])
        self.calls = 0
        self.raise_exc: Exception | None = None

    @property
    def nombre_modelo(self) -> str:
        return "stub"

    async def razonar_libre(
        self, *, system: str, user: str, max_tokens: int = 2000,
    ) -> tuple[str, str]:
        self.calls += 1
        if self.raise_exc is not None:
            raise self.raise_exc
        return self._payloads.pop(0), "stub"

    async def generar_resumen_ejecutivo(self, e):  # pragma: no cover
        raise NotImplementedError

    async def clasificar_area_tematica(self, e):  # pragma: no cover
        raise NotImplementedError

    async def generar_argumentos(self, e, *, contraargumentos=False):  # pragma: no cover
        raise NotImplementedError

    async def clasificar_norma_bo(self, n, *, texto=None):  # pragma: no cover
        raise NotImplementedError

    async def disambiguar_mencion(self, **k):  # pragma: no cover
        raise NotImplementedError

    async def generar_bajada_propia(self, a, *, texto_articulo):  # pragma: no cover
        raise NotImplementedError

    async def clasificar_articulo(self, a, *, texto_articulo):  # pragma: no cover
        raise NotImplementedError


def _chunk(
    fuente: str = "ley_25188_etica_publica",
    articulo_label: str = "Artículo 14",
    texto: str = "Los funcionarios deben declarar sus bienes...",
    distancia: float = 0.1,
) -> ChunkSimilar:
    return ChunkSimilar(
        fuente=fuente,
        articulo_label=articulo_label,
        texto=texto,
        distancia=distancia,
    )


class _StubBuscador:
    """Reemplaza `BuscarNormativaSimilar` por una versión que devuelve
    una lista hardcodeada por (query → chunks)."""

    def __init__(self, por_query: dict[str, list[ChunkSimilar]]) -> None:
        self._por_query = por_query
        self.calls: list[str] = []

    def __call__(self, *, session: Any) -> "_StubBuscador":
        # Cuando el use case construye `BuscarNormativaSimilar(session=...)`,
        # nuestro factory devuelve `self`.
        return self

    async def ejecutar(
        self, *, query: str, top_k: int = 5,
    ) -> list[ChunkSimilar]:
        self.calls.append(query)
        return self._por_query.get(query, [])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_severidad_conflicto_se_registra(monkeypatch) -> None:
    chunk = _chunk()
    stub = _StubBuscador({"Artículo 1° — X.": [chunk]})
    monkeypatch.setattr(vcn_mod, "BuscarNormativaSimilar", stub)

    llm = StubLlm([
        json.dumps({"severidad": "conflicto", "explicacion": "Contradice"}),
    ])
    uc = ValidarConflictosNormativos(
        session=object(), llm=llm, top_k_por_articulo=1,
    )
    result = await uc.ejecutar(articulado=["Artículo 1° — X."])
    assert len(result) == 1
    assert result[0].severidad == "conflicto"
    assert result[0].indice_articulo_proyecto == 0
    assert result[0].fuente == "ley_25188_etica_publica"
    assert result[0].articulo_label == "Artículo 14"


@pytest.mark.asyncio
async def test_severidad_modificacion_se_registra(monkeypatch) -> None:
    chunk = _chunk()
    stub = _StubBuscador({"Artículo 1° — Y.": [chunk]})
    monkeypatch.setattr(vcn_mod, "BuscarNormativaSimilar", stub)

    llm = StubLlm([
        json.dumps({"severidad": "modificacion", "explicacion": "Enmienda tácita"}),
    ])
    uc = ValidarConflictosNormativos(
        session=object(), llm=llm, top_k_por_articulo=1,
    )
    result = await uc.ejecutar(articulado=["Artículo 1° — Y."])
    assert len(result) == 1
    assert result[0].severidad == "modificacion"


@pytest.mark.asyncio
async def test_severidad_complementa_o_ninguno_se_omite(monkeypatch) -> None:
    """Solo conflicto y modificación se registran — los otros se descartan."""
    chunk1 = _chunk(articulo_label="Artículo 14")
    chunk2 = _chunk(articulo_label="Artículo 15")
    stub = _StubBuscador({
        "Artículo 1° — Z.": [chunk1, chunk2],
    })
    monkeypatch.setattr(vcn_mod, "BuscarNormativaSimilar", stub)

    llm = StubLlm([
        json.dumps({"severidad": "complementa", "explicacion": "Sano"}),
        json.dumps({"severidad": "ninguno", "explicacion": "No se tocan"}),
    ])
    uc = ValidarConflictosNormativos(
        session=object(), llm=llm, top_k_por_articulo=2,
    )
    result = await uc.ejecutar(articulado=["Artículo 1° — Z."])
    assert result == []
    assert llm.calls == 2          # se llamó por los 2 chunks


@pytest.mark.asyncio
async def test_articulo_vacio_se_skipea(monkeypatch) -> None:
    """Si un elemento del articulado es '' o whitespace, no llama al
    buscador ni al LLM para ese artículo."""
    stub = _StubBuscador({"Artículo 2° — X.": [_chunk()]})
    monkeypatch.setattr(vcn_mod, "BuscarNormativaSimilar", stub)

    llm = StubLlm([
        json.dumps({"severidad": "conflicto", "explicacion": "z"}),
    ])
    uc = ValidarConflictosNormativos(
        session=object(), llm=llm, top_k_por_articulo=1,
    )
    result = await uc.ejecutar(articulado=["", "   ", "Artículo 2° — X."])

    # El conflicto registrado debe traer indice=2 (no 0, no 1).
    assert len(result) == 1
    assert result[0].indice_articulo_proyecto == 2
    assert stub.calls == ["Artículo 2° — X."]   # solo el 3er artículo busca


@pytest.mark.asyncio
async def test_json_con_fences_se_parsea(monkeypatch) -> None:
    chunk = _chunk()
    stub = _StubBuscador({"Artículo 1° — X.": [chunk]})
    monkeypatch.setattr(vcn_mod, "BuscarNormativaSimilar", stub)

    raw = (
        "```json\n"
        + json.dumps({"severidad": "conflicto", "explicacion": "Y"})
        + "\n```"
    )
    llm = StubLlm([raw])
    uc = ValidarConflictosNormativos(
        session=object(), llm=llm, top_k_por_articulo=1,
    )
    result = await uc.ejecutar(articulado=["Artículo 1° — X."])
    assert len(result) == 1
    assert result[0].severidad == "conflicto"


@pytest.mark.asyncio
async def test_llm_falla_par_se_ignora(monkeypatch) -> None:
    """Si el LLM levanta excepción para un par, ese par se ignora pero
    los demás se procesan."""
    chunk1 = _chunk(articulo_label="Artículo 14")
    chunk2 = _chunk(articulo_label="Artículo 15")
    stub = _StubBuscador({"Artículo 1° — X.": [chunk1, chunk2]})
    monkeypatch.setattr(vcn_mod, "BuscarNormativaSimilar", stub)

    # Lanza exc en la 1ª llamada, devuelve conflicto en la 2ª.
    payloads = [json.dumps({"severidad": "conflicto", "explicacion": "Y"})]
    llm = StubLlm(payloads)

    # Para forzar la excepción en la primera llamada y respuesta en la
    # segunda, hacemos un wrapper inline:
    llamadas = {"n": 0}
    original = llm.razonar_libre

    async def lanza_y_luego_responde(*, system, user, max_tokens=2000):
        llamadas["n"] += 1
        if llamadas["n"] == 1:
            raise RuntimeError("LLM timeout")
        return await original(system=system, user=user, max_tokens=max_tokens)

    llm.razonar_libre = lanza_y_luego_responde  # type: ignore[method-assign]

    uc = ValidarConflictosNormativos(
        session=object(), llm=llm, top_k_por_articulo=2,
    )
    result = await uc.ejecutar(articulado=["Artículo 1° — X."])
    # Primer par se ignora (exc), segundo registra conflicto.
    assert len(result) == 1
    assert result[0].articulo_label == "Artículo 15"


@pytest.mark.asyncio
async def test_json_invalido_se_ignora(monkeypatch) -> None:
    """JSON malformado del LLM se loguea y se omite el par."""
    chunk = _chunk()
    stub = _StubBuscador({"Artículo 1° — X.": [chunk]})
    monkeypatch.setattr(vcn_mod, "BuscarNormativaSimilar", stub)

    llm = StubLlm(["esto no es json {{{"])
    uc = ValidarConflictosNormativos(
        session=object(), llm=llm, top_k_por_articulo=1,
    )
    result = await uc.ejecutar(articulado=["Artículo 1° — X."])
    assert result == []


@pytest.mark.asyncio
async def test_texto_norma_referida_se_recorta_400(monkeypatch) -> None:
    """texto_norma_referida queda capada en 400 chars para no saturar UI."""
    texto_largo = "A" * 1200
    chunk = _chunk(texto=texto_largo)
    stub = _StubBuscador({"Artículo 1° — X.": [chunk]})
    monkeypatch.setattr(vcn_mod, "BuscarNormativaSimilar", stub)

    llm = StubLlm([json.dumps({"severidad": "conflicto", "explicacion": "Y"})])
    uc = ValidarConflictosNormativos(
        session=object(), llm=llm, top_k_por_articulo=1,
    )
    result = await uc.ejecutar(articulado=["Artículo 1° — X."])
    assert len(result[0].texto_norma_referida) == 400
