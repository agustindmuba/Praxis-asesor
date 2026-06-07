"""Router /expedientes — listado/búsqueda + ficha individual."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from praxis.api.deps import CurrentContext, LlmProviderDep, SessionDep
from praxis.api.schemas import (
    ExpedienteFicha,
    FiltrosExpediente,
    InteligenciaExpedienteDTO,
    ResultadoBusquedaDTO,
    ResumenEjecutivoDTO,
)
from praxis.application import (
    CalcularInteligenciaExpediente,
    GenerarResumenEjecutivo,
)
from praxis.domain import (
    Camara,
    ExpedienteNoEncontrado,
    NumeroExpediente,
)
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyExpedienteRepository,
    SqlAlchemyResumenEjecutivoRepository,
    SqlAlchemySeguimientoExpedienteRepository,
)

router = APIRouter(prefix="/expedientes", tags=["expedientes"])


@router.get(
    "",
    summary="Búsqueda paginada de expedientes",
    response_model=ResultadoBusquedaDTO,
)
async def listar_expedientes(
    session: SessionDep,
    ctx: CurrentContext,
    filtros: Annotated[FiltrosExpediente, Query()],
) -> ResultadoBusquedaDTO:
    """Busca expedientes con los filtros del query string.

    El catálogo de expedientes es **global** (todos los despachos ven los
    mismos datos públicos). Lo tenant-scoped es el seguimiento (ver
    POST /seguimientos), no el expediente en sí.

    Igualmente exigimos auth (`ctx`) para no servir el catálogo a anónimos.
    """
    # Los toggles `solo_seguidos` / `solo_titular` se resuelven con el
    # despacho activo del request (feat-43.1).
    repo = SqlAlchemyExpedienteRepository(session)
    resultado = await repo.buscar(filtros.to_domain(despacho=ctx.despacho))
    return ResultadoBusquedaDTO.from_domain(resultado)


@router.get(
    "/{expediente_id}",
    summary="Ficha completa de un expediente",
    response_model=ExpedienteFicha,
)
async def ficha_expediente(
    expediente_id: UUID,
    session: SessionDep,
    ctx: CurrentContext,
) -> ExpedienteFicha:
    """Devuelve el expediente con firmantes, giros y trámite.

    Si el despacho activo sigue este expediente, embebe el seguimiento
    para que el frontend pueda mostrar prioridad/responsable/estado en
    la misma vista, sin un round trip extra.
    """
    exp_repo = SqlAlchemyExpedienteRepository(session)
    expediente = await exp_repo.buscar_por_id(expediente_id)
    if expediente is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Expediente no encontrado",
        )

    seg_repo = SqlAlchemySeguimientoExpedienteRepository(session)
    seguimiento = await seg_repo.buscar(
        despacho_id=ctx.despacho.id,
        expediente_id=expediente_id,
    )

    return ExpedienteFicha.from_domain(expediente, seguimiento=seguimiento)


@router.post(
    "/{expediente_id}/resumir",
    summary="Genera (o devuelve cacheado) el resumen ejecutivo con IA",
    response_model=ResumenEjecutivoDTO,
)
async def resumir_expediente(
    expediente_id: UUID,
    session: SessionDep,
    ctx: CurrentContext,
    llm: LlmProviderDep,
) -> ResumenEjecutivoDTO:
    """Devuelve un resumen ejecutivo del expediente, generado por LLM.

    Idempotente: si ya hay resumen cacheado, lo devuelve. Sino, llama al
    `LlmProvider` configurado (Fake en dev, Anthropic cuando hay API key).

    El catálogo de expedientes es global; el resumen también lo es
    (todos los despachos ven el mismo). Auth solo sirve para no servir
    a anónimos. Ver `docs/specs/13-resumen-ejecutivo-ia.md`.
    """
    del ctx  # auth exigida, no se usa en la lógica todavía.
    use_case = GenerarResumenEjecutivo(
        expedientes=SqlAlchemyExpedienteRepository(session),
        resumenes=SqlAlchemyResumenEjecutivoRepository(session),
        llm=llm,
    )
    try:
        resumen = await use_case.execute(expediente_id)
    except ExpedienteNoEncontrado as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Expediente no encontrado",
        ) from exc

    # Commit (el caso de uso solo flushea).
    await session.commit()

    return ResumenEjecutivoDTO.model_validate(resumen)


@router.get(
    "/{expediente_id}/inteligencia",
    summary="Panel de inteligencia: progreso del trámite + comparación con peers",
    response_model=InteligenciaExpedienteDTO,
)
async def inteligencia_expediente(
    expediente_id: UUID,
    session: SessionDep,
    ctx: CurrentContext,
) -> InteligenciaExpedienteDTO:
    """Devuelve el panel data-driven del expediente.

    Calcula a demanda (no se cachea — el dato cambia con cada nuevo
    expediente que se agrega al catálogo). Es liviano: 1 query SQL
    agregada sobre peers + cálculo en Python sobre el propio expediente.
    """
    del ctx  # auth exigida, lógica global.
    use_case = CalcularInteligenciaExpediente(
        session=session,
        expedientes=SqlAlchemyExpedienteRepository(session),
    )
    try:
        inteligencia = await use_case.execute(expediente_id)
    except ExpedienteNoEncontrado as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Expediente no encontrado",
        ) from exc

    return InteligenciaExpedienteDTO.model_validate(inteligencia)


# ---------------------------------------------------------------------------
# Resolver números HCDN → UUIDs (feat/31)
# ---------------------------------------------------------------------------


class ResolverNumerosBody(BaseModel):
    """Lista de números HCDN/HSN en formato texto a resolver."""

    numeros: list[str] = Field(default_factory=list, min_length=1)


class NumeroResuelto(BaseModel):
    numero_raw: str
    expediente_id: UUID
    titulo: str


class ResolverNumerosResponse(BaseModel):
    resueltos: list[NumeroResuelto]
    no_encontrados: list[str]
    invalidos: list[str]


@router.post(
    "/resolver-numeros",
    summary="Resuelve números '0013-D-2024' → UUIDs",
    response_model=ResolverNumerosResponse,
)
async def resolver_numeros(
    body: ResolverNumerosBody,
    session: SessionDep,
    ctx: CurrentContext,
) -> ResolverNumerosResponse:
    """Best-effort resolver: para cada string, intenta parsear como número
    HCDN (`NNNN-X-YYYY`) o HSN (`NNNN/YY`) y buscarlo en DB.

    Devuelve:
    - `resueltos`: los que matchearon (incluye titulo para feedback en UI).
    - `no_encontrados`: parsearon pero no están en DB.
    - `invalidos`: no parsearon a ningún formato conocido.

    Tenant: pide auth pero no filtra por despacho — el catálogo es global.
    """
    del ctx
    repo = SqlAlchemyExpedienteRepository(session)
    resueltos: list[NumeroResuelto] = []
    no_encontrados: list[str] = []
    invalidos: list[str] = []

    for raw in body.numeros:
        raw_stripped = raw.strip()
        if not raw_stripped:
            continue
        # Intentar HCDN primero (formato más común en el corpus).
        numero: NumeroExpediente | None = None
        try:
            numero = NumeroExpediente.parse_hcdn(raw_stripped)
        except ValueError:
            try:
                numero = NumeroExpediente.parse_hsn(raw_stripped)
                # parse_hsn devuelve por default Camara=HSN.
                numero = NumeroExpediente(
                    numero=numero.numero,
                    origen=numero.origen,
                    anio=numero.anio,
                    camara=Camara.HSN,
                )
            except ValueError:
                invalidos.append(raw_stripped)
                continue

        expediente = await repo.buscar_por_numero(numero)
        if expediente is None or expediente.id is None:
            no_encontrados.append(raw_stripped)
            continue
        resueltos.append(
            NumeroResuelto(
                numero_raw=raw_stripped,
                expediente_id=expediente.id,
                titulo=expediente.titulo,
            )
        )

    return ResolverNumerosResponse(
        resueltos=resueltos,
        no_encontrados=no_encontrados,
        invalidos=invalidos,
    )
