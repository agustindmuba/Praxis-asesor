"""Tests del helper `run_task_async` (feat-42.11).

Cubre la regresión de feat-42.9: el `engine` async global queda atado
al primer event loop que lo usa. Sin `run_task_async`, la 2ª task
Celery rompe con `'NoneType' object has no attribute 'send'` en
Windows.

Tests unit (este archivo):
- Devuelve el valor de la corutina.
- `engine.dispose()` se invoca en el finally aunque la corutina
  termine bien.
- `engine.dispose()` se invoca aún si la corutina tira excepción
  (la excepción se propaga, pero el dispose corre primero).
- Cada invocación crea un loop NUEVO.

Tests integración (`tests/integration/test_async_runtime_db.py`):
- 2 invocaciones consecutivas que tocan la DB real funcionan.
  Esto es el smoke del bug original.
"""

from __future__ import annotations

import asyncio

import pytest

from praxis.infrastructure.queue import _async_runtime as mod

pytestmark = pytest.mark.unit


class _EngineSpy:
    """Stand-in del `engine` global de SQLAlchemy."""

    def __init__(self) -> None:
        self.dispose_calls = 0

    async def dispose(self) -> None:
        self.dispose_calls += 1


def _instalar_engine_spy(monkeypatch) -> _EngineSpy:
    """Inyecta un spy en el módulo `db.engine` para que `run_task_async`
    lo use cuando hace el import lazy."""
    spy = _EngineSpy()
    import praxis.infrastructure.db.engine as engine_mod

    monkeypatch.setattr(engine_mod, "engine", spy, raising=True)
    return spy


def test_run_task_async_devuelve_resultado_de_corutina(monkeypatch) -> None:
    _instalar_engine_spy(monkeypatch)

    async def _coro() -> int:
        return 42

    assert mod.run_task_async(_coro()) == 42


def test_run_task_async_dispose_en_finally_caso_feliz(monkeypatch) -> None:
    spy = _instalar_engine_spy(monkeypatch)

    async def _coro() -> str:
        return "ok"

    mod.run_task_async(_coro())
    assert spy.dispose_calls == 1


def test_run_task_async_dispose_aun_si_la_corutina_tira(monkeypatch) -> None:
    """Si la corutina rompe, la excepción se propaga, pero el dispose
    igual corre (es la garantía del finally)."""
    spy = _instalar_engine_spy(monkeypatch)

    async def _coro() -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        mod.run_task_async(_coro())
    assert spy.dispose_calls == 1


def test_run_task_async_loop_es_distinto_en_cada_invocacion(monkeypatch) -> None:
    """Cada invocación debe correr en un loop NUEVO. Esto es lo que
    rompe la dependencia entre tasks (bug feat-42.9)."""
    _instalar_engine_spy(monkeypatch)

    loops_capturados: list[asyncio.AbstractEventLoop] = []

    async def _capturar_loop() -> None:
        loops_capturados.append(asyncio.get_event_loop())

    mod.run_task_async(_capturar_loop())
    mod.run_task_async(_capturar_loop())

    assert len(loops_capturados) == 2
    assert loops_capturados[0] is not loops_capturados[1]


def test_run_task_async_dispose_que_falla_no_propaga(monkeypatch) -> None:
    """Si `dispose` rompe (ej. red caída), el error se loguea pero no
    se propaga — la task ya terminó. La corutina principal sí devuelve
    su resultado."""

    class _EngineRoto:
        async def dispose(self) -> None:
            raise RuntimeError("redis caído")

    import praxis.infrastructure.db.engine as engine_mod
    monkeypatch.setattr(engine_mod, "engine", _EngineRoto(), raising=True)

    async def _coro() -> int:
        return 7

    # No tira: el log warning come la excepción del dispose.
    assert mod.run_task_async(_coro()) == 7


def test_run_task_async_loop_se_cierra(monkeypatch) -> None:
    """El loop creado se cierra al final — confirma que no nos
    quedamos con loops zombi que después choquen con asyncio.get_event_loop()."""
    _instalar_engine_spy(monkeypatch)

    capturado: list[asyncio.AbstractEventLoop] = []

    async def _capturar() -> None:
        capturado.append(asyncio.get_event_loop())

    mod.run_task_async(_capturar())
    assert capturado[0].is_closed()
