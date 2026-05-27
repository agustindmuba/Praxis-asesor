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

(Vacío. El primer ADR se abrirá cuando empiece el ciclo 1.)
