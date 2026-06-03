"""Caso de uso: sembrar (o re-sembrar) el perfil de interés del despacho.

Decisión D1 (sembrado híbrido + editable): el perfil se construye
automáticamente desde:

- `areas_tematicas`: áreas de los expedientes que el despacho sigue
  (vía `ExpedienteAreaTematica` cacheado por feat/27).
- `comisiones_legislador`: comisiones del legislador titular. **Hoy
  queda vacío** porque la relación legislador↔comisiones no existe en
  el padrón actual. Cuando se introduzca, este caso de uso la popula.
- `distritos_observados`: distrito de la banca del legislador.
- `aliases_legislador`: `[nombre_completo, apellido]` del titular. El
  asesor agrega manualmente alias de Twitter / informales desde la UI.

El asesor edita libremente desde `/configuracion`. Tras edición manual,
las llamadas a `execute()` por defecto respetan los valores manuales:
solo re-siembran si `sobreescribir_edicion_manual=True`.

Trigger natural del sembrado:
- Onboarding del despacho.
- Cambios en seguimientos (job nightly o trigger explícito desde
  caso de uso de "seguir/dejar de seguir expediente").

Ver `docs/specs/15-resumen-bo-accionable.md` §"Decisiones de dominio
NUEVAS (resueltas) · D1" y ADR 0006 §"Compartida —
PerfilInteresDespacho".
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from praxis.application.ports import (
    CatalogoLegisladores,
    DespachoRepository,
    ExpedienteAreaTematicaRepository,
    PerfilInteresDespachoRepository,
    SeguimientoExpedienteRepository,
)
from praxis.domain import (
    Camara,
    Legislador,
    PerfilInteresDespacho,
)
from praxis.domain.despacho import Despacho


class SembrarPerfilInteres:
    """Orquesta el sembrado híbrido del `PerfilInteresDespacho`.

    Flujo:
    1. Cargar `Despacho`. Si no existe → `ValueError`.
    2. Resolver `Legislador` titular del padrón (si hay slug).
    3. Si existe perfil previo con edición manual posterior al último
       sembrado y `sobreescribir_edicion_manual=False`, devolverlo sin
       tocar.
    4. Componer el sembrado:
       - áreas únicas de los seguimientos clasificados,
       - distrito del legislador (si hay) → `distritos_observados`,
       - `aliases_legislador` derivados del padrón,
       - `comisiones_legislador = []` (deuda v1).
    5. UPSERT y devolver.
    """

    def __init__(
        self,
        *,
        despachos: DespachoRepository,
        legisladores: CatalogoLegisladores,
        seguimientos: SeguimientoExpedienteRepository,
        clasificaciones: ExpedienteAreaTematicaRepository,
        perfiles: PerfilInteresDespachoRepository,
    ) -> None:
        self._despachos = despachos
        self._legisladores = legisladores
        self._seguimientos = seguimientos
        self._clasificaciones = clasificaciones
        self._perfiles = perfiles

    async def execute(
        self,
        despacho_id: UUID,
        *,
        sobreescribir_edicion_manual: bool = False,
    ) -> PerfilInteresDespacho:
        despacho = await self._despachos.buscar_por_id(despacho_id)
        if despacho is None:
            raise ValueError(f"Despacho {despacho_id} no existe")

        actual = await self._perfiles.buscar_por_despacho(despacho_id)
        if (
            actual is not None
            and actual.fue_editado_despues_de_sembrar
            and not sobreescribir_edicion_manual
        ):
            # Respetar edición manual.
            return actual

        legislador = self._resolver_legislador(despacho)

        areas = await self._areas_de_seguimientos(despacho_id)
        distritos = (
            [legislador.distrito] if legislador and legislador.distrito else []
        )
        aliases = self._derivar_aliases(legislador)

        nuevo = PerfilInteresDespacho(
            despacho_id=despacho_id,
            areas_tematicas=areas,
            comisiones_legislador=[],   # deuda v1 — ver docstring del módulo
            distritos_observados=distritos,
            aliases_legislador=aliases,
            sembrado_at=datetime.now(UTC),
            # Si había edición manual previa y estamos sobreescribiendo,
            # limpiamos `editado_at` — el nuevo sembrado es la verdad.
            editado_at=None,
        )
        return await self._perfiles.upsert(nuevo)

    def _resolver_legislador(self, despacho: Despacho) -> Legislador | None:
        slug = despacho.legislador_titular_slug
        if not slug:
            return None

        # La cámara del titular se guarda en configuración; si no está,
        # default a HCDN (caso más común). El día que se modele Despacho
        # con `camara_titular` propia, esto sale solo.
        camara_str = despacho.configuracion.get("camara_titular", "HCDN")
        try:
            camara = Camara(camara_str)
        except ValueError:
            camara = Camara.HCDN

        try:
            return self._legisladores.buscar_por_slug(slug, camara)
        except KeyError:
            return None

    async def _areas_de_seguimientos(self, despacho_id: UUID) -> list[str]:
        seguimientos = await self._seguimientos.listar_por_despacho(
            despacho_id, incluir_archivados=False,
        )
        # Áreas únicas, en orden de aparición.
        areas_set: set[str] = set()
        areas_lista: list[str] = []
        for s in seguimientos:
            cache = await self._clasificaciones.buscar_por_expediente(
                s.expediente_id
            )
            if cache is None:
                continue
            valor = cache.area.value
            if valor not in areas_set:
                areas_set.add(valor)
                areas_lista.append(valor)
        return areas_lista

    @staticmethod
    def _derivar_aliases(legislador: Legislador | None) -> list[str]:
        if legislador is None:
            return []
        aliases = []
        if legislador.apellido and legislador.nombre:
            aliases.append(f"{legislador.nombre} {legislador.apellido}".strip())
        if legislador.apellido:
            aliases.append(legislador.apellido)
        return aliases
