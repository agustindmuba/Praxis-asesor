# RUNBOOK Praxis Asesor

Operativa diaria del sistema. Si algo no anda, este es el primer lugar para mirar.

---

## Stack en una imagen

```
┌────────────────────┐    ┌────────────────────┐    ┌────────────────────┐
│  Postgres + pgvec  │    │  Redis (broker)    │    │  Anthropic API     │
│  :5432             │    │  :6379             │    │  (paga, cap $5/mo) │
└────────┬───────────┘    └─────────┬──────────┘    └─────────┬──────────┘
         │                          │                          │
         │ ┌────────────────────────┴────────────┐             │
         │ │                                     │             │
┌────────┴─┴─────────┐   ┌────────────────┐   ┌─┴─────────────┐│
│ FastAPI            │   │ Celery worker  │   │ Celery beat   ││
│ :8007              │   │ (pool=solo)    │   │ (scheduler)   ││
│ uvicorn            │   │                │   │               ││
└────────┬───────────┘   └────────────────┘   └───────────────┘│
         │                                                     │
┌────────┴───────────┐                                         │
│ Next.js 15         │←────────────── Anthropic SDK ───────────┘
│ :3001              │                (worker + API la usan)
└────────────────────┘
```

---

## Qué tiene que estar corriendo siempre

| Proceso | Cómo se arranca | Si muere... |
|---|---|---|
| **Postgres + Redis** | `docker compose up -d` (en raíz del repo) | nada funciona |
| **FastAPI backend** | `cd backend && unset ANTHROPIC_API_KEY ; PRAXIS_AUTH_PROVIDER=dev uv run uvicorn praxis.api.main:app --port 8007 --reload` | la app web no responde |
| **Next.js frontend** | `cd frontend && npm run dev` | la app web no carga |
| **Celery worker** | `cd backend && unset ANTHROPIC_API_KEY ; uv run celery -A praxis.infrastructure.queue.celery_app worker --pool=solo --loglevel=info` | nada async se procesa (BO, noticias, WhatsApp, RAG) |
| **Celery beat** | `cd backend && uv run celery -A praxis.infrastructure.queue.celery_app beat --loglevel=info` | las tasks programadas (BO 5:30 AM, briefing 8 AM, etc.) NO disparan |

> `unset ANTHROPIC_API_KEY` antes de cada comando del backend: si el shell tiene la var vacía, **pisa el `.env`** y rompe el LLM real.

---

## Schedule programado (hora Argentina)

| Hora ART | Task | Qué hace |
|---|---|---|
| **5:30 AM** | `praxis.bo.ingestar_diario` | Baja PDFs del Boletín Oficial del día |
| **6:00 AM** | `praxis.bo.clasificar_pendientes` | Clasifica con LLM cada norma BO |
| **7:00 AM** | `praxis.bo.evaluar_accionables_por_despacho` | Calcula top-N normas accionables por despacho |
| **8:00 AM** | `praxis.whatsapp.enviar_briefings_diarios` | Manda WhatsApp con resumen BO + noticias |
| **continuo** | `praxis.noticias.procesar_fuentes` | Cada 15 min: scrapea RSS/sitemaps de medios |
| **continuo** | `praxis.noticias.enviar_alertas_pendientes` | Cada 10 min: WhatsApp por mención al legislador |
| **mar/jue 9-19** | `praxis.hcdn.detectar_od` | Cada 1h: detecta órdenes del día nuevas en HCDN |
| **18:00 PM** | `praxis.whatsapp.enviar_avisos_proxima_sesion` | Si mañana hay sesión, manda WhatsApp con link al briefing |

---

## Comandos de smoke (verificar que algo funciona)

### Ping worker
```bash
cd backend && uv run python -c "from praxis.infrastructure.queue.tasks import ping; print(ping.delay().get(timeout=5))"
# debe imprimir: pong
```

### Disparar task BO manualmente
```bash
cd backend && uv run python -c "
from praxis.infrastructure.queue.tasks_bo import ingestar_diario_task
print(ingestar_diario_task.delay().get(timeout=120))
"
```

### Disparar detector de OD HCDN
```bash
cd backend && uv run python -c "
from praxis.infrastructure.queue.tasks_hcdn import detectar_od_task
print(detectar_od_task.delay(2).get(timeout=120))
"
```

---

## Levantar todo desde cero

1. **Containers** (10 seg):
   ```bash
   docker compose up -d
   ```

2. **4 terminales separadas en `praxis-asesor/`:**
   - Terminal 1 — Backend
     ```
     cd backend
     unset ANTHROPIC_API_KEY
     PRAXIS_AUTH_PROVIDER=dev uv run uvicorn praxis.api.main:app --port 8007 --reload
     ```
   - Terminal 2 — Frontend
     ```
     cd frontend
     npm run dev
     ```
   - Terminal 3 — Celery worker
     ```
     cd backend
     unset ANTHROPIC_API_KEY
     uv run celery -A praxis.infrastructure.queue.celery_app worker --pool=solo --loglevel=info
     ```
   - Terminal 4 — Celery beat
     ```
     cd backend
     uv run celery -A praxis.infrastructure.queue.celery_app beat --loglevel=info
     ```

3. Abrir `http://localhost:3001/dev-login` y entrar.

---

## Producción real (cuando llegue ese momento)

Hoy los procesos viven en tu terminal. Para que sobrevivan a reboots:

- **Worker + beat como Windows Service** (con `nssm` o equivalente)
- **O migración a Docker** del worker + beat (definir un service en `docker-compose.yml`)
- **O hosting** (Railway / Fly / VM con systemd)

Sin esto, si tu PC se reinicia, mañana 8 AM no llega briefing.

---

## Troubleshooting

| Síntoma | Causa probable | Fix |
|---|---|---|
| `/dashboard` redirige a `/dev-login` | Sesión expirada | re-login |
| `/dashboard` redirige a `/onboarding` | Despacho sin `legislador_titular_slug` | completar onboarding |
| Mensaje "MissingGreenlet" | PyTorch cargado en el API | Reiniciar el backend (worker debería estar separado, ver feat-42.8) |
| Task ejecuta in-process pero no via worker | Worker no arrancado | levantar Terminal 3 |
| Beat schedule no dispara | Beat no arrancado | levantar Terminal 4 |
| `praxis_briefing_diario` template not found | Meta no aprobó plantilla | esperar 24-72h o crear manual en Meta |
| Foto del legislador no aparece | No seteada vía `PATCH /legislador-titular/foto` | usar el form en `/configuracion` cuando esté listo (pendiente) |

---

## Variables de entorno críticas (en `backend/.env`)

- `DATABASE_URL`: postgres async
- `REDIS_URL`: redis del docker compose
- `ANTHROPIC_API_KEY`: ⚠️ rotar antes de cerrar sesión si la expusiste
- `META_WHATSAPP_TOKEN`: token sandbox de Meta (caduca cada 24h, regenerar)
- `META_WHATSAPP_PHONE_NUMBER_ID`: ID del número de WhatsApp configurado
- `CLERK_*`: para auth real (en dev no se usan)
