"""Tests del caso de uso `ProcesarArticulosDeFuente` (feat-40.5).

Orquestador entre adapter de fuente + repos + LLM + detector de
menciones. Usa fakes in-memory para los 6 repos + un FuenteNoticias
controlable + el FakeLlmProvider real + el caso de uso real de
DetectarMencionesEnArticulo.

Cubre el pipeline completo del Celery task:

- Dedup forever: artículo cuyo hash ya estaba en ArticuloHash → se
  omite (ni siquiera se baja el texto).
- Persistencia: snapshot + bajada propia + clasificación → repos.
- Detección de menciones por despacho → MencionRepository.
- Scoring de relevancia → solo se persiste si ≥ SCORE_MINIMO.
- Marca de revisada en la fuente.
- Resiliencia: una excepción en un artículo no rompe los otros.
- Sin despachos suscriptos: igual procesa + clasifica + no levanta.

Y también testea la función pura `calcular_score_relevancia` en sus
casos clave.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest

from praxis.application.use_cases import (
    DespachoSuscrito,
    DetectarMencionesEnArticulo,
    LegisladorAMonitorear,
    ProcesarArticulosDeFuente,
    calcular_score_relevancia,
)
from praxis.application.use_cases.procesar_articulos_de_fuente import (
    SCORE_AREA_TEMATICA_MATCH,
    SCORE_DISTRITO_DEL_LEGISLADOR,
    SCORE_HAY_MENCION_LEGISLADOR,
    SCORE_MINIMO_ARTICULO_RELEVANTE,
)
from praxis.domain import (
    AlcanceMedio,
    AreaTematica,
    Articulo,
    ArticuloRelevante,
    Bloque,
    Camara,
    ClasificacionArticulo,
    FuenteNoticia,
    Legislador,
    Mencion,
    ModoAccesoFuente,
    PerfilInteresDespacho,
    TipoFuenteNoticia,
)
from praxis.infrastructure.llm.fake import FakeLlmProvider

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fakes minimales — implementan los 6 puertos en memoria
# ---------------------------------------------------------------------------


class FakeFuenteAdapter:
    """Devuelve una lista fija de artículos + cuerpo configurable.

    Si `texto_por_url[url]` levanta excepción, se propaga (para
    simular sitios caídos).
    """

    def __init__(
        self,
        *,
        articulos: list[Articulo],
        texto_por_url: dict[str, str | Exception],
    ) -> None:
        self._articulos = articulos
        self._texto_por_url = texto_por_url
        self.llamadas_listar = 0
        self.llamadas_texto = 0

    async def listar_articulos_nuevos(
        self, fuente: FuenteNoticia, *, desde: datetime,
    ) -> list[Articulo]:
        self.llamadas_listar += 1
        _ = fuente, desde
        return list(self._articulos)

    async def obtener_texto_articulo(self, articulo: Articulo) -> str:
        self.llamadas_texto += 1
        valor = self._texto_por_url.get(articulo.url, "")
        if isinstance(valor, Exception):
            raise valor
        return valor


class FakeFuenteRepo:
    def __init__(self) -> None:
        self.revisadas: dict[UUID, datetime] = {}

    async def marcar_revisada(
        self, fuente_id: UUID, *, momento: datetime,
    ) -> None:
        self.revisadas[fuente_id] = momento


class FakeHashRepo:
    def __init__(self) -> None:
        self._set: set[str] = set()

    async def existe(self, hash_dedup: str) -> bool:
        return hash_dedup in self._set

    async def registrar(self, hash_dedup: str) -> bool:
        if hash_dedup in self._set:
            return False
        self._set.add(hash_dedup)
        return True


class FakeArticuloRepo:
    def __init__(self) -> None:
        self._por_id: dict[UUID, Articulo] = {}
        self._por_hash: dict[str, Articulo] = {}

    async def upsert_lote(
        self, articulos: list[Articulo],
    ) -> list[Articulo]:
        out: list[Articulo] = []
        for a in articulos:
            ex = self._por_hash.get(a.hash_dedup)
            if ex is not None:
                out.append(ex)
                continue
            nuevo_id = uuid4()
            persistido = Articulo(
                id=nuevo_id,
                fuente_id=a.fuente_id,
                url=a.url,
                titulo=a.titulo,
                bajada_propia=a.bajada_propia,
                publicado_en=a.publicado_en,
                capturado_en=a.capturado_en or datetime.now(UTC),
                hash_dedup=a.hash_dedup,
            )
            self._por_id[nuevo_id] = persistido
            self._por_hash[a.hash_dedup] = persistido
            out.append(persistido)
        return out

    async def actualizar_bajada_propia(
        self, articulo_id: UUID, *, bajada: str,
    ) -> Articulo:
        a = self._por_id[articulo_id]
        actualizado = Articulo(
            id=a.id,
            fuente_id=a.fuente_id,
            url=a.url,
            titulo=a.titulo,
            bajada_propia=bajada,
            publicado_en=a.publicado_en,
            capturado_en=a.capturado_en,
            hash_dedup=a.hash_dedup,
        )
        self._por_id[articulo_id] = actualizado
        self._por_hash[a.hash_dedup] = actualizado
        return actualizado


class FakeClasifRepo:
    def __init__(self) -> None:
        self.por_articulo: dict[UUID, ClasificacionArticulo] = {}

    async def buscar_por_articulo(
        self, articulo_id: UUID,
    ) -> ClasificacionArticulo | None:
        return self.por_articulo.get(articulo_id)

    async def crear(
        self, clasif: ClasificacionArticulo,
    ) -> ClasificacionArticulo:
        con_id = ClasificacionArticulo(
            id=uuid4(),
            articulo_id=clasif.articulo_id,
            area_tematica=clasif.area_tematica,
            palabras_clave=list(clasif.palabras_clave),
            modelo=clasif.modelo,
            prompt_version=clasif.prompt_version,
            generado_en=clasif.generado_en,
        )
        self.por_articulo[clasif.articulo_id] = con_id
        return con_id


class FakeMencionRepo:
    def __init__(self) -> None:
        self.persistidas: list[Mencion] = []

    async def crear_lote(self, menciones: list[Mencion]) -> list[Mencion]:
        out: list[Mencion] = []
        for m in menciones:
            con_id = Mencion(
                id=uuid4(),
                articulo_id=m.articulo_id,
                legislador_id=m.legislador_id,
                despacho_id=m.despacho_id,
                snippet_contexto=m.snippet_contexto,
                tono=m.tono,
                confianza_tono=m.confianza_tono,
                alcance_medio=m.alcance_medio,
                detectado_en=m.detectado_en,
                notificada=m.notificada,
            )
            self.persistidas.append(con_id)
            out.append(con_id)
        return out


class FakeRelevanteRepo:
    def __init__(self) -> None:
        self.persistidas: list[ArticuloRelevante] = []

    async def upsert(
        self, relevante: ArticuloRelevante,
    ) -> ArticuloRelevante:
        self.persistidas.append(relevante)
        return relevante


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def _fuente_nacional() -> FuenteNoticia:
    return FuenteNoticia(
        id=uuid4(),
        nombre="La Nación",
        dominio="lanacion.com.ar",
        tipo=TipoFuenteNoticia.NACIONAL,
        alcance=AlcanceMedio.NACIONAL,
        modo_acceso=ModoAccesoFuente.RSS,
        feed_url="https://lanacion.com.ar/rss",
    )


def _fuente_distrital(distrito: str = "BUENOS AIRES") -> FuenteNoticia:
    return FuenteNoticia(
        id=uuid4(),
        nombre=f"Medio {distrito}",
        dominio=f"{distrito.lower().replace(' ', '-')}.com.ar",
        tipo=TipoFuenteNoticia.DISTRITAL,
        alcance=AlcanceMedio.PROVINCIAL,
        modo_acceso=ModoAccesoFuente.RSS,
        feed_url=f"https://{distrito.lower()}.com.ar/rss",
        distrito=distrito,
    )


def _articulo_crudo(
    fuente_id: UUID, *, titulo: str = "Educación pública", url: str | None = None,
) -> Articulo:
    return Articulo(
        id=None,
        fuente_id=fuente_id,
        url=url or f"https://medio.com.ar/{uuid4().hex[:6]}",
        titulo=titulo,
        publicado_en=datetime(2026, 6, 1, 9, 0, tzinfo=UTC),
    )


def _legislador() -> Legislador:
    return Legislador(
        slug="pjuliano",
        apellido="Juliano",
        nombre="Pablo",
        camara=Camara.HCDN,
        distrito="BUENOS AIRES",
        bloque=Bloque(nombre="DEMOCRACIA PARA SIEMPRE", camara=Camara.HCDN),
        periodo_mandato="2023-2027",
        fecha_inicio_mandato=date(2023, 12, 10),
        fecha_fin_mandato=date(2027, 12, 9),
    )


def _despacho_suscrito(
    *,
    perfil: PerfilInteresDespacho | None = None,
    legisladores: Iterable[LegisladorAMonitorear] | None = None,
) -> DespachoSuscrito:
    return DespachoSuscrito(
        despacho_id=uuid4(),
        perfil_interes=perfil,
        legisladores=list(legisladores or []),
    )


def _perfil(
    despacho_id: UUID,
    *,
    areas: Iterable[str] = (),
    distritos: Iterable[str] = (),
) -> PerfilInteresDespacho:
    return PerfilInteresDespacho(
        despacho_id=despacho_id,
        areas_tematicas=list(areas),
        distritos_observados=list(distritos),
    )


def _build_caso_de_uso(
    *,
    adapter: FakeFuenteAdapter,
) -> tuple[
    ProcesarArticulosDeFuente,
    FakeFuenteRepo,
    FakeHashRepo,
    FakeArticuloRepo,
    FakeClasifRepo,
    FakeMencionRepo,
    FakeRelevanteRepo,
]:
    fuentes = FakeFuenteRepo()
    hashes = FakeHashRepo()
    articulos = FakeArticuloRepo()
    clasif = FakeClasifRepo()
    menciones = FakeMencionRepo()
    relevantes = FakeRelevanteRepo()
    llm = FakeLlmProvider()
    detector = DetectarMencionesEnArticulo(llm=llm)
    uc = ProcesarArticulosDeFuente(
        fuente_adapter=adapter,  # type: ignore[arg-type]
        articulos=articulos,  # type: ignore[arg-type]
        hashes=hashes,  # type: ignore[arg-type]
        clasificaciones=clasif,  # type: ignore[arg-type]
        menciones=menciones,  # type: ignore[arg-type]
        relevantes=relevantes,  # type: ignore[arg-type]
        fuentes=fuentes,  # type: ignore[arg-type]
        llm=llm,
        detector_menciones=detector,
    )
    return uc, fuentes, hashes, articulos, clasif, menciones, relevantes


# ---------------------------------------------------------------------------
# Casos felices
# ---------------------------------------------------------------------------


async def test_pipeline_completo_sin_despachos() -> None:
    fuente = _fuente_nacional()
    arts = [_articulo_crudo(fuente.id, titulo="Educación pública")]  # type: ignore[arg-type]
    adapter = FakeFuenteAdapter(
        articulos=arts,
        texto_por_url={
            arts[0].url: (
                "La nueva ley de educación pública anuncia más jornadas "
                "escolares en todo el país. Es una reforma extensa."
            ),
        },
    )
    uc, fuentes, _hashes, articulos, clasif, menciones, relevantes = (
        _build_caso_de_uso(adapter=adapter)
    )

    resultado = await uc.ejecutar(
        fuente,
        desde=datetime(2026, 5, 1, tzinfo=UTC),
        despachos=[],
    )

    assert resultado.articulos_descubiertos == 1
    assert resultado.articulos_nuevos == 1
    assert resultado.articulos_omitidos_por_dedup == 0
    assert resultado.bajadas_generadas == 1
    assert resultado.clasificaciones_persistidas == 1
    assert resultado.menciones_creadas == 0
    assert resultado.relevancias_persistidas == 0
    assert resultado.fallidos == 0

    # Verifica fuente marcada como revisada.
    assert fuente.id in fuentes.revisadas
    # Verifica que se persistió bajada + clasificación.
    persistido = next(iter(articulos._por_id.values()))
    assert persistido.bajada_propia is not None
    assert len(clasif.por_articulo) == 1
    # Menciones y relevancias sin despachos: vacías.
    assert menciones.persistidas == []
    assert relevantes.persistidas == []


async def test_dedup_omite_articulo_ya_visto() -> None:
    fuente = _fuente_nacional()
    art = _articulo_crudo(fuente.id, titulo="Repe")  # type: ignore[arg-type]
    adapter = FakeFuenteAdapter(
        articulos=[art],
        texto_por_url={art.url: "irrelevante"},
    )
    uc, _f, hashes, _a, _c, _m, _r = _build_caso_de_uso(adapter=adapter)
    # Seedeamos el hash como ya conocido.
    await hashes.registrar(art.hash_dedup)

    resultado = await uc.ejecutar(
        fuente,
        desde=datetime(2026, 5, 1, tzinfo=UTC),
        despachos=[],
    )
    assert resultado.articulos_descubiertos == 1
    assert resultado.articulos_nuevos == 0
    assert resultado.articulos_omitidos_por_dedup == 1
    # No se bajó el texto.
    assert adapter.llamadas_texto == 0


async def test_excepcion_en_texto_no_rompe_ni_persiste_clasif() -> None:
    fuente = _fuente_nacional()
    art = _articulo_crudo(fuente.id)  # type: ignore[arg-type]
    adapter = FakeFuenteAdapter(
        articulos=[art],
        texto_por_url={art.url: RuntimeError("connection reset")},
    )
    uc, _f, hashes, _a, clasif, _m, _r = _build_caso_de_uso(adapter=adapter)

    resultado = await uc.ejecutar(
        fuente,
        desde=datetime(2026, 5, 1, tzinfo=UTC),
        despachos=[],
    )
    assert resultado.articulos_nuevos == 1
    assert resultado.bajadas_generadas == 0
    assert resultado.clasificaciones_persistidas == 0
    # El hash se registra igual para no reintentarlo.
    assert await hashes.existe(art.hash_dedup)
    assert clasif.por_articulo == {}


async def test_despacho_con_perfil_y_legislador_genera_relevancia() -> None:
    fuente = _fuente_nacional()
    art = _articulo_crudo(fuente.id, titulo="Diputados aprobó reforma educativa")  # type: ignore[arg-type]
    texto = (
        "El diputado Pablo Juliano impulsó hoy una nueva ley de "
        "educación pública en el recinto. Acompañaron 130 votos."
    )
    adapter = FakeFuenteAdapter(
        articulos=[art],
        texto_por_url={art.url: texto},
    )
    leg = _legislador()
    despacho = _despacho_suscrito(
        legisladores=[
            LegisladorAMonitorear(
                legislador=leg,
                legislador_id=uuid4(),
                despacho_id=uuid4(),
            ),
        ],
    )
    perfil = _perfil(
        despacho.despacho_id,
        areas=["educacion"],
    )
    despacho = DespachoSuscrito(
        despacho_id=despacho.despacho_id,
        perfil_interes=perfil,
        legisladores=despacho.legisladores,
    )

    uc, _f, _h, _a, _c, menciones, relevantes = _build_caso_de_uso(
        adapter=adapter,
    )
    resultado = await uc.ejecutar(
        fuente,
        desde=datetime(2026, 5, 1, tzinfo=UTC),
        despachos=[despacho],
    )

    # Mención creada.
    assert len(menciones.persistidas) == 1
    assert menciones.persistidas[0].despacho_id == despacho.despacho_id
    # Relevancia persistida: área educación (+35) + mención (+35) = 70 ≥ 30.
    assert len(relevantes.persistidas) == 1
    assert relevantes.persistidas[0].score >= SCORE_MINIMO_ARTICULO_RELEVANTE
    assert resultado.menciones_creadas == 1
    assert resultado.relevancias_persistidas == 1


async def test_sin_perfil_no_persiste_relevancia() -> None:
    fuente = _fuente_nacional()
    art = _articulo_crudo(fuente.id, titulo="Salud pública")  # type: ignore[arg-type]
    texto = "El hospital público atendió 1000 vacunas en mayo. Una jornada larga."
    adapter = FakeFuenteAdapter(
        articulos=[art],
        texto_por_url={art.url: texto},
    )
    despacho = _despacho_suscrito(perfil=None)
    uc, _f, _h, _a, _c, _m, relevantes = _build_caso_de_uso(adapter=adapter)
    resultado = await uc.ejecutar(
        fuente,
        desde=datetime(2026, 5, 1, tzinfo=UTC),
        despachos=[despacho],
    )
    assert relevantes.persistidas == []
    assert resultado.relevancias_persistidas == 0


async def test_excepcion_en_un_articulo_no_corta_el_loop() -> None:
    """Si un artículo falla por excepción en el adapter, los otros se
    procesan igual."""
    fuente = _fuente_nacional()
    a1 = _articulo_crudo(fuente.id, url="https://m.com/ok-1")  # type: ignore[arg-type]
    a2 = _articulo_crudo(fuente.id, url="https://m.com/fail")  # type: ignore[arg-type]
    a3 = _articulo_crudo(fuente.id, url="https://m.com/ok-2")  # type: ignore[arg-type]
    adapter = FakeFuenteAdapter(
        articulos=[a1, a2, a3],
        texto_por_url={
            a1.url: "Texto suficiente para ser una bajada interesante.",
            a2.url: ValueError("boom"),
            a3.url: "Otro texto suficientemente largo para procesar bien.",
        },
    )
    uc, _f, hashes, _a, _c, _m, _r = _build_caso_de_uso(adapter=adapter)

    resultado = await uc.ejecutar(
        fuente,
        desde=datetime(2026, 5, 1, tzinfo=UTC),
        despachos=[],
    )
    # 3 nuevos (a2 falla en texto, no en upsert).
    assert resultado.articulos_nuevos == 3
    # 2 bajadas (la del texto que falló sí o sí no tiene bajada).
    assert resultado.bajadas_generadas == 2
    assert resultado.clasificaciones_persistidas == 2
    # El hash de a2 quedó registrado (no reintentamos).
    assert await hashes.existe(a2.hash_dedup)


# ---------------------------------------------------------------------------
# calcular_score_relevancia (función pura)
# ---------------------------------------------------------------------------


def _clasif(area: AreaTematica, *, palabras: list[str] | None = None) -> ClasificacionArticulo:
    return ClasificacionArticulo(
        id=uuid4(),
        articulo_id=uuid4(),
        area_tematica=area,
        palabras_clave=palabras or [],
        modelo="fake",
    )


class TestScoreRelevancia:
    def test_sin_perfil_score_0(self) -> None:
        score, razon = calcular_score_relevancia(
            fuente=_fuente_nacional(),
            clasificacion=None,
            perfil=None,
            hay_mencion_de_legislador=True,
        )
        assert score == 0
        assert "Sin perfil" in razon

    def test_area_matchea_suma_35(self) -> None:
        score, razon = calcular_score_relevancia(
            fuente=_fuente_nacional(),
            clasificacion=_clasif(AreaTematica.SALUD),
            perfil=PerfilInteresDespacho(
                despacho_id=uuid4(),
                areas_tematicas=["salud"],
            ),
            hay_mencion_de_legislador=False,
        )
        assert score == SCORE_AREA_TEMATICA_MATCH
        assert "salud" in razon

    def test_area_no_matchea_score_0(self) -> None:
        score, _ = calcular_score_relevancia(
            fuente=_fuente_nacional(),
            clasificacion=_clasif(AreaTematica.SEGURIDAD),
            perfil=PerfilInteresDespacho(
                despacho_id=uuid4(),
                areas_tematicas=["salud"],
            ),
            hay_mencion_de_legislador=False,
        )
        assert score == 0

    def test_mencion_y_area_combinan(self) -> None:
        score, _ = calcular_score_relevancia(
            fuente=_fuente_nacional(),
            clasificacion=_clasif(AreaTematica.SALUD),
            perfil=PerfilInteresDespacho(
                despacho_id=uuid4(),
                areas_tematicas=["salud"],
            ),
            hay_mencion_de_legislador=True,
        )
        assert score == SCORE_AREA_TEMATICA_MATCH + SCORE_HAY_MENCION_LEGISLADOR

    def test_distrito_de_fuente_distrital_suma(self) -> None:
        score, razon = calcular_score_relevancia(
            fuente=_fuente_distrital("BUENOS AIRES"),
            clasificacion=None,
            perfil=PerfilInteresDespacho(
                despacho_id=uuid4(),
                distritos_observados=["BUENOS AIRES"],
            ),
            hay_mencion_de_legislador=False,
        )
        assert score == SCORE_DISTRITO_DEL_LEGISLADOR
        assert "BUENOS AIRES" in razon

    def test_score_cap_100(self) -> None:
        """Aunque todo matchee, no excede 100."""
        score, _ = calcular_score_relevancia(
            fuente=_fuente_distrital("BUENOS AIRES"),
            clasificacion=_clasif(
                AreaTematica.SALUD, palabras=["hospital"],
            ),
            perfil=PerfilInteresDespacho(
                despacho_id=uuid4(),
                areas_tematicas=["salud"],
                distritos_observados=["BUENOS AIRES"],
                comisiones_legislador=["hospital"],
            ),
            hay_mencion_de_legislador=True,
        )
        assert score <= 100


# Sanity para que pytest no se queje de import no usado.
_ = dataclass
