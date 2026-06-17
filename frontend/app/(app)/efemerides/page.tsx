/**
 * /efemerides — calendario de efemérides + generación de declaraciones (feat-53.5).
 *
 * Server Component que llama GET /api/v1/efemerides (todas) y
 * /api/v1/efemerides/proximas (las próximas 30 días desde hoy).
 *
 * Por cada efeméride se ofrece un botón "Generar declaración" que dispara
 * el POST /api/v1/efemerides/{id}/generar-declaracion (Client Component).
 */
import { Calendar, Sparkle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { getApiContextServer } from "@/lib/api/context-server";
import {
  listarEfemerides,
  proximasEfemerides,
  type EfemerideDTO,
} from "@/lib/api/endpoints";

import { EfemerideCard } from "./efemeride-card";

export const metadata = { title: "Efemérides" };


function relevanciaColor(relevancia: string): string {
  if (relevancia === "alta") return "var(--color-praxis-azul)";
  if (relevancia === "media") return "var(--color-praxis-salmon)";
  return "var(--color-praxis-verde)";
}


export default async function EfemeridesPage() {
  const ctx = await getApiContextServer();

  const [proximas, todas] = await Promise.all([
    proximasEfemerides(ctx, { dias: 60, relevancia_minima: "baja" }),
    listarEfemerides(ctx),
  ]);

  return (
    <main className="mx-auto max-w-6xl px-4 py-8 space-y-8">
      <header className="space-y-1">
        <div className="flex items-center gap-2 text-[var(--color-praxis-azul)]">
          <Calendar className="size-5" />
          <h1 className="font-display text-2xl font-semibold">Efemérides</h1>
        </div>
        <p className="text-sm text-muted-foreground">
          Calendario de fechas conmemorativas con valor parlamentario.
          Generá un proyecto de declaración con un click sobre
          cualquiera.
        </p>
      </header>

      {/* PRÓXIMOS 60 DÍAS */}
      <section className="space-y-3">
        <h2 className="font-display text-sm font-semibold uppercase tracking-wider text-[var(--color-praxis-azul)] flex items-center gap-2">
          <Sparkle className="size-4" />
          Próximos 60 días — {proximas.length} efemérides
        </h2>
        {proximas.length === 0 ? (
          <Card className="p-6 text-center text-sm text-muted-foreground">
            No hay efemérides relevantes en los próximos 60 días.
          </Card>
        ) : (
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            {proximas.map((ef) => (
              <EfemerideCard key={ef.id} efemeride={ef} />
            ))}
          </div>
        )}
      </section>

      {/* TODAS — agrupadas por mes */}
      <section className="space-y-3">
        <h2 className="font-display text-sm font-semibold uppercase tracking-wider text-[var(--color-praxis-azul)]">
          Calendario completo del año — {todas.length} efemérides
        </h2>
        <div className="space-y-2">
          {agruparPorMes(todas).map(({ mes, items }) => (
            <details key={mes} className="rounded-md border border-border bg-card p-3">
              <summary className="cursor-pointer text-sm font-medium uppercase tracking-wider text-[var(--color-praxis-azul)]">
                {NOMBRE_MES[mes - 1]} · {items.length} efemérides
              </summary>
              <ul className="mt-3 space-y-1.5 text-sm">
                {items.map((ef) => (
                  <li key={ef.id} className="flex items-start gap-3">
                    <span
                      className="inline-block w-12 shrink-0 font-mono text-xs font-semibold"
                      style={{ color: relevanciaColor(ef.relevancia) }}
                    >
                      {ef.fecha_corta}
                    </span>
                    <span className="flex-1">{ef.titulo}</span>
                    <Badge
                      variant="outline"
                      className="shrink-0 text-[10px]"
                    >
                      {ef.tipo_label}
                    </Badge>
                  </li>
                ))}
              </ul>
            </details>
          ))}
        </div>
      </section>
    </main>
  );
}


const NOMBRE_MES = [
  "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
];


function agruparPorMes(efs: EfemerideDTO[]): { mes: number; items: EfemerideDTO[] }[] {
  const map = new Map<number, EfemerideDTO[]>();
  for (const ef of efs) {
    const arr = map.get(ef.mes) ?? [];
    arr.push(ef);
    map.set(ef.mes, arr);
  }
  // Ordenar por (mes asc) y dentro por (dia asc)
  const result = Array.from(map.entries()).map(([mes, items]) => ({
    mes,
    items: items.sort((a, b) => a.dia - b.dia),
  }));
  result.sort((a, b) => a.mes - b.mes);
  return result;
}
