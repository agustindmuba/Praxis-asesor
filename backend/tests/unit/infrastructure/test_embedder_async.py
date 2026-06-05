"""Tests del wrapper async `embeber_textos_async` (feat-42.8).

NO levanta Celery ni PyTorch. Verifica que el wrapper:
- Devuelve [] sin tocar Celery si la lista de textos está vacía.
- Despacha `.delay()` y await sobre el resultado vía `asyncio.to_thread`.
- Pasa el timeout configurado al `.get()`.

Estrategia: monkeypatch del símbolo `embeber_textos_task` en
`embedder_async`. No tocamos broker ni worker. El handle fake
implementa `.get(timeout)` síncrono.
"""

from __future__ import annotations

import pytest

from praxis.infrastructure.rag import embedder_async as mod

pytestmark = pytest.mark.unit


class _FakeResultHandle:
    """Imita el AsyncResult que devuelve `task.delay()`."""

    def __init__(self, payload: list[list[float]]) -> None:
        self._payload = payload
        self.get_calls: list[float | None] = []

    def get(self, timeout: float | None = None) -> list[list[float]]:
        self.get_calls.append(timeout)
        return self._payload


class _FakeTask:
    """Imita `embeber_textos_task` con `.delay(textos)`."""

    def __init__(self, embeddings: list[list[float]]) -> None:
        self._embeddings = embeddings
        self.delay_calls: list[list[str]] = []

    def delay(self, textos: list[str]) -> _FakeResultHandle:
        self.delay_calls.append(list(textos))
        return _FakeResultHandle(self._embeddings)


@pytest.mark.asyncio
async def test_textos_vacios_devuelve_lista_vacia_sin_tocar_celery(
    monkeypatch,
) -> None:
    """Camino corto: lista vacía → return []. No llama a delay()."""
    fake = _FakeTask([[1.0, 2.0]])
    monkeypatch.setattr(mod, "embeber_textos_task", fake, raising=False)

    result = await mod.embeber_textos_async([])
    assert result == []
    assert fake.delay_calls == []


@pytest.mark.asyncio
async def test_devuelve_embeddings_del_handle(monkeypatch) -> None:
    fake = _FakeTask(embeddings=[[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])
    monkeypatch.setattr(mod, "embeber_textos_task", fake, raising=False)

    result = await mod.embeber_textos_async(["hola", "mundo"])
    assert result == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    assert fake.delay_calls == [["hola", "mundo"]]


@pytest.mark.asyncio
async def test_pasa_timeout_configurado_al_get(monkeypatch) -> None:
    """El `.get()` debe usar el timeout del módulo, no None."""
    embeddings = [[0.0]]
    fake = _FakeTask(embeddings)

    captured_handles: list[_FakeResultHandle] = []
    original_delay = fake.delay

    def delay_wrapper(textos):
        h = original_delay(textos)
        captured_handles.append(h)
        return h

    fake.delay = delay_wrapper                          # type: ignore[method-assign]
    monkeypatch.setattr(mod, "embeber_textos_task", fake, raising=False)

    await mod.embeber_textos_async(["x"])

    assert len(captured_handles) == 1
    assert captured_handles[0].get_calls == [mod.EMBEDDER_TIMEOUT_SEG]


@pytest.mark.asyncio
async def test_to_thread_se_invoca(monkeypatch) -> None:
    """El `.get()` se ejecuta vía `asyncio.to_thread`, no inline.

    Esto importa: si no usáramos to_thread, el `.get()` síncrono
    bloquearía el event loop del API. Verificamos parchando
    `asyncio.to_thread` y confirmando que pasó por ahí.
    """
    import asyncio as _asyncio

    fake = _FakeTask(embeddings=[[0.9]])
    monkeypatch.setattr(mod, "embeber_textos_task", fake, raising=False)

    invocaciones: list[tuple[object, tuple, dict]] = []

    original = _asyncio.to_thread

    async def to_thread_spy(func, *args, **kw):
        invocaciones.append((func, args, kw))
        return await original(func, *args, **kw)

    monkeypatch.setattr(_asyncio, "to_thread", to_thread_spy)

    result = await mod.embeber_textos_async(["x"])
    assert result == [[0.9]]
    assert len(invocaciones) == 1
