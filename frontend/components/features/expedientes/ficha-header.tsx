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

      <Card className="space-y-4 border-border bg-card p-6 shadow-none">
        <div className="space-y-1.5">
          <p className="text-[10.5px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
            {buildSubtitulo(e)}
          </p>
          <h2 className="font-display text-[22px] font-bold leading-snug tracking-tight text-[var(--color-praxis-azul)]">
            {e.titulo}
          </h2>
        </div>

        <div className="flex flex-wrap items-center gap-3 border-t border-border pt-3">
          <EstadoBadge estado={e.estado} />
          {e.fecha_caducidad && (
            <p className="text-xs text-muted-foreground">
              Vence{" "}
              <span className="font-semibold text-foreground">
                {formatFechaCorta(e.fecha_caducidad)}
              </span>
              {e.prorrogado && (
                <span className="ml-1 text-[var(--color-praxis-salmon)]">
                  · prorrogado
                </span>
              )}
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
