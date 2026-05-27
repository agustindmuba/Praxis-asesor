"""Test unitario de praxis.config.

Verifica que Settings carga correctamente con las variables de entorno
seteadas en `tests/conftest.py` y expone los helpers esperados.
"""

import pytest

pytestmark = pytest.mark.unit


def test_settings_loads_from_env() -> None:
    from praxis.config import Settings, get_settings

    get_settings.cache_clear()
    settings = get_settings()
    assert isinstance(settings, Settings)
    assert settings.env == "dev"
    assert settings.log_level == "WARNING"


def test_settings_environment_helpers() -> None:
    from praxis.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    assert settings.is_dev is True
    assert settings.is_prod is False
