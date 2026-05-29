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
      <Card className="flex flex-col items-center justify-center gap-2 py-12 text-center">
        <FileText className="size-8 text-muted-foreground" />
        <p className="text-sm font-medium">No hay expedientes que matcheen los filtros.</p>
        <p className="text-xs text-muted-foreground">
          Probá con menos filtros o cambiá el texto de búsqueda.
        </p>
      </Card>
    );
  }

  return (
    <Card className="overflow-hidden p-0">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-[160px]">N°</TableHead>
            <TableHead>Título</TableHead>
            <TableHead className="w-[140px]">Cámara</TableHead>
            <TableHead className="w-[180px]">Estado</TableHead>
            <TableHead className="w-[120px]">Ingreso</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {resultado.items.map((e) => (
            <TableRow key={e.id} className="cursor-pointer hover:bg-muted/40">
              <TableCell className="font-mono text-xs">
                <Link href={`/expedientes/${e.id}`} className="block">
                  {formatNumero(e)}
                </Link>
              </TableCell>
              <TableCell>
                <Link href={`/expedientes/${e.id}`} className="block">
                  <span className="line-clamp-1 text-sm font-medium">{e.titulo}</span>
                  {e.sumario && (
                    <span className="line-clamp-1 text-xs text-muted-foreground">
                      {e.sumario}
                    </span>
                  )}
                </Link>
              </TableCell>
              <TableCell>
                <Link href={`/expedientes/${e.id}`} className="block text-xs uppercase">
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
