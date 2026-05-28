# 07 — Inferencia automática de estado parlamentario y caducidad

- **Estado**: en desarrollo
- **Bloque del MVP**: 2 (Aplicación core)
- **Feature en PRODUCT.md**: §"Features en orden de implementación" item 10
- **Depende de**: ADR 0002 + Amendment 1 (campos de caducidad), feat 4 (histórico de trámites), funciones puras `praxis.domain.tramite_historico`.

## Problema

Después del bloque 1, cada `Expediente` viene con `estado=DESCONOCIDO` y campos de caducidad vacíos. La feature 9 (búsqueda y filtrado), la 14 (alertas) y la 18 (calendario de plazos) consumen estos campos. Sin inferencia, todo expediente parece "desconocido" / sin vencimiento, anulando esas features.

## Solución propuesta

Módulo `praxis.domain.inferencia_estado` con funciones puras (sin I/O) que derivan estado y caducidad desde el trámite + fecha de ingreso.

```python
def inferir_estado(*, tramite, fecha_caducidad, hoy) -> EstadoExpediente: ...
def inferir_caducidad(fecha_ingreso, tramite) -> tuple[...]: ...
def inferir_estado_y_caducidad(expediente, *, hoy=None) -> InferenciaResult: ...
```

Caso de uso `EnriquecerExpediente` que aplica la inferencia y muta los campos correspondientes del `Expediente`.

## Heurística

Aprobada por Agustín (dominio: ex-asesor parlamentario) el 2026-05-28.

### Estado (orden de evaluación, primer match gana)

1. Evento con texto que matche regex `\bARCHIV` → `ARCHIVADO`.
2. Evento que matche `\bCADUC` **o** `fecha_caducidad < hoy` → `CADUCO`.
3. Evento `\bSANCION` en HCDN **y** en HSN → `SANCIONADO`.
4. Evento `\bSANCION` solo en HCDN → `MEDIA_SANCION_HCDN`.
5. Evento `\bSANCION` solo en HSN → `MEDIA_SANCION_HSN`.
6. Evento `\bDICTAMEN` → `CON_DICTAMEN`.
7. Evento `\bGIRO\b` o `EN COMISI` → `EN_COMISION`.
8. Al menos un evento con `INGRES` → `INGRESADO`.
9. Default → `DESCONOCIDO`.

El matching es sobre `evento + " " + detalle` upper-cased, regex con `re.IGNORECASE`.

### Caducidad (Ley 13.640)

Si `fecha_ingreso` es `None` → los tres campos quedan `None`.

Si no:
- `fecha_caducidad_original = fecha_ingreso + 730 días` (aproximación de "2 años parlamentarios").
- `prorrogado = True` si hay evento que matche `\b(prorroga|prorrogad)\w*\b` case-insensitive en `evento + detalle`.
- `fecha_caducidad = fecha_caducidad_original + 730 días` si prorrogado, sino igual a original.

### Limitaciones conocidas y aceptadas

Documentadas como caveats en el código y la spec:

- **Años calendario vs parlamentarios**: la Ley 13.640 cuenta "años parlamentarios" (1 marzo a 28/29 febrero). La aproximación de 730 días es ±15 días de error en peores casos. Refinable cuando aparezca un expediente real donde la diferencia importe.
- **Prórroga sin distinguir origen**: en el Senado, la prórroga aplica solo a proyectos venidos de Diputados (art. 1 párr. 4 Ley 13.640). La heurística actual no distingue origen. Refinable.
- **"Sanción" sub-string matching**: la regex `\bSANCION` matchea cualquier evento con la palabra. Casos edge (eventos que mencionan otra sanción de otra ley) podrían producir falsos positivos. Refinable con regex más estricta.

## Criterios de aceptación

- [ ] `praxis.domain.inferencia_estado` con las funciones puras especificadas.
- [ ] `praxis.domain.InferenciaResult` (frozen dataclass) que agrupa los 4 campos derivados.
- [ ] `praxis.application.use_cases.EnriquecerExpediente` que aplica la inferencia al Expediente.
- [ ] Tests unitarios cubriendo cada rama de la heurística de estado.
- [ ] Tests unitarios cubriendo casos de caducidad (sin ingreso, sin prórroga, con prórroga).
- [ ] Tests de integración del use case (muta correctamente el Expediente).
- [ ] Lint + type-check + tests verdes.

## Fuera de alcance

- Refinamiento de regex / matching semántico avanzado.
- Cálculo exacto de año parlamentario.
- Distinción de origen para prórroga en Senado.
- Detección de "sanción definitiva" vs "media sanción explícita" cuando el portal usa lenguaje ambiguo.
- Persistencia del estado inferido. Por ahora se calcula on-demand al enriquecer un Expediente.

## Notas técnicas

- Las funciones aceptan `hoy: date | None` para inyectar la fecha en tests (defaults a `date.today()`).
- Las funciones devuelven valores, no mutan. Solo el use case `EnriquecerExpediente` muta el Expediente.
- El use case devuelve el mismo Expediente (mutado in-place) para facilitar chaining.
