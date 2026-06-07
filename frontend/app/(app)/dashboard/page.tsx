/**
 * /dashboard — Hub diario (feat-42.5).
 *
 * Pantalla principal del asesor al abrir Praxis cada mañana.
 * Server Component que llama GET /api/v1/hub-diario y muestra:
 *
 * 1. Saludo + stats rápidas (BO, noticias, menciones).
 * 2. "Necesita acción hoy" — accionables BO + Noticias con tweets
 *    listos para copiar (botón Copy con feedback visual).
 * 3. "No tocar" — items con accion=silencio_estratégico.
 * 4. Próxima sesión parlamentaria con CTA al briefing.
 */
import Link from "next/link";
import {
  AlertCircle,
  CalendarDays,
  FileText,
  MessageCircle,
  Newspaper,
  Sparkles,
  TrendingUp,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { HuellaLegisladorPanel } from "@/components/features/legislador/huella-panel";
import { getApiContextServer } from "@/lib/api/context-server";
import { getHubDiario } from "@/lib/api/endpoints";
import type {
  AccionSugerida,
  ConfianzaAccionable,
  HubItemDTO,
  HubStatsDTO,
  ProximaSesionDTO,
  TweetSugeridoBreveDTO,
} from "@/lib/api/types";

import { TweetCopyButton } from "./tweet-copy-button";

export const metadata = { title: "Hub diario" };

const ACCION_LABEL: Record<AccionSugerida, string> = {
  pedido_informes: "Pedido de informes",
  proyecto_contraposicion: "Contraproyecto",
  declaracion_camara: "Declaración",
  silencio_estrategico: "Silencio",
  retweet_critico: "RT crítico",
  retweet_apoyo: "RT apoyo",
  articulo_opinion: "Opinión",
  interpelacion: "Interpelación",
  otro: "Revisar",
};

const ACCION_COLOR: Record<AccionSugerida, string> = {
  pedido_informes: "var(--color-praxis-azul)",
  proyecto_contraposicion: "var(--color-praxis-azul)",
  declaracion_camara: "var(--color-praxis-azul)",
  silencio_estrategico: "var(--color-praxis-salmon)",
  retweet_critico: "var(--color-praxis-salmon)",
  retweet_apoyo: "var(--color-praxis-verde)",
  articulo_opinion: "var(--color-praxis-azul)",
  interpelacion: "var(--color-praxis-salmon)",
  otro: "rgb(100 116 139)",
};

const CONFIANZA_COLOR: Record<ConfianzaAccionable, string> = {
  alta: "var(--color-praxis-verde)",
  media: "var(--color-praxis-azul)",
  baja: "var(--color-praxis-salmon)",
};

function formatFechaLarga(iso: string): string {
  const f = new Date(iso + "T00:00:00").toLocaleDateString("es-AR", {
    weekday: "long",
    day: "2-digit",
    month: "long",
    year: "numeric",
  });
  return f.charAt(0).toUpperCase() + f.slice(1);
}

export default async function DashboardPage() {
  const ctx = await getApiContextServer();
  const hub = await getHubDiario(ctx).catch(() => null);

  if (hub === null) {
    return (
      <Card className="border-border bg-card p-6 shadow-none">
        <p className="text-sm text-muted-foreground">
          No se pudo cargar el hub. Verificá la conexión al backend.
        </p>
      </Card>
    );
  }

  return (
    <div className="space-y-8">
      <header className="space-y-1">
        <p className="text-[10.5px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
          Hub diario
        </p>
        <h2 className="font-display text-3xl font-bold tracking-tight text-[var(--color-praxis-azul)]">
          {formatFechaLarga(hub.fecha)}
        </h2>
      </header>

      {/* Huella del legislador titular (feat-46) */}
      <HuellaLegisladorPanel />

      {!hub.perfil_opositor_cargado && (
        <Card className="border-[var(--color-praxis-salmon)]/40 bg-[var(--color-praxis-salmon)]/5 p-4 shadow-none">
          <div className="flex items-start gap-3">
            <AlertCircle className="size-5 flex-shrink-0 text-[var(--color-praxis-salmon)]" />
            <div className="flex-1 text-sm">
              <p className="font-medium text-foreground">
                Perfil opositor sin cargar
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                Cargá el perfil del despacho para que el bot conecte
                cada evento con tu línea política.{" "}
                <Link
                  href="/configuracion/perfil-opositor"
                  className="font-medium text-[var(--color-praxis-azul)] underline-offset-2 hover:underline"
                >
                  Cargar perfil →
                </Link>
              </p>
            </div>
          </div>
        </Card>
      )}

      <StatsRow stats={hub.stats} />

      <AccionRequeridaSection items={hub.accion_requerida} />

      {hub.silenciar.length > 0 && (
        <SilenciarSection items={hub.silenciar} />
      )}

      {hub.proxima_sesion && <ProximaSesionCard sesion={hub.proxima_sesion} />}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stats
// ---------------------------------------------------------------------------

function StatsRow({ stats }: { stats: HubStatsDTO }) {
  return (
    <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
      <StatCard
        icon={<FileText className="size-4" />}
        label="BO de hoy"
        valor={`${stats.bo_accionables} / ${stats.bo_total_hoy}`}
        hint="accionables / total"
      />
      <StatCard
        icon={<Newspaper className="size-4" />}
        label="Noticias 24h"
        valor={String(stats.noticias_relevantes_24h)}
        hint="relevantes"
      />
      <StatCard
        icon={<MessageCircle className="size-4" />}
        label="Menciones 24h"
        valor={String(stats.menciones_24h)}
        hint="al legislador"
      />
      <StatCard
        icon={<TrendingUp className="size-4" />}
        label="Total accionable"
        valor={String(stats.bo_accionables + stats.noticias_relevantes_24h)}
        hint="entradas hoy"
      />
    </div>
  );
}

function StatCard({
  icon,
  label,
  valor,
  hint,
}: {
  icon: React.ReactNode;
  label: string;
  valor: string;
  hint: string;
}) {
  return (
    <Card className="border-border bg-card px-3 py-2.5 shadow-none">
      <div className="flex items-center gap-1.5 text-[10.5px] uppercase tracking-wider text-muted-foreground">
        <span className="text-[var(--color-praxis-salmon)]">{icon}</span>
        {label}
      </div>
      <p className="mt-1 font-display text-xl font-bold text-foreground">
        {valor}
      </p>
      <p className="text-[10.5px] text-muted-foreground">{hint}</p>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Acción requerida
// ---------------------------------------------------------------------------

function AccionRequeridaSection({ items }: { items: HubItemDTO[] }) {
  return (
    <section className="space-y-3">
      <div className="flex items-center gap-2">
        <Sparkles className="size-4 text-[var(--color-praxis-salmon)]" />
        <h3 className="font-display text-sm font-semibold uppercase tracking-wider text-[var(--color-praxis-azul)]">
          Necesita acción hoy
        </h3>
        <Badge variant="outline" className="text-[10px]">
          {items.length}
        </Badge>
      </div>
      {items.length === 0 ? (
        <Card className="border-border bg-card p-6 text-center shadow-none">
          <p className="text-sm text-muted-foreground">
            Sin acciones pendientes generadas todavía. Generá acciones
            desde{" "}
            <Link
              href="/bo"
              className="font-medium text-[var(--color-praxis-azul)] underline-offset-2 hover:underline"
            >
              /bo
            </Link>{" "}
            o{" "}
            <Link
              href="/noticias"
              className="font-medium text-[var(--color-praxis-azul)] underline-offset-2 hover:underline"
            >
              /noticias
            </Link>
            .
          </p>
        </Card>
      ) : (
        <div className="space-y-2.5">
          {items.map((it) => (
            <AccionRequeridaCard
              key={`${it.tipo_evento}-${it.evento_id}`}
              item={it}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function AccionRequeridaCard({ item }: { item: HubItemDTO }) {
  const color = ACCION_COLOR[item.accion];
  return (
    <Card
      className="border-border bg-card p-4 shadow-none"
      style={{ borderLeftColor: color, borderLeftWidth: 3 }}
    >
      <div className="flex flex-wrap items-start gap-2">
        <Badge
          className="text-[10px] font-semibold uppercase"
          style={{ backgroundColor: color, color: "white" }}
        >
          {ACCION_LABEL[item.accion]}
        </Badge>
        <Badge
          variant="outline"
          className="border-current text-[10px] font-semibold"
          style={{ color: CONFIANZA_COLOR[item.confianza] }}
        >
          {item.confianza}
        </Badge>
        <span className="text-[10.5px] uppercase tracking-wider text-muted-foreground">
          {item.tipo_evento === "norma_bo" ? "BO" : "Noticia"} ·{" "}
          {item.fuente_o_organismo}
        </span>
      </div>
      <Link
        href={item.url_detalle}
        className="mt-2 block font-medium leading-snug text-foreground hover:underline"
      >
        {item.titulo}
      </Link>
      <p className="mt-1 text-xs text-muted-foreground line-clamp-2">
        {item.razon_breve}
      </p>
      {item.tweets.length > 0 && <TweetsRow tweets={item.tweets} />}
    </Card>
  );
}

function TweetsRow({ tweets }: { tweets: TweetSugeridoBreveDTO[] }) {
  return (
    <div className="mt-3 space-y-1.5">
      <p className="text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">
        Tweets listos para usar
      </p>
      {tweets.map((t, i) => (
        <div
          key={i}
          className="rounded-md border border-border bg-background px-2.5 py-2 text-xs"
        >
          <div className="mb-1 flex items-center justify-between gap-2">
            <Badge variant="outline" className="text-[9.5px] uppercase">
              {t.tono}
            </Badge>
            <div className="flex items-center gap-2">
              <span
                className={`text-[10px] tabular-nums ${t.caracteres > 280 ? "font-semibold text-[var(--color-praxis-salmon)]" : "text-muted-foreground"}`}
              >
                {t.caracteres}/280
              </span>
              <TweetCopyButton texto={t.texto} />
            </div>
          </div>
          <p className="leading-relaxed text-foreground">{t.texto}</p>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Silenciar
// ---------------------------------------------------------------------------

function SilenciarSection({ items }: { items: HubItemDTO[] }) {
  return (
    <section className="space-y-2.5">
      <div className="flex items-center gap-2">
        <AlertCircle className="size-4 text-[var(--color-praxis-salmon)]" />
        <h3 className="font-display text-sm font-semibold uppercase tracking-wider text-[var(--color-praxis-azul)]">
          No tocar / silencio estratégico
        </h3>
        <Badge variant="outline" className="text-[10px]">
          {items.length}
        </Badge>
      </div>
      <Card className="border-border bg-muted/30 p-4 shadow-none">
        <p className="mb-2 text-[11px] italic text-muted-foreground">
          El bot detectó que estos temas no encajan con la línea del
          despacho. Recomendación: no responder, no twittear, dejar
          pasar.
        </p>
        <ul className="space-y-1.5">
          {items.map((it) => (
            <li
              key={`${it.tipo_evento}-${it.evento_id}`}
              className="text-xs leading-relaxed"
            >
              <Link
                href={it.url_detalle}
                className="font-medium text-foreground hover:underline"
              >
                {it.titulo}
              </Link>{" "}
              <span className="text-muted-foreground">
                — {it.razon_breve}
              </span>
            </li>
          ))}
        </ul>
      </Card>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Próxima sesión
// ---------------------------------------------------------------------------

function ProximaSesionCard({ sesion }: { sesion: ProximaSesionDTO }) {
  const fecha = new Date(
    sesion.fecha_sesion + "T00:00:00",
  ).toLocaleDateString("es-AR", {
    weekday: "long",
    day: "2-digit",
    month: "long",
  });
  return (
    <section className="space-y-2.5">
      <div className="flex items-center gap-2">
        <CalendarDays className="size-4 text-[var(--color-praxis-salmon)]" />
        <h3 className="font-display text-sm font-semibold uppercase tracking-wider text-[var(--color-praxis-azul)]">
          Próxima sesión parlamentaria
        </h3>
      </div>
      <Card className="border-border bg-card p-4 shadow-none">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <p className="text-[10.5px] uppercase tracking-wider text-muted-foreground">
              {sesion.camara} · {fecha}
            </p>
            <p className="mt-1 font-medium text-foreground">
              {sesion.titulo ?? "Sesión sin título"}
            </p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {sesion.expedientes_count} expedientes en el orden del día
            </p>
          </div>
          {sesion.briefing_id ? (
            <Link
              href={`/briefings/${sesion.briefing_id}`}
              className="inline-flex items-center gap-1.5 rounded-md bg-[var(--color-praxis-azul)] px-3 py-1.5 text-xs font-semibold text-white"
            >
              Ver briefing pre-sesión
            </Link>
          ) : (
            <Link
              href="/briefings/nuevo"
              className="inline-flex items-center gap-1.5 rounded-md border border-[var(--color-praxis-azul)] px-3 py-1.5 text-xs font-semibold text-[var(--color-praxis-azul)]"
            >
              Generar briefing
            </Link>
          )}
        </div>
      </Card>
    </section>
  );
}
