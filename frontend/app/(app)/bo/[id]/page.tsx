/**
 * /bo/[id] — detalle estructurado de una norma del Boletín Oficial.
 *
 * Server Component que muestra:
 * - Metadata (tipo, número, organismo, sumario).
 * - Clasificación cacheada si está (área + palabras clave + referencias
 *   legales + flag de afectación a expedientes HCDN).
 * - Link al BO oficial.
 *
 * NO mostramos el cuerpo del texto (regla de producto ADR 0006).
 */
import Link from "next/link";
import { ArrowLeft, ExternalLink, FileText, Tag } from "lucide-react";
import { notFound } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { ApiError404 } from "@/lib/api/client";
import { getApiContextServer } from "@/lib/api/context-server";
import { getNormaBO } from "@/lib/api/endpoints";

export const metadata = { title: "Detalle norma BO" };

interface PageProps {
  params: Promise<{ id: string }>;
}

export default async function BODetailPage({ params }: PageProps) {
  const { id } = await params;
  const ctx = await getApiContextServer();

  let detalle;
  try {
    detalle = await getNormaBO(ctx, id);
  } catch (err) {
    if (err instanceof ApiError404) {
      notFound();
    }
    throw err;
  }

  const { norma, clasificacion } = detalle;
  return (
    <div className="space-y-7">
      <Link
        href="/bo"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" />
        Volver al listado del día
      </Link>

      <header>
        <p className="text-[10.5px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
          Boletín Oficial · {norma.seccion}
        </p>
        <h2 className="mt-1 font-display text-2xl font-bold tracking-tight text-[var(--color-praxis-azul)]">
          {norma.tipo_norma} {norma.numero_norma}
        </h2>
        <p className="mt-1.5 text-sm font-medium text-foreground">
          {norma.organismo_emisor}
        </p>
        <p className="mt-3 text-sm leading-relaxed text-foreground">
          {norma.sumario}
        </p>
        <p className="mt-2 text-xs text-muted-foreground">
          Publicado el {norma.fecha_publicacion} · capturado el{" "}
          {new Date(norma.capturado_en).toLocaleString("es-AR")}
        </p>
        <a
          href={norma.url_oficial}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-4 inline-flex items-center gap-1.5 text-sm font-medium text-[var(--color-praxis-azul)] underline-offset-2 hover:underline"
        >
          <ExternalLink className="size-4" />
          Ver en boletinoficial.gob.ar
        </a>
      </header>

      {clasificacion ? (
        <ClasificacionCard clasificacion={clasificacion} />
      ) : (
        <Card className="border-border bg-card p-5 text-sm text-muted-foreground shadow-none">
          <FileText className="mb-2 size-5 text-muted-foreground" />
          <p>
            La norma todavía no fue clasificada por la IA. El job
            nocturno se ejecuta a las 05:30 ART.
          </p>
        </Card>
      )}
    </div>
  );
}

function ClasificacionCard({
  clasificacion,
}: {
  clasificacion: NonNullable<
    Awaited<ReturnType<typeof getNormaBO>>["clasificacion"]
  >;
}) {
  return (
    <Card className="space-y-4 border-border bg-card p-6 shadow-none">
      <div className="flex items-baseline gap-2.5">
        <Tag className="size-4 text-[var(--color-praxis-salmon)]" />
        <h3 className="font-display text-sm font-semibold uppercase tracking-wider text-[var(--color-praxis-azul)]">
          Clasificación IA
        </h3>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <p className="text-[10.5px] font-semibold uppercase tracking-wide text-muted-foreground">
            Área temática
          </p>
          <p className="mt-1 text-sm font-medium text-foreground">
            {clasificacion.area_tematica}
          </p>
        </div>
        <div>
          <p className="text-[10.5px] font-semibold uppercase tracking-wide text-muted-foreground">
            Afecta expedientes HCDN
          </p>
          <p className="mt-1 text-sm font-medium text-foreground">
            {clasificacion.afecta_expedientes_hcdn ? "Sí" : "No detectado"}
          </p>
        </div>
      </div>

      {clasificacion.palabras_clave.length > 0 && (
        <div>
          <p className="text-[10.5px] font-semibold uppercase tracking-wide text-muted-foreground">
            Palabras clave
          </p>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {clasificacion.palabras_clave.map((p) => (
              <Badge
                key={p}
                variant="outline"
                className="border-border bg-secondary/60 text-[10.5px]"
              >
                {p}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {clasificacion.referencias_legales.length > 0 && (
        <div>
          <p className="text-[10.5px] font-semibold uppercase tracking-wide text-muted-foreground">
            Referencias legales mencionadas
          </p>
          <ul className="mt-1.5 space-y-0.5 text-sm text-foreground">
            {clasificacion.referencias_legales.map((r) => (
              <li key={r}>• {r}</li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}
