/**
 * Tabla de expedientes (Server Component).
 *
 * Recibe el `ResultadoBusquedaDTO` ya resuelto (la página padre hace el fetch
 * en RSC). Renderiza filas con número, título, tipo, estado, fecha.
 */
import Link from "next/link";
import { FileText } from "lucide-react";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Card } from "@/components/ui/card";
import type { ExpedienteResumen, ResultadoBusquedaDTO } from "@/lib/api/types";

import { EstadoBadge } from "./estado-badge";

function formatNumero(e: ExpedienteResumen): string {
  if (e.numero.camara === "HCDN") {
    return `${e.numero.numero.toString().padStart(4, "0")}-${e.numero.origen}-${e.numero.anio}`;
  }
  // HSN: formato NNNN/YY
  return `${e.numero.numero}/${(e.numero.anio % 100).toString().padStart(2, "0")}`;
}

function formatFecha(iso: string | null): string {
  if (!iso) return "—";
  // YYYY-MM-DD → DD/MM/YYYY para legibilidad de asesor argentino.
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y}`;
}

export function ExpedientesTable({ resultado }: { resultado: ResultadoBusquedaDTO }) {
  if (resultado.items.length === 0) {
    return (
      <Card className="flex flex-col items-center justify-center gap-3 border-border bg-card py-16 text-center shadow-none">
        <FileText className="size-9 text-[var(--color-praxis-salmon)]" />
        <p className="font-display text-base font-semibold text-[var(--color-praxis-azul)]">
          No hay expedientes que matcheen los filtros
        </p>
        <p className="max-w-md text-xs text-muted-foreground">
          Probá con menos filtros o cambiá el texto de búsqueda.
        </p>
      </Card>
    );
  }

  return (
    <Card className="overflow-hidden border-border bg-card p-0 shadow-none">
      <Table>
        <TableHeader className="bg-[var(--color-praxis-crema)]/60">
          <TableRow className="border-border">
            <TableHead className="w-[160px] text-[10.5px] font-semibold uppercase tracking-wide text-[var(--color-praxis-azul)]">
              N°
            </TableHead>
            <TableHead className="text-[10.5px] font-semibold uppercase tracking-wide text-[var(--color-praxis-azul)]">
              Título
            </TableHead>
            <TableHead className="w-[120px] text-[10.5px] font-semibold uppercase tracking-wide text-[var(--color-praxis-azul)]">
              Cámara
            </TableHead>
            <TableHead className="w-[180px] text-[10.5px] font-semibold uppercase tracking-wide text-[var(--color-praxis-azul)]">
              Estado
            </TableHead>
            <TableHead className="w-[120px] text-[10.5px] font-semibold uppercase tracking-wide text-[var(--color-praxis-azul)]">
              Ingreso
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {resultado.items.map((e) => (
            <TableRow
              key={e.id}
              className="cursor-pointer border-border transition-colors hover:bg-[var(--color-praxis-crema)]/60"
            >
              <TableCell className="font-mono text-[11px] uppercase tracking-wide text-muted-foreground">
                <Link href={`/expedientes/${e.id}`} className="block">
                  {formatNumero(e)}
                </Link>
              </TableCell>
              <TableCell>
                <Link href={`/expedientes/${e.id}`} className="block">
                  <span className="line-clamp-1 text-[13.5px] font-medium leading-snug">
                    {e.titulo}
                  </span>
                  {e.sumario && (
                    <span className="line-clamp-1 text-[11.5px] text-muted-foreground">
                      {e.sumario}
                    </span>
                  )}
                </Link>
              </TableCell>
              <TableCell>
                <Link
                  href={`/expedientes/${e.id}`}
                  className="block text-[10.5px] font-semibold uppercase tracking-wide text-muted-foreground"
                >
                  {e.numero.camara}
                </Link>
              </TableCell>
              <TableCell>
                <Link href={`/expedientes/${e.id}`} className="block">
                  <EstadoBadge estado={e.estado} />
                </Link>
              </TableCell>
              <TableCell className="text-xs text-muted-foreground">
                <Link href={`/expedientes/${e.id}`} className="block">
                  {formatFecha(e.fecha_ingreso)}
                </Link>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Card>
  );
}
