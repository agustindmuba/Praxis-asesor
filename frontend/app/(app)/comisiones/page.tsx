/**
 * /comisiones — comisiones del despacho + agenda próximas reuniones (feat-61.7).
 *
 * Server Component: fetcha en paralelo /comisiones/del-despacho y
 * /comisiones/agenda-del-despacho con el contexto del request.
 */
import { Calendar, Users, ExternalLink } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { getApiContextServer } from "@/lib/api/context-server";
import {
  agendaDelDespacho,
  comisionesDelDespacho,
  type ComisionDTO,
  type ReunionConComisionDTO,
} from "@/lib/api/endpoints";

import { ComisionCard } from "./comision-card";
import { ReunionCard } from "./reunion-card";

export const metadata = { title: "Comisiones" };

const NOMBRE_MES = [
  "ene", "feb", "mar", "abr", "may", "jun",
  "jul", "ago", "sep", "oct", "nov", "dic",
];

function fechaCorta(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${parseInt(d, 10)} ${NOMBRE_MES[parseInt(m, 10) - 1]}`;
}

function agruparPorFecha(
  reuniones: ReunionConComisionDTO[],
): { fecha: string; items: ReunionConComisionDTO[] }[] {
  const map = new Map<string, ReunionConComisionDTO[]>();
  for (const r of reuniones) {
    const arr = map.get(r.fecha) ?? [];
    arr.push(r);
    map.set(r.fecha, arr);
  }
  return Array.from(map.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([fecha, items]) => ({ fecha, items }));
}

export default async function ComisionesPage() {
  const ctx = await getApiContextServer();
  const [comisiones, agenda] = await Promise.all([
    comisionesDelDespacho(ctx).catch((): ComisionDTO[] => []),
    agendaDelDespacho(ctx, { dias: 30 }).catch(
      (): ReunionConComisionDTO[] => [],
    ),
  ]);

  const agendaAgrupada = agruparPorFecha(agenda);

  return (
    <main className="mx-auto max-w-6xl px-4 py-8 space-y-8">
      <header className="space-y-1">
        <div className="flex items-center gap-2 text-[var(--color-praxis-azul)]">
          <Users className="size-5" />
          <h1 className="font-display text-2xl font-semibold">
            Comisiones del despacho
          </h1>
        </div>
        <p className="text-sm text-muted-foreground">
          Las comisiones donde figura el legislador titular en HCDN, con su
          rol y la agenda de próximas reuniones. Datos del portal oficial.
        </p>
      </header>

      {/* AGENDA PRÓXIMOS 30 DÍAS */}
      <section className="space-y-3">
        <h2 className="flex items-center gap-2 font-display text-sm font-semibold uppercase tracking-wider text-[var(--color-praxis-azul)]">
          <Calendar className="size-4" />
          Próximos 30 días — {agenda.length} reuniones
        </h2>
        {agenda.length === 0 ? (
          <Card className="p-6 text-center text-sm text-muted-foreground">
            No hay reuniones convocadas en las comisiones del despacho para
            los próximos 30 días.
          </Card>
        ) : (
          <div className="space-y-3">
            {agendaAgrupada.map(({ fecha, items }) => (
              <Card
                key={fecha}
                className="border-border bg-card p-4 shadow-none"
              >
                <div className="mb-2 flex items-baseline gap-2">
                  <span className="font-mono text-sm font-bold text-[var(--color-praxis-azul)]">
                    {fechaCorta(fecha)}
                  </span>
                  <Badge variant="outline" className="text-[10px]">
                    {items.length} reunion{items.length === 1 ? "" : "es"}
                  </Badge>
                </div>
                <ul className="space-y-4">
                  {items.map((r) => (
                    <ReunionCard key={r.id} reunion={r} />
                  ))}
                </ul>
              </Card>
            ))}
          </div>
        )}
      </section>

      {/* COMISIONES INTEGRADAS */}
      <section className="space-y-3">
        <h2 className="font-display text-sm font-semibold uppercase tracking-wider text-[var(--color-praxis-azul)]">
          Integra {comisiones.length} comisi
          {comisiones.length === 1 ? "ón" : "ones"} permanente
          {comisiones.length === 1 ? "" : "s"}
        </h2>
        {comisiones.length === 0 ? (
          <Card className="p-6 text-center text-sm text-muted-foreground">
            No detectamos al legislador titular del despacho como integrante
            de ninguna comisión. Verificá el slug del legislador en
            Configuración.
          </Card>
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {comisiones.map((c) => (
              <ComisionCard key={c.id} comision={c} />
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
