# `praxis.infrastructure.queue`

Adaptador de cola de tareas: Celery sobre Redis.

## Archivos

| Archivo | Rol |
|---|---|
| `celery_app.py` | Instancia y configuración de Celery. |
| `tasks.py` | Tarea `ping` (smoke test). |
| `tasks_bo.py` | Pipeline Boletín Oficial (ingesta nocturna + clasificación + accionabilidad por despacho). |
| `tasks_noticias.py` | Polling de fuentes de noticias + envío de alertas. |
| `tasks_whatsapp.py` | Briefing diario WhatsApp a las 07:00 ART. |
| `tasks_rag.py` | Embeddings semánticos del corpus normativo (sentence-transformers). Aislado en worker para no cargar PyTorch en el API (feat-42.8). |

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

## Worker dedicado para RAG (feat-42.8)

`tasks_rag.embeber_textos_task` carga sentence-transformers (~120MB) y
PyTorch. Si lo corriéramos en el proceso del API, los hilos OpenMP/MKL
de PyTorch chocan con los greenlets de asyncpg y rompen los endpoints
async siguientes con `MissingGreenlet`.

Solución: el API SIEMPRE despacha embeddings a un worker Celery. El
módulo `praxis.infrastructure.rag.embedder_async.embeber_textos_async`
es el único punto de entrada async; internamente hace
`task.delay(...).get()` envuelto en `asyncio.to_thread` para no
bloquear el event loop.

Para correr el worker (recomendado `--pool=solo` para que cargue el
modelo una sola vez):

```bash
uv run celery -A praxis.infrastructure.queue.celery_app worker \
    --loglevel=info --pool=solo
```

En entornos chicos, el mismo worker default consume todas las queues.
Si la carga lo justifica, dedicar uno con `--queues=rag` y otro con
`--queues=celery` para aislar PyTorch del resto.
