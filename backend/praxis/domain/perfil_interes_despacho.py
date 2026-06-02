"""Perfil de interés del despacho — qué temas, comisiones, distritos y
aliases del legislador definen "lo que le importa" a un despacho.

Entidad compartida entre specs 15 (BO), 16 (Noticias + menciones) y 17
(WhatsApp). Materializa la decisión D1 (sembrado híbrido + editable).

Estrategia de sembrado:

- Al onboarding o al recalcular, se siembra desde:
  - `comisiones_legislador`: comisiones del legislador titular (cuando
    esa relación esté disponible — hoy queda vacía y se completa
    manualmente, ver `SembrarPerfilInteres`).
  - `areas_tematicas`: áreas de los expedientes que el despacho sigue
    (vía `ExpedienteAreaTematica` ya cacheado).
  - `distritos_observados`: distrito del legislador titular si hay.
  - `aliases_legislador`: nombre completo + apellido del titular.

- El asesor puede editar libremente desde `/configuracion`. Tras
  edición manual, los re-sembrados respetan los valores manuales
  salvo que se pase `sobreescribir_edicion_manual=True` al caso de uso.

- `sembrado_at` y `editado_at` permiten saber qué versión es más
  reciente y decidir si re-sembrar.

Ver `docs/specs/15-resumen-bo-accionable.md` §"Algoritmos · Accionabilidad
por despacho" y ADR 0006 §"Compartida — PerfilInteresDespacho".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from praxis.domain.area_tematica import AreaTematica


@dataclass(slots=True)
class PerfilInteresDespacho:
    """Perfil declarativo del despacho para evaluar accionabilidad/relevancia.

    Mutable: editable desde la UI. Una sola fila por despacho (PK =
    `despacho_id`). Cuando se re-siembra, se hace UPSERT.

    Invariantes:
    - `areas_tematicas` contiene strings que son `AreaTematica.value`
      válidos. La validación se ejecuta en `__post_init__`.
    - Los demás listados son strings libres, deduplicados y stripeados
      antes de persistir.
    - `aliases_legislador` debe tener al menos 1 elemento si se quiere
      que el detector de menciones encuentre algo. Vacío = el despacho
      no monitorea menciones (válido v1).
    """

    despacho_id: UUID
    areas_tematicas: list[str] = field(default_factory=list)
    comisiones_legislador: list[str] = field(default_factory=list)
    distritos_observados: list[str] = field(default_factory=list)
    aliases_legislador: list[str] = field(default_factory=list)
    sembrado_at: datetime | None = None
    editado_at: datetime | None = None
    actualizado_en: datetime | None = None

    def __post_init__(self) -> None:
        # Normalizar listas: strip + dedup conservando orden de aparición.
        self.areas_tematicas = _dedup_strip(self.areas_tematicas)
        self.comisiones_legislador = _dedup_strip(self.comisiones_legislador)
        self.distritos_observados = _dedup_strip(self.distritos_observados)
        self.aliases_legislador = _dedup_strip(self.aliases_legislador)

        # Validar áreas contra el enum conocido.
        validas = {a.value for a in AreaTematica}
        invalidas = [a for a in self.areas_tematicas if a not in validas]
        if invalidas:
            raise ValueError(
                "PerfilInteresDespacho.areas_tematicas contiene áreas "
                f"desconocidas: {invalidas}. Áreas válidas: {sorted(validas)}"
            )

    @property
    def fue_editado_despues_de_sembrar(self) -> bool:
        """True si el perfil fue editado manualmente después del último
        sembrado automático.

        Cuando es True, `SembrarPerfilInteres` respeta la edición salvo
        que el caller pase `sobreescribir_edicion_manual=True`.
        """
        if self.editado_at is None:
            return False
        if self.sembrado_at is None:
            # Hay edición pero nunca se sembró → respetar la edición.
            return True
        return self.editado_at > self.sembrado_at


def _dedup_strip(items: list[str]) -> list[str]:
    """Strip + dedup conservando el orden de la primera aparición."""
    visto: set[str] = set()
    resultado: list[str] = []
    for item in items:
        clean = item.strip()
        if not clean or clean in visto:
            continue
        visto.add(clean)
        resultado.append(clean)
    return resultado
