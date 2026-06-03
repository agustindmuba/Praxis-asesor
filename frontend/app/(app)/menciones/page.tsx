/**
 * /menciones — histórico tenant-scoped de menciones del despacho.
 *
 * Server Component. GET /api/v1/menciones con filtros opcionales por
 * tono y fuente (via query params). Ventana default: últimos 30 días.
 */
import Link from "next/link";
import { ExternalLink, MessageSquare, Radio } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { getApiContextServer } from "@/lib/api/context-server";
import { listarMenciones } from "@/lib/api/endpoints";
import type { MencionConArticuloDTO, TonoMencion } from "@/lib/api/types";

export const metadata = { title: "Menciones" };

interface PageProps {
  searchParams?: Promise<{
    tono?: string;
    fuente_id?: string;
    desde?: string;
    hasta?: string;
  }>;
}

const TONO_COLOR: Record<TonoMencion, string> = {
  positivo: "var(--color-praxis-verde)",
  neutro: "var(--color-praxis-azul)",
  negativo: "var(--color-praxis-salmon)",
};

const TONO_LABEL: Record<TonoMencion, string> = {
  positivo: "POSITIVO",
  neutro: "NEUTRO",
  negativo: "NEGATIVO",
};

function isTono(t: string | undefined): t is TonoMencion {
  return t === "positivo" || t === "neutro" || t === "negativo";
}

function formatDetectado(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("es-AR", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default async function MencionesPage({ searchParams }: PageProps) {
  const params = (await searchParams) ?? {};
  const tono = isTono(params.tono) ? params.tono : undefined;

  const ctx = await getApiContextServer();
  const menciones = await listarMenciones(ctx, {
    tono,
    fuente_id: params.fuente_id,
    desde: params.desde,
    hasta: params.hasta,
  }).catch(() => []);

  return (
    <div className="space-y-8">
      <header>
        <p className="text-[10.5px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
          Despacho · Menciones
        </p>
        <h2 className="mt-1 font-display text-3xl font-bold tracking-tight text-[var(--color-praxis-azul)]">
          Histórico de menciones
        </h2>
        <p className="mt-1.5 text-sm text-muted-foreground">
          Últimos 30 días · {menciones.length}{" "}
          {menciones.length === 1 ? "mención" : "menciones"}
        </p>
      </header>

      <FiltrosTono tonoActual={tono} />

      {menciones.length === 0 ? (
        <Card className="border-border bg-card p-6 text-center shadow-none">
          <MessageSquare className="mx-auto size-8 text-[var(--color-praxis-salmon)]" />
          <p className="mt-2.5 text-sm font-medium text-foreground">
            Sin menciones para los filtros seleccionados
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            Las menciones se detectan automáticamente sobre los artículos
            procesados por el polling de fuentes (cada 15 minutos).
          </p>
        </Card>
      ) : (
        <ul className="space-y-2.5">
          {menciones.map((m) => (
            <MencionItem key={m.mencion.id} item={m} />
          ))}
        </ul>
      )}
    </div>
  );
}

function FiltrosTono({ tonoActual }: { tonoActual?: TonoMencion }) {
  const opciones: { value?: TonoMencion; label: string }[] = [
    { value: undefined, label: "Todos" },
    { value: "positivo", label: "Positivos" },
    { value: "neutro", label: "Neutros" },
    { value: "negativo", label: "Negativos" },
  ];
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">
        Tono
      </span>
      {opciones.map((o) => {
        const activo = o.value === tonoActual;
        const href = o.value ? `/menciones?tono=${o.value}` : "/menciones";
        return (
          <Link
            key={o.label}
            href={href}
            className={
              activo
                ? "rounded-full bg-[var(--color-praxis-azul)] px-3 py-1 text-xs font-semibold text-white"
                : "rounded-full border border-border px-3 py-1 text-xs text-muted-foreground hover:bg-muted"
            }
          >
            {o.label}
          </Link>
        );
      })}
    </div>
  );
}

function MencionItem({ item }: { item: MencionConArticuloDTO }) {
  const { mencion: m, articulo, fuente } = item;
  const color = TONO_COLOR[m.tono];
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
          {TONO_LABEL[m.tono]}
        </Badge>
        <div className="min-w-0 flex-1">
          <p className="text-sm italic text-foreground">
            “{m.snippet_contexto}”
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-2.5">
            <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
              <Radio className="size-3" />
              {fuente.nombre}
            </span>
            <span className="text-xs text-muted-foreground">
              · {formatDetectado(m.detectado_en)}
            </span>
            <Link
              href={`/noticias/${articulo.id}`}
              className="text-xs font-medium text-[var(--color-praxis-azul)] underline-offset-2 hover:underline"
            >
              {articulo.titulo}
            </Link>
          </div>
        </div>
        <div className="flex flex-col items-end gap-1.5 flex-shrink-0">
          <span className="text-xs font-semibold text-muted-foreground">
            {Math.round(m.confianza_tono * 100)}%
          </span>
          <a
            href={articulo.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          >
            <ExternalLink className="size-3" />
            Original
          </a>
        </div>
      </div>
    </Card>
  );
}
