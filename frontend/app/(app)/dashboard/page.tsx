/**
 * Dashboard — "Mis seguimientos" agrupados por prioridad.
 *
 * Server Component que hace en paralelo:
 *   1. GET /seguimientos
 *   2. Para cada seguimiento: GET /expedientes/{id} (para tener título + estado)
 *
 * Esto es O(N) requests con N pequeño (un asesor típico sigue <100 expedientes).
 * Si N crece, agregamos un endpoint backend `GET /seguimientos?expand=expediente`
 * en una feature futura.
 */
import Link from "next/link";
import { FileText, Inbox } from "lucide-react";

import { EstadoBadge } from "@/components/features/expedientes/estado-badge";
import { Card } from "@/components/ui/card";
import { ApiError404 } from "@/lib/api/client";
import { getApiContextServer } from "@/lib/api/context-server";
import { getExpediente, listarSeguimientos } from "@/lib/api/endpoints";
import type { ExpedienteFicha, Prioridad, SeguimientoDTO } from "@/lib/api/types";
import {
  formatFechaCorta,
  formatNumeroExpediente,
  formatPrioridad,
} from "@/lib/formato-expediente";

export const metadata = { title: "Dashboard" };

interface ItemEnriquecido {
  seguimiento: SeguimientoDTO;
  expediente: ExpedienteFicha | null;
}

const PRIORIDADES: readonly Prioridad[] = ["alta", "media", "baja"];

export default async function DashboardPage() {
  const ctx = await getApiContextServer();
  const seguimientos = await listarSeguimientos(ctx);

  // Fetch en paralelo de los expedientes. Si alguno tira 404 (rare race),
  // lo ignoramos y dejamos `expediente: null`.
  const enriquecidos = await Promise.all(
    seguimientos.map(async (s): Promise<ItemEnriquecido> => {
      try {
        const expediente = await getExpediente(ctx, s.expediente_id);
        return { seguimiento: s, expediente };
      } catch (err) {
        if (err instanceof ApiError404) {
          return { seguimiento: s, expediente: null };
        }
        throw err;
      }
    }),
  );

  const porPrioridad: Record<Prioridad, ItemEnriquecido[]> = {
    alta: [],
    media: [],
    baja: [],
  };
  for (const item of enriquecidos) {
    porPrioridad[item.seguimiento.prioridad].push(item);
  }

  return (
    <div className="space-y-8">
      <div>
        <p className="text-[10.5px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
          Despacho · Dashboard
        </p>
        <h2 className="mt-1 font-display text-3xl font-bold tracking-tight text-[var(--color-praxis-azul)]">
          Mis seguimientos
        </h2>
        <p className="mt-1.5 text-sm text-muted-foreground">
          {enriquecidos.length}{" "}
          {enriquecidos.length === 1 ? "expediente activo" : "expedientes activos"}{" "}
          marcados por el despacho.
        </p>
      </div>

      {enriquecidos.length === 0 ? (
        <Card className="flex flex-col items-center justify-center gap-3 border-border bg-card py-20 text-center shadow-none">
          <Inbox className="size-10 text-[var(--color-praxis-salmon)]" />
          <p className="font-display text-lg font-semibold text-[var(--color-praxis-azul)]">
            Todavía no marcaste ningún expediente
          </p>
          <p className="max-w-md text-sm text-muted-foreground">
            Empezá por{" "}
            <Link
              href="/expedientes"
              className="font-medium text-[var(--color-praxis-azul)] underline-offset-2 hover:underline"
            >
              Expedientes
            </Link>{" "}
            y marcá el primero con la estrella. Acá lo vas a ver agrupado por
            prioridad.
          </p>
        </Card>
      ) : (
        <div className="space-y-7">
          {PRIORIDADES.map((p) => (
            <PrioridadSection key={p} prioridad={p} items={porPrioridad[p]} />
          ))}
        </div>
      )}
    </div>
  );
}

const PRIORIDAD_DOT: Record<Prioridad, string> = {
  alta: "var(--color-praxis-azul)",
  media: "var(--color-praxis-salmon)",
  baja: "var(--color-praxis-verde)",
};

function PrioridadSection({
  prioridad,
  items,
}: {
  prioridad: Prioridad;
  items: ItemEnriquecido[];
}) {
  if (items.length === 0) return null;
  return (
    <section className="space-y-3">
      <div className="flex items-baseline gap-2.5">
        <span
          className="inline-block size-2 rounded-full"
          style={{ backgroundColor: PRIORIDAD_DOT[prioridad] }}
        />
        <h3 className="font-display text-sm font-semibold uppercase tracking-wider text-[var(--color-praxis-azul)]">
          Prioridad {formatPrioridad(prioridad)}
        </h3>
        <span className="text-xs font-medium text-muted-foreground">
          {items.length}
        </span>
      </div>
      <Card className="overflow-hidden border-border bg-card p-0 shadow-none">
        <ul className="divide-y divide-border">
          {items.map(({ seguimiento, expediente }) => (
            <li key={seguimiento.id}>
              {expediente ? (
                <Link
                  href={`/expedientes/${expediente.id}`}
                  className="flex items-center justify-between gap-4 px-5 py-3.5 transition-colors hover:bg-[var(--color-praxis-crema)]/60"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2.5">
                      <span className="font-mono text-[11px] uppercase tracking-wide text-muted-foreground">
                        {formatNumeroExpediente(expediente.numero)}
                      </span>
                      <EstadoBadge estado={expediente.estado} />
                    </div>
                    <p className="mt-1 line-clamp-1 text-[13.5px] font-medium leading-snug text-foreground">
                      {expediente.titulo}
                    </p>
                  </div>
                  {expediente.fecha_caducidad && (
                    <p className="flex-shrink-0 text-xs text-muted-foreground">
                      Vence {formatFechaCorta(expediente.fecha_caducidad)}
                    </p>
                  )}
                </Link>
              ) : (
                <div className="flex items-center gap-2 px-5 py-3.5 text-sm text-muted-foreground">
                  <FileText className="size-4" />
                  Expediente {seguimiento.expediente_id.slice(0, 8)}… no encontrado.
                </div>
              )}
            </li>
          ))}
        </ul>
      </Card>
    </section>
  );
}
