"""Tests de `SembrarPerfilInteres`.

Cubren la decisión D1 (sembrado híbrido + editable):

- Despacho inexistente → ValueError.
- Sin legislador resoluble → solo se siembran áreas (las de los
  seguimientos clasificados).
- Con legislador → áreas + distrito + aliases (`nombre apellido`,
  `apellido`).
- Sólo expedientes clasificados contribuyen áreas (los sin cache se
  ignoran).
- Áreas se deduplican y conservan orden de aparición.
- Si hay perfil con edición manual posterior al último sembrado, el
  caso de uso lo RESPETA salvo que se pase
  `sobreescribir_edicion_manual=True`.

Se usan fakes explícitos en memoria de los repos/puertos involucrados.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from praxis.application.ports import (
    CatalogoLegisladores,
    DespachoRepository,
    ExpedienteAreaTematicaRepository,
    PerfilInteresDespachoRepository,
    SeguimientoExpedienteRepository,
)
from praxis.application.use_cases.sembrar_perfil_interes import (
    SembrarPerfilInteres,
)
from praxis.domain import (
    AreaTematica,
    Bloque,
    Camara,
    ExpedienteAreaTematica,
    Legislador,
    PerfilInteresDespacho,
    Prioridad,
    SeguimientoExpediente,
)
from praxis.domain.despacho import Despacho

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fakes en memoria
# ---------------------------------------------------------------------------


class FakeDespachoRepo(DespachoRepository):
    def __init__(self, despachos: list[Despacho]) -> None:
        self._by_id = {d.id: d for d in despachos}

    async def crear(self, despacho: Despacho) -> Despacho:
        self._by_id[despacho.id] = despacho
        return despacho

    async def buscar_por_id(self, despacho_id: UUID) -> Despacho | None:
        return self._by_id.get(despacho_id)

    async def listar(self) -> list[Despacho]:
        return list(self._by_id.values())


class FakeCatalogoLegisladores(CatalogoLegisladores):
    def __init__(self, legisladores: list[Legislador]) -> None:
        self._all = legisladores

    def listar(self, camara: Camara) -> list[Legislador]:
        return [leg for leg in self._all if leg.camara == camara]

    def buscar_por_slug(self, slug: str, camara: Camara) -> Legislador:
        for leg in self._all:
            if leg.slug == slug and leg.camara == camara:
                return leg
        raise KeyError(f"Legislador {slug!r}/{camara} no existe")

    def buscar_por_nombre(self, query: str) -> list[Legislador]:
        q = query.lower()
        return [
            leg for leg in self._all
            if q in leg.apellido.lower() or q in leg.nombre.lower()
        ]


class FakeSeguimientoRepo(SeguimientoExpedienteRepository):
    def __init__(self, seguimientos: list[SeguimientoExpediente]) -> None:
        self._all = seguimientos

    async def crear(
        self, seguimiento: SeguimientoExpediente,
    ) -> SeguimientoExpediente:
        self._all.append(seguimiento)
        return seguimiento

    async def buscar(
        self, *, despacho_id: UUID, expediente_id: UUID,
    ) -> SeguimientoExpediente | None:
        for s in self._all:
            if s.despacho_id == despacho_id and s.expediente_id == expediente_id:
                return s
        return None

    async def buscar_por_id(
        self, *, despacho_id: UUID, seguimiento_id: UUID,
    ) -> SeguimientoExpediente | None:
        for s in self._all:
            if s.id == seguimiento_id and s.despacho_id == despacho_id:
                return s
        return None

    async def listar_por_despacho(
        self, despacho_id: UUID, *, incluir_archivados: bool = False,
    ) -> list[SeguimientoExpediente]:
        return [
            s for s in self._all
            if s.despacho_id == despacho_id
            and (incluir_archivados or not s.archivado)
        ]

    async def archivar(
        self, *, despacho_id: UUID, seguimiento_id: UUID,
    ) -> bool:
        raise NotImplementedError

    async def asignar_responsable(
        self, *, despacho_id: UUID, seguimiento_id: UUID,
        responsable_id: UUID | None,
    ) -> bool:
        raise NotImplementedError


class FakeClasificacionRepo(ExpedienteAreaTematicaRepository):
    def __init__(self, cache: dict[UUID, ExpedienteAreaTematica]) -> None:
        self._cache = cache

    async def buscar_por_expediente(
        self, expediente_id: UUID,
    ) -> ExpedienteAreaTematica | None:
        return self._cache.get(expediente_id)

    async def crear(
        self, cache: ExpedienteAreaTematica,
    ) -> ExpedienteAreaTematica:
        self._cache[cache.expediente_id] = cache
        return cache

    async def eliminar(self, expediente_id: UUID) -> bool:
        return self._cache.pop(expediente_id, None) is not None

    async def listar_por_area(
        self, area: AreaTematica, *, limit: int = 100,
    ) -> list[ExpedienteAreaTematica]:
        return [c for c in self._cache.values() if c.area == area][:limit]


class FakePerfilRepo(PerfilInteresDespachoRepository):
    def __init__(self) -> None:
        self._by_despacho: dict[UUID, PerfilInteresDespacho] = {}
        self.upserts: list[PerfilInteresDespacho] = []

    async def buscar_por_despacho(
        self, despacho_id: UUID,
    ) -> PerfilInteresDespacho | None:
        return self._by_despacho.get(despacho_id)

    async def upsert(
        self, perfil: PerfilInteresDespacho,
    ) -> PerfilInteresDespacho:
        # Simular que el server asigna actualizado_en.
        perfil.actualizado_en = datetime.now(UTC)
        self._by_despacho[perfil.despacho_id] = perfil
        self.upserts.append(perfil)
        return perfil

    def seed(self, perfil: PerfilInteresDespacho) -> None:
        """Helper para tests: inyecta un perfil sin pasar por upsert()."""
        self._by_despacho[perfil.despacho_id] = perfil


# ---------------------------------------------------------------------------
# Helpers de construcción
# ---------------------------------------------------------------------------


def _legislador_juliano() -> Legislador:
    bloque = Bloque(
        nombre="Democracia Para Siempre",
        camara=Camara.HCDN,
    )
    return Legislador(
        slug="pjuliano",
        apellido="Juliano",
        nombre="Pablo",
        camara=Camara.HCDN,
        distrito="Buenos Aires",
        bloque=bloque,
        periodo_mandato="2023-2027",
        fecha_inicio_mandato=datetime(2023, 12, 10).date(),
        fecha_fin_mandato=datetime(2027, 12, 9).date(),
    )


def _despacho(
    legislador_slug: str | None = "pjuliano",
    camara_titular: str | None = "HCDN",
) -> Despacho:
    config: dict[str, object] = {}
    if camara_titular is not None:
        config["camara_titular"] = camara_titular
    return Despacho(
        id=uuid4(),
        nombre="Despacho Juliano",
        legislador_titular_slug=legislador_slug,
        configuracion=config,
    )


def _clasificacion(
    expediente_id: UUID, area: AreaTematica,
) -> ExpedienteAreaTematica:
    return ExpedienteAreaTematica(
        id=uuid4(),
        expediente_id=expediente_id,
        area=area,
        modelo="fake-keywords",
    )


def _seguimiento(despacho_id: UUID, expediente_id: UUID) -> SeguimientoExpediente:
    return SeguimientoExpediente(
        id=uuid4(),
        despacho_id=despacho_id,
        expediente_id=expediente_id,
        prioridad=Prioridad.MEDIA,
    )


def _build_use_case(
    *,
    despacho: Despacho,
    legisladores: list[Legislador] | None = None,
    seguimientos: list[SeguimientoExpediente] | None = None,
    clasificaciones: dict[UUID, ExpedienteAreaTematica] | None = None,
    perfil_existente: PerfilInteresDespacho | None = None,
) -> tuple[SembrarPerfilInteres, FakePerfilRepo]:
    perfiles = FakePerfilRepo()
    if perfil_existente is not None:
        perfiles.seed(perfil_existente)
    uc = SembrarPerfilInteres(
        despachos=FakeDespachoRepo([despacho]),
        legisladores=FakeCatalogoLegisladores(legisladores or []),
        seguimientos=FakeSeguimientoRepo(seguimientos or []),
        clasificaciones=FakeClasificacionRepo(clasificaciones or {}),
        perfiles=perfiles,
    )
    return uc, perfiles


# ---------------------------------------------------------------------------
# Casos
# ---------------------------------------------------------------------------


async def test_despacho_inexistente_levanta_value_error() -> None:
    uc, _ = _build_use_case(despacho=_despacho())
    with pytest.raises(ValueError, match="no existe"):
        await uc.execute(uuid4())


async def test_sin_legislador_resoluble_solo_areas_de_seguimientos() -> None:
    """Si el slug del titular no resuelve, igual sembramos áreas pero
    distritos y aliases quedan vacíos."""
    despacho = _despacho(legislador_slug="inexistente")
    exp1_id = uuid4()
    exp2_id = uuid4()
    uc, _perfiles = _build_use_case(
        despacho=despacho,
        legisladores=[],   # padrón vacío → no resuelve
        seguimientos=[
            _seguimiento(despacho.id, exp1_id),
            _seguimiento(despacho.id, exp2_id),
        ],
        clasificaciones={
            exp1_id: _clasificacion(exp1_id, AreaTematica.EDUCACION),
            exp2_id: _clasificacion(exp2_id, AreaTematica.SALUD),
        },
    )

    perfil = await uc.execute(despacho.id)

    assert sorted(perfil.areas_tematicas) == ["educacion", "salud"]
    assert perfil.distritos_observados == []
    assert perfil.aliases_legislador == []
    assert perfil.sembrado_at is not None
    assert perfil.editado_at is None


async def test_con_legislador_resoluble_siembra_completo() -> None:
    despacho = _despacho()
    exp_id = uuid4()
    uc, _ = _build_use_case(
        despacho=despacho,
        legisladores=[_legislador_juliano()],
        seguimientos=[_seguimiento(despacho.id, exp_id)],
        clasificaciones={exp_id: _clasificacion(exp_id, AreaTematica.EDUCACION)},
    )

    perfil = await uc.execute(despacho.id)

    assert perfil.areas_tematicas == ["educacion"]
    assert perfil.distritos_observados == ["Buenos Aires"]
    assert perfil.aliases_legislador == ["Pablo Juliano", "Juliano"]


async def test_areas_solo_de_seguimientos_clasificados() -> None:
    """Un expediente seguido pero sin clasificación cacheada no
    contribuye al sembrado."""
    despacho = _despacho()
    exp_clasificado = uuid4()
    exp_sin_clasificar = uuid4()
    uc, _ = _build_use_case(
        despacho=despacho,
        legisladores=[_legislador_juliano()],
        seguimientos=[
            _seguimiento(despacho.id, exp_clasificado),
            _seguimiento(despacho.id, exp_sin_clasificar),
        ],
        clasificaciones={
            exp_clasificado: _clasificacion(exp_clasificado, AreaTematica.JUSTICIA),
        },
    )

    perfil = await uc.execute(despacho.id)
    assert perfil.areas_tematicas == ["justicia"]


async def test_areas_dedupean_conservando_orden() -> None:
    """Dos expedientes en la misma área → un solo valor en areas."""
    despacho = _despacho()
    exp1 = uuid4()
    exp2 = uuid4()
    exp3 = uuid4()
    uc, _ = _build_use_case(
        despacho=despacho,
        legisladores=[_legislador_juliano()],
        seguimientos=[
            _seguimiento(despacho.id, exp1),
            _seguimiento(despacho.id, exp2),
            _seguimiento(despacho.id, exp3),
        ],
        clasificaciones={
            exp1: _clasificacion(exp1, AreaTematica.EDUCACION),
            exp2: _clasificacion(exp2, AreaTematica.SALUD),
            exp3: _clasificacion(exp3, AreaTematica.EDUCACION),
        },
    )

    perfil = await uc.execute(despacho.id)
    # Educación primero (es el primero en aparecer en la lista de seguimientos).
    assert perfil.areas_tematicas == ["educacion", "salud"]


async def test_seguimiento_archivado_no_contribuye() -> None:
    """Los expedientes archivados quedan fuera por default."""
    despacho = _despacho()
    exp_id = uuid4()
    seguimiento_archivado = SeguimientoExpediente(
        id=uuid4(),
        despacho_id=despacho.id,
        expediente_id=exp_id,
        archivado=True,
    )
    uc, _ = _build_use_case(
        despacho=despacho,
        legisladores=[_legislador_juliano()],
        seguimientos=[seguimiento_archivado],
        clasificaciones={exp_id: _clasificacion(exp_id, AreaTematica.EDUCACION)},
    )

    perfil = await uc.execute(despacho.id)
    assert perfil.areas_tematicas == []


async def test_perfil_editado_se_respeta_por_default() -> None:
    """Si hay edición manual posterior al último sembrado, no se piss."""
    despacho = _despacho()
    sembrado_at = datetime.now(UTC) - timedelta(hours=2)
    editado_at = sembrado_at + timedelta(hours=1)
    perfil_existente = PerfilInteresDespacho(
        despacho_id=despacho.id,
        areas_tematicas=["transporte"],
        distritos_observados=["CABA"],
        aliases_legislador=["alias custom"],
        sembrado_at=sembrado_at,
        editado_at=editado_at,
    )
    uc, perfiles = _build_use_case(
        despacho=despacho,
        legisladores=[_legislador_juliano()],
        seguimientos=[_seguimiento(despacho.id, uuid4())],
        clasificaciones={},
        perfil_existente=perfil_existente,
    )

    perfil = await uc.execute(despacho.id)

    # Devuelve la edición manual sin tocar.
    assert perfil.areas_tematicas == ["transporte"]
    assert perfil.distritos_observados == ["CABA"]
    assert perfil.aliases_legislador == ["alias custom"]
    # No hizo upsert nuevo.
    assert perfiles.upserts == []


async def test_perfil_editado_se_pisa_con_sobreescribir_true() -> None:
    """Con el flag, el sembrado pisa la edición manual."""
    despacho = _despacho()
    sembrado_at = datetime.now(UTC) - timedelta(hours=2)
    editado_at = sembrado_at + timedelta(hours=1)
    perfil_existente = PerfilInteresDespacho(
        despacho_id=despacho.id,
        areas_tematicas=["transporte"],
        sembrado_at=sembrado_at,
        editado_at=editado_at,
    )
    exp_id = uuid4()
    uc, perfiles = _build_use_case(
        despacho=despacho,
        legisladores=[_legislador_juliano()],
        seguimientos=[_seguimiento(despacho.id, exp_id)],
        clasificaciones={
            exp_id: _clasificacion(exp_id, AreaTematica.EDUCACION),
        },
        perfil_existente=perfil_existente,
    )

    perfil = await uc.execute(
        despacho.id, sobreescribir_edicion_manual=True,
    )

    assert perfil.areas_tematicas == ["educacion"]
    assert perfil.distritos_observados == ["Buenos Aires"]
    # El nuevo sembrado limpia editado_at — la verdad ahora es la siembra.
    assert perfil.editado_at is None
    assert perfil.sembrado_at is not None
    assert len(perfiles.upserts) == 1


async def test_sin_camara_titular_en_config_usa_hcdn_por_default() -> None:
    """Si configuracion no tiene camara_titular, asumimos HCDN."""
    despacho = _despacho(camara_titular=None)
    uc, _ = _build_use_case(
        despacho=despacho,
        legisladores=[_legislador_juliano()],   # está en HCDN
        seguimientos=[],
        clasificaciones={},
    )

    perfil = await uc.execute(despacho.id)
    # Si hubiera usado HSN por error, no encontraría al legislador →
    # aliases vacíos. La presencia confirma el default HCDN.
    assert perfil.aliases_legislador == ["Pablo Juliano", "Juliano"]


def test_constructor_exige_keyword_args() -> None:
    """Garantía de DI: nada de orden posicional."""
    despachos = FakeDespachoRepo([])
    legisladores = FakeCatalogoLegisladores([])
    seguimientos = FakeSeguimientoRepo([])
    clasificaciones = FakeClasificacionRepo({})
    perfiles = FakePerfilRepo()
    with pytest.raises(TypeError):
        SembrarPerfilInteres(   # type: ignore[misc]
            despachos, legisladores, seguimientos, clasificaciones, perfiles,
        )
