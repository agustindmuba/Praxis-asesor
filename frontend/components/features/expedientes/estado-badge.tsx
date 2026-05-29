/**
 * Badge para el estado del expediente. Mapea cada estado a una variante
 * visual y a un label legible.
 */
import { Badge } from "@/components/ui/badge";
import type { EstadoExpediente } from "@/lib/api/types";

const LABELS: Record<EstadoExpediente, string> = {
  ingresado: "Ingresado",
  en_comision: "En comisión",
  con_dictamen: "Con dictamen",
  media_sancion_hcdn: "Media sanción HCDN",
  media_sancion_hsn: "Media sanción HSN",
  sancionado: "Sancionado",
  archivado: "Archivado",
  caduco: "Caduco",
  desconocido: "Desconocido",
};

const VARIANTS: Record<EstadoExpediente, "default" | "secondary" | "outline" | "destructive"> = {
  ingresado: "outline",
  en_comision: "secondary",
  con_dictamen: "default",
  media_sancion_hcdn: "default",
  media_sancion_hsn: "default",
  sancionado: "default",
  archivado: "outline",
  caduco: "destructive",
  desconocido: "outline",
};

export function EstadoBadge({ estado }: { estado: EstadoExpediente }) {
  return (
    <Badge variant={VARIANTS[estado]} className="whitespace-nowrap">
      {LABELS[estado]}
    </Badge>
  );
}
