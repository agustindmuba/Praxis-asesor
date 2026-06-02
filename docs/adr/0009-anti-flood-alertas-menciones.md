# 0009 — Anti-flood y agrupamiento de alertas de menciones

- **Estado**: propuesta
- **Fecha**: 2026-06-02
- **Autores**: Agustín DM
- **Supersede a**: —
- **Superseded por**: —
- **Specs que aterriza**: 16 (alertas de menciones).

## Contexto

Las alertas de menciones del legislador van por WhatsApp en tiempo real
(spec 16). Para un legislador con poca exposición mediática, el flujo es
manejable: 0-2 alertas por día. Pero hay escenarios reales donde la
exposición se dispara:

- El legislador interviene en un debate televisivo y los portales
  políticos lo levantan en cascada (20+ menciones en 1 hora).
- Una crisis política toca al bloque y todos los medios levantan al
  legislador como vocero.
- Un dictamen polémico del despacho hace ruido.

Sin anti-flood, el legislador recibiría 20 WhatsApps en una hora — UX
pésima, riesgo de opt-out y de quemar el número Meta de Praxis. Pero
**ninguna alerta puede quedar sin notificar**: hay menciones puntuales
que disparan acción inmediata (rectificar declaración, llamar al medio).

El owner ya decidió (D8): **3 alertas individuales por hora + agrupar
el resto con buffer diferido de 5 min**. Este ADR formaliza el
algoritmo, su implementación con Redis y los invariantes que tiene que
preservar.

Restricciones que la decisión debe respetar:

1. **Ninguna mención queda sin notificar**: o cae en individual, o en
   agrupada. Nunca se pierde.
2. **Idempotencia**: si una mención dispara el job dos veces (retry
   Celery), no genera dos alertas.
3. **Por destinatario**: la cuota es por destinatario individual, no
   por despacho. Distintos destinatarios del mismo despacho pueden
   recibir alertas en paralelo si están en config para esa mención.
4. **Sin bloqueo de la pipeline**: la decisión "individual vs.
   agrupada" no puede bloquear el procesamiento de otros artículos.
5. **Observable**: el operador puede ver qué está en buffer y por
   cuánto tiempo.

## Decisión

### Algoritmo (pseudocódigo)

```
EnviarAlertaMencion.execute(mencion_id, destinatario_id):

    mencion = MencionRepository.buscar_por_id(mencion_id)
    if mencion.notificada: return       # idempotente

    key = f"flood:{destinatario_id}"
    bucket = f"flood:bucket:{destinatario_id}"

    # 1. ¿Cuántas alertas individuales ya se mandaron a este
    #    destinatario en la ventana móvil de los últimos 60 min?
    enviadas_en_ventana = Redis.zcount(
        key,
        min=now() - 60min,
        max=now(),
    )

    if enviadas_en_ventana < 3:
        # Espacio en la cuota — alerta individual
        await MessagingProvider.enviar_plantilla(
            destinatario, "praxis_mencion_individual_v1", params={...},
            correlativo_id=mencion.id, tipo="mencion_individual",
        )
        Redis.zadd(key, score=now().timestamp(), member=mencion_id)
        Redis.expire(key, 65min)
        MencionRepository.marcar_notificada(mencion_id)
        return

    # 2. Sin cuota: cae al buffer agrupado
    Redis.sadd(bucket, mencion_id)
    Redis.expire(bucket, 65min)

    # 3. ¿Hay job de envío de agrupada ya programado?
    job_key = f"flood:job:{destinatario_id}"
    if not Redis.exists(job_key):
        # Programar el job UNO solo, para 5 min en el futuro
        Redis.set(job_key, "scheduled", ex=6min)
        EnviarAlertaAgrupada.delay(
            destinatario_id, eta=now() + 5min,
        )
```

```
EnviarAlertaAgrupada.execute(destinatario_id):

    bucket = f"flood:bucket:{destinatario_id}"
    job_key = f"flood:job:{destinatario_id}"

    mencion_ids = Redis.smembers(bucket)
    if not mencion_ids:
        Redis.delete(job_key)
        return                          # nada que agrupar, no-op

    # Snapshot atómico:
    Redis.delete(bucket)
    Redis.delete(job_key)

    menciones = MencionRepository.buscar_por_ids(mencion_ids)

    # Componer params de la plantilla agrupada
    params = {
        "1": str(len(menciones)),
        "2": distribuir_tono(menciones),   # "3 negativas · 2 neutras · 1 positiva"
        "3": top_fuentes(menciones, n=3),  # "La Nación, Infobae, La Política Online"
    }

    await MessagingProvider.enviar_plantilla(
        destinatario, "praxis_mencion_agrupada_v1", params=params,
        correlativo_id=None, tipo="mencion_agrupada",
    )

    for m in menciones:
        MencionRepository.marcar_notificada(m.id)

    AlertaMencionEnviadaRepository.crear(
        destinatario_id=destinatario_id,
        tipo="agrupada",
        menciones_ids=list(mencion_ids),
        ...,
    )
```

### Invariantes que el algoritmo garantiza

1. **Nunca > 3 individuales por hora por destinatario.** La ventana
   móvil de 60 min sobre `zset` lo asegura.
2. **Toda mención termina notificada.** O entra en individual, o en
   agrupada. Nunca queda en buffer indefinidamente porque
   `Redis.expire(bucket, 65min)` es el techo absoluto: si el job
   Celery falla repetidamente, igual hay una ventana de 5 min después
   de que se llene la cuota; pasados 60 min vuelve a haber cuota y se
   procesan menciones nuevas como individuales.
3. **Idempotencia**: `mencion.notificada` bloquea reintentos del job
   sobre la misma mención.
4. **Una sola alerta agrupada por ventana**: `flood:job:{...}` previene
   que múltiples menciones en el mismo minuto programen N jobs.
5. **Ninguna alerta agrupada vacía**: si el bucket está vacío cuando
   dispara el job, se sale como no-op.

### Estructura de keys Redis

```
flood:{destinatario_id}            ZSET    enviadas_en_ventana (score=ts, member=mencion_id)
flood:bucket:{destinatario_id}     SET     menciones_pending_de_agrupar
flood:job:{destinatario_id}        STRING  marker de job programado, TTL 6 min
```

TTLs:
- `flood:{...}`: 65 min (deja margen al borde de la ventana móvil).
- `flood:bucket:{...}`: 65 min (techo absoluto si todo falla).
- `flood:job:{...}`: 6 min (1 min de margen tras el ETA).

### Configurabilidad

Los dos parámetros viven en `Settings`:

```python
class Settings(BaseSettings):
    ...
    flood_cuota_individuales_por_hora: int = 3
    flood_delay_agrupada_segundos: int = 300
```

Permitir tunearlos por env si en producción se observa otro comportamiento
óptimo, sin tocar código.

### Observabilidad

Dashboard interno (`/configuracion/envios` u otra ruta admin) muestra
para un destinatario:

- Alertas individuales en la última hora (gráfico de barras).
- Si hay buffer activo: cuántas menciones espera y cuánto al disparo.
- Histórico de agrupadas (cuándo se mandaron, cuántas menciones
  juntaban).

Métricas Prometheus (opcional v2):

```
praxis_flood_individuales_total{despacho_id,destinatario_id}
praxis_flood_agrupadas_total{despacho_id,destinatario_id}
praxis_flood_buffer_size{destinatario_id}
```

### Edge cases manejados

#### Mismo artículo, dos legisladores monitoreados, dos destinatarios

Cada `EnviarAlertaMencion` job es por `(mencion_id, destinatario_id)`.
La cuota es por destinatario. Funciona naturalmente sin colisión.

#### Mención que llega EXACTAMENTE en el minuto 60

Ventana móvil basada en `now() - 60min` lo trata correctamente: la
mención de hace 60 min y 1 segundo ya no cuenta.

#### Job de agrupada falla y se reintenta

`MencionRepository.marcar_notificada` se ejecuta solo si el envío fue
exitoso. Si falla, el bucket sigue vivo (TTL 65 min) y el siguiente
intento del scheduler lo recoge. Mensaje doble se previene porque el
job consume el bucket atómicamente.

#### Redis cae

El consumidor del envío falla cleanly. El job se reintenta vía Celery
retry policy. Si Redis está caído de verdad, el sistema empieza a
acumular alertas en cola Celery — eventualmente backpressure que llega
hasta el detector de menciones. Aceptable: Redis es crítico v1 y el
deployment lo trata como tal.

#### Mensajería de Meta cae

`MessagingProvider.enviar_plantilla` falla. El job se reintenta. Si
falla N veces, el envío queda `estado="fallo"` en
`EnvioWhatsApp`; la mención no se marca notificada → reintenta más
tarde. Si la falla persiste (cuota Meta, plantilla pausada),
intervención manual.

#### Destinatario hace opt-out durante el delay de 5 min

`MessagingProvider.enviar_plantilla` valida pre-envío:
`if destinatario.opt_out_en: raise OptOutError`. El job de agrupada
falla, las menciones del bucket NO se marcan notificadas. No hay
intento de reenvío automático: el buffer expira en 65 min y se
descarta. El histórico de menciones en la app igual está disponible.

## Alternativas consideradas

### Cuota fija sin agrupamiento (sólo descartar excedente)

Idea: 3/hora, las siguientes se descartan (sólo visibles en
`/menciones`). Descartado:

- Rompe la promesa "ninguna alerta queda sin notificar".
- Para un escenario de crisis, exactamente las menciones más urgentes
  se perderían.

### Agrupamiento inmediato (sin delay de 5 min)

Idea: al exceder cuota, enviar 1 alerta agrupada con 1 sola mención.
Descartado:

- Pierde el sentido: agrupar 1 mención no aporta. El delay permite
  consolidar varias menciones en una sola alerta.
- 5 min es un trade-off razonable entre inmediatez y consolidación.

### Quotas dinámicas (más cuota durante "rush", menos en off-hours)

Descartado por sobre-ingeniería para v1. Reabrir si la operación
muestra que el patrón temporal lo justifica.

### Anti-flood global a nivel de WABA, no por destinatario

Idea: cap total de mensajes/hora desde el número Praxis para no
quemar el número. Descartado porque ya está cubierto por el cap
mensual por despacho (D14, ADR 0008) y por la calidad de
contenido (utility, no marketing) que Meta mide.

### Persistir buffer en Postgres en vez de Redis

Idea: tabla `mencion_buffer` con cron periódico. Descartado:

- Postgres no es óptimo para TTL automático.
- Latencia para el lookup "¿cuántas envié en la última hora?" es
  peor.
- Redis ya está deployed para cache HTTP y mantiene patrón de uso
  consistente.

## Consecuencias

### Positivas

- Garantía dura "nunca > 3/hora individuales" sin perder menciones.
- Ventana móvil más justa que ventana fija (no hay "se reinicia a la
  hora").
- Algoritmo barato: pocas keys Redis, lookups O(log N) en `zcount`.
- Observable y configurable.

### Negativas / Trade-offs

- **Dependencia de Redis** para el path crítico de alertas. Si Redis
  cae, alertas se pausan. Aceptable: ya es dependencia para HTTP cache
  y para Celery broker.
- **5 min de retraso** en escenarios de flood. Aceptable para UX
  pero NO para crisis aguda. Si el feedback de Juliano dice que es
  mucho, bajar a 3 min vía env var.
- **Complejidad de testing**: tests sintéticos con tiempo simulado
  necesarios. Existe patrón con `freezegun` en otros lados del repo,
  reutilizable.

### Operación

- Runbook: cómo limpiar buffer manual si un test queda colgado en dev.
- Alerta interna si Redis no responde durante > 2 min.
- En `/configuracion/envios` el admin del despacho ve los próximos
  agrupados pendientes.

## Trabajo derivado

- feat/40.5: `EnviarAlertaMencion` + `EnviarAlertaAgrupada` casos de
  uso con esta lógica.
- Tests unitarios con `freezegun` para simular ventana móvil y
  validar la distribución exacta individual/agrupada en escenarios
  sintéticos.
- Métricas + dashboard observabilidad (opcional v2).
