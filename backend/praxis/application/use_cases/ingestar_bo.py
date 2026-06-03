"""Caso de uso: ingesta del Boletín Oficial para una fecha.

Pipeline simple del job nocturno (spec 15 §"Pipeline diario"):

1. Por cada sección activa (v1: sólo LEGISLACION):
   1.1. Bajar PDF del día desde `FuenteBO.listar_normas_del_dia()`.
   1.2. Upsert idempotente por identidad natural en NormaBORepository.
   1.3. Para las normas nuevas, obtener el texto via
        `FuenteBO.obtener_texto_completo()` y persistir en
        NormaBOTextoRepository.

Idempotente: re-correr la misma corrida no duplica filas. Las normas
que ya existen se devuelven sin tocar.

Es independiente del clasificador y del scoring por despacho — esos
viven en `ClasificarNormasBOPendientes` y
`EvaluarAccionabilidadPorDespacho` respectivamente.

Ver `docs/specs/15-resumen-bo-accionable.md`.
"""

from __future__ import annotations

from datetime import date

from praxis.application.ports import (
    FuenteBO,
    NormaBORepository,
    NormaBOTextoRepository,
)
from praxis.domain import (
    SECCIONES_ACTIVAS_V1,
    NormaBO,
    NormaBOTexto,
    SeccionBO,
)


class IngestarBoletinOficial:
    """Caso de uso de ingesta. Idempotente por fecha + sección."""

    def __init__(
        self,
        *,
        fuente: FuenteBO,
        normas: NormaBORepository,
        textos: NormaBOTextoRepository,
    ) -> None:
        self._fuente = fuente
        self._normas = normas
        self._textos = textos

    async def execute(
        self,
        *,
        fecha: date,
        secciones: list[SeccionBO] | None = None,
    ) -> int:
        """Ingesta para una fecha. Devuelve la cantidad total de normas
        persistidas (nuevas o pre-existentes confirmadas).

        Si `secciones` es None, usa `SECCIONES_ACTIVAS_V1`.
        """
        activas = secciones or list(SECCIONES_ACTIVAS_V1)
        total = 0
        for seccion in activas:
            cantidad = await self._ingerir_seccion(fecha, seccion)
            total += cantidad
        return total

    async def _ingerir_seccion(
        self, fecha: date, seccion: SeccionBO,
    ) -> int:
        # FuenteBO devuelve NormaBO sin id (entidades nuevas) cuando
        # corresponde al día corriente. Persistimos idempotente.
        normas_de_fuente = await self._fuente.listar_normas_del_dia(
            fecha, seccion,
        )
        if not normas_de_fuente:
            return 0

        persistidas = await self._normas.upsert_lote(normas_de_fuente)

        # Para cada norma persistida nueva (sin id en la fuente pero con
        # id tras upsert), aseguramos el texto. Si ya está, el repo
        # NO se llama (no tenemos exists() — checamos por buscar_por_norma).
        await self._asegurar_textos(persistidas)
        return len(persistidas)

    async def _asegurar_textos(self, normas: list[NormaBO]) -> None:
        for norma in normas:
            assert norma.id is not None
            existente = await self._textos.buscar_por_norma(norma.id)
            if existente is not None:
                continue
            texto = await self._fuente.obtener_texto_completo(norma)
            if texto is None or not texto.strip():
                # Sin texto disponible — saltamos. La invariante de
                # NormaBOTexto exige texto no vacío.
                continue
            await self._textos.crear(
                NormaBOTexto(
                    norma_id=norma.id,
                    texto=texto,
                    capturado_en=norma.capturado_en,
                )
            )
