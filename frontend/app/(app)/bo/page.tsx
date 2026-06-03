/**
 * /bo — listado de normas del Boletín Oficial del día (feat-39 spec 15).
 *
 * Server Component que en paralelo:
 *   1. GET /bo/normas?fecha=… (sin tenant scoping — son públicas).
 *   2. GET /bo/accionables?fecha=… (tenant-scoped al despacho).
 *
 * El usuario puede pasar `?fecha=YYYY-MM-DD` en el query para mirar
 * fechas anteriores; si no, se usa "hoy" (la única fecha viva v1).
 *
 * Diseño con marca Praxis aplicada (azul para títulos, salmón para
 * acentos, verde para estados positivos).
 */
import Link from "next/link";
import { ExternalLink, FileText, Newspaper, RefreshCw } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { getApiContextServer } from "@/lib/api/context-server";
import {
  listarAccionablesBO,
  listarNormasBO,
} from "@/lib/api/endpoints";
import type {
  NormaBOAccionableConNormaDTO,
  NormaBODTO,
  PrioridadAccionabilidad,
} from "@/lib/api/types";

export const metadata = { title: "Boletín Oficial" };

interface PageProps {
  searchParams?: Promise<{ fecha?: string }>;
}

function hoyISO(): string {
  return new Date().toISOString().slice(0, 10);
}

function formatFechaLarga(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString("es-AR", {
    weekday: "long",
    day: "2-digit",
    month: "long",
    year: "numeric",
  });
}

const PRIORIDAD_COLOR: Record<PrioridadAccionabilidad, string> = {
  alta: "var(--color-praxis-azul)",
  media: "var(--color-praxis-salmon)",
  baja: "var(--color-praxis-verde)",
};

const PRIORIDAD_LABEL: Record<PrioridadAccionabilidad, string> = {
  alta: "ALTA",
  media: "MEDIA",
  baja: "BAJA",
};

export default async function BOPage({ searchParams }: PageProps) {
  const params = (await searchParams) ?? {};
  const fecha = params.fecha ?? hoyISO();

  const ctx = await getApiContextServer();

  const [normas, accionables] = await Promise.all([
    listarNormasBO(ctx, fecha),
    listarAccionablesBO(ctx, fecha, 20).catch(() => []),
  ]);

  return (
    <div className="space-y-8">
      <header>
        <p className="text-[10.5px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
          Despacho · Boletín Oficial
        </p>
        <h2 className="mt-1 font-display text-3xl font-bold tracking-tight text-[var(--color-praxis-azul)]">
          Normas accionables
        </h2>
        <p className="mt-1.5 text-sm text-muted-foreground">
          {formatFechaLarga(fecha)}
        </p>
      </header>

      <AccionablesSection accionables={accionables} fecha={fecha} />

      <NormasSection normas={normas} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Accionables
// ---------------------------------------------------------------------------

function AccionablesSection({
  accionables,
  fecha,
}: {
  accionables: NormaBOAccionableConNormaDTO[];
  fecha: string;
}) {
  return (
    <section className="space-y-3">
      <div className="flex items-baseline justify-between">
        <h3 className="font-display text-sm font-semibold uppercase tracking-wider text-[var(--color-praxis-azul)]">
          Accionables para tu despacho
        </h3>
        <form
          action={`/api/v1/bo/normas/reclasificar-perfil?fecha=${fecha}`}
          method="POST"
        >
          <button
            type="submit"
            className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--color-praxis-azul)] underline-offset-2 hover:underline"
            title="Re-evaluar con el perfil actual"
          >
            <RefreshCw className="size-3" />
            Refrescar
          </button>
        </form>
      </div>
      {accionables.length === 0 ? (
        <Card className="border-border bg-card p-6 text-center shadow-none">
          <Newspaper className="mx-auto size-8 text-[var(--color-praxis-salmon)]" />
          <p className="mt-2.5 text-sm font-medium text-foreground">
            Sin accionables para esta fecha
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            Configurá tu perfil de interés desde {" "}
            <span className="text-foreground">Configuración → Perfil</span>{" "}
            y refrescá. Si recién cargaste el perfil, hacé clic en
            "Refrescar" arriba.
          </p>
        </Card>
      ) : (
        <ul className="space-y-2.5">
          {accionables.map((a) => (
            <AccionableItem key={a.norma.id} item={a} />
          ))}
        </ul>
      )}
    </section>
  );
}

function AccionableItem({
  item,
}: {
  item: NormaBOAccionableConNormaDTO;
}) {
  const { accionable: a, norma } = item;
  const color = PRIORIDAD_COLOR[a.prioridad];
  return (
    <Card
      className="border-border bg-card p-5 shadow-none"
      style={{ borderLeftColor: color, borderLeftWidth: 4 }}
    >
      <div className="flex flex-wrap items-start gap-3">
        <Badge
          className="font-semibold"
          style={{ backgroundColor: color, color: "white" }}
        >
          {PRIORIDAD_LABEL[a.prioridad]}
        </Badge>
        <div className="min-w-0 flex-1">
          <p className="text-[13.5px] font-medium leading-snug text-foreground">
            <span className="text-[var(--color-praxis-azul)]">
              {norma.tipo_norma} {norma.numero_norma}
            </span>{" "}
            — <span className="line-clamp-2">{norma.sumario}</span>
          </p>
          <p className="mt-1.5 text-xs text-muted-foreground">
            {norma.organismo_emisor}
          </p>
          <p className="mt-1 text-xs text-foreground">
            <span className="font-semibold">Razón:</span> {a.razon}
          </p>
        </div>
        <div className="flex flex-col items-end gap-1.5 flex-shrink-0">
          <span className="text-xs font-semibold text-muted-foreground">
            score {a.score}
          </span>
          <Link
            href={`/bo/${norma.id}`}
            className="text-xs font-medium text-[var(--color-praxis-azul)] underline-offset-2 hover:underline"
          >
            Detalle
          </Link>
          <a
            href={norma.url_oficial}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          >
            <ExternalLink className="size-3" />
            BO oficial
          </a>
        </div>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Listado completo
// ---------------------------------------------------------------------------

function NormasSection({ normas }: { normas: NormaBODTO[] }) {
  return (
    <section className="space-y-3">
      <div className="flex items-baseline gap-2.5">
        <h3 className="font-display text-sm font-semibold uppercase tracking-wider text-[var(--color-praxis-azul)]">
          Todas las normas del día
        </h3>
        <span className="text-xs font-medium text-muted-foreground">
          {normas.length}
        </span>
      </div>
      {normas.length === 0 ? (
        <Card className="border-border bg-card p-6 text-center shadow-none">
          <FileText className="mx-auto size-8 text-muted-foreground" />
          <p className="mt-2.5 text-sm text-muted-foreground">
            No hay normas cargadas para esta fecha. El job nocturno corre a
            las 05:00 ART.
          </p>
        </Card>
      ) : (
        <Card className="overflow-hidden border-border bg-card p-0 shadow-none">
          <ul className="divide-y divide-border">
            {normas.map((n) => (
              <li key={n.id}>
                <Link
                  href={`/bo/${n.id}`}
                  className="flex items-center justify-between gap-4 px-5 py-3.5 transition-colors hover:bg-[var(--color-praxis-crema)]/60"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2.5">
                      <span className="font-mono text-[11px] uppercase tracking-wide text-muted-foreground">
                        {n.tipo_norma} {n.numero_norma}
                      </span>
                      <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
                        {n.seccion}
                      </span>
                    </div>
                    <p className="mt-1 line-clamp-1 text-[13.5px] text-foreground">
                      {n.sumario}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {n.organismo_emisor}
                    </p>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </section>
  );
}
