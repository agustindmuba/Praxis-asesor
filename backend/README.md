# backend

Servicio Python del Praxis Asesor. Arquitectura hexagonal (ver [`../ARCHITECTURE.md`](../ARCHITECTURE.md)).

## Estructura prevista

```
backend/
├── praxis/
│   ├── domain/         # entidades, value objects, reglas puras
│   ├── application/    # casos de uso, puertos
│   ├── infrastructure/ # adaptadores (DB, scrapers, email, ...)
│   ├── api/            # endpoints FastAPI
│   └── config.py
├── tests/
├── alembic/
└── pyproject.toml
```

## Estado

Sin scaffolding aún. Se materializa en el ciclo 1.
