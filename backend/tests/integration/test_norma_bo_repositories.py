"""Tests de integración de los 4 repos BO sobre SQLite in-memory.

Cubren:
- NormaBO: upsert idempotente por identidad natural; lookup por id,
  fecha, sección, hash.
- NormaBOTexto: crear + buscar.
- ClasificacionNormaBO: cache por norma + delete.
- NormaBOAccionable: PK compuesta, ordenamiento por score desc,
  recálculo borrando por despacho+fecha.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from praxis.domain import (
    BO_PROMPT_VERSION,
    AreaTematica,
    ClasificacionNormaBO,
    Despacho,
    NormaBO,
    NormaBOAccionable,
    NormaBOTexto,
    PrioridadAccionabilidad,
    SeccionBO,
    hash_sumario,
)
from praxis.infrastructure.persistence.base import Base
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyClasificacionNormaBORepository,
    SqlAlchemyDespachoRepository,
    SqlAlchemyNormaBOAccionableRepository,
    SqlAlchemyNormaBORepository,
    SqlAlchemyNormaBOTextoRepository,
)

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def despacho(session: AsyncSession) -> Despacho:
    repo = SqlAlchemyDespachoRepository(session)
    return await repo.crear(Despacho(id=uuid4(), nombre="Despacho test"))


def _norma(
    *,
    numero: str = "412/2026",
    fecha: date = date(2026, 6, 1),
    sumario: str | None = None,
    seccion: SeccionBO = SeccionBO.LEGISLACION,
    tipo: str = "decreto",
) -> NormaBO:
    # Si no se pasa sumario explícito, generamos uno único por
    # (tipo, numero) — distinto para cada norma — así no chocan el
    # UNIQUE de hash_sumario cuando el test seedea varias normas.
    sumario_efectivo = sumario or (
        f"Norma {tipo} {numero} del {fecha} — sumario de prueba"
    )
    return NormaBO(
        id=None,
        fecha_publicacion=fecha,
        seccion=seccion,
        tipo_norma=tipo,
        numero_norma=numero,
        organismo_emisor="Poder Ejecutivo Nacional",
        sumario=sumario_efectivo,
        url_oficial=f"https://www.boletinoficial.gob.ar/det/{tipo}-{numero}",
        hash_sumario=hash_sumario(sumario_efectivo),
        capturado_en=datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# NormaBO
# ---------------------------------------------------------------------------


async def test_upsert_lote_inserta_y_es_idempotente(
    session: AsyncSession,
) -> None:
    repo = SqlAlchemyNormaBORepository(session)
    norma = _norma()

    primero = await repo.upsert_lote([norma])
    assert len(primero) == 1
    assert primero[0].id is not None
    primer_id = primero[0].id

    # Re-correr no duplica.
    segundo = await repo.upsert_lote([norma])
    assert len(segundo) == 1
    assert segundo[0].id == primer_id


async def test_buscar_por_id_devuelve_lo_persistido(
    session: AsyncSession,
) -> None:
    repo = SqlAlchemyNormaBORepository(session)
    creadas = await repo.upsert_lote([_norma()])
    leida = await repo.buscar_por_id(creadas[0].id)  # type: ignore[arg-type]
    assert leida is not None
    assert leida.numero_norma == "412/2026"


async def test_listar_por_fecha_filtra_por_seccion(
    session: AsyncSession,
) -> None:
    repo = SqlAlchemyNormaBORepository(session)
    await repo.upsert_lote(
        [
            _norma(numero="100/2026", seccion=SeccionBO.LEGISLACION),
            _norma(numero="200/2026", seccion=SeccionBO.LEGISLACION),
            _norma(
                numero="300/2026",
                seccion=SeccionBO.DESIGNACIONES,
                tipo="resolucion",
            ),
        ]
    )
    todas = await repo.listar_por_fecha(date(2026, 6, 1))
    assert len(todas) == 3

    solo_legis = await repo.listar_por_fecha(
        date(2026, 6, 1), seccion=SeccionBO.LEGISLACION,
    )
    assert len(solo_legis) == 2
    assert all(n.seccion == SeccionBO.LEGISLACION for n in solo_legis)


async def test_buscar_por_hash(session: AsyncSession) -> None:
    repo = SqlAlchemyNormaBORepository(session)
    n = _norma(sumario="Sumario único X")
    await repo.upsert_lote([n])
    leida = await repo.buscar_por_hash(n.hash_sumario)
    assert leida is not None
    assert leida.hash_sumario == n.hash_sumario


# ---------------------------------------------------------------------------
# NormaBOTexto
# ---------------------------------------------------------------------------


async def test_norma_bo_texto_crear_y_buscar(
    session: AsyncSession,
) -> None:
    normas = SqlAlchemyNormaBORepository(session)
    textos = SqlAlchemyNormaBOTextoRepository(session)
    norma = (await normas.upsert_lote([_norma()]))[0]
    assert norma.id is not None

    creado = await textos.crear(
        NormaBOTexto(
            norma_id=norma.id,
            texto="ARTÍCULO 1 — Modifíquese el artículo 12...",
            capturado_en=datetime.now(UTC),
        )
    )
    assert creado.norma_id == norma.id
    leido = await textos.buscar_por_norma(norma.id)
    assert leido is not None
    assert leido.texto.startswith("ARTÍCULO")


# ---------------------------------------------------------------------------
# ClasificacionNormaBO
# ---------------------------------------------------------------------------


async def test_clasificacion_norma_bo_crear_buscar_eliminar(
    session: AsyncSession,
) -> None:
    normas = SqlAlchemyNormaBORepository(session)
    clasifs = SqlAlchemyClasificacionNormaBORepository(session)
    norma = (await normas.upsert_lote([_norma()]))[0]
    assert norma.id is not None

    creada = await clasifs.crear(
        ClasificacionNormaBO(
            id=None,
            norma_id=norma.id,
            area_tematica=AreaTematica.JUSTICIA,
            palabras_clave=["jubilación", "docentes"],
            afecta_expedientes_hcdn=True,
            referencias_legales=["Ley 24.660"],
            modelo="fake-keywords",
            prompt_version=BO_PROMPT_VERSION,
        )
    )
    assert creada.id is not None

    leida = await clasifs.buscar_por_norma(norma.id)
    assert leida is not None
    assert leida.area_tematica == AreaTematica.JUSTICIA
    assert leida.palabras_clave == ["jubilación", "docentes"]

    borrado = await clasifs.eliminar(norma.id)
    assert borrado is True
    assert await clasifs.buscar_por_norma(norma.id) is None
    # Idempotente: segundo delete devuelve False.
    assert await clasifs.eliminar(norma.id) is False


# ---------------------------------------------------------------------------
# NormaBOAccionable
# ---------------------------------------------------------------------------


async def _seed_accionable(
    session: AsyncSession,
    despacho_id,
    *,
    numero: str,
    score: int,
    fecha: date = date(2026, 6, 1),
) -> NormaBOAccionable:
    normas = SqlAlchemyNormaBORepository(session)
    accionables = SqlAlchemyNormaBOAccionableRepository(session)
    norma = (await normas.upsert_lote([_norma(numero=numero, fecha=fecha)]))[0]
    assert norma.id is not None
    return await accionables.upsert(
        NormaBOAccionable(
            norma_id=norma.id,
            despacho_id=despacho_id,
            score=score,
            prioridad=(
                PrioridadAccionabilidad.ALTA
                if score >= 60
                else PrioridadAccionabilidad.MEDIA
                if score >= 30
                else PrioridadAccionabilidad.BAJA
            ),
            razon=f"Razón para norma {numero}",
            expedientes_tocados=[uuid4()],
        )
    )


async def test_accionable_upsert_y_listar_ordena_por_score_desc(
    session: AsyncSession, despacho: Despacho,
) -> None:
    accionables = SqlAlchemyNormaBOAccionableRepository(session)
    await _seed_accionable(session, despacho.id, numero="100/2026", score=20)
    await _seed_accionable(session, despacho.id, numero="200/2026", score=75)
    await _seed_accionable(session, despacho.id, numero="300/2026", score=45)

    lista = await accionables.listar_por_despacho_y_fecha(
        despacho_id=despacho.id, fecha=date(2026, 6, 1),
    )
    assert [a.score for a in lista] == [75, 45, 20]


async def test_accionable_top_n_recorta(
    session: AsyncSession, despacho: Despacho,
) -> None:
    accionables = SqlAlchemyNormaBOAccionableRepository(session)
    await _seed_accionable(session, despacho.id, numero="100/2026", score=20)
    await _seed_accionable(session, despacho.id, numero="200/2026", score=75)
    await _seed_accionable(session, despacho.id, numero="300/2026", score=45)

    top1 = await accionables.listar_por_despacho_y_fecha(
        despacho_id=despacho.id, fecha=date(2026, 6, 1), top_n=1,
    )
    assert len(top1) == 1
    assert top1[0].score == 75


async def test_accionable_upsert_actualiza_score(
    session: AsyncSession, despacho: Despacho,
) -> None:
    accionables = SqlAlchemyNormaBOAccionableRepository(session)
    creado = await _seed_accionable(
        session, despacho.id, numero="100/2026", score=20,
    )
    # Re-upsert con nuevo score (subido a alta).
    actualizado = await accionables.upsert(
        NormaBOAccionable(
            norma_id=creado.norma_id,
            despacho_id=creado.despacho_id,
            score=80,
            prioridad=PrioridadAccionabilidad.ALTA,
            razon="razón actualizada",
            expedientes_tocados=[],
        )
    )
    assert actualizado.score == 80
    assert actualizado.prioridad == PrioridadAccionabilidad.ALTA
    assert actualizado.razon == "razón actualizada"


async def test_accionable_borrar_por_despacho_y_fecha_es_atomico(
    session: AsyncSession, despacho: Despacho,
) -> None:
    accionables = SqlAlchemyNormaBOAccionableRepository(session)
    await _seed_accionable(session, despacho.id, numero="100/2026", score=20)
    await _seed_accionable(session, despacho.id, numero="200/2026", score=75)

    borrados = await accionables.borrar_por_despacho_y_fecha(
        despacho_id=despacho.id, fecha=date(2026, 6, 1),
    )
    assert borrados == 2
    quedaron = await accionables.listar_por_despacho_y_fecha(
        despacho_id=despacho.id, fecha=date(2026, 6, 1),
    )
    assert quedaron == []


async def test_accionable_tenant_scope_no_filtra_a_otro_despacho(
    session: AsyncSession, despacho: Despacho,
) -> None:
    """Sanity: una mention de despacho A no sale en query del despacho B."""
    otro_despacho = await SqlAlchemyDespachoRepository(session).crear(
        Despacho(id=uuid4(), nombre="Despacho B")
    )
    await _seed_accionable(session, despacho.id, numero="100/2026", score=75)
    await _seed_accionable(
        session, otro_despacho.id, numero="200/2026", score=80,
    )

    accionables = SqlAlchemyNormaBOAccionableRepository(session)
    lista_a = await accionables.listar_por_despacho_y_fecha(
        despacho_id=despacho.id, fecha=date(2026, 6, 1),
    )
    assert len(lista_a) == 1
    assert lista_a[0].score == 75
