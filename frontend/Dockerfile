# Frontend Praxis Asesor — Next.js 15 con Turbopack.
#
# Multi-stage para minimizar imagen final:
#   1. deps:    instala node_modules (pnpm frozen lockfile)
#   2. builder: corre `pnpm build` (Turbopack ya en next build)
#   3. runner:  imagen mínima, solo el standalone + static + public
#
# Standalone output requiere `output: 'standalone'` en next.config.ts
# (lo agregamos si no está).

# ---------- deps ----------
FROM node:22-alpine AS deps

# pnpm via corepack (viene con Node 22 por default).
RUN corepack enable && corepack prepare pnpm@latest --activate

WORKDIR /app

# Cache maximum: solo package.json + lockfile en esta layer.
COPY package.json pnpm-lock.yaml* ./
RUN --mount=type=cache,id=pnpm,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile

# ---------- builder ----------
FROM node:22-alpine AS builder

RUN corepack enable && corepack prepare pnpm@latest --activate

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# NEXT_PUBLIC_* se compila al bundle, así que se debe pasar acá.
# El resto (server-only) se lee en runtime.
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL:-http://backend:8000}

# Build de producción. Turbopack.
ENV NEXT_TELEMETRY_DISABLED=1
RUN pnpm build

# ---------- runner ----------
FROM node:22-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# Standalone contiene node_modules mínimo + server.js.
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

USER nextjs

EXPOSE 3000

CMD ["node", "server.js"]
