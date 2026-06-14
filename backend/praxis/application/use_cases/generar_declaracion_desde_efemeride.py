"""Generar proyecto de declaración desde efeméride (feat-53.3).

90% de los proyectos de declaración en HCDN/HSN conmemoran una
efeméride. Este caso de uso automatiza ese flujo:

1. Toma una efeméride (ej. "Día Internacional de la Mujer").
2. Construye un tema rico usando título + descripción + áreas
   temáticas relacionadas.
3. Llama a `GenerarArticuladoConLLM` con tipo=PROYECTO_DECLARACION.
4. Llama a `GenerarFundamentosConLLM` para construir el cuerpo.
5. Devuelve el proyecto completo listo para revisar y publicar.

El asesor puede después refinar con `RefinarArticuloConLLM` o
agregar antecedentes/cofirmantes con los use cases dedicados.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from praxis.application.ports import (
    EfemerideRepository,
    LlmProvider,
    PerfilOpositorRepository,
)
from praxis.application.use_cases.asistir_redaccion_proyecto import (
    GenerarArticuladoConLLM,
    GenerarFundamentosConLLM,
)
from praxis.domain import (
    EFEMERIDE_TIPO_LABELS,
    Efemeride,
    TipoProyecto,
)

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DeclaracionDesdeEfemeride:
    """Resultado del use case: declaración generada + metadata."""

    efemeride: Efemeride
    tema_generado: str            # el "tema" que se le pasó al LLM
    articulado: list[str]
    fundamentos: str
    modelo: str


class EfemerideNoEncontrada(Exception):
    """La efeméride solicitada no existe."""

    def __init__(self, efemeride_id: UUID) -> None:
        super().__init__(f"Efeméride {efemeride_id} no encontrada")
        self.efemeride_id = efemeride_id


class GenerarDeclaracionDesdeEfemeride:
    """Use case orquestador (feat-53.3)."""

    def __init__(
        self,
        *,
        efemerides: EfemerideRepository,
        perfiles: PerfilOpositorRepository,
        llm: LlmProvider,
    ) -> None:
        self._efemerides = efemerides
        self._perfiles = perfiles
        self._llm = llm
        self._articulador = GenerarArticuladoConLLM(
            perfiles=perfiles, llm=llm,
        )
        self._fundamentos = GenerarFundamentosConLLM(
            perfiles=perfiles, llm=llm,
        )

    async def ejecutar(
        self,
        *,
        efemeride_id: UUID,
        despacho_id: UUID,
    ) -> DeclaracionDesdeEfemeride:
        efemeride = await self._efemerides.buscar_por_id(efemeride_id)
        if efemeride is None:
            raise EfemerideNoEncontrada(efemeride_id)

        tema = self._armar_tema(efemeride)
        log.info(
            "efemeride.declaracion.armado",
            efemeride_id=str(efemeride_id),
            tema_preview=tema[:80],
        )

        articulado_res = await self._articulador.ejecutar(
            despacho_id=despacho_id,
            tipo=TipoProyecto.DECLARACION,
            tema=tema,
        )
        fundamentos_res = await self._fundamentos.ejecutar(
            despacho_id=despacho_id,
            tipo=TipoProyecto.DECLARACION,
            tema=tema,
            articulado=articulado_res.articulado,
        )

        return DeclaracionDesdeEfemeride(
            efemeride=efemeride,
            tema_generado=tema,
            articulado=articulado_res.articulado,
            fundamentos=fundamentos_res.fundamentos,
            modelo=articulado_res.modelo,
        )

    def _armar_tema(self, ef: Efemeride) -> str:
        """Convierte la efeméride en un 'tema' que el LLM entiende.

        Incluye todo lo relevante para que el articulado conmemore
        adecuadamente: título, fecha, contexto histórico (si hay),
        tipo de efeméride y áreas temáticas para que el LLM tome
        decisiones de tono y léxico.
        """
        partes = [
            f"Declarar de interés / expresar adhesión a la conmemoración "
            f"del {ef.fecha_corta} — {ef.titulo}.",
            f"Tipo de efeméride: {EFEMERIDE_TIPO_LABELS[ef.tipo]}.",
        ]
        if ef.descripcion:
            partes.append(f"Contexto histórico: {ef.descripcion}")
        if ef.fuente:
            partes.append(f"Fuente declaratoria / referencia: {ef.fuente}")
        if ef.areas_tematicas:
            partes.append(
                f"Áreas temáticas relacionadas: {', '.join(ef.areas_tematicas)}."
            )
        if ef.anio_unico is not None:
            partes.append(
                f"Esta es una conmemoración puntual del año {ef.anio_unico} "
                f"(no recurrente)."
            )
        partes.append(
            "El proyecto debe declarar de interés la conmemoración y "
            "expresar adhesión, sin entrar en disposiciones de fondo."
        )
        return "\n".join(partes)
