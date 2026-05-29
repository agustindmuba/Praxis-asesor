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
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold tracking-tight">Dashboard</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Resumen de tus seguimientos. {enriquecidos.length} expedientes activos.
        </p>
      </div>

      {enriquecidos.length === 0 ? (
        <Card className="flex flex-col items-center justify-center gap-2 py-16 text-center">
          <Inbox className="size-10 text-muted-foreground" />
          <p className="text-base font-medium">Todavía no marcaste ningún expediente.</p>
          <p className="text-sm text-muted-foreground">
            Andá a{" "}
            <Link href="/expedientes" className="underline hover:text-foreground">
              Expedientes
            </Link>{" "}
            y marcá el primero con ★.
          </p>
        </Card>
      ) : (
        <div className="space-y-6">
          {PRIORIDADES.map((p) => (
            <PrioridadSection key={p} prioridad={p} items={porPrioridad[p]} />
          ))}
        </div>
      )}
    </div>
  );
}

function PrioridadSection({
  prioridad,
  items,
}: {
  prioridad: Prioridad;
  items: ItemEnriquecido[];
}) {
  if (items.length === 0) return null;
  return (
    <section className="space-y-2">
      <h3 className="text-sm font-semibold text-muted-foreground">
        Prioridad {formatPrioridad(prioridad)}{" "}
        <span className="text-xs font-normal">({items.length})</span>
      </h3>
      <Card className="overflow-hidden p-0">
        <ul className="divide-y divide-border">
          {items.map(({ seguimiento, expediente }) => (
            <li key={seguimiento.id}>
              {expediente ? (
                <Link
                  href={`/expedientes/${expediente.id}`}
                  className="flex items-center justify-between gap-4 px-4 py-3 hover:bg-muted/40"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs text-muted-foreground">
                        {formatNumeroExpediente(expediente.numero)}
                      </span>
                      <EstadoBadge estado={expediente.estado} />
                    </div>
                    <p className="mt-1 line-clamp-1 text-sm font-medium">
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
                <div className="flex items-center gap-2 px-4 py-3 text-sm text-muted-foreground">
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
