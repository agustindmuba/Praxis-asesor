"""Caso de uso: evaluar accionabilidad de normas BO para un despacho.

Pipeline (spec 15 §"Pipeline diario nocturno"):

1. Cargar perfil de interés del despacho (si no hay → score 0 para todo).
2. Por cada NormaBO de la fecha:
   2.1. Asegurar clasificación cacheada (`ClasificacionNormaBORepository`);
        si falta, llamar al `LlmProvider.clasificar_norma_bo()` y
        persistir.
   2.2. Calcular score 0-100 cruzando perfil + clasificación + organismo
        + sumario contra distritos observados.
3. Borrar accionables previas del (despacho, fecha) — recálculo atómico.
4. Persistir top-N por score >= SCORE_MINIMO_ACCIONABLE.

El scoring no es LLM — es heurístico determinístico. El LLM sólo aporta
la clasificación general (área temática + palabras clave + referencias).

Ver `docs/specs/15-resumen-bo-accionable.md` §"Accionabilidad por
despacho".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from praxis.application.ports import (
    ClasificacionNormaBORepository,
    LlmProvider,
    NormaBOAccionableRepository,
    NormaBORepository,
    NormaBOTextoRepository,
    PerfilInteresDespachoRepository,
)
from praxis.domain import (
    BO_PROMPT_VERSION,
    MAX_RAZON_ACCIONABILIDAD_CHARS,
    SCORE_MINIMO_ACCIONABLE,
    AreaTematica,
    ClasificacionNormaBO,
    NormaBO,
    NormaBOAccionable,
    PerfilInteresDespacho,
    prioridad_para_score,
)

# Top default que la spec 15 sugiere mostrar en el briefing.
TOP_N_ACCIONABLES_DEFAULT = 5

# Pesos del scoring (suma máxima posible = 90 → cabe holgado en [0,100]).
SCORE_AREA_TEMATICA_MATCH = 30
SCORE_AFECTA_EXPEDIENTES_HCDN = 35
SCORE_DISTRITO_MENCIONADO = 10
SCORE_DESIGNACION_AREA_PROPIA = 15


@dataclass(frozen=True, slots=True)
class _ScoringResult:
    score: int
    razon: str


class EvaluarAccionabilidadPorDespacho:
    """Orquesta clasificación + scoring + persistencia de accionabilidad
    BO para un despacho en una fecha dada."""

    def __init__(
        self,
        *,
        perfiles: PerfilInteresDespachoRepository,
        normas: NormaBORepository,
        textos: NormaBOTextoRepository,
        clasificaciones: ClasificacionNormaBORepository,
        accionables: NormaBOAccionableRepository,
        llm: LlmProvider,
    ) -> None:
        self._perfiles = perfiles
        self._normas = normas
        self._textos = textos
        self._clasificaciones = clasificaciones
        self._accionables = accionables
        self._llm = llm

    async def execute(
        self,
        *,
        despacho_id: UUID,
        fecha: date,
        top_n: int = TOP_N_ACCIONABLES_DEFAULT,
    ) -> list[NormaBOAccionable]:
        perfil = await self._perfiles.buscar_por_despacho(despacho_id)
        normas = await self._normas.listar_por_fecha(fecha)
        if not normas:
            # Nada que procesar — limpiamos accionables previas igual.
            await self._accionables.borrar_por_despacho_y_fecha(
                despacho_id=despacho_id, fecha=fecha,
            )
            return []

        # Evaluación + scoring por norma.
        candidatas: list[tuple[NormaBO, _ScoringResult]] = []
        for norma in normas:
            assert norma.id is not None   # vinieron persistidas
            clasif = await self._asegurar_clasificacion(norma)
            scoring = _calcular_score(
                norma=norma, clasificacion=clasif, perfil=perfil,
            )
            if scoring.score >= SCORE_MINIMO_ACCIONABLE:
                candidatas.append((norma, scoring))

        # Recálculo atómico: borrar accionables previas y reinsertar
        # las que pasaron el umbral.
        await self._accionables.borrar_por_despacho_y_fecha(
            despacho_id=despacho_id, fecha=fecha,
        )
        candidatas.sort(key=lambda x: x[1].score, reverse=True)
        if top_n is not None:
            candidatas = candidatas[:top_n]

        creadas: list[NormaBOAccionable] = []
        ahora = datetime.now(UTC)
        for norma, scoring in candidatas:
            assert norma.id is not None
            accionable = NormaBOAccionable(
                norma_id=norma.id,
                despacho_id=despacho_id,
                score=scoring.score,
                prioridad=prioridad_para_score(scoring.score),
                razon=scoring.razon,
                expedientes_tocados=[],   # v1: sin matching por número
                generado_en=ahora,
            )
            creadas.append(await self._accionables.upsert(accionable))
        return creadas

    async def _asegurar_clasificacion(
        self, norma: NormaBO,
    ) -> ClasificacionNormaBO:
        """Lookup en cache; si falta, llama al LLM y persiste."""
        assert norma.id is not None
        cacheada = await self._clasificaciones.buscar_por_norma(norma.id)
        if cacheada is not None:
            return cacheada

        # No hay cache: llamar al LLM.
        texto_obj = await self._textos.buscar_por_norma(norma.id)
        texto = texto_obj.texto if texto_obj is not None else None
        result = await self._llm.clasificar_norma_bo(norma, texto=texto)
        clasif = ClasificacionNormaBO(
            id=uuid4(),
            norma_id=norma.id,
            area_tematica=result.area_tematica,
            palabras_clave=list(result.palabras_clave),
            afecta_expedientes_hcdn=result.afecta_expedientes_hcdn,
            referencias_legales=list(result.referencias_legales),
            modelo=self._llm.nombre_modelo,
            prompt_version=BO_PROMPT_VERSION,
        )
        return await self._clasificaciones.crear(clasif)


def _calcular_score(
    *,
    norma: NormaBO,
    clasificacion: ClasificacionNormaBO,
    perfil: PerfilInteresDespacho | None,
) -> _ScoringResult:
    """Scoring heurístico spec 15 §"Accionabilidad por despacho".

    Suma puntos por componente y compone una razón en lenguaje natural.

    Sin perfil → score 0 (la norma no será accionable para este despacho).
    """
    if perfil is None:
        return _ScoringResult(score=0, razon="")

    razones: list[str] = []
    score = 0

    # 1. Área temática en perfil.
    if clasificacion.area_tematica.value in perfil.areas_tematicas:
        score += SCORE_AREA_TEMATICA_MATCH
        razones.append(f"toca tu área {clasificacion.area_tematica.value}")

    # 2. Afecta expedientes HCDN según el clasificador.
    if clasificacion.afecta_expedientes_hcdn:
        score += SCORE_AFECTA_EXPEDIENTES_HCDN
        if clasificacion.referencias_legales:
            primera_ref = clasificacion.referencias_legales[0]
            razones.append(f"menciona {primera_ref}")
        else:
            razones.append("afecta expedientes en trámite")

    # 3. Designación en organismo de un área del perfil.
    if _es_designacion(norma) and (
        clasificacion.area_tematica.value in perfil.areas_tematicas
        or clasificacion.area_tematica == AreaTematica.OTROS
    ):
        score += SCORE_DESIGNACION_AREA_PROPIA
        razones.append("designación en organismo de interés")

    # 4. Distrito observado mencionado en sumario u organismo.
    distrito_match = _distrito_mencionado(norma, perfil.distritos_observados)
    if distrito_match is not None:
        score += SCORE_DISTRITO_MENCIONADO
        razones.append(f"refiere a {distrito_match}")

    # Razón en lenguaje natural — 1 frase ≤ 140 chars.
    razon = _componer_razon(razones)
    return _ScoringResult(score=min(score, 100), razon=razon)


def _es_designacion(norma: NormaBO) -> bool:
    """Heurística: decreto + sumario que arranca con 'desígnase' / 'designase'."""
    if "decreto" not in norma.tipo_norma.lower():
        return False
    sum_lower = norma.sumario.lower()
    return sum_lower.startswith(("desígnase", "designase", "design"))


def _distrito_mencionado(
    norma: NormaBO, distritos: list[str],
) -> str | None:
    """Devuelve el primer distrito que aparece en sumario u organismo."""
    haystack = f"{norma.sumario} {norma.organismo_emisor}".lower()
    for distrito in distritos:
        if distrito.lower() in haystack:
            return distrito
    return None


def _componer_razon(razones: list[str]) -> str:
    """Une las razones en una frase corta; respeta el cap de chars."""
    if not razones:
        # Razón mínima — solo aparece si el score es por algo no
        # cubierto en las razones (edge case improbable).
        return "Coincidencia parcial con el perfil del despacho"
    base = "Norma " + " y ".join(razones[:2])
    base = base[0].upper() + base[1:]
    base = base.rstrip(". ") + "."
    if len(base) <= MAX_RAZON_ACCIONABILIDAD_CHARS:
        return base
    # Truncar respetando el límite. Margen de "…" al final.
    truncado = base[: MAX_RAZON_ACCIONABILIDAD_CHARS - 1].rstrip()
    return truncado + "…"
