"""Tests del caso de uso `EnviarAlertaMencion` (feat-40.5.C).

Anti-flood (ADR 0009): ≤ 1 alerta agrupada por despacho por hora.

Cubre:

- Sin pendientes → motivo=sin_pendientes, no marca nada.
- Con pendientes + sin alerta reciente → motivo=ok_enviar, devuelve
  las menciones agrupadas y las marca como notificadas atómicamente.
- Con pendientes + alerta reciente (mención notificada en la ventana)
  → motivo=rate_limited, NO marca pendientes.
- Cap por lote: si hay >N pendientes, sólo se envían N (el resto
  queda para la próxima corrida).
- Atomicidad: el caso de uso marca como notificadas ANTES de
  devolver — preferimos pérdida ocasional al duplicado.

Usa fakes minimal que cumplen la interface `MencionRepository`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from praxis.application.use_cases import (
    EnviarAlertaMencion,
)
from praxis.application.use_cases.enviar_alerta_mencion import (
    MAX_MENCIONES_POR_INTENCION,
    VENTANA_ANTI_FLOOD_DEFAULT,
)
from praxis.domain import AlcanceMedio, Mencion, TonoMencion

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fake repo
# ---------------------------------------------------------------------------


class FakeMencionRepo:
    """Mantiene en memoria todas las menciones por despacho. Implementa
    los 3 métodos que el caso de uso usa."""

    def __init__(self) -> None:
        self._por_id: dict[UUID, Mencion] = {}
        self.calls_marcar: list[list[UUID]] = []

    def seed(self, m: Mencion) -> Mencion:
        assert m.id is not None
        self._por_id[m.id] = m
        return m

    async def listar_por_despacho_no_notificadas(
        self, despacho_id: UUID, *, limite: int = 100,
    ) -> list[Mencion]:
        result = [
            m for m in self._por_id.values()
            if m.despacho_id == despacho_id and not m.notificada
        ]
        # Orden por detectado_en DESC (replica el repo real).
        result.sort(
            key=lambda m: m.detectado_en or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )
        return result[:limite]

    async def listar_recientes_por_despacho(
        self,
        despacho_id: UUID,
        *,
        desde: datetime,
        hasta: datetime,
    ) -> list[Mencion]:
        return [
            m for m in self._por_id.values()
            if m.despacho_id == despacho_id
            and m.detectado_en is not None
            and desde <= m.detectado_en <= hasta
        ]

    async def marcar_notificadas(self, mencion_ids: list[UUID]) -> int:
        self.calls_marcar.append(list(mencion_ids))
        n = 0
        for mid in mencion_ids:
            if mid in self._por_id:
                m = self._por_id[mid]
                self._por_id[mid] = Mencion(
                    id=m.id,
                    articulo_id=m.articulo_id,
                    legislador_id=m.legislador_id,
                    despacho_id=m.despacho_id,
                    snippet_contexto=m.snippet_contexto,
                    tono=m.tono,
                    confianza_tono=m.confianza_tono,
                    alcance_medio=m.alcance_medio,
                    detectado_en=m.detectado_en,
                    notificada=True,
                )
                n += 1
        return n


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def _mencion(
    despacho_id: UUID,
    *,
    detectado_en: datetime,
    notificada: bool = False,
    tono: TonoMencion = TonoMencion.NEUTRO,
) -> Mencion:
    return Mencion(
        id=uuid4(),
        articulo_id=uuid4(),
        legislador_id=uuid4(),
        despacho_id=despacho_id,
        snippet_contexto="…contexto…",
        tono=tono,
        confianza_tono=0.7,
        alcance_medio=AlcanceMedio.NACIONAL,
        detectado_en=detectado_en,
        notificada=notificada,
    )


# ---------------------------------------------------------------------------
# Casos
# ---------------------------------------------------------------------------


async def test_sin_pendientes_motivo_sin_pendientes() -> None:
    despacho_id = uuid4()
    repo = FakeMencionRepo()
    uc = EnviarAlertaMencion(menciones=repo)  # type: ignore[arg-type]

    intencion = await uc.ejecutar(
        despacho_id, ahora=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
    )
    assert intencion.motivo == "sin_pendientes"
    assert intencion.menciones == []
    assert repo.calls_marcar == []


async def test_con_pendientes_y_sin_alerta_reciente_envia() -> None:
    despacho_id = uuid4()
    ahora = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    repo = FakeMencionRepo()
    m1 = repo.seed(_mencion(despacho_id, detectado_en=ahora - timedelta(minutes=10)))
    m2 = repo.seed(_mencion(despacho_id, detectado_en=ahora - timedelta(minutes=5)))
    uc = EnviarAlertaMencion(menciones=repo)  # type: ignore[arg-type]

    intencion = await uc.ejecutar(despacho_id, ahora=ahora)
    assert intencion.motivo == "ok_enviar"
    ids = {m.id for m in intencion.menciones}
    assert ids == {m1.id, m2.id}
    # Marcado atómico hecho.
    assert len(repo.calls_marcar) == 1
    assert set(repo.calls_marcar[0]) == ids


async def test_alerta_reciente_rate_limita() -> None:
    """Si hay una mención `notificada=True` con `detectado_en` en la
    ventana → rate-limited; los pendientes no se marcan."""
    despacho_id = uuid4()
    ahora = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    repo = FakeMencionRepo()
    # Notificada hace 30 min (dentro de la ventana de 1 hora).
    repo.seed(_mencion(
        despacho_id,
        detectado_en=ahora - timedelta(minutes=30),
        notificada=True,
    ))
    # Pendiente fresca.
    repo.seed(_mencion(
        despacho_id,
        detectado_en=ahora - timedelta(minutes=5),
        notificada=False,
    ))
    uc = EnviarAlertaMencion(menciones=repo)  # type: ignore[arg-type]

    intencion = await uc.ejecutar(despacho_id, ahora=ahora)
    assert intencion.motivo == "rate_limited_hace_menos_de_la_ventana"
    assert intencion.menciones == []
    # No marcamos nada.
    assert repo.calls_marcar == []


async def test_alerta_vieja_fuera_de_ventana_no_rate_limita() -> None:
    """Si la última notificada está fuera de la ventana → enviamos."""
    despacho_id = uuid4()
    ahora = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    repo = FakeMencionRepo()
    # Notificada hace 2 horas (fuera de la ventana de 1 hora).
    repo.seed(_mencion(
        despacho_id,
        detectado_en=ahora - timedelta(hours=2),
        notificada=True,
    ))
    pendiente = repo.seed(_mencion(
        despacho_id,
        detectado_en=ahora - timedelta(minutes=10),
        notificada=False,
    ))
    uc = EnviarAlertaMencion(menciones=repo)  # type: ignore[arg-type]

    intencion = await uc.ejecutar(despacho_id, ahora=ahora)
    assert intencion.motivo == "ok_enviar"
    assert [m.id for m in intencion.menciones] == [pendiente.id]


async def test_ventana_parametrizable() -> None:
    """La ventana se puede cambiar (ej. 6 horas para pruebas)."""
    despacho_id = uuid4()
    ahora = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    repo = FakeMencionRepo()
    repo.seed(_mencion(
        despacho_id,
        detectado_en=ahora - timedelta(hours=5),
        notificada=True,
    ))
    repo.seed(_mencion(
        despacho_id,
        detectado_en=ahora - timedelta(minutes=5),
        notificada=False,
    ))
    uc = EnviarAlertaMencion(menciones=repo)  # type: ignore[arg-type]

    # Con ventana de 6 horas, la notificada de hace 5h SÍ rate-limita.
    intencion = await uc.ejecutar(
        despacho_id, ahora=ahora, ventana_anti_flood=timedelta(hours=6),
    )
    assert intencion.motivo == "rate_limited_hace_menos_de_la_ventana"


async def test_cap_por_lote() -> None:
    """Si hay más pendientes que `max_por_lote`, sólo se envían N."""
    despacho_id = uuid4()
    ahora = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    repo = FakeMencionRepo()
    for i in range(30):
        repo.seed(_mencion(
            despacho_id,
            detectado_en=ahora - timedelta(minutes=30 - i),
        ))
    uc = EnviarAlertaMencion(menciones=repo)  # type: ignore[arg-type]

    intencion = await uc.ejecutar(
        despacho_id, ahora=ahora, max_por_lote=5,
    )
    assert intencion.motivo == "ok_enviar"
    assert len(intencion.menciones) == 5
    # Los otros 25 quedan pendientes para la próxima corrida.
    restantes = await repo.listar_por_despacho_no_notificadas(despacho_id)
    assert len(restantes) == 25


async def test_no_cruza_despachos() -> None:
    """Los pendientes de otro despacho no aparecen acá."""
    a = uuid4()
    b = uuid4()
    ahora = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    repo = FakeMencionRepo()
    repo.seed(_mencion(a, detectado_en=ahora - timedelta(minutes=5)))
    repo.seed(_mencion(b, detectado_en=ahora - timedelta(minutes=5)))
    uc = EnviarAlertaMencion(menciones=repo)  # type: ignore[arg-type]

    intencion_a = await uc.ejecutar(a, ahora=ahora)
    assert len(intencion_a.menciones) == 1
    assert intencion_a.menciones[0].despacho_id == a


# ---------------------------------------------------------------------------
# Sanity de constantes
# ---------------------------------------------------------------------------


def test_constantes_default_razonables() -> None:
    assert VENTANA_ANTI_FLOOD_DEFAULT == timedelta(hours=1)
    assert MAX_MENCIONES_POR_INTENCION >= 5
