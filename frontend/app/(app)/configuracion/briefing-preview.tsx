/**
 * Server Component que renderiza el preview del briefing diario que
 * se va a mandar mañana al WhatsApp del destinatario (feat-42.4).
 *
 * Muestra:
 * - Resumen corto (lo que va al slot {{3}} de la plantilla aprobada).
 * - Body rich (el render text-free, futuro).
 * - Items separados (BO + Noticias) con badge de acción y razón breve.
 * - Empty state si el día no tiene contenido.
 */
import { CalendarDays, MessageCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { getApiContextServer } from "@/lib/api/context-server";
import { previewBriefingDiario } from "@/lib/api/endpoints";
import type {
  AccionSugerida,
  BriefingDiarioItemDTO,
} from "@/lib/api/types";

const ACCION_LABEL: Record<AccionSugerida, string> = {
  pedido_informes: "Informes",
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

export async function BriefingPreviewSection() {
  const ctx = await getApiContextServer();
  const preview = await previewBriefingDiario(ctx).catch(() => null);

  if (preview === null) {
    return null;
  }

  return (
    <section className="space-y-3">
      <div className="flex items-center gap-2">
        <MessageCircle className="size-4 text-[var(--color-praxis-salmon)]" />
        <h3 className="font-display text-sm font-semibold uppercase tracking-wider text-[var(--color-praxis-azul)]">
          Próximo briefing diario
        </h3>
        <Badge variant="outline" className="text-[10px] uppercase">
          Preview
        </Badge>
      </div>

      <Card className="border-border bg-card p-5 shadow-none">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <CalendarDays className="size-3.5" />
          Se envía a las 7:00 ART. Fecha del briefing:{" "}
          <span className="font-medium text-foreground">{preview.fecha}</span>
        </div>

        {preview.sin_contenido ? (
          <p className="mt-4 text-sm italic text-muted-foreground">
            Sin novedades para esa fecha — el briefing no se manda.
            (Pasa típico en fines de semana y feriados.)
          </p>
        ) : (
          <>
            <div className="mt-4 space-y-1">
              <p className="text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">
                Resumen corto (texto que va al WhatsApp aprobado)
              </p>
              <p className="rounded-md bg-muted/40 px-3 py-2 text-xs font-mono leading-relaxed text-foreground">
                {preview.resumen_corto}
              </p>
            </div>

            <div className="mt-4 space-y-1">
              <p className="text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">
                Detalle (cuando se habilite formato libre)
              </p>
              <pre className="overflow-x-auto rounded-md bg-muted/40 px-3 py-2 text-[11px] leading-relaxed text-foreground whitespace-pre-wrap font-mono">
                {preview.body_rich}
              </pre>
            </div>

            {preview.items_bo.length > 0 && (
              <ItemsBlock label="Boletín Oficial" items={preview.items_bo} />
            )}
            {preview.items_noticias.length > 0 && (
              <ItemsBlock label="Noticias" items={preview.items_noticias} />
            )}
          </>
        )}
      </Card>
    </section>
  );
}

function ItemsBlock({
  label,
  items,
}: {
  label: string;
  items: BriefingDiarioItemDTO[];
}) {
  return (
    <div className="mt-4 space-y-1.5">
      <p className="text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">
        {label} ({items.length})
      </p>
      <ul className="divide-y divide-border rounded-md border border-border">
        {items.map((it, i) => (
          <li key={i} className="flex items-start gap-2 px-3 py-2 text-xs">
            {it.accion && (
              <Badge
                style={{
                  backgroundColor: ACCION_COLOR[it.accion],
                  color: "white",
                }}
                className="text-[9.5px] font-semibold uppercase"
              >
                {ACCION_LABEL[it.accion]}
              </Badge>
            )}
            <div className="min-w-0 flex-1">
              <p className="font-medium text-foreground">{it.titulo_corto}</p>
              {it.razon_breve && (
                <p className="mt-0.5 text-[11px] text-muted-foreground line-clamp-2">
                  {it.razon_breve}
                </p>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
