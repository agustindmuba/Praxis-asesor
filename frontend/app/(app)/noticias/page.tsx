/**
 * /noticias — listado de artículos relevantes del despacho.
 *
 * Server Component que llama GET /api/v1/noticias. Devuelve el top-N
 * de artículos relevantes en las últimas 24h del despacho actual,
 * ordenado por score DESC.
 *
 * Diseño con marca Praxis (azul, salmón, verde).
 */
import Link from "next/link";
import { ExternalLink, Newspaper, Radio } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { getApiContextServer } from "@/lib/api/context-server";
import { listarNoticiasRelevantes } from "@/lib/api/endpoints";
import type { ArticuloRelevanteConArticuloDTO } from "@/lib/api/types";

export const metadata = { title: "Noticias" };

function scoreColor(score: number): string {
  if (score >= 70) return "var(--color-praxis-azul)";
  if (score >= 50) return "var(--color-praxis-salmon)";
  return "var(--color-praxis-verde)";
}

function scoreLabel(score: number): string {
  if (score >= 70) return "ALTA";
  if (score >= 50) return "MEDIA";
  return "BAJA";
}

function formatPublicado(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("es-AR", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default async function NoticiasPage() {
  const ctx = await getApiContextServer();
  const noticias = await listarNoticiasRelevantes(ctx, 20).catch(() => []);

  return (
    <div className="space-y-8">
      <header>
        <p className="text-[10.5px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
          Despacho · Noticias
        </p>
        <h2 className="mt-1 font-display text-3xl font-bold tracking-tight text-[var(--color-praxis-azul)]">
          Artículos relevantes
        </h2>
        <p className="mt-1.5 text-sm text-muted-foreground">
          Últimas 24 horas · ordenado por score de relevancia
        </p>
      </header>

      {noticias.length === 0 ? (
        <Card className="border-border bg-card p-6 text-center shadow-none">
          <Newspaper className="mx-auto size-8 text-[var(--color-praxis-salmon)]" />
          <p className="mt-2.5 text-sm font-medium text-foreground">
            Sin artículos relevantes en las últimas 24 horas
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            El polling corre cada 15 minutos. Si recién cargaste tu perfil
            de interés, esperá una corrida o configurá fuentes en{" "}
            <span className="text-foreground">Configuración → Fuentes</span>.
          </p>
        </Card>
      ) : (
        <ul className="space-y-2.5">
          {noticias.map((n) => (
            <NoticiaItem key={n.articulo.id} item={n} />
          ))}
        </ul>
      )}
    </div>
  );
}

function NoticiaItem({ item }: { item: ArticuloRelevanteConArticuloDTO }) {
  const { relevante, articulo, fuente, clasificacion } = item;
  const color = scoreColor(relevante.score);

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
          {scoreLabel(relevante.score)}
        </Badge>
        <div className="min-w-0 flex-1">
          <Link
            href={`/noticias/${articulo.id}`}
            className="text-[14px] font-semibold leading-snug text-[var(--color-praxis-azul)] hover:underline"
          >
            {articulo.titulo}
          </Link>
          {articulo.bajada_propia && (
            <p className="mt-1.5 line-clamp-2 text-sm text-foreground">
              {articulo.bajada_propia}
            </p>
          )}
          <div className="mt-2 flex flex-wrap items-center gap-2.5">
            <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
              <Radio className="size-3" />
              {fuente.nombre}
            </span>
            <span className="text-xs text-muted-foreground">
              · {formatPublicado(articulo.publicado_en)}
            </span>
            {clasificacion && (
              <Badge
                variant="outline"
                className="text-[10.5px] uppercase tracking-wider"
              >
                {clasificacion.area_tematica}
              </Badge>
            )}
          </div>
          <p className="mt-2 text-xs text-foreground">
            <span className="font-semibold">Razón:</span> {relevante.razon}
          </p>
        </div>
        <div className="flex flex-col items-end gap-1.5 flex-shrink-0">
          <span className="text-xs font-semibold text-muted-foreground">
            score {relevante.score}
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
