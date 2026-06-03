"""Tests del dominio WhatsApp (feat-41.1).

Cubren:
- `validar_e164`: regex de teléfonos, normalización (espacios/guiones).
- `Destinatario`: invariantes (nombre vacío, e164 inválido, opt_out
  anterior a opt_in, activo sin opt-in vigente). `puede_recibir`.
- `PlantillaWhatsApp`: name snake_case, body_params vs placeholders
  `{{N}}` del contenido.
- `EnvioWhatsApp`: consistencia estado ↔ campos (ENVIADO requiere
  message_id_meta, FALLIDO/RECHAZADO requiere error). `fue_exitoso`,
  `es_terminal`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from praxis.domain import (
    CategoriaPlantilla,
    Destinatario,
    EnvioWhatsApp,
    EstadoEnvio,
    EstadoMetaPlantilla,
    PlantillaWhatsApp,
    RolDestinatario,
    TipoEnvio,
    validar_e164,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# validar_e164
# ---------------------------------------------------------------------------


class TestValidarE164:
    def test_ok(self) -> None:
        assert validar_e164("+5491155551234") == "+5491155551234"

    def test_normaliza_espacios_y_guiones(self) -> None:
        assert validar_e164("+54 9 11 5555-1234") == "+5491155551234"

    @pytest.mark.parametrize("malo", [
        "5491155551234",   # sin +
        "+0491155551234",  # arranca con 0
        "+54",             # muy corto
        "+5491155551234567890",  # muy largo
        "+abc91155551234",  # letras
        "",
    ])
    def test_invalido_lanza(self, malo: str) -> None:
        with pytest.raises(ValueError, match=r"E\.164"):
            validar_e164(malo)


# ---------------------------------------------------------------------------
# Destinatario
# ---------------------------------------------------------------------------


def _dest(**overrides: object) -> Destinatario:
    defaults = {
        "id": None,
        "despacho_id": uuid4(),
        "nombre": "Pablo Juliano",
        "rol_interno": RolDestinatario.LEGISLADOR,
        "telefono_e164": "+5491155551234",
    }
    defaults.update(overrides)  # type: ignore[arg-type]
    return Destinatario(**defaults)  # type: ignore[arg-type]


class TestDestinatario:
    def test_construir_minimo(self) -> None:
        d = _dest()
        assert d.opt_in_vigente is False
        assert d.activo is False

    def test_nombre_vacio_lanza(self) -> None:
        with pytest.raises(ValueError, match="nombre"):
            _dest(nombre="   ")

    def test_telefono_invalido_lanza(self) -> None:
        with pytest.raises(ValueError, match=r"E\.164"):
            _dest(telefono_e164="555-1234")

    def test_opt_out_anterior_a_opt_in_lanza(self) -> None:
        ahora = datetime(2026, 6, 1, tzinfo=UTC)
        with pytest.raises(ValueError, match="opt_out"):
            _dest(opt_in_en=ahora, opt_out_en=ahora - timedelta(days=1))

    def test_activo_sin_opt_in_lanza(self) -> None:
        with pytest.raises(ValueError, match="opt_in vigente"):
            _dest(activo=True)

    def test_activo_con_opt_out_lanza(self) -> None:
        ahora = datetime(2026, 6, 1, tzinfo=UTC)
        with pytest.raises(ValueError, match="opt_in vigente"):
            _dest(
                opt_in_en=ahora - timedelta(days=10),
                opt_out_en=ahora,
                activo=True,
            )

    def test_activo_con_opt_in_vigente_ok(self) -> None:
        d = _dest(
            opt_in_en=datetime(2026, 6, 1, tzinfo=UTC),
            activo=True,
        )
        assert d.opt_in_vigente is True
        assert d.activo is True

    def test_puede_recibir_respeta_flag(self) -> None:
        d = _dest(
            opt_in_en=datetime(2026, 6, 1, tzinfo=UTC),
            activo=True,
            recibe_briefing_diario=False,
            recibe_alertas_menciones=True,
            recibe_alertas_otras=False,
        )
        assert d.puede_recibir(TipoEnvio.BRIEFING_DIARIO) is False
        assert d.puede_recibir(TipoEnvio.ALERTA_MENCION) is True
        assert d.puede_recibir(TipoEnvio.ALERTA_BO) is False

    def test_puede_recibir_inactivo_siempre_falso(self) -> None:
        d = _dest(recibe_briefing_diario=True, recibe_alertas_menciones=True)
        # No tiene opt_in → no puede.
        assert d.puede_recibir(TipoEnvio.BRIEFING_DIARIO) is False


# ---------------------------------------------------------------------------
# PlantillaWhatsApp
# ---------------------------------------------------------------------------


class TestPlantillaWhatsApp:
    def test_construir_ok(self) -> None:
        p = PlantillaWhatsApp(
            name="briefing_diario",
            categoria=CategoriaPlantilla.UTILITY,
            body_params=["nombre", "fecha"],
            contenido_referencia="Hola {{1}}, tu briefing del {{2}}.",
        )
        assert p.aprobada is False
        assert p.idioma == "es_AR"

    def test_name_invalido_lanza(self) -> None:
        with pytest.raises(ValueError, match="snake_case"):
            PlantillaWhatsApp(
                name="Briefing-Diario",
                categoria=CategoriaPlantilla.UTILITY,
                body_params=[],
                contenido_referencia="Hola",
            )

    def test_placeholders_no_cuadran_lanza(self) -> None:
        with pytest.raises(ValueError, match="body_params"):
            PlantillaWhatsApp(
                name="x",
                categoria=CategoriaPlantilla.UTILITY,
                body_params=["uno"],  # 1 param
                contenido_referencia="Hola {{1}} y {{2}}.",  # 2 placeholders
            )

    def test_aprobada_property(self) -> None:
        p = PlantillaWhatsApp(
            name="x",
            categoria=CategoriaPlantilla.UTILITY,
            body_params=[],
            contenido_referencia="Hola.",
            estado_meta=EstadoMetaPlantilla.APROBADA,
        )
        assert p.aprobada is True


# ---------------------------------------------------------------------------
# EnvioWhatsApp
# ---------------------------------------------------------------------------


def _envio(**overrides: object) -> EnvioWhatsApp:
    defaults = {
        "id": None,
        "destinatario_id": uuid4(),
        "despacho_id": uuid4(),
        "plantilla_name": "briefing_diario",
        "tipo": TipoEnvio.BRIEFING_DIARIO,
    }
    defaults.update(overrides)  # type: ignore[arg-type]
    return EnvioWhatsApp(**defaults)  # type: ignore[arg-type]


class TestEnvioWhatsApp:
    def test_pendiente_minimo(self) -> None:
        e = _envio()
        assert e.estado == EstadoEnvio.PENDIENTE
        assert e.fue_exitoso is False
        assert e.es_terminal is False

    def test_enviado_sin_message_id_lanza(self) -> None:
        with pytest.raises(ValueError, match="message_id_meta"):
            _envio(estado=EstadoEnvio.ENVIADO)

    def test_enviado_con_message_id_ok(self) -> None:
        e = _envio(
            estado=EstadoEnvio.ENVIADO,
            message_id_meta="wamid.HBgM...",
        )
        assert e.fue_exitoso is True
        assert e.es_terminal is False

    def test_fallido_sin_error_lanza(self) -> None:
        with pytest.raises(ValueError, match="error"):
            _envio(estado=EstadoEnvio.FALLIDO)

    def test_rechazado_sin_error_lanza(self) -> None:
        with pytest.raises(ValueError, match="error"):
            _envio(estado=EstadoEnvio.RECHAZADO)

    def test_leido_es_terminal_y_exitoso(self) -> None:
        e = _envio(
            estado=EstadoEnvio.LEIDO,
            message_id_meta="wamid.x",
        )
        # LEIDO no requiere message_id según las reglas (solo ENVIADO sí),
        # pero acá lo pasamos igual.
        assert e.fue_exitoso is True
        assert e.es_terminal is True
