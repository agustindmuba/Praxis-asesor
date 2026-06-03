# Architecture Decision Records (ADR)

Cada decisión arquitectónica significativa de Praxis Asesor vive acá como un archivo numerado.

## Formato

Archivo: `NNNN-titulo-en-kebab-case.md` (NNNN = número secuencial con padding a 4 dígitos).

Estructura mínima de cada ADR:

```markdown
# NNNN — Título de la decisión

- **Estado**: propuesta | aceptada | superseded por ADR-NNNN | rechazada
- **Fecha**: AAAA-MM-DD
- **Autores**: nombres

## Contexto

Qué problema o disyuntiva estamos resolviendo. Qué restricciones hay.

## Decisión

Qué decidimos hacer.

## Alternativas consideradas

Otras opciones que evaluamos y por qué las descartamos.

## Consecuencias

Qué cambia en el código, en el equipo, en la operación. Riesgos y trade-offs aceptados.
```

## Cuándo abrir un ADR

- Cambios al modelo de datos central.
- Reemplazo o agregado de servicios externos con impacto cross-cutting.
- Cambios de framework, lenguaje o paradigma de un módulo.
- Cualquier cosa que un dev nuevo, leyendo el código en 6 meses, debería poder reconstruir como decisión deliberada.

## ADRs vigentes

- [`0001-stack-inicial.md`](0001-stack-inicial.md) — Stack inicial de Praxis Asesor (aceptada, 2026-05-27).
- [`0002-modelo-expediente.md`](0002-modelo-expediente.md) — Modelo de Expediente, Trámite y Firmante (aceptada, 2026-05-27, con Amendment 1 del mismo día).
- [`0003-persistencia.md`](0003-persistencia.md) — Persistencia con SQLAlchemy 2.0 async + multi-tenancy (aceptada, 2026-05-28).
- [`0006-modelo-bo-noticias-menciones-whatsapp.md`](0006-modelo-bo-noticias-menciones-whatsapp.md) — Modelo de datos BO, Noticias, Menciones y WhatsApp (propuesta, 2026-06-02).
- [`0007-politica-scraping-respetuoso.md`](0007-politica-scraping-respetuoso.md) — Política de scraping respetuoso para BO y medios (propuesta, 2026-06-02).
- [`0008-integracion-whatsapp-cloud-api.md`](0008-integracion-whatsapp-cloud-api.md) — Integración WhatsApp Cloud API directo (sin BSP) (propuesta, 2026-06-02).
- [`0009-anti-flood-alertas-menciones.md`](0009-anti-flood-alertas-menciones.md) — Anti-flood y agrupamiento de alertas de menciones (propuesta, 2026-06-02).
