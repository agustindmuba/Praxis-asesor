# 04 — Histórico de trámites por expediente

- **Estado**: en desarrollo
- **Bloque del MVP**: 1 (Fundamentos de datos)
- **Feature en PRODUCT.md**: §"Features en orden de implementación" item 4
- **Depende de**: ADR 0002 + Amendment 1 (`TramiteEvento`), features 1-3 (scrapers + use case).

## Problema

Los adaptadores HCDN y HSN ya producen `list[TramiteEvento]` como parte del `Expediente`. Falta el **soporte de dominio** para operar sobre esa lista de manera consistente:

- **Re-ingesta**: cuando volvemos a scrapear el mismo expediente, hay que **mergear** los nuevos eventos con los ya conocidos, sin duplicar.
- **Consultas**: filtrar por cámara, por rango de fechas, traer los últimos N.
- **Validación**: detectar inconsistencias como duplicados internos o fechas no monotónicas.

Sin estas funciones, cada caso de uso futuro reinventaría la lógica.

## Solución propuesta

Módulo `praxis.domain.tramite_historico` con funciones puras (sin I/O, sin estado). Operan sobre `list[TramiteEvento]` y devuelven nuevas listas.

Funciones:
- `merge_tramite(existente, nuevo)`: une dos listas sin duplicar. Clave de duplicado: `(fecha, evento, detalle, camara)`. Resultado ordenado cronológicamente.
- `filter_by_camara(tramite, camara)`: subset de eventos por cámara.
- `filter_by_rango(tramite, desde, hasta)`: subset por rango de fechas (incluye bordes). Eventos sin fecha se incluyen solo si `desde` y `hasta` son ambos `None`.
- `eventos_recientes(tramite, n)`: últimos N eventos cronológicamente (sin fecha al final, ignorados si n no alcanza).
- `validar_consistencia(tramite)`: devuelve lista de strings con problemas detectados (duplicados exactos, etc.). Lista vacía = OK.

## Criterios de aceptación

- [ ] Existe `praxis.domain.tramite_historico` con las 5 funciones puras.
- [ ] `merge_tramite` no duplica eventos idénticos y preserva orden cronológico.
- [ ] Filtros devuelven nuevas listas; nunca mutan inputs.
- [ ] `validar_consistencia` detecta duplicados y eventos con fecha cero/inválida.
- [ ] Tests unitarios por función con casos chicos sintéticos.
- [ ] Lint + type-check + tests verdes.

## Fuera de alcance

- **Persistencia**: las funciones operan sobre listas en memoria. Cuando llegue DB, el repositorio usará estas funciones para reconciliar lo persistido con lo nuevo.
- **Detección semántica de eventos repetidos** (ej. dos "GIRO A COMISION" con texto similar pero levemente distinto): por ahora la igualdad es estructural exacta, no fuzzy.
- **Inferencia de estado desde trámite**: feature 10 (PRODUCT.md), no entra acá.

## Notas técnicas

- Las funciones reciben/devuelven `list[TramiteEvento]` (no tuplas, no generators). Para listas grandes se puede revisitar, pero los expedientes reales rara vez pasan de 20-30 eventos.
- `merge_tramite` usa un `set` de claves para deduplicar. La clave es una tupla `(fecha, evento, detalle, camara)`. `fuente` NO entra en la clave: si el mismo evento fue scrapeado tanto desde HCDN como derivado en HSN, son el mismo evento.
- Orden cronológico: eventos sin fecha al final, en orden de inserción.
