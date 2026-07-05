# Deploy de Praxis Asesor a producción

Instrucciones paso a paso para poner Praxis en vivo en
`https://praxisconsultora.com` con todo corriendo automático (BO,
noticias, comisiones, WhatsApp) sin tocar nada después.

## Arquitectura final

```
                    Internet
                        │
                        ▼
              praxisconsultora.com
                        │  (DNS A → IP del droplet)
                        ▼
        ┌───────────────────────────────┐
        │        VPS DigitalOcean       │
        │  ┌─────────────────────────┐  │
        │  │ Caddy (puerto 80/443)   │  │  ← HTTPS auto con Let's Encrypt
        │  └────┬─────────────┬──────┘  │
        │       │             │         │
        │       ▼             ▼         │
        │   frontend      backend       │  ← FastAPI + Next.js
        │   (Next.js)     (uvicorn)     │
        │                     │         │
        │        ┌────────────┼──────┐  │
        │        ▼            ▼      ▼  │
        │     worker       beat  postgres│  ← Celery + Postgres/pgvector
        │     (Celery)   (scheduler) redis │
        └───────────────────────────────┘
```

## Prerequisitos (los tenés)

- ✅ Dominio `praxisconsultora.com` en Hostinger
- ✅ Cuenta GitHub con el repo de Praxis
- ✅ Anthropic API key
- ✅ Meta WhatsApp System User token permanente
- ⏳ Cuenta DigitalOcean (creála primero)

## Paso 1 — Crear el droplet en DigitalOcean

1. Login en [cloud.digitalocean.com](https://cloud.digitalocean.com).
2. Click **Create → Droplets**.
3. Configuración:
   - **Región**: `NYC3` (buena latencia AR) o `SFO3`.
   - **Imagen**: **Ubuntu 24.04 (LTS) x64**.
   - **Tipo**: Basic → Regular Intel → **$6/mes** (1 GB RAM, 1 vCPU, 25 GB SSD).
     - Si tenés margen, mejor **$12/mes** (2 GB RAM). El LLM + embeddings de RAG comen memoria.
   - **Authentication**: SSH Key.
     - Si no tenés SSH key, generá una con `ssh-keygen -t ed25519 -C "praxis"` desde CMD de tu PC. Copia el contenido de `~/.ssh/id_ed25519.pub` y pegalo en DO.
   - **Hostname**: `praxis-prod`.
4. Click **Create Droplet**.
5. Cuando esté listo (~30 seg), copiá la **IP pública** que te da (algo tipo `164.90.xxx.xxx`).

## Paso 2 — Configurar DNS en Hostinger

1. Login en Hostinger → **Domains** → tu dominio → **DNS / Nameservers**.
2. Agregá o editá estos registros:

| Type | Name | Value | TTL |
|---|---|---|---|
| A | `@` | `IP-del-droplet` | 300 |
| A | `www` | `IP-del-droplet` | 300 |

3. Esperá 5-15 min para que propague. Podés chequear con:
   ```
   nslookup praxisconsultora.com
   ```

## Paso 3 — Bootstrap del VPS

Desde CMD:

```
ssh root@IP-del-droplet
```

(La primera vez te pregunta si confiar en el host, decí `yes`).

Ya adentro del VPS:

```
curl -fsSL https://raw.githubusercontent.com/agustindmuba/Praxis-asesor/main/scripts/bootstrap-vps.sh | bash
```

⚠️ Reemplazá `agustindmuba/Praxis-asesor` con el nombre real del repo.

El script:
- Instala Docker
- Configura firewall (solo 22, 80, 443 abiertos)
- Activa fail2ban
- Crea usuario `praxis` con permisos de docker
- Prepara `/opt/praxis` como directorio del proyecto

Al terminar, cambiá de usuario:

```
su - praxis
cd /opt/praxis
```

## Paso 4 — Clonar el repo y configurar `.env`

```
git clone -b develop https://github.com/agustindmuba/Praxis-asesor.git .
cp .env.production.example .env
nano .env
```

En `nano`, editá cada línea marcada `CAMBIAME`:

| Variable | Valor |
|---|---|
| `PUBLIC_HOST` | `praxisconsultora.com` |
| `POSTGRES_PASSWORD` | generá con `openssl rand -base64 32` |
| `ANTHROPIC_API_KEY` | la key `sk-ant-api03-...` que ya tenés |
| `META_WHATSAPP_TOKEN` | el System User token permanente |
| `META_WHATSAPP_PHONE_NUMBER_ID` | `1192656733921760` |
| `META_WHATSAPP_VERIFY_TOKEN` | inventá un string random largo |
| `CLERK_SECRET_KEY` | `sk_live_...` de tu app Clerk de prod |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | `pk_live_...` |
| `CLERK_JWT_ISSUER` | URL del issuer Clerk |

Ctrl+O → Enter → Ctrl+X para guardar.

## Paso 5 — Primer arranque

```
docker compose -f docker-compose.prod.yml up -d --build
```

Tarda 3-5 min la primera vez (compila las imágenes). Cuando termina:

```
docker compose -f docker-compose.prod.yml ps
```

Deberías ver 7 servicios `Up`: postgres, redis, backend, worker, beat, frontend, caddy.

**Verificación**:
- Abrí `https://praxisconsultora.com` en el navegador. Debería servir el login de Praxis con certificado HTTPS válido (candado verde).
- El certificado lo emite Let's Encrypt automáticamente la primera vez que Caddy recibe una request. Tarda ~10 seg.

## Paso 6 — Configurar CI/CD automático

Cargar los secretos en GitHub para que cada `git push` a `main`
despliegue solo.

1. En GitHub, andá al repo → **Settings → Secrets and variables → Actions → New repository secret**.
2. Creá estos secretos:

| Nombre | Valor |
|---|---|
| `VPS_HOST` | IP del droplet |
| `VPS_USER` | `praxis` |
| `VPS_SSH_KEY` | contenido de `~/.ssh/id_ed25519` (privada, la que corresponde a la pública que subiste a DO) |
| `VPS_PROJECT_PATH` | `/opt/praxis` |

3. Listo. Desde ese momento, cada `git push origin main` dispara el workflow `Deploy to Production`.

## Paso 7 — Cargar el padrón / datos iniciales

Desde el VPS:

```
docker compose -f docker-compose.prod.yml exec backend uv run python -m scripts.seed_hcdn_real --anio 2026 --desde 1 --hasta 5000 --origen D
docker compose -f docker-compose.prod.yml exec backend uv run python -m scripts.seed_comisiones_hcdn
docker compose -f docker-compose.prod.yml exec backend uv run python -m scripts.seed_efemerides
```

(O migrás el volumen `postgres_data` desde tu máquina si querés
reusar lo que ya sembraste).

## Paso 8 — Webhook Meta apuntando al VPS

En Meta Business Suite → WhatsApp Business Account → Configuration → Webhooks:
- **Callback URL**: `https://praxisconsultora.com/webhooks/meta`
- **Verify token**: el que pusiste en `META_WHATSAPP_VERIFY_TOKEN`

Meta hace un GET al endpoint. Caddy lo proxea al backend, el backend responde con el challenge, Meta lo aprueba.

## Comandos útiles para el día a día

```
# Ver logs de un servicio
docker compose -f docker-compose.prod.yml logs -f beat
docker compose -f docker-compose.prod.yml logs -f backend

# Reiniciar un servicio (por ej. si cambiaste .env)
docker compose -f docker-compose.prod.yml up -d backend

# Migración de DB manual (Alembic ya la corre al arrancar backend)
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head

# Shell dentro del backend (para debug)
docker compose -f docker-compose.prod.yml exec backend bash

# Backup manual de Postgres
docker compose -f docker-compose.prod.yml exec postgres \
    pg_dump -U praxis praxis > backup-$(date +%Y%m%d).sql
```

## Costos mensuales estimados

| Item | USD |
|---|---|
| Droplet DigitalOcean $6/mes (o $12 si vas por 2GB RAM) | 6-12 |
| Anthropic API (Sonnet, ~500 llamadas/día del clasificador BO) | 15-30 |
| Meta WhatsApp (primeras 1000 conversations/mes gratis, después $0.05 c/u) | 0-5 |
| Dominio (ya pagado) | 0 |
| **Total** | **~$25-50/mes** |

## Troubleshooting rápido

- **HTTPS no funciona**: chequear DNS (`nslookup praxisconsultora.com`). Caddy necesita que el A record esté propagado para pedir cert.
- **Backend no arranca**: `docker compose logs backend`. Si dice "connection refused" a postgres, esperá 30 seg — Postgres tarda en el healthcheck.
- **WhatsApp no llega**: chequear `docker compose logs beat` — buscar la línea `praxis.whatsapp.enviar_briefings_diarios` a las 11:20 UTC (08:20 ART).
- **Cambios no se reflejan tras push**: mirá el workflow en GitHub → Actions.

## Rollback

Si un deploy rompe algo:

```
cd /opt/praxis
git log --oneline -5              # ver últimos commits
git reset --hard <commit-anterior>
docker compose -f docker-compose.prod.yml up -d --build
```
