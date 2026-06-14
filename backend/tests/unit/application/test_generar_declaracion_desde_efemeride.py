"""Tests del use case GenerarDeclaracionDesdeEfemeride (feat-53.3)."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest

from praxis.application.ports import (
    EfemerideRepository,
    LlmProvider,
    PerfilOpositorRepository,
)
from praxis.application.use_cases.generar_declaracion_desde_efemeride import (
    DeclaracionDesdeEfemeride,
    EfemerideNoEncontrada,
    GenerarDeclaracionDesdeEfemeride,
)
from praxis.domain import (
    Efemeride,
    RelevanciaEfemeride,
    TipoEfemeride,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeEfemerideRepo(EfemerideRepository):
    def __init__(self, efemerides: dict | None = None) -> None:
        self._store = efemerides or {}

    async def buscar_por_id(self, efemeride_id):
        return self._store.get(efemeride_id)

    async def proximas(self, **kw):
        return list(self._store.values())

    async def listar_todas(self, **kw):
        return list(self._store.values())


class FakePerfilRepo(PerfilOpositorRepository):
    async def buscar_por_despacho(self, despacho_id):
        return None  # sin perfil, el LLM usa defaults

    async def upsert(self, perfil):
        raise NotImplementedError


class FakeLlmProvider(LlmProvider):
    """LLM falso que devuelve respuestas predecibles para testear el flujo."""

    def __init__(self) -> None:
        self.llamadas: list[dict] = []

    async def razonar_libre(self, *, system, user, max_tokens):
        self.llamadas.append({"system": system, "user": user})
        # Detecta qué use case está llamando por presencia de fragmento del prompt
        if "JSON del articulado" in user or "Devolvé EXACTAMENTE este JSON" in system:
            return (
                '{"articulado": ["Artículo 1°.- Declárese de interés...", '
                '"Artículo 2°.- De forma."]}',
                "fake-llm",
            )
        # Si es fundamentos, devuelve un markdown breve
        return (
            "## Fundamentos\n\nSeñor Presidente:\n\nEl presente proyecto...",
            "fake-llm",
        )

    # Abstract methods que el caso de uso NO llama — implementación no-op.
    @property
    def nombre_modelo(self) -> str:
        return "fake-llm"

    async def clasificar_area_tematica(self, *args, **kw):
        raise NotImplementedError

    async def clasificar_articulo(self, *args, **kw):
        raise NotImplementedError

    async def clasificar_norma_bo(self, *args, **kw):
        raise NotImplementedError

    async def disambiguar_mencion(self, *args, **kw):
        raise NotImplementedError

    async def generar_argumentos(self, *args, **kw):
        raise NotImplementedError

    async def generar_bajada_propia(self, *args, **kw):
        raise NotImplementedError

    async def generar_resumen_ejecutivo(self, *args, **kw):
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.fixture
def efemeride_mujer() -> Efemeride:
    return Efemeride(
        id=uuid4(),
        mes=3,
        dia=8,
        titulo="Día Internacional de la Mujer",
        tipo=TipoEfemeride.INTERNACIONAL,
        relevancia=RelevanciaEfemeride.ALTA,
        descripcion="Conmemoración de las luchas por la igualdad de género.",
        fuente="ONU Resolución 32/142 (1977)",
        areas_tematicas=["derechos_humanos", "trabajo"],
        creado_en=datetime.now(),
    )


async def test_genera_declaracion_correctamente(efemeride_mujer):
    repo = FakeEfemerideRepo({efemeride_mujer.id: efemeride_mujer})
    perfiles = FakePerfilRepo()
    llm = FakeLlmProvider()
    uc = GenerarDeclaracionDesdeEfemeride(
        efemerides=repo, perfiles=perfiles, llm=llm,
    )

    resultado = await uc.ejecutar(
        efemeride_id=efemeride_mujer.id,
        despacho_id=uuid4(),
    )

    assert isinstance(resultado, DeclaracionDesdeEfemeride)
    assert resultado.efemeride.id == efemeride_mujer.id
    assert len(resultado.articulado) == 2
    assert "Declárese de interés" in resultado.articulado[0]
    assert resultado.fundamentos.startswith("## Fundamentos")
    assert resultado.modelo == "fake-llm"


async def test_tema_incluye_titulo_y_descripcion(efemeride_mujer):
    repo = FakeEfemerideRepo({efemeride_mujer.id: efemeride_mujer})
    perfiles = FakePerfilRepo()
    llm = FakeLlmProvider()
    uc = GenerarDeclaracionDesdeEfemeride(
        efemerides=repo, perfiles=perfiles, llm=llm,
    )

    resultado = await uc.ejecutar(
        efemeride_id=efemeride_mujer.id,
        despacho_id=uuid4(),
    )

    # El tema debe contener título, fecha, descripción y áreas
    assert "Día Internacional de la Mujer" in resultado.tema_generado
    assert "03-08" in resultado.tema_generado
    assert "Conmemoración de las luchas" in resultado.tema_generado
    assert "derechos_humanos" in resultado.tema_generado
    assert "trabajo" in resultado.tema_generado


async def test_efemeride_inexistente_lanza():
    repo = FakeEfemerideRepo({})
    perfiles = FakePerfilRepo()
    llm = FakeLlmProvider()
    uc = GenerarDeclaracionDesdeEfemeride(
        efemerides=repo, perfiles=perfiles, llm=llm,
    )

    with pytest.raises(EfemerideNoEncontrada):
        await uc.ejecutar(
            efemeride_id=uuid4(),
            despacho_id=uuid4(),
        )


async def test_efemeride_con_anio_unico_lo_menciona():
    """Aniversarios puntuales (50° del Golpe) llevan mención del año."""
    ef = Efemeride(
        id=uuid4(),
        mes=3,
        dia=24,
        titulo="50° aniversario del Golpe de Estado",
        tipo=TipoEfemeride.ANIVERSARIO,
        relevancia=RelevanciaEfemeride.ALTA,
        anio_unico=2026,
    )
    repo = FakeEfemerideRepo({ef.id: ef})
    perfiles = FakePerfilRepo()
    llm = FakeLlmProvider()
    uc = GenerarDeclaracionDesdeEfemeride(
        efemerides=repo, perfiles=perfiles, llm=llm,
    )

    resultado = await uc.ejecutar(
        efemeride_id=ef.id, despacho_id=uuid4(),
    )

    assert "2026" in resultado.tema_generado
    assert "no recurrente" in resultado.tema_generado


async def test_efemeride_sin_descripcion_no_rompe():
    """Si la efeméride no tiene descripción, el tema se arma igual."""
    ef = Efemeride(
        id=uuid4(),
        mes=1,
        dia=1,
        titulo="Año Nuevo",
        tipo=TipoEfemeride.TEMATICA,
        relevancia=RelevanciaEfemeride.BAJA,
    )
    repo = FakeEfemerideRepo({ef.id: ef})
    perfiles = FakePerfilRepo()
    llm = FakeLlmProvider()
    uc = GenerarDeclaracionDesdeEfemeride(
        efemerides=repo, perfiles=perfiles, llm=llm,
    )

    resultado = await uc.ejecutar(
        efemeride_id=ef.id, despacho_id=uuid4(),
    )
    assert "Año Nuevo" in resultado.tema_generado
    assert len(resultado.articulado) > 0


async def test_llamadas_al_llm_son_dos(efemeride_mujer):
    """Cada generación dispara 2 llamadas: articulado + fundamentos."""
    repo = FakeEfemerideRepo({efemeride_mujer.id: efemeride_mujer})
    perfiles = FakePerfilRepo()
    llm = FakeLlmProvider()
    uc = GenerarDeclaracionDesdeEfemeride(
        efemerides=repo, perfiles=perfiles, llm=llm,
    )

    await uc.ejecutar(
        efemeride_id=efemeride_mujer.id, despacho_id=uuid4(),
    )
    assert len(llm.llamadas) == 2
