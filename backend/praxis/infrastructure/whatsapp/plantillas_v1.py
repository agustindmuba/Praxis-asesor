"""Catálogo de plantillas WhatsApp v1 (spec 17, feat-41.2).

Estas son las plantillas que vamos a registrar manualmente en Meta
WhatsApp Manager para v1 del producto. El script `scripts/
seed_plantillas_whatsapp.py` las upserta en la tabla local con estado
`pendiente_aprobacion`; cuando Meta aprueba cada una, corremos el
mismo script con `--mark-aprobada <name>` para marcarla `aprobada`.

Convenciones:
- `name`: snake_case, prefijo del use case (briefing_, alerta_,
  opt_in_).
- `idioma`: `es_AR` por default.
- `body_params`: nombres descriptivos de cada placeholder en orden.
- `contenido_referencia`: texto exacto registrado en Meta. Debe tener
  exactamente N placeholders `{{1}}..{{N}}` donde N = len(body_params).
- Todas son `CategoriaPlantilla.UTILITY` (notificaciones operativas;
  no requieren opt-in marketing).
"""

from __future__ import annotations

from praxis.domain import (
    CategoriaPlantilla,
    EstadoMetaPlantilla,
    PlantillaWhatsApp,
)

PLANTILLAS_V1: tuple[PlantillaWhatsApp, ...] = (
    PlantillaWhatsApp(
        name="briefing_diario",
        categoria=CategoriaPlantilla.UTILITY,
        body_params=["nombre", "fecha", "resumen_corto"],
        contenido_referencia=(
            "Hola {{1}}, tu briefing del {{2}}: {{3}}. "
            "Abrí Praxis Asesor para ver el detalle completo."
        ),
        estado_meta=EstadoMetaPlantilla.PENDIENTE_APROBACION,
    ),
    PlantillaWhatsApp(
        name="alerta_mencion_simple",
        categoria=CategoriaPlantilla.UTILITY,
        body_params=["nombre", "medio", "tono", "snippet"],
        contenido_referencia=(
            "Hola {{1}}, te mencionaron en {{2}} (tono {{3}}): "
            "“{{4}}”. Mirá la nota en Praxis Asesor."
        ),
        estado_meta=EstadoMetaPlantilla.PENDIENTE_APROBACION,
    ),
    PlantillaWhatsApp(
        name="alerta_mencion_agrupada",
        categoria=CategoriaPlantilla.UTILITY,
        body_params=["nombre", "cantidad", "ventana"],
        contenido_referencia=(
            "Hola {{1}}, hubo {{2}} menciones del despacho en las "
            "últimas {{3}}. Ingresá a Praxis Asesor para revisarlas."
        ),
        estado_meta=EstadoMetaPlantilla.PENDIENTE_APROBACION,
    ),
    PlantillaWhatsApp(
        name="alerta_bo",
        categoria=CategoriaPlantilla.UTILITY,
        body_params=["nombre", "tipo_norma", "sumario_corto"],
        contenido_referencia=(
            "Hola {{1}}, hay un {{2}} accionable en el BO de hoy: "
            "{{3}}. Mirá el detalle en Praxis Asesor."
        ),
        estado_meta=EstadoMetaPlantilla.PENDIENTE_APROBACION,
    ),
    PlantillaWhatsApp(
        name="opt_in_solicitud",
        categoria=CategoriaPlantilla.UTILITY,
        body_params=["nombre", "despacho"],
        contenido_referencia=(
            "Hola {{1}}, el despacho {{2}} te agregó a Praxis Asesor "
            "para mandarte briefings y alertas por WhatsApp. "
            "Respondé SI para confirmar, NO para descartar."
        ),
        estado_meta=EstadoMetaPlantilla.PENDIENTE_APROBACION,
    ),
    PlantillaWhatsApp(
        name="opt_out_confirmacion",
        categoria=CategoriaPlantilla.UTILITY,
        body_params=["nombre"],
        contenido_referencia=(
            "Hola {{1}}, registramos tu baja. Ya no vas a recibir "
            "más mensajes de Praxis Asesor. Hablá con tu despacho "
            "para volver a sumarte."
        ),
        estado_meta=EstadoMetaPlantilla.PENDIENTE_APROBACION,
    ),
)


def plantillas_v1_por_name() -> dict[str, PlantillaWhatsApp]:
    """Dict de name → PlantillaWhatsApp. Útil para lookups del caso de
    uso `EnviarBriefingDiario` (feat-41.4)."""
    return {p.name: p for p in PLANTILLAS_V1}
