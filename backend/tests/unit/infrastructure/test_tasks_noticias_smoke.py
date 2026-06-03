"""Smoke test minimal de las Celery tasks de noticias (feat-40.5.D).

NO ejecuta las tasks (esos son tests de integración separados que
viven en feat-40.7 con smoke real). Sólo verifica que:

- `legislador_uuid()` es estable + diferente para distintos slugs.
- Las tasks están registradas en `celery_app.tasks`.
- El beat_schedule incluye las 2 tasks nuevas con `crontab`.

No imitamos un broker Redis — pickleamos sólo la registración.
"""

from __future__ import annotations

import pytest
from celery.schedules import crontab

from praxis.domain import Camara
from praxis.infrastructure.queue.celery_app import celery_app
from praxis.infrastructure.queue.tasks_noticias import legislador_uuid

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# legislador_uuid
# ---------------------------------------------------------------------------


def test_legislador_uuid_es_estable() -> None:
    """El mismo (slug, cámara) genera el mismo UUID en distintas
    corridas."""
    u1 = legislador_uuid(slug="pjuliano", camara=Camara.HCDN)
    u2 = legislador_uuid(slug="pjuliano", camara=Camara.HCDN)
    assert u1 == u2


def test_legislador_uuid_distinto_por_camara() -> None:
    u_hcdn = legislador_uuid(slug="aguirre", camara=Camara.HCDN)
    u_hsn = legislador_uuid(slug="aguirre", camara=Camara.HSN)
    assert u_hcdn != u_hsn


def test_legislador_uuid_distinto_por_slug() -> None:
    a = legislador_uuid(slug="pjuliano", camara=Camara.HCDN)
    b = legislador_uuid(slug="haguirre", camara=Camara.HCDN)
    assert a != b


# ---------------------------------------------------------------------------
# Registración en Celery
# ---------------------------------------------------------------------------


def test_tasks_registradas_en_celery() -> None:
    nombres = set(celery_app.tasks.keys())
    assert "praxis.noticias.procesar_fuentes" in nombres
    assert "praxis.noticias.enviar_alertas_pendientes" in nombres


def test_beat_schedule_incluye_noticias() -> None:
    schedule = celery_app.conf.beat_schedule
    assert "noticias-procesar-fuentes" in schedule
    assert "noticias-enviar-alertas-pendientes" in schedule
    # Ambas son crontab (no intervalos sueltos).
    assert isinstance(
        schedule["noticias-procesar-fuentes"]["schedule"], crontab,
    )
    assert isinstance(
        schedule["noticias-enviar-alertas-pendientes"]["schedule"],
        crontab,
    )
    # Las dos tasks deben apuntar al nombre registrado.
    assert (
        schedule["noticias-procesar-fuentes"]["task"]
        == "praxis.noticias.procesar_fuentes"
    )
    assert (
        schedule["noticias-enviar-alertas-pendientes"]["task"]
        == "praxis.noticias.enviar_alertas_pendientes"
    )
