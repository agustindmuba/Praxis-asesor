# `praxis.infrastructure.queue`

Adaptador de cola de tareas: Celery sobre Redis.

## Archivos

| Archivo | Rol |
|---|---|
| `celery_app.py` | Instancia y configuración de Celery. |
| `tasks.py` | Tareas registradas. Por ahora: `ping`. |

## Cómo probar end-to-end (con uv + docker compose ya andando)

```bash
# Terminal 1: levantar Redis (y Postgres).
docker compose up -d

# Terminal 2: levantar un worker.
uv run celery -A praxis.infrastructure.queue.celery_app worker --loglevel=info

# Terminal 3: encolar la tarea y esperar resultado.
uv run python -c "from praxis.infrastructure.queue.tasks import ping; print(ping.delay().get(timeout=5))"
# debe imprimir: pong
```

## Convenciones

- Toda tarea **tiene un `name=` explícito** prefijado con `praxis.`. Si no, Celery infiere uno basado en el módulo y los renames lo rompen.
- **Sin lógica de negocio dentro de la tarea**: la tarea es un adaptador. Llama a un caso de uso de `praxis.application` y maneja errores/reintentos. Esto preserva el aislamiento hexagonal.
- **Retries con backoff exponencial** para fuentes externas (scrapers): usar `autoretry_for` + `retry_backoff=True`.
- **Idempotencia**: las tareas deben ser seguras de re-ejecutar. Si modifican estado, usar `idempotency_key` o equivalente.
- **Programación periódica**: definir en un `celery_app.conf.beat_schedule` (se agrega cuando aparezca la primera tarea periódica).
