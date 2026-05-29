import { ArrowLeft } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EstadoBadge } from "@/components/features/expedientes/estado-badge";
import { MarcarSeguimientoButton } from "@/components/features/expedientes/marcar-seguimiento-button";
import type { ExpedienteFicha } from "@/lib/api/types";
import {
  buildSubtitulo,
  formatFechaCorta,
} from "@/lib/formato-expediente";

interface Props {
  expediente: ExpedienteFicha;
}

export function FichaHeader({ expediente }: Props) {
  const e = expediente;
  return (
    <div className="space-y-3">
      <Button asChild variant="ghost" size="sm" className="-ml-2">
        <Link href="/expedientes">
          <ArrowLeft className="mr-1 size-3.5" />
          Volver a Expedientes
        </Link>
      </Button>

      <Card className="space-y-4 p-6">
        <div className="space-y-1">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {buildSubtitulo(e)}
          </p>
          <h2 className="text-xl font-bold leading-tight tracking-tight">{e.titulo}</h2>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <EstadoBadge estado={e.estado} />
          {e.fecha_caducidad && (
            <p className="text-xs text-muted-foreground">
              Vence{" "}
              <span className="font-medium text-foreground">
                {formatFechaCorta(e.fecha_caducidad)}
              </span>
              {e.prorrogado && " (prorrogado)"}
            </p>
          )}
          <div className="ml-auto">
            <MarcarSeguimientoButton
              expedienteId={e.id}
              seguimiento={e.seguimiento}
            />
          </div>
        </div>
      </Card>
    </div>
  );
}
