# `spike/`

Código exploratorio del ciclo 1. **No es código de producción** — sirve para validar viabilidad de captura desde HCDN y HSN antes de invertir en los adaptadores definitivos en `backend/praxis/infrastructure/`.

## Reglas

- **Throwaway**: cuando los hallazgos pasen a `backend/`, este directorio se archiva (no se mantiene en sync).
- **Standalone**: cada script declara sus dependencias inline con PEP 723. Se corren con `uv run spike/<carpeta>/<script>.py` sin tocar el venv del backend.
- **Respetuoso**: 1 req/segundo por dominio (`time.sleep(1)`), User-Agent honesto `PraxisAsesor/0.1 (+contacto@dominio.com)`, respeto a `robots.txt`.
- **Cacheable**: todo lo bajado se guarda en `_cache/` (gitignored) para iterar sin volver a pegarle al portal.

## Estructura

```
spike/
├── README.md          # este archivo
├── .gitignore         # ignora _cache/
├── _cache/            # HTML cacheado (no versionado)
├── hcdn/
│   └── explore.py     # exploración del portal de Diputados
└── hsn/
    └── explore.py     # exploración del portal de Senado
```

## Cómo correr

Con `uv` instalado (ver [`../backend/README.md`](../backend/README.md) § Bootstrap):

```bash
uv run spike/hcdn/explore.py
uv run spike/hsn/explore.py
```

Salida esperada: lista de expedientes, detalle parseado de algunos, y un resumen de qué campos están accesibles.

## Hallazgos

Se documentan en [`../docs/data-sources.md`](../docs/data-sources.md) a medida que aparecen.
