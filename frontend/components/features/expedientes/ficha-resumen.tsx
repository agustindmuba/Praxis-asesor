import { ExternalLink, FileText } from "lucide-react";

import { Card } from "@/components/ui/card";
import type { ExpedienteFicha } from "@/lib/api/types";
import { formatFechaLarga, formatTipoExpediente } from "@/lib/formato-expediente";

interface Props {
  expediente: ExpedienteFicha;
}

export function FichaResumen({ expediente }: Props) {
  const e = expediente;
  return (
    <Card className="space-y-6 p-6">
      {e.sumario && (
        <Field label="Sumario">
          <p className="text-sm leading-relaxed text-foreground">{e.sumario}</p>
        </Field>
      )}

      <div className="grid grid-cols-1 gap-x-8 gap-y-4 md:grid-cols-2">
        <Field label="Tipo">{formatTipoExpediente(e.tipo)}</Field>
        <Field label="Cámara">{e.numero.camara}</Field>
        <Field label="Fecha de ingreso">{formatFechaLarga(e.fecha_ingreso)}</Field>
        <Field label="Fecha de caducidad">
          {formatFechaLarga(e.fecha_caducidad)}
          {e.prorrogado && (
            <span className="ml-2 text-xs text-muted-foreground">
              (prorrogado desde {formatFechaLarga(e.fecha_caducidad_original)})
            </span>
          )}
        </Field>
      </div>

      {(e.texto_url || e.fuente_url) && (
        <div className="flex flex-wrap gap-3 pt-2">
          {e.texto_url && (
            <a
              href={e.texto_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 rounded-md border border-border bg-background px-3 py-1.5 text-xs font-medium hover:bg-accent"
            >
              <FileText className="size-3.5" />
              Texto del expediente
              <ExternalLink className="size-3" />
            </a>
          )}
          {e.fuente_url && (
            <a
              href={e.fuente_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 rounded-md border border-border bg-background px-3 py-1.5 text-xs font-medium hover:bg-accent"
            >
              Ver en portal oficial
              <ExternalLink className="size-3" />
            </a>
          )}
        </div>
      )}
    </Card>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </dt>
      <dd className="text-sm text-foreground">{children}</dd>
    </div>
  );
}
