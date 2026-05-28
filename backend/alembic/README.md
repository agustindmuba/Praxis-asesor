# `backend/alembic`

Migraciones de la base de datos. Stack: Alembic 1.13+ sobre SQLAlchemy 2.0 async.

## Estructura

```
alembic/
├── env.py             # configuración del entorno (async-aware)
├── script.py.mako     # template para nuevas migraciones
├── versions/          # archivos de migración
└── README.md
```

## Comandos habituales (desde `backend/`)

| Acción | Comando |
|---|---|
| Generar nueva migración vacía | `uv run alembic revision -m "descripción corta"` |
| Generar migración autogenerada | `uv run alembic revision --autogenerate -m "descripción"` |
| Aplicar todas pendientes | `uv run alembic upgrade head` |
| Revertir una | `uv run alembic downgrade -1` |
| Ver historial | `uv run alembic history` |
| Ver revisión actual | `uv run alembic current` |

## Convenciones

- **Nombres de archivo**: `YYYYMMDD_HHMM_slug.py` (ver `alembic.ini` `file_template`).
- **`target_metadata`** se setea en `env.py` cuando exista un `Base` con modelos declarados.
- **Migraciones de schema** y **migraciones de datos** se hacen en archivos separados, no mezclar.
- Toda migración tiene `upgrade()` Y `downgrade()` funcionales; sin migraciones one-way salvo justificación.
- Hook post-write: `ruff format` se aplica automáticamente a archivos generados.

## URL de DB

Se inyecta desde `praxis.config.get_settings().database_url` en `env.py`. El valor de `sqlalchemy.url` en `alembic.ini` es solo un fallback.
