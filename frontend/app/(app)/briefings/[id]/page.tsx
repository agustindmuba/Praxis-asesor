/**
 * Página /briefings/[id] — el id es del OrdenDelDia.
 *
 * Server Component:
 * 1. Carga el OD del despacho.
 * 2. Genera/recupera el Briefing (cache-aware).
 * 3. Renderiza el HTML embebido + botones de acción.
 *
 * El detalle visual está en el HTML que devuelve el endpoint /html
 * (mismo CSS que el PDF). Acá solo lo embebemos en un iframe + chrome
 * de la app.
 */
import { notFound } from "next/navigation";

import { BriefingActions } from "@/components/features/briefing/briefing-actions";
import { BriefingHeader } from "@/components/features/briefing/briefing-header";
import { Card, CardContent } from "@/components/ui/card";
import { ApiError404 } from "@/lib/api/client";
import { getApiContextServer } from "@/lib/api/context-server";
import {
  generarBriefing,
  getBriefingHtml,
  getOrdenDelDia,
} from "@/lib/api/endpoints";

interface PageProps {
  params: Promise<{ id: string }>;
}

export async function generateMetadata({ params }: PageProps) {
  const { id } = await params;
  return { title: `Briefing ${id.slice(0, 8)}…` };
}

export default async function BriefingDetallePage({ params }: PageProps) {
  const { id } = await params;
  const ctx = await getApiContextServer();

  let od;
  try {
    od = await getOrdenDelDia(ctx, id);
  } catch (err) {
    if (err instanceof ApiError404) {
      notFound();
    }
    throw err;
  }

  // Generar/recuperar el briefing (cache hit la 2da vez).
  const briefing = await generarBriefing(ctx, { orden_del_dia_id: id });

  // Fetch del HTML server-side y embebido via srcDoc.
  // No usamos iframe.src = url porque el browser no incluye el header
  // Authorization en sub-requests del iframe.
  const html = await getBriefingHtml(ctx, briefing.id);

  return (
    <div className="space-y-6">
      <BriefingHeader od={od} briefing={briefing} />

      <BriefingActions briefingId={briefing.id} odId={od.id} />

      <Card className="border-border bg-card shadow-none">
        <CardContent className="p-0">
          {/* HTML del briefing embebido via srcDoc — el iframe lo aísla
              del CSS de la app sin requerir headers de auth. */}
          <iframe
            srcDoc={html}
            title={`Briefing ${briefing.id}`}
            className="h-[1000px] w-full rounded-lg border-0"
          />
        </CardContent>
      </Card>
    </div>
  );
}
