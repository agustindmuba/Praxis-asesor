"""Tests de integración de búsqueda filtrada sobre ExpedienteRepository.

Ver spec: docs/specs/08-busqueda-expedientes.md
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from praxis.domain import (
    Camara,
    EstadoExpediente,
    Expediente,
    ExpedienteQuery,
    Firmante,
    Giro,
    NumeroExpediente,
    OrigenExpediente,
    TipoExpediente,
)
from praxis.infrastructure.persistence.base import Base
from praxis.infrastructure.persistence.repositories import SqlAlchemyExpedienteRepository

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as s:
        yield s
    await engine.dispose()


@pytest_asyncio.fixture
async def repo(session: AsyncSession) -> SqlAlchemyExpedienteRepository:
    return SqlAlchemyExpedienteRepository(session)


async def _seed_corpus(repo: SqlAlchemyExpedienteRepository) -> None:
    """Inserta un corpus heterogéneo para que los filtros tengan algo
    significativo que separar.

    Resumen del seed (firmantes/comisión en mayúsculas, como en el portal):

    - 1-D-2024 | LEY  | HCDN | "Presupuesto Salud" | Massot | Salud   | EN_COMISION  | 2024-03-15
    - 2-D-2024 | LEY  | HCDN | "Reforma Tributaria"| Massot | Hacienda| CON_DICTAMEN | 2024-04-01
    - 3-S-2023 | LEY  | HSN  | "Educacion publica" | Fernández | Educ. | EN_COMISION | 2023-12-10
    - 4-D-2025 | RESO | HCDN | "Declaracion ..."   | Garcia | Cultura | INGRESADO    | 2025-02-20
    - 5-PE-2024| MSJ  | HCDN | "Convenio ..."      | (sin)  | RR EE   | DESCONOCIDO  | NULL
    """
    await repo.crear(
        Expediente(
            numero=NumeroExpediente.parse_hcdn("1-D-2024"),
            tipo=TipoExpediente.PROYECTO_LEY,
            titulo="Presupuesto Salud 2024",
            sumario="Asignacion de fondos al sistema sanitario",
            fecha_ingreso=date(2024, 3, 15),
            estado=EstadoExpediente.EN_COMISION,
            firmantes=[Firmante(nombre="MASSOT, NICOLAS", orden=1)],
            giros=[Giro(comision="ACCION SOCIAL Y SALUD PUBLICA")],
        )
    )
    await repo.crear(
        Expediente(
            numero=NumeroExpediente.parse_hcdn("2-D-2024"),
            tipo=TipoExpediente.PROYECTO_LEY,
            titulo="Reforma Tributaria",
            sumario="Impuesto a las ganancias",
            fecha_ingreso=date(2024, 4, 1),
            estado=EstadoExpediente.CON_DICTAMEN,
            firmantes=[Firmante(nombre="MASSOT, NICOLAS", orden=1)],
            giros=[Giro(comision="PRESUPUESTO Y HACIENDA")],
        )
    )
    await repo.crear(
        Expediente(
            numero=NumeroExpediente.parse_hsn("3/23"),  # NumeroExpediente HSN
            tipo=TipoExpediente.PROYECTO_LEY,
            titulo="Educacion publica",
            sumario="Inversion en universidades",
            fecha_ingreso=date(2023, 12, 10),
            estado=EstadoExpediente.EN_COMISION,
            firmantes=[Firmante(nombre="FERNANDEZ, MARIA", orden=1)],
            giros=[Giro(comision="EDUCACION Y CULTURA")],
        )
    )
    await repo.crear(
        Expediente(
            numero=NumeroExpediente.parse_hcdn("4-D-2025"),
            tipo=TipoExpediente.PROYECTO_RESOLUCION,
            titulo="Declaracion de homenaje",
            sumario="Reconocimiento a docentes",
            fecha_ingreso=date(2025, 2, 20),
            estado=EstadoExpediente.INGRESADO,
            firmantes=[Firmante(nombre="GARCIA, JUAN", orden=1)],
            giros=[Giro(comision="CULTURA")],
        )
    )
    await repo.crear(
        Expediente(
            numero=NumeroExpediente.parse_hcdn("5-PE-2024"),
            tipo=TipoExpediente.MENSAJE_PE,
            titulo="Convenio internacional firmado",
            # sin sumario, sin firmantes, sin fecha_ingreso
            estado=EstadoExpediente.DESCONOCIDO,
            giros=[Giro(comision="RELACIONES EXTERIORES")],
        )
    )


# --- Sin filtros: devuelve todos --------------------------------------------


async def test_buscar_sin_filtros_devuelve_todos(
    repo: SqlAlchemyExpedienteRepository,
) -> None:
    await _seed_corpus(repo)
    r = await repo.buscar(ExpedienteQuery())
    assert r.total == 5
    assert len(r.items) == 5
    assert r.limit == 50
    assert r.offset == 0


# --- Filtros estructurados ---------------------------------------------------


async def test_filtrar_por_camara(repo: SqlAlchemyExpedienteRepository) -> None:
    await _seed_corpus(repo)
    r = await repo.buscar(ExpedienteQuery(camara=Camara.HCDN))
    assert r.total == 4
    assert all(e.numero.camara == Camara.HCDN for e in r.items)


async def test_filtrar_por_tipo(repo: SqlAlchemyExpedienteRepository) -> None:
    await _seed_corpus(repo)
    r = await repo.buscar(ExpedienteQuery(tipo=TipoExpediente.PROYECTO_LEY))
    assert r.total == 3


async def test_filtrar_por_origen(repo: SqlAlchemyExpedienteRepository) -> None:
    await _seed_corpus(repo)
    r = await repo.buscar(ExpedienteQuery(origen=OrigenExpediente.EJECUTIVO))
    assert r.total == 1
    assert r.items[0].tipo == TipoExpediente.MENSAJE_PE


async def test_filtrar_por_anio(repo: SqlAlchemyExpedienteRepository) -> None:
    await _seed_corpus(repo)
    r = await repo.buscar(ExpedienteQuery(anio=2024))
    assert r.total == 3


async def test_filtrar_por_estado(repo: SqlAlchemyExpedienteRepository) -> None:
    await _seed_corpus(repo)
    r = await repo.buscar(ExpedienteQuery(estado=EstadoExpediente.EN_COMISION))
    assert r.total == 2


# --- Texto libre -------------------------------------------------------------


async def test_filtrar_por_texto_matchea_titulo(
    repo: SqlAlchemyExpedienteRepository,
) -> None:
    await _seed_corpus(repo)
    r = await repo.buscar(ExpedienteQuery(texto="presupuesto"))
    # "presupuesto" aparece en "Presupuesto Salud" (titulo) y en "PRESUPUESTO
    # Y HACIENDA" (que es una comisión, no se cuenta acá). Pero ojo: NO buscamos
    # en comision, solo en titulo+sumario.
    titulos = [e.titulo for e in r.items]
    assert "Presupuesto Salud 2024" in titulos
    assert (
        r.total == 1
    )  # solo el primero, "Reforma Tributaria" no menciona "presupuesto" en titulo/sumario


async def test_filtrar_por_texto_matchea_sumario(
    repo: SqlAlchemyExpedienteRepository,
) -> None:
    await _seed_corpus(repo)
    r = await repo.buscar(ExpedienteQuery(texto="ganancias"))
    assert r.total == 1
    assert r.items[0].titulo == "Reforma Tributaria"


async def test_filtrar_por_texto_case_insensitive(
    repo: SqlAlchemyExpedienteRepository,
) -> None:
    await _seed_corpus(repo)
    r1 = await repo.buscar(ExpedienteQuery(texto="EDUCACION"))
    r2 = await repo.buscar(ExpedienteQuery(texto="educacion"))
    r3 = await repo.buscar(ExpedienteQuery(texto="EdUcAcIoN"))
    assert r1.total == r2.total == r3.total == 1


async def test_filtrar_por_texto_no_encuentra_en_comision(
    repo: SqlAlchemyExpedienteRepository,
) -> None:
    """`texto` matchea solo titulo+sumario, no comision/firmantes."""
    await _seed_corpus(repo)
    # "RELACIONES EXTERIORES" es comisión del exp 5; "internacional" sí está en titulo.
    r_titulo = await repo.buscar(ExpedienteQuery(texto="internacional"))
    r_comision = await repo.buscar(ExpedienteQuery(texto="relaciones exteriores"))
    assert r_titulo.total == 1
    assert r_comision.total == 0  # no se busca en giros


# --- Filtros por relaciones (EXISTS) ----------------------------------------


async def test_filtrar_por_autor_nombre(
    repo: SqlAlchemyExpedienteRepository,
) -> None:
    await _seed_corpus(repo)
    r = await repo.buscar(ExpedienteQuery(autor_nombre="Massot"))
    assert r.total == 2  # exp 1 y 2
    titulos = {e.titulo for e in r.items}
    assert titulos == {"Presupuesto Salud 2024", "Reforma Tributaria"}


async def test_filtrar_por_autor_nombre_case_insensitive(
    repo: SqlAlchemyExpedienteRepository,
) -> None:
    await _seed_corpus(repo)
    r = await repo.buscar(ExpedienteQuery(autor_nombre="MASSOT"))
    assert r.total == 2


async def test_filtrar_por_comision(repo: SqlAlchemyExpedienteRepository) -> None:
    await _seed_corpus(repo)
    r = await repo.buscar(ExpedienteQuery(comision="salud"))
    assert r.total == 1
    assert r.items[0].titulo == "Presupuesto Salud 2024"


async def test_exists_no_duplica_expediente_con_multiples_firmantes(
    repo: SqlAlchemyExpedienteRepository,
) -> None:
    """Bug clásico de JOIN sin DISTINCT: si un exp tiene 3 firmantes que
    matchean, no debe aparecer 3 veces."""
    await repo.crear(
        Expediente(
            numero=NumeroExpediente.parse_hcdn("99-D-2024"),
            tipo=TipoExpediente.PROYECTO_LEY,
            titulo="Multi-firma",
            firmantes=[
                Firmante(nombre="LOPEZ, A", orden=1),
                Firmante(nombre="LOPEZ, B", orden=2),
                Firmante(nombre="LOPEZ, C", orden=3),
            ],
        )
    )
    r = await repo.buscar(ExpedienteQuery(autor_nombre="lopez"))
    assert r.total == 1
    assert len(r.items) == 1


# --- Rango de fechas ---------------------------------------------------------


async def test_filtrar_por_rango_de_fechas(
    repo: SqlAlchemyExpedienteRepository,
) -> None:
    await _seed_corpus(repo)
    r = await repo.buscar(
        ExpedienteQuery(
            fecha_ingreso_desde=date(2024, 1, 1),
            fecha_ingreso_hasta=date(2024, 12, 31),
        )
    )
    # Solo expedientes 2024 con fecha (exp 5 tiene fecha=NULL, no entra).
    assert r.total == 2
    assert all(e.fecha_ingreso is not None and e.fecha_ingreso.year == 2024 for e in r.items)


async def test_filtrar_solo_desde(repo: SqlAlchemyExpedienteRepository) -> None:
    await _seed_corpus(repo)
    r = await repo.buscar(ExpedienteQuery(fecha_ingreso_desde=date(2025, 1, 1)))
    assert r.total == 1
    assert r.items[0].titulo.startswith("Declaracion")


# --- Combinaciones AND -------------------------------------------------------


async def test_filtros_se_combinan_con_AND(
    repo: SqlAlchemyExpedienteRepository,
) -> None:
    await _seed_corpus(repo)
    r = await repo.buscar(
        ExpedienteQuery(
            camara=Camara.HCDN,
            tipo=TipoExpediente.PROYECTO_LEY,
            autor_nombre="Massot",
        )
    )
    # Massot firma 1 y 2 (ambos HCDN/LEY).
    assert r.total == 2


async def test_filtros_AND_que_no_intersectan_devuelve_vacio(
    repo: SqlAlchemyExpedienteRepository,
) -> None:
    await _seed_corpus(repo)
    r = await repo.buscar(ExpedienteQuery(camara=Camara.HSN, autor_nombre="Garcia"))
    assert r.total == 0
    assert r.items == []


# --- Paginación + total ------------------------------------------------------


async def test_paginacion_respeta_limit_y_offset(
    repo: SqlAlchemyExpedienteRepository,
) -> None:
    await _seed_corpus(repo)
    p1 = await repo.buscar(ExpedienteQuery(limit=2, offset=0))
    p2 = await repo.buscar(ExpedienteQuery(limit=2, offset=2))
    p3 = await repo.buscar(ExpedienteQuery(limit=2, offset=4))
    assert (p1.total, p2.total, p3.total) == (5, 5, 5)  # total no cambia con offset
    assert (len(p1.items), len(p2.items), len(p3.items)) == (2, 2, 1)
    # Sin overlap.
    ids = [e.id for e in (*p1.items, *p2.items, *p3.items)]
    assert len(set(ids)) == 5


async def test_orden_por_fecha_descendente_nulls_last(
    repo: SqlAlchemyExpedienteRepository,
) -> None:
    """El exp 5 no tiene fecha; debe aparecer último."""
    await _seed_corpus(repo)
    r = await repo.buscar(ExpedienteQuery())
    fechas = [e.fecha_ingreso for e in r.items]
    # El último debe ser el sin-fecha.
    assert fechas[-1] is None
    # Los con fecha, en orden descendente.
    con_fecha = [f for f in fechas if f is not None]
    assert con_fecha == sorted(con_fecha, reverse=True)


# --- contar() ---------------------------------------------------------------


async def test_contar_sin_filtros(repo: SqlAlchemyExpedienteRepository) -> None:
    await _seed_corpus(repo)
    assert await repo.contar(ExpedienteQuery()) == 5


async def test_contar_con_filtro(repo: SqlAlchemyExpedienteRepository) -> None:
    await _seed_corpus(repo)
    assert await repo.contar(ExpedienteQuery(autor_nombre="Massot")) == 2


async def test_contar_ignora_limit_offset(
    repo: SqlAlchemyExpedienteRepository,
) -> None:
    await _seed_corpus(repo)
    n1 = await repo.contar(ExpedienteQuery(limit=2, offset=0))
    n2 = await repo.contar(ExpedienteQuery(limit=200, offset=3))
    assert n1 == n2 == 5
