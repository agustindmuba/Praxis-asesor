import { Card } from "@/components/ui/card";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { TramiteEventoDTO } from "@/lib/api/types";
import { formatFechaLarga } from "@/lib/formato-expediente";

interface Props {
  tramite: TramiteEventoDTO[];
}

export function FichaTramite({ tramite }: Props) {
  if (tramite.length === 0) {
    return (
      <Card className="py-12 text-center text-sm text-muted-foreground">
        Sin eventos de trámite registrados.
      </Card>
    );
  }

  return (
    <Card className="p-6">
      <ol className="relative space-y-6 border-l-2 border-border pl-6">
        {tramite.map((t, i) => {
          const esDerivado = t.fuente?.startsWith("derived:");
          return (
            <li key={i} className="relative">
              <span
                className="absolute -left-[1.6rem] top-1.5 size-3 rounded-full border-2 border-background bg-primary"
                aria-hidden
              />
              <div className="flex items-start justify-between gap-4">
                <div className="space-y-1">
                  <p className="text-sm font-medium">{t.evento}</p>
                  {t.detalle && (
                    <p className="text-xs text-muted-foreground">{t.detalle}</p>
                  )}
                </div>
                <div className="flex-shrink-0 text-right">
                  <p className="text-xs text-muted-foreground">
                    {formatFechaLarga(t.fecha)}
                  </p>
                  <p className="mt-0.5 text-xs uppercase text-muted-foreground">
                    {t.camara}
                  </p>
                </div>
              </div>
              {esDerivado && (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span className="mt-1 inline-block cursor-help text-[10px] uppercase tracking-wide text-muted-foreground/70">
                      Evento derivado
                    </span>
                  </TooltipTrigger>
                  <TooltipContent>
                    Este evento se infirió a partir de los timestamps de etapa del portal,
                    no es un evento explícito.
                  </TooltipContent>
                </Tooltip>
              )}
            </li>
          );
        })}
      </ol>
    </Card>
  );
}
