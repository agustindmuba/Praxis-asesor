/**
 * /noticias/[id] — detalle de un artículo.
 *
 * Server Component. Muestra metadatos + bajada propia + clasificación
 * + menciones del despacho asociadas al artículo. NO renderiza el
 * cuerpo del artículo (no se persiste — ADR 0006); el usuario va al
 * medio original con el botón "Original".
 */
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, ExternalLink, MessageSquare, Radio } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { getApiContextServer } from "@/lib/api/context-server";
import { getNoticiaDetalle } from "@/lib/api/endpoints";
import type { MencionDTO, TonoMencion } from "@/lib/api/types";

export const metadata = { title: "Detalle artículo" };

interface PageProps {
  params: Promise<{ id: string }>;
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

function formatPublicado(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("es-AR", {
    day: "2-digit",
    month: "long",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default async function NoticiaDetallePage({ params }: PageProps) {
  const { id } = await params;
  const ctx = await getApiContextServer();

  let detalle;
  try {
    detalle = await getNoticiaDetalle(ctx, id);
  } catch {
    notFound();
  }

  const { articulo, fuente, clasificacion, relevante, menciones } = detalle;

  return (
    <div className="space-y-6">
      <Link
        href="/noticias"
        className="inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-3" />
        Volver a noticias
      </Link>

      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-2.5">
          <Radio className="size-4 text-[var(--color-praxis-salmon)]" />
          <span className="font-semibold text-[var(--color-praxis-azul)]">
            {fuente.nombre}
          </span>
          <span className="text-xs text-muted-foreground">
            · {formatPublicado(articulo.publicado_en)}
          </span>
          {clasificacion && (
            <Badge variant="outline" className="text-[10.5px] uppercase tracking-wider">
              {clasificacion.area_tematica}
            </Badge>
          )}
        </div>
        <h1 className="font-display text-2xl font-bold leading-tight text-foreground">
          {articulo.titulo}
        </h1>
        {articulo.bajada_propia && (
          <p className="text-base leading-relaxed text-muted-foreground">
            {articulo.bajada_propia}
          </p>
        )}
        <a
          href={articulo.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 pt-1 text-sm font-medium text-[var(--color-praxis-azul)] underline-offset-2 hover:underline"
        >
          <ExternalLink className="size-3.5" />
          Leer artículo original en {fuente.dominio}
        </a>
      </header>

      {relevante && (
        <Card className="border-border bg-[var(--color-praxis-crema)]/40 p-5 shadow-none">
          <p className="text-xs font-semibold uppercase tracking-wider text-[var(--color-praxis-azul)]">
            Relevancia para tu despacho
          </p>
          <div className="mt-2 flex items-baseline gap-3">
            <span className="font-display text-2xl font-bold text-foreground">
              {relevante.score}
            </span>
            <span className="text-sm text-muted-foreground">/ 100</span>
          </div>
          <p className="mt-2 text-sm text-foreground">{relevante.razon}</p>
        </Card>
      )}

      {clasificacion && clasificacion.palabras_clave.length > 0 && (
        <section className="space-y-2">
          <h3 className="font-display text-sm font-semibold uppercase tracking-wider text-[var(--color-praxis-azul)]">
            Palabras clave
          </h3>
          <div className="flex flex-wrap gap-1.5">
            {clasificacion.palabras_clave.map((p) => (
              <Badge key={p} variant="outline" className="text-xs">
                {p}
              </Badge>
            ))}
          </div>
        </section>
      )}

      <section className="space-y-3">
        <div className="flex items-center gap-2">
          <MessageSquare className="size-4 text-[var(--color-praxis-azul)]" />
          <h3 className="font-display text-sm font-semibold uppercase tracking-wider text-[var(--color-praxis-azul)]">
            Menciones de tu despacho
          </h3>
          <span className="text-xs font-medium text-muted-foreground">
            {menciones.length}
          </span>
        </div>
        {menciones.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No se detectaron menciones del legislador titular en este
            artículo. Si esperabas verlas, verificá los aliases del
            legislador en{" "}
            <span className="text-foreground">Configuración → Perfil</span>.
          </p>
        ) : (
          <ul className="space-y-2.5">
            {menciones.map((m) => (
              <MencionItem key={m.id} mencion={m} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function MencionItem({ mencion }: { mencion: MencionDTO }) {
  const color = TONO_COLOR[mencion.tono];
  return (
    <Card
      className="border-border bg-card p-4 shadow-none"
      style={{ borderLeftColor: color, borderLeftWidth: 4 }}
    >
      <div className="flex items-start gap-3">
        <Badge
          className="font-semibold"
          style={{ backgroundColor: color, color: "white" }}
        >
          {TONO_LABEL[mencion.tono]}
        </Badge>
        <div className="min-w-0 flex-1">
          <p className="text-sm italic text-foreground">
            “{mencion.snippet_contexto}”
          </p>
          <p className="mt-1.5 text-xs text-muted-foreground">
            Confianza {Math.round(mencion.confianza_tono * 100)}% ·
            alcance {mencion.alcance_medio}
          </p>
        </div>
      </div>
    </Card>
  );
}
