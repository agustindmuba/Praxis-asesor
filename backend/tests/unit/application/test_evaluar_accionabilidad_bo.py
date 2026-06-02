"""Tests del caso de uso `EvaluarAccionabilidadPorDespacho`.

Cubren:
- Sin perfil → no se persiste accionabilidad (score 0 para todo).
- Con perfil + área matcheante → score 30 → MEDIA persistida.
- Afecta expedientes HCDN suma 35 → ALTA.
- Distrito mencionado suma 10.
- Designación en organismo suma 15.
- Top-N recorta correctamente.
- Recálculo atómico: borra previas antes de reinsertar.
- Si hay cache de clasificación, no llama al LLM.
- Si falta cache, llama al LLM y persiste.

Usa fakes in-memory de todos los puertos.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest

from praxis.application.ports import (
    ClasificacionNormaBORepository,
    LlmProvider,
    NormaBOAccionableRepository,
    NormaBORepository,
    NormaBOTextoRepository,
    PerfilInteresDespachoRepository,
)
from praxis.application.use_cases.evaluar_accionabilidad_bo import (
    TOP_N_ACCIONABLES_DEFAULT,
    EvaluarAccionabilidadPorDespacho,
)
from praxis.domain import (
    AreaTematica,
    ClasificacionNormaBO,
    ClasificacionNormaBOResult,
    Expediente,
    NormaBO,
    NormaBOAccionable,
    NormaBOTexto,
    PerfilInteresDespacho,
    PrioridadAccionabilidad,
    SeccionBO,
    hash_sumario,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakePerfilRepo(PerfilInteresDespachoRepository):
    def __init__(
        self, perfil: PerfilInteresDespacho | None = None,
    ) -> None:
        self._perfil = perfil

    async def buscar_por_despacho(
        self, despacho_id: UUID,
    ) -> PerfilInteresDespacho | None:
        if self._perfil and self._perfil.despacho_id == despacho_id:
            return self._perfil
        return None

    async def upsert(
        self, perfil: PerfilInteresDespacho,
    ) -> PerfilInteresDespacho:
        self._perfil = perfil
        return perfil


class FakeNormaBORepo(NormaBORepository):
    def __init__(self, normas: list[NormaBO]) -> None:
        self._normas = normas

    async def upsert_lote(self, normas: list[NormaBO]) -> list[NormaBO]:
        raise NotImplementedError

    async def buscar_por_id(self, norma_id: UUID) -> NormaBO | None:
        for n in self._normas:
            if n.id == norma_id:
                return n
        return None

    async def listar_por_fecha(
        self, fecha: date, *, seccion: SeccionBO | None = None,
    ) -> list[NormaBO]:
        return [n for n in self._normas if n.fecha_publicacion == fecha]

    async def buscar_por_hash(self, hash_sumario: str) -> NormaBO | None:
        for n in self._normas:
            if n.hash_sumario == hash_sumario:
                return n
        return None


class FakeNormaBOTextoRepo(NormaBOTextoRepository):
    def __init__(self) -> None:
        self._by_norma: dict[UUID, NormaBOTexto] = {}

    async def crear(self, texto: NormaBOTexto) -> NormaBOTexto:
        self._by_norma[texto.norma_id] = texto
        return texto

    async def buscar_por_norma(
        self, norma_id: UUID,
    ) -> NormaBOTexto | None:
        return self._by_norma.get(norma_id)


class FakeClasificacionRepo(ClasificacionNormaBORepository):
    def __init__(self) -> None:
        self._by_norma: dict[UUID, ClasificacionNormaBO] = {}
        self.creadas: list[ClasificacionNormaBO] = []

    async def buscar_por_norma(
        self, norma_id: UUID,
    ) -> ClasificacionNormaBO | None:
        return self._by_norma.get(norma_id)

    async def crear(
        self, clasif: ClasificacionNormaBO,
    ) -> ClasificacionNormaBO:
        self._by_norma[clasif.norma_id] = clasif
        self.creadas.append(clasif)
        return clasif

    async def eliminar(self, norma_id: UUID) -> bool:
        return self._by_norma.pop(norma_id, None) is not None


class FakeAccionableRepo(NormaBOAccionableRepository):
    def __init__(self, normas: list[NormaBO]) -> None:
        self._items: list[NormaBOAccionable] = []
        self._normas = normas   # para emular el JOIN por fecha

    async def upsert(
        self, accionable: NormaBOAccionable,
    ) -> NormaBOAccionable:
        for i, existing in enumerate(self._items):
            if (
                existing.norma_id == accionable.norma_id
                and existing.despacho_id == accionable.despacho_id
            ):
                self._items[i] = accionable
                return accionable
        self._items.append(accionable)
        return accionable

    async def listar_por_despacho_y_fecha(
        self, *, despacho_id: UUID, fecha: date, top_n: int | None = None,
    ) -> list[NormaBOAccionable]:
        normas_de_fecha = {
            n.id for n in self._normas if n.fecha_publicacion == fecha
        }
        filtrados = sorted(
            (
                a for a in self._items
                if a.despacho_id == despacho_id and a.norma_id in normas_de_fecha
            ),
            key=lambda a: a.score,
            reverse=True,
        )
        return filtrados[:top_n] if top_n is not None else filtrados

    async def borrar_por_despacho_y_fecha(
        self, *, despacho_id: UUID, fecha: date,
    ) -> int:
        normas_de_fecha = {
            n.id for n in self._normas if n.fecha_publicacion == fecha
        }
        antes = len(self._items)
        self._items = [
            a for a in self._items
            if not (
                a.despacho_id == despacho_id and a.norma_id in normas_de_fecha
            )
        ]
        return antes - len(self._items)


class FakeLlmProviderClasificadorBO(LlmProvider):
    def __init__(self, *, result: ClasificacionNormaBOResult) -> None:
        self._result = result
        self.llamadas = 0

    @property
    def nombre_modelo(self) -> str:
        return "fake-test"

    async def clasificar_norma_bo(
        self, norma: NormaBO, *, texto: str | None = None,
    ) -> ClasificacionNormaBOResult:
        self.llamadas += 1
        return self._result

    # Métodos no usados en este test.
    async def generar_resumen_ejecutivo(self, expediente: Expediente) -> str:
        raise NotImplementedError

    async def clasificar_area_tematica(
        self, expediente: Expediente,
    ) -> AreaTematica:
        raise NotImplementedError

    async def generar_argumentos(
        self, expediente: Expediente, *, contraargumentos: bool = False,
    ) -> list[str]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _norma(
    *,
    sumario: str = "Modifica el régimen jubilatorio docente",
    organismo: str = "Poder Ejecutivo Nacional",
    tipo: str = "Decreto",
    numero: str = "412/2026",
) -> NormaBO:
    return NormaBO(
        id=uuid4(),
        fecha_publicacion=date(2026, 6, 1),
        seccion=SeccionBO.LEGISLACION,
        tipo_norma=tipo,
        numero_norma=numero,
        organismo_emisor=organismo,
        sumario=sumario,
        url_oficial="https://www.boletinoficial.gob.ar/det/x",
        hash_sumario=hash_sumario(sumario + numero),
        capturado_en=datetime.now(UTC),
    )


def _perfil(
    despacho_id: UUID,
    *,
    areas: list[str] | None = None,
    distritos: list[str] | None = None,
) -> PerfilInteresDespacho:
    return PerfilInteresDespacho(
        despacho_id=despacho_id,
        areas_tematicas=areas or [],
        distritos_observados=distritos or [],
    )


def _clasificacion(
    norma_id: UUID,
    *,
    area: AreaTematica = AreaTematica.JUSTICIA,
    afecta_hcdn: bool = False,
    referencias: list[str] | None = None,
) -> ClasificacionNormaBO:
    return ClasificacionNormaBO(
        id=uuid4(),
        norma_id=norma_id,
        area_tematica=area,
        palabras_clave=[],
        afecta_expedientes_hcdn=afecta_hcdn,
        referencias_legales=referencias or [],
        modelo="fake-test",
        prompt_version="v1",
    )


def _build_uc(
    *,
    perfil: PerfilInteresDespacho | None,
    normas: list[NormaBO],
    clasifs_precargadas: dict[UUID, ClasificacionNormaBO] | None = None,
    llm_result: ClasificacionNormaBOResult | None = None,
):
    clasif_repo = FakeClasificacionRepo()
    if clasifs_precargadas:
        for c in clasifs_precargadas.values():
            clasif_repo._by_norma[c.norma_id] = c

    llm = FakeLlmProviderClasificadorBO(
        result=llm_result
        or ClasificacionNormaBOResult(
            area_tematica=AreaTematica.OTROS,
            palabras_clave=[],
            afecta_expedientes_hcdn=False,
            referencias_legales=[],
        ),
    )

    accionables = FakeAccionableRepo(normas)
    uc = EvaluarAccionabilidadPorDespacho(
        perfiles=FakePerfilRepo(perfil),
        normas=FakeNormaBORepo(normas),
        textos=FakeNormaBOTextoRepo(),
        clasificaciones=clasif_repo,
        accionables=accionables,
        llm=llm,
    )
    return uc, clasif_repo, accionables, llm


# ---------------------------------------------------------------------------
# Sin perfil
# ---------------------------------------------------------------------------


async def test_sin_perfil_no_persiste_accionabilidad() -> None:
    despacho_id = uuid4()
    norma = _norma()
    uc, _, accionables, _ = _build_uc(
        perfil=None,
        normas=[norma],
        clasifs_precargadas={norma.id: _clasificacion(norma.id)},  # type: ignore[arg-type]
    )

    creadas = await uc.execute(despacho_id=despacho_id, fecha=date(2026, 6, 1))
    assert creadas == []
    assert accionables._items == []


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


async def test_perfil_con_area_match_da_score_30() -> None:
    despacho_id = uuid4()
    norma = _norma(sumario="Decreto sobre justicia")
    uc, _, _accionables, _ = _build_uc(
        perfil=_perfil(despacho_id, areas=["justicia"]),
        normas=[norma],
        clasifs_precargadas={
            norma.id: _clasificacion(norma.id, area=AreaTematica.JUSTICIA),  # type: ignore[arg-type]
        },
    )

    creadas = await uc.execute(despacho_id=despacho_id, fecha=date(2026, 6, 1))
    assert len(creadas) == 1
    assert creadas[0].score == 30
    assert creadas[0].prioridad == PrioridadAccionabilidad.MEDIA
    assert "justicia" in creadas[0].razon.lower()


async def test_afecta_hcdn_suma_35_total_65_alta() -> None:
    despacho_id = uuid4()
    norma = _norma()
    uc, _, _, _ = _build_uc(
        perfil=_perfil(despacho_id, areas=["justicia"]),
        normas=[norma],
        clasifs_precargadas={
            norma.id: _clasificacion(  # type: ignore[arg-type]
                norma.id,
                area=AreaTematica.JUSTICIA,
                afecta_hcdn=True,
                referencias=["Ley 27.812"],
            ),
        },
    )

    creadas = await uc.execute(despacho_id=despacho_id, fecha=date(2026, 6, 1))
    assert len(creadas) == 1
    assert creadas[0].score == 65
    assert creadas[0].prioridad == PrioridadAccionabilidad.ALTA
    assert "Ley 27.812" in creadas[0].razon


async def test_distrito_mencionado_suma_10() -> None:
    despacho_id = uuid4()
    norma = _norma(
        sumario="Decreto que asigna fondos a la Provincia de Buenos Aires"
    )
    uc, _, _, _ = _build_uc(
        perfil=_perfil(
            despacho_id, areas=[], distritos=["Buenos Aires"],
        ),
        normas=[norma],
        clasifs_precargadas={
            norma.id: _clasificacion(norma.id),  # type: ignore[arg-type]
        },
    )

    creadas = await uc.execute(despacho_id=despacho_id, fecha=date(2026, 6, 1))
    # Score = 10 < SCORE_MINIMO_ACCIONABLE (15) → no se persiste.
    assert creadas == []


async def test_distrito_mas_area_pasa_el_umbral() -> None:
    despacho_id = uuid4()
    norma = _norma(
        sumario="Decreto que asigna fondos para Buenos Aires"
    )
    uc, _, _, _ = _build_uc(
        perfil=_perfil(
            despacho_id, areas=["economia"], distritos=["Buenos Aires"],
        ),
        normas=[norma],
        clasifs_precargadas={
            norma.id: _clasificacion(  # type: ignore[arg-type]
                norma.id, area=AreaTematica.ECONOMIA,
            ),
        },
    )

    creadas = await uc.execute(despacho_id=despacho_id, fecha=date(2026, 6, 1))
    assert len(creadas) == 1
    assert creadas[0].score == 40   # 30 + 10
    assert creadas[0].prioridad == PrioridadAccionabilidad.MEDIA


async def test_designacion_en_area_propia_suma_15() -> None:
    despacho_id = uuid4()
    norma = _norma(
        sumario="Desígnase Subsecretario Legal en el área educativa",
        tipo="Decreto",
    )
    uc, _, _, _ = _build_uc(
        perfil=_perfil(despacho_id, areas=["educacion"]),
        normas=[norma],
        clasifs_precargadas={
            norma.id: _clasificacion(  # type: ignore[arg-type]
                norma.id, area=AreaTematica.EDUCACION,
            ),
        },
    )

    creadas = await uc.execute(despacho_id=despacho_id, fecha=date(2026, 6, 1))
    assert len(creadas) == 1
    # 30 (area educacion) + 15 (designacion en area propia) = 45.
    assert creadas[0].score == 45


# ---------------------------------------------------------------------------
# top-N
# ---------------------------------------------------------------------------


async def test_top_n_recorta_a_los_mas_altos() -> None:
    despacho_id = uuid4()
    normas = [
        _norma(numero=f"{i}/2026", sumario=f"Norma {i}") for i in range(8)
    ]
    clasifs = {
        n.id: _clasificacion(  # type: ignore[misc]
            n.id,
            area=AreaTematica.JUSTICIA,
            afecta_hcdn=(i % 2 == 0),   # las pares: score más alto
        )
        for i, n in enumerate(normas)
    }
    uc, _, _, _ = _build_uc(
        perfil=_perfil(despacho_id, areas=["justicia"]),
        normas=normas,
        clasifs_precargadas=clasifs,
    )

    creadas = await uc.execute(
        despacho_id=despacho_id, fecha=date(2026, 6, 1), top_n=3,
    )
    assert len(creadas) == 3
    # Los top 3 deben tener afecta_hcdn=True (score 65).
    assert all(c.score == 65 for c in creadas)


async def test_top_n_default_es_5() -> None:
    """TOP_N_ACCIONABLES_DEFAULT es 5 según spec 15."""
    assert TOP_N_ACCIONABLES_DEFAULT == 5


# ---------------------------------------------------------------------------
# Recálculo atómico
# ---------------------------------------------------------------------------


async def test_recalculo_atomico_borra_previos() -> None:
    """Si re-corremos el use case, los accionables previos se reemplazan."""
    despacho_id = uuid4()
    norma_a = _norma(numero="100/2026", sumario="A")
    norma_b = _norma(numero="200/2026", sumario="B")
    clasifs = {
        norma_a.id: _clasificacion(  # type: ignore[arg-type]
            norma_a.id, area=AreaTematica.JUSTICIA,
        ),
        norma_b.id: _clasificacion(  # type: ignore[arg-type]
            norma_b.id, area=AreaTematica.SALUD,
        ),
    }
    uc, _, accionables, _ = _build_uc(
        perfil=_perfil(despacho_id, areas=["justicia"]),
        normas=[norma_a, norma_b],
        clasifs_precargadas=clasifs,
    )

    # 1ra corrida: persiste norma_a (score 30).
    primera = await uc.execute(
        despacho_id=despacho_id, fecha=date(2026, 6, 1),
    )
    assert {a.norma_id for a in primera} == {norma_a.id}

    # Cambia el perfil del despacho: ahora le importa "salud".
    uc._perfiles = FakePerfilRepo(_perfil(despacho_id, areas=["salud"]))

    # 2da corrida: ahora solo norma_b debería estar.
    segunda = await uc.execute(
        despacho_id=despacho_id, fecha=date(2026, 6, 1),
    )
    assert {a.norma_id for a in segunda} == {norma_b.id}
    # Y el repo no tiene la anterior.
    assert len(accionables._items) == 1


# ---------------------------------------------------------------------------
# Cache de clasificación
# ---------------------------------------------------------------------------


async def test_si_hay_cache_no_llama_al_llm() -> None:
    despacho_id = uuid4()
    norma = _norma()
    uc, clasif_repo, _, llm = _build_uc(
        perfil=_perfil(despacho_id, areas=["justicia"]),
        normas=[norma],
        clasifs_precargadas={
            norma.id: _clasificacion(  # type: ignore[arg-type]
                norma.id, area=AreaTematica.JUSTICIA,
            ),
        },
    )

    await uc.execute(despacho_id=despacho_id, fecha=date(2026, 6, 1))
    assert llm.llamadas == 0
    assert clasif_repo.creadas == []   # tampoco se creó nueva


async def test_si_falta_cache_llama_al_llm_y_persiste() -> None:
    despacho_id = uuid4()
    norma = _norma()
    uc, clasif_repo, _, llm = _build_uc(
        perfil=_perfil(despacho_id, areas=["justicia"]),
        normas=[norma],
        clasifs_precargadas=None,   # sin cache
        llm_result=ClasificacionNormaBOResult(
            area_tematica=AreaTematica.JUSTICIA,
            palabras_clave=["ley"],
            afecta_expedientes_hcdn=False,
            referencias_legales=[],
        ),
    )

    creadas = await uc.execute(
        despacho_id=despacho_id, fecha=date(2026, 6, 1),
    )
    assert llm.llamadas == 1
    assert len(clasif_repo.creadas) == 1
    # Y la clasificación persistida queda cacheada para la siguiente corrida.
    assert len(creadas) == 1
    assert creadas[0].score == 30


async def test_sin_normas_no_levanta_y_borra_previos() -> None:
    despacho_id = uuid4()
    uc, _, accionables, _ = _build_uc(
        perfil=_perfil(despacho_id, areas=["justicia"]),
        normas=[],
    )
    creadas = await uc.execute(
        despacho_id=despacho_id, fecha=date(2026, 6, 1),
    )
    assert creadas == []
    assert accionables._items == []
