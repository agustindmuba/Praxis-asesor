# 0008 — Integración WhatsApp Cloud API directo (sin BSP)

- **Estado**: propuesta
- **Fecha**: 2026-06-02
- **Autores**: Agustín DM
- **Supersede a**: —
- **Superseded por**: —
- **Specs que aterriza**: 17 (canal WhatsApp).

## Contexto

WhatsApp aparece como el canal central de notificación proactiva de
Praxis (briefing diario en spec 15+16, alertas de menciones en spec 16,
y consumidores futuros). Hay dos formas de integrar:

1. **WhatsApp Cloud API directo** (Meta): provee la API REST oficial,
   recibimos webhooks de estado de entrega, gestionamos la cuenta
   WhatsApp Business y las plantillas directamente.
2. **Business Solution Provider (BSP)**: Twilio, 360Dialog, Infobip,
   Sinch, MessageBird, etc. Proveen una capa sobre la API de Meta con
   herramientas adicionales (queues, plantillas managed, dashboards,
   billing en una única factura, soporte humano).

El owner ya decidió **Meta directo**. Este ADR documenta el razonamiento
y las consecuencias técnicas y operativas.

Restricciones que la decisión tiene que respetar:

1. **Compliance Meta**: opt-in explícito, plantillas pre-aprobadas para
   mensajes proactivos fuera de ventana 24h, manejo limpio de STOP.
2. **Tenancy**: cada `EnvioWhatsApp` pertenece a un despacho. Un bug
   nunca debe disparar un mensaje al destinatario equivocado.
3. **Auditoría**: cada envío persiste con `message_id_meta`. El
   destinatario o el legislador puede pedir el log.
4. **Cap de gasto**: 1.500 mensajes/mes/despacho (D14). Hay que
   medirlo y frenar al llegar al cap.
5. **Idempotencia**: webhooks de Meta pueden llegar duplicados; el
   handler tiene que tolerar.

## Decisión

### Stack

- **WhatsApp Business Account (WABA)** única para Praxis, asociada a un
  **número de teléfono Meta verificado** (D15 → un número Praxis).
- **WhatsApp Cloud API** (`https://graph.facebook.com/v19.0`) como
  endpoint de envío.
- **Webhooks de Meta** apuntando a `https://api.praxisasesor.com/webhooks/meta/*`.
- **App Meta dedicada** con permisos `whatsapp_business_messaging` y
  `whatsapp_business_management`.
- **Token de acceso de larga duración** (system user token, ~60 días
  + auto-rotación).

### Configuración (variables de entorno)

```
META_WHATSAPP_PHONE_NUMBER_ID=...     # el que Meta da al verificar el número
META_WHATSAPP_TOKEN=...               # system user token
META_BUSINESS_ACCOUNT_ID=...
META_VERIFY_TOKEN=...                 # token aleatorio que Praxis genera, sirve para el handshake del webhook
META_APP_SECRET=...                   # para verificar HMAC X-Hub-Signature-256
```

`Settings` (`praxis.config`) los expone como `meta_*` y arroja
`ConfigError` si están vacíos cuando `messaging_enabled=true`. En dev,
`messaging_enabled=false` mantiene la app corriendo con
`FakeMessagingProvider` (logs en STDOUT, no envíos reales).

### Adaptador `WhatsAppCloudApiProvider`

```python
class MessagingProvider(ABC):
    async def enviar_plantilla(
        self, *,
        destinatario: Destinatario,
        plantilla: PlantillaWhatsApp,
        params: dict[str, str],
        correlativo_id: UUID | None,
        tipo: str,
    ) -> EnvioWhatsApp: ...

class WhatsAppCloudApiProvider(MessagingProvider):
    async def enviar_plantilla(...) -> EnvioWhatsApp:
        # 1. Validaciones de pre-envío:
        if not destinatario.activo: raise OptOutError(...)
        if destinatario.opt_out_en: raise OptOutError(...)
        if cap_excedido(destinatario.despacho_id): raise CapExcedidoError(...)
        # 2. Persistir EnvioWhatsApp(estado="pendiente")
        # 3. POST a Meta /messages con plantilla + params
        # 4. Actualizar estado="enviado" + message_id_meta
        # 5. Si Meta rechaza (cuota, plantilla pausada, número inválido):
        #    actualizar estado="fallo" + error, raise.
```

### Plantillas

Las plantillas v1 (D11) están documentadas en spec 17:

1. `praxis_briefing_diario_v1` — utility, es_AR, params: fecha + cuerpo.
2. `praxis_mencion_individual_v1` — utility, es_AR, params: fuente, hora, tono, alcance, titulo.
3. `praxis_mencion_agrupada_v1` — utility, es_AR, params: cantidad, distribucion, top_fuentes.

Workflow:

1. Definir el contenido (texto + botones) en
   `praxis/infrastructure/messaging/plantillas/*.json`.
2. Script `scripts/registrar_plantillas_meta.py` las sube a la WABA via
   Graph API y queda en estado `pendiente_aprobacion`.
3. Tras aprobación Meta (24-48h), se cambia a `aprobada` y queda
   utilizable. El estado se sincroniza con un webhook
   `template_status_update` de Meta.

Una plantilla `marketing` o un cambio mayor de contenido requiere
re-aprobación.

### Webhooks

Dos endpoints públicos en FastAPI:

#### `GET /webhooks/meta/messages-status`

Verificación inicial (handshake de Meta).

```python
@router.get("/webhooks/meta/messages-status")
async def verify_webhook(hub_mode: str, hub_verify_token: str, hub_challenge: str):
    if hub_mode == "subscribe" and hub_verify_token == settings.meta_verify_token:
        return Response(hub_challenge, media_type="text/plain")
    raise HTTPException(403)
```

#### `POST /webhooks/meta/messages-status`

Recibe estados (`sent`, `delivered`, `read`, `failed`).

```python
@router.post("/webhooks/meta/messages-status")
async def messages_status(request: Request):
    body = await request.body()
    if not verify_hmac(body, request.headers["X-Hub-Signature-256"]):
        raise HTTPException(401)
    payload = json.loads(body)
    await ProcesarWebhookMeta(payload).execute()
    return {"ok": True}
```

#### `POST /webhooks/meta/inbound`

Recibe mensajes entrantes (opt-in "SI", opt-out "STOP", ruido).

```python
# Detector simple:
texto = msg["text"]["body"].strip().lower()
if texto in {"si", "sí", "yes", "ok"} and not destinatario.opt_in_en:
    await DestinatarioRepository.marcar_opt_in(destinatario.id)
elif texto in {"stop", "baja", "no", "cancelar", "unsubscribe"}:
    await DestinatarioRepository.marcar_opt_out(telefono_e164)
else:
    # Ruido: ignorar pero loguear para debugging
    await EnvioWhatsAppRepository.registrar_ruido(...)
```

### Verificación de firma HMAC

Meta firma cada webhook con el secret de la app (`META_APP_SECRET`):

```python
def verify_hmac(body: bytes, signature_header: str) -> bool:
    expected = "sha256=" + hmac.new(
        settings.meta_app_secret.encode(),
        body, hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)
```

Si la firma no valida → 401, no se procesa.

### Idempotencia

`message_id_meta` se persiste con UNIQUE constraint. El handler de
estado hace UPSERT por `message_id_meta`. Si el mismo callback llega
N veces, el estado final es el último observado, no hay duplicación.

### Cap de gasto

`envio_whatsapp` se cuenta por `despacho_id` y por mes (zona horaria
ART). El caso de uso `EnviarBriefingDiario` y `EnviarAlertaMencion`
consultan el contador antes de pedir el envío:

```python
if EnvioWhatsAppRepository.contar_mes_actual(despacho_id) >= 1500:
    # Cap alcanzado. No enviamos.
    await NotificarAdminDespacho.execute(...)  # email interno
    raise CapExcedidoError(...)
```

Alerta interna cuando un despacho llega al 80% del cap (1.200 envíos).

### Caso de uso `EnviarBriefingDiario` (composición)

```python
class EnviarBriefingDiario:
    async def execute(self, *, despacho_id: UUID, fecha: date) -> None:
        # 1. Componer payload del briefing (BO accionables + Noticias)
        # 2. Por cada Destinatario.recibe_briefing_diario activo:
        #    - Renderizar params de plantilla_briefing_diario_v1
        #    - Disparar provider.enviar_plantilla(...)
        # 3. Persistir EnvioBriefingDiario (entidad de spec 15+16, no de spec 17)
```

`EnviarAlertaMencion` se documenta en ADR 0009 (anti-flood).

### Mensaje de confirmación opt-in

Al registrar un `Destinatario`:

1. Persistir con `opt_in_en=null, activo=false`.
2. Enviar la **primera plantilla** (`praxis_optin_v1` — la única
   `utility` que no requiere opt-in previo según las reglas Meta para
   el primer contacto autorizado por el cliente B2B).
3. Esperar respuesta "SI" para `marcar_opt_in`.
4. Sin respuesta en 72h → `EnviarBriefingDiario` salta a ese
   destinatario, se marca como **pendiente** en la UI de
   `/configuracion`.

*Nota:* la plantilla `praxis_optin_v1` se suma como cuarta plantilla a
registrar en Meta. Spec 17 lista 3 plantillas; este ADR agrega la
cuarta como decisión derivada del flujo de onboarding. Total: **4
plantillas v1**.

## Alternativas consideradas

### Twilio (BSP)

- **Pros**: dashboard, soporte humano, billing simple en USD por mes,
  abstrae cambios de API.
- **Contras**: markup ~30-50% sobre el costo Meta directo, lock-in
  parcial (su SDK), un actor más que rompe en producción si baja.
- **Veredicto**: descartado por costo + por evitar dependencia
  intermedia para un canal central del producto.

### 360Dialog (BSP especializado en WhatsApp)

- **Pros**: más barato que Twilio, integración limpia con WABA.
- **Contras**: aún suma markup, billing en EUR, soporte en alemán/inglés.
- **Veredicto**: descartado por la misma razón. Si Praxis llega a
  escala con > 50 despachos, reabrir.

### Hospedarnos en WhatsApp Business API on-premise

Modo legacy de Meta (Docker container que self-hostea la API).
Descartado: Meta lo está deprecando en favor de Cloud API.

### Telegram en lugar de WhatsApp

- **Pros**: API gratuita, sin plantillas, sin opt-in formal.
- **Contras**: no es donde está la audiencia política argentina.
- **Veredicto**: descartado. Posible canal secundario v3.

### Un número por despacho desde v1

- **Pros**: branding "Despacho Juliano" en vez de "Praxis Asesor".
- **Contras**: verificación Meta por cada uno (24-48h cada despacho),
  multiplicación de costo fijo, gestión administrativa N veces.
- **Veredicto**: descartado por D15. Reabrir en v2 si clientes lo piden.

## Consecuencias

### Positivas

- Costo por mensaje al precio Meta vigente (sin markup BSP).
- Control total sobre la cuenta WABA y plantillas.
- Sin dependencia intermedia: si Meta API funciona, Praxis envía.
- Una sola integración Meta cubre todos los consumidores actuales y
  futuros del canal.

### Negativas / Trade-offs

- **Mantener nosotros la integración**: cuando Meta cambia la API
  (versionado v18 → v19 → v20), hay que migrar manualmente. Mitigable
  con tests de contrato.
- **Sin dashboard Meta amigable**: cualquier visibilidad operativa la
  tenemos que construir nosotros (`/configuracion/envios`).
- **Verificación de negocio**: Praxis tiene que verificar su Business
  con Meta (proceso documental ~1 semana). Pre-requisito real.
- **Templates rejection rate**: las primeras versiones pueden ser
  rechazadas por Meta por contenido ambiguo. Iterar templates es ciclo
  de 24-48h cada uno.
- **Token expirado** = desastre operativo. Hay que rotar **system user
  tokens** antes de expiración. Job Celery beat mensual chequea
  expiración y avisa.

### Operación

- **Setup inicial** (manual, una vez):
  1. Crear WABA en Meta Business Manager.
  2. Verificar negocio Praxis con documentación.
  3. Comprar / asignar número de teléfono.
  4. Crear app Meta + permisos.
  5. Generar system user token + `verify_token` random.
  6. Registrar plantillas con `scripts/registrar_plantillas_meta.py`.
  7. Esperar aprobaciones.

- **Runbook**:
  - Si plantilla queda `pausada` por bajo engagement → revisar contenido.
  - Si Meta suspende la WABA → flujo de apelación documentado.
  - Si tasa de delivery cae bajo 90% → revisar tasa de opt-out y
    calidad del contenido.

- **Health check** `/health/meta` verifica token vigente + WABA
  accesible.

## Trabajo derivado

- feat/41.1: dominio (`Destinatario`, `PlantillaWhatsApp`,
  `EnvioWhatsApp`).
- feat/41.2: `WhatsAppCloudApiProvider` + script registro plantillas +
  `FakeMessagingProvider` para dev.
- feat/41.3: webhooks Meta (status + inbound) + opt-in/opt-out.
- feat/41.4: `EnviarBriefingDiario` (consumidor).
- feat/41.5: UI `/configuracion`.
- feat/41.6: smoke real con teléfono de Agustín.
