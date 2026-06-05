/**
 * /proyectos — lista de proyectos en redacción del despacho (feat-42.3).
 *
 * Server Component. Muestra cards por proyecto con tipo + estado +
 * fecha de actualización. CTA para crear nuevo.
 */
import Link from "next/link";
import { FileText, Plus } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { getApiContextServer } from "@/lib/api/context-server";
import { listarProyectosRedaccion } from "@/lib/api/endpoints";
import type {
  EstadoProyecto,
  ProyectoRedaccionDTO,
  TipoProyecto,
} from "@/lib/api/types";

export const metadata = { title: "Proyectos en redacción" };

const TIPO_LABEL: Record<TipoProyecto, string> = {
  ley: "Proyecto de Ley",
  resolucion: "Proyecto de Resolución",
  comunicacion: "Proyecto de Comunicación",
  declaracion: "Proyecto de Declaración",
};

const ESTADO_COLOR: Record<EstadoProyecto, string> = {
  borrador: "rgb(100 116 139)",
  listo: "var(--color-praxis-verde)",
  presentado: "var(--color-praxis-azul)",
};

const ESTADO_LABEL: Record<EstadoProyecto, string> = {
  borrador: "Borrador",
  listo: "Listo",
  presentado: "Presentado",
};

function formatFecha(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("es-AR", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default async function ProyectosPage() {
  const ctx = await getApiContextServer();
  const proyectos = await listarProyectosRedaccion(ctx).catch(() => []);

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-[10.5px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
            Despacho · Redacción
          </p>
          <h2 className="mt-1 font-display text-3xl font-bold tracking-tight text-[var(--color-praxis-azul)]">
            Proyectos en redacción
          </h2>
          <p className="mt-1.5 text-sm text-muted-foreground">
            Borradores internos antes de presentarse en HCDN. El bot te
            ayuda a redactar articulado, fundamentos y refinar texto.
          </p>
        </div>
        <Link
          href="/proyectos/nuevo"
          className="inline-flex items-center gap-1.5 rounded-md bg-[var(--color-praxis-azul)] px-4 py-2 text-xs font-semibold text-white"
        >
          <Plus className="size-3.5" />
          Nuevo proyecto
        </Link>
      </header>

      {proyectos.length === 0 ? (
        <Card className="border-border bg-card p-6 text-center shadow-none">
          <FileText className="mx-auto size-8 text-[var(--color-praxis-salmon)]" />
          <p className="mt-2.5 text-sm font-medium text-foreground">
            Sin proyectos en redacción
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            Empezá uno nuevo con el botón de arriba. El bot te asiste
            con el articulado y los fundamentos.
          </p>
        </Card>
      ) : (
        <ul className="space-y-2.5">
          {proyectos.map((p) => (
            <ProyectoItem key={p.id} proyecto={p} />
          ))}
        </ul>
      )}
    </div>
  );
}

function ProyectoItem({ proyecto: p }: { proyecto: ProyectoRedaccionDTO }) {
  return (
    <Link href={`/proyectos/${p.id}`} className="block">
      <Card className="border-border bg-card p-4 shadow-none transition-colors hover:border-[var(--color-praxis-salmon)]">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline" className="text-[10px] uppercase">
                {TIPO_LABEL[p.tipo]}
              </Badge>
              <Badge
                className="text-[10px] font-semibold"
                style={{
                  backgroundColor: ESTADO_COLOR[p.estado],
                  color: "white",
                }}
              >
                {ESTADO_LABEL[p.estado]}
              </Badge>
              <span className="text-[10.5px] text-muted-foreground">
                {p.articulado.length} artículos
              </span>
            </div>
            <p className="mt-2 font-medium leading-snug text-foreground">
              {p.titulo}
            </p>
            <p className="mt-1 text-xs text-muted-foreground line-clamp-2">
              {p.sumario}
            </p>
          </div>
          <div className="text-right text-[10.5px] text-muted-foreground">
            <p>Actualizado</p>
            <p>{formatFecha(p.actualizado_en)}</p>
          </div>
        </div>
      </Card>
    </Link>
  );
}
