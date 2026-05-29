import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { FirmanteDTO, GiroDTO } from "@/lib/api/types";

interface Props {
  firmantes: FirmanteDTO[];
  giros: GiroDTO[];
}

export function FichaFirmantes({ firmantes, giros }: Props) {
  return (
    <div className="space-y-6">
      <Card className="overflow-hidden p-0">
        <div className="border-b border-border bg-muted/40 px-4 py-2">
          <h4 className="text-sm font-semibold">Firmantes ({firmantes.length})</h4>
        </div>
        {firmantes.length === 0 ? (
          <p className="px-4 py-6 text-center text-sm text-muted-foreground">
            Sin firmantes registrados.
          </p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[80px]">#</TableHead>
                <TableHead>Nombre</TableHead>
                <TableHead>Distrito</TableHead>
                <TableHead>Bloque</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {firmantes.map((f) => (
                <TableRow key={`${f.orden}-${f.nombre}`}>
                  <TableCell>
                    {f.orden === 1 ? (
                      <Badge variant="default">{f.orden}</Badge>
                    ) : (
                      <span className="text-xs text-muted-foreground">{f.orden}</span>
                    )}
                  </TableCell>
                  <TableCell className="text-sm font-medium">{f.nombre}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {f.distrito ?? "—"}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {f.bloque ?? "—"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>

      <Card className="overflow-hidden p-0">
        <div className="border-b border-border bg-muted/40 px-4 py-2">
          <h4 className="text-sm font-semibold">Giros a comisión ({giros.length})</h4>
        </div>
        {giros.length === 0 ? (
          <p className="px-4 py-6 text-center text-sm text-muted-foreground">
            No fue girado a comisión todavía.
          </p>
        ) : (
          <ul className="divide-y divide-border">
            {giros.map((g, i) => (
              <li key={i} className="px-4 py-3">
                <p className="text-sm font-medium">{g.comision}</p>
                {(g.fecha_ingreso || g.fecha_egreso) && (
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {g.fecha_ingreso && <>Ingreso: {g.fecha_ingreso}</>}
                    {g.fecha_ingreso && g.fecha_egreso && " · "}
                    {g.fecha_egreso && <>Egreso: {g.fecha_egreso}</>}
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
