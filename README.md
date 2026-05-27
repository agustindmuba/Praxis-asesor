# Praxis Asesor

> Sistema operativo del despacho parlamentario. Para asesores del Congreso Nacional Argentino.

## Documentación clave

- [`CLAUDE.md`](./CLAUDE.md) — memoria del proyecto para Claude Code (leer al inicio de cada sesión).
- [`PRODUCT.md`](./PRODUCT.md) — visión de producto, alcance del MVP, roadmap.
- [`ARCHITECTURE.md`](./ARCHITECTURE.md) — decisiones técnicas, stack, modelo de datos.
- `docs/adr/` — Architecture Decision Records.
- `docs/glosario.md` — términos parlamentarios.
- `docs/data-sources.md` — documentación de fuentes de datos.

## Estado

🚧 Ciclo 0: setup. Próximo ciclo: scaffolding + scraping exploratorio.

## Workflow con Claude Code

1. Al iniciar una sesión, asegurarse de que Claude Code lea `CLAUDE.md`.
2. Antes de cada feature, revisar `PRODUCT.md` y crear/leer la spec correspondiente.
3. Cambios de modelo de datos → ADR primero, código después.
4. PR a `develop`. Nada de push directo a `main`.

## Licencia

Propietario. Todos los derechos reservados.
