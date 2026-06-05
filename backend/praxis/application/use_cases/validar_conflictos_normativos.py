"""Casos de uso de RAG normativo (feat-42.6).

1. `BuscarNormativaSimilar(query, top_k) → list[ChunkSimilar]`
   Búsqueda semántica directa por cosine sobre `norma_juridica_chunk`.

2. `ValidarConflictosNormativos(proyecto) → list[ConflictoDetectado]`
   Para cada artículo del proyecto:
   - Busca los top 5 chunks normativos más similares (cosine).
   - Pasa al LLM (Sonnet) los pares (artículo proyecto, chunk normativo)
     con instrucción: "¿este artículo entra en conflicto, deroga,
     modifica tácitamente, o se complementa con esta norma?"
   - Si el LLM detecta conflicto/modificación/derogación, agrega a la
     lista de conflictos.

Diseño: el caso de uso es READ-ONLY. NO modifica el proyecto.
La UI muestra los conflictos y deja que el asesor decida.

Costo por validación de proyecto típico (5-7 artículos):
- Embeddings: gratis (local).
- 5-7 búsquedas Postgres: gratis.
- 5-7 llamadas LLM × top-5 chunks → ~25-35 llamadas Sonnet × ~500 tokens
  output = ~$0.15-0.25 USD.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from praxis.application.ports import LlmProvider
from praxis.infrastructure.rag.embedder import embeber_textos

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ChunkSimilar:
    """Un chunk normativo devuelto por la búsqueda semántica."""

    fuente: str
    articulo_label: str
    texto: str
    distancia: float          # 0 = idéntico (cosine), 1 = ortogonal


@dataclass(frozen=True, slots=True)
class ConflictoDetectado:
    """Resultado del análisis LLM por par (artículo proyecto, chunk)."""

    indice_articulo_proyecto: int    # 0-based en el articulado del proyecto
    fuente: str                       # ej "ley_25188_etica_publica"
    articulo_label: str               # ej "Artículo 14"
    severidad: str                    # "conflicto" | "modificacion" | "complementa" | "ninguno"
    explicacion: str
    texto_norma_referida: str         # primeros 400 chars para contexto UI


# Reusa el mismo escape hatch `razonar_libre` del LlmProvider.
SYSTEM_PROMPT_CONFLICTO = """Sos un asesor jurídico parlamentario.
Te paso un ARTÍCULO de un PROYECTO en redacción y una NORMA VIGENTE
de derecho público argentino. Tu tarea: evaluar la relación entre
ambos.

Devolvé EXACTAMENTE este JSON:

{
  "severidad": "conflicto | modificacion | complementa | ninguno",
  "explicacion": "1-3 oraciones explicando la relación. Si severidad=conflicto, especificá el conflicto. Si ninguno, decí por qué no se tocan."
}

Reglas:
- "conflicto" = el artículo propuesto contradice o anula derecho/obligación de la norma vigente. Riesgo de inconstitucionalidad o derogación tácita.
- "modificacion" = el artículo propuesto enmienda implícitamente la norma vigente sin decirlo. Esto requiere cláusula expresa de derogación.
- "complementa" = el artículo propuesto extiende, regula o operativiza la norma vigente. Sano si está bien encuadrado.
- "ninguno" = el artículo y la norma tratan temas distintos o el solapamiento es incidental.

NO inventes contenido de la norma — si el texto no es claro, devolvé "ninguno" con esa observación.
"""


class BuscarNormativaSimilar:
    """Use case 1: búsqueda semántica directa sobre el corpus."""

    def __init__(self, *, session: AsyncSession) -> None:
        self._session = session

    async def ejecutar(
        self, *, query: str, top_k: int = 10,
    ) -> list[ChunkSimilar]:
        if not query.strip():
            return []
        emb = embeber_textos([query])[0]
        # pgvector usa <=> para cosine distance cuando el índice es
        # vector_cosine_ops. El operador <=> devuelve 0 = idéntico.
        result = await self._session.execute(
            text("""
            SELECT
                fuente,
                articulo_label,
                texto,
                (embedding <=> CAST(:emb AS vector)) AS distancia
            FROM norma_juridica_chunk
            WHERE embedding IS NOT NULL
            ORDER BY distancia ASC
            LIMIT :top_k
            """),
            {"emb": str(emb), "top_k": top_k},
        )
        return [
            ChunkSimilar(
                fuente=r[0],
                articulo_label=r[1],
                texto=r[2],
                distancia=float(r[3]),
            )
            for r in result.all()
        ]


class ValidarConflictosNormativos:
    """Use case 2: por cada artículo del proyecto, evalúa conflictos
    con el corpus normativo cargado."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        llm: LlmProvider,
        top_k_por_articulo: int = 5,
    ) -> None:
        self._session = session
        self._llm = llm
        self._top_k = top_k_por_articulo

    async def ejecutar(
        self, *, articulado: list[str],
    ) -> list[ConflictoDetectado]:
        buscador = BuscarNormativaSimilar(session=self._session)
        conflictos: list[ConflictoDetectado] = []
        for indice, articulo in enumerate(articulado):
            if not articulo.strip():
                continue
            candidatos = await buscador.ejecutar(
                query=articulo, top_k=self._top_k,
            )
            for chunk in candidatos:
                resultado = await self._evaluar_par(
                    articulo_proyecto=articulo, chunk=chunk,
                )
                if resultado is None:
                    continue
                # Solo registramos conflicto/modificacion para no
                # inflar la UI con "ninguno"s.
                if resultado["severidad"] in ("conflicto", "modificacion"):
                    conflictos.append(
                        ConflictoDetectado(
                            indice_articulo_proyecto=indice,
                            fuente=chunk.fuente,
                            articulo_label=chunk.articulo_label,
                            severidad=resultado["severidad"],
                            explicacion=resultado["explicacion"],
                            texto_norma_referida=chunk.texto[:400],
                        ),
                    )
        return conflictos

    async def _evaluar_par(
        self, *, articulo_proyecto: str, chunk: ChunkSimilar,
    ) -> dict | None:
        contenido = (
            f"=== ARTÍCULO DEL PROYECTO EN REDACCIÓN ===\n"
            f"{articulo_proyecto[:1500]}\n\n"
            f"=== NORMA VIGENTE: {chunk.fuente} / {chunk.articulo_label} ===\n"
            f"{chunk.texto[:1500]}\n\n"
            f"Devolvé el JSON con la severidad."
        )
        try:
            raw, _ = await self._llm.razonar_libre(
                system=SYSTEM_PROMPT_CONFLICTO,
                user=contenido,
                max_tokens=600,
            )
        except Exception as exc:
            log.warning("LLM falló evaluando %s: %s", chunk.fuente, exc)
            return None
        try:
            return self._parsear_json(raw)
        except Exception as exc:
            log.warning("Parse JSON falló (%s): %s", chunk.fuente, exc)
            return None

    def _parsear_json(self, raw: str) -> dict:
        s = raw.strip()
        if s.startswith("```"):
            s = s.split("\n", 1)[1] if "\n" in s else s
            if s.endswith("```"):
                s = s[:-3].strip()
            if s.startswith("json"):
                s = s[4:].strip()
        return json.loads(s)
