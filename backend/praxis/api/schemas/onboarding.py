"""Schemas Pydantic para /onboarding (feat-44).

Estructura del wizard:
1. configurar-despacho → setea legislador titular + cámara + foto, dispara InferirPerfilOpositor.
2. GET estado → devuelve qué pasos del onboarding ya están hechos.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from praxis.domain.value_objects import Camara


class ConfigurarDespachoBody(BaseModel):
    """Body del POST /onboarding/configurar-despacho.

    `legislador_titular_slug` es el "APELLIDO, NOMBRE" canónico que
    aparece en HCDN (ej. "JULIANO, PABLO"). El bot va a hacer match
    laxo por apellido contra la tabla `firmante`.
    """

    model_config = ConfigDict(extra="forbid")

    legislador_titular_slug: str = Field(min_length=3, max_length=100)
    camara: Camara = Camara.HCDN
    foto_url: str | None = Field(default=None, max_length=500)
    inferir_perfil: bool = True   # si False, no llama al LLM


class ConfigurarDespachoResponse(BaseModel):
    despacho_id: str
    legislador_titular_slug: str
    foto_url: str | None
    perfil_inferido: bool
    perfil_id: str | None
    mensaje: str
    error_inferencia: str | None = None


class EstadoOnboardingDTO(BaseModel):
    """Devuelve qué pasos ya están hechos."""

    despacho_id: str
    paso_1_legislador_cargado: bool
    paso_2_perfil_opositor_cargado: bool
    paso_3_destinatarios_cargados: bool
    paso_4_primer_accionable: bool
    todo_listo: bool
