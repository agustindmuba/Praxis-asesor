/**
 * Helpers de formato visual de expedientes.
 *
 * Estos helpers son puros y testeables (no dependen de hooks o fetch).
 */
import type {
  ExpedienteBase,
  NumeroExpedienteDTO,
  Prioridad,
  TipoExpediente,
} from "@/lib/api/types";

/** Número HCDN (NNNN-X-YYYY) o HSN (NNNN/YY) según corresponda. */
export function formatNumeroExpediente(n: NumeroExpedienteDTO): string {
  if (n.camara === "HCDN") {
    return `${n.numero.toString().padStart(4, "0")}-${n.origen}-${n.anio}`;
  }
  return `${n.numero}/${(n.anio % 100).toString().padStart(2, "0")}`;
}

/** ISO `YYYY-MM-DD` → `DD/MM/YYYY`. Devuelve "—" para null. */
export function formatFechaCorta(iso: string | null): string {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y}`;
}

/** Para fechas con día de la semana, ej. "lunes 15 de marzo de 2024". */
export function formatFechaLarga(iso: string | null): string {
  if (!iso) return "—";
  try {
    const date = new Date(iso + "T00:00:00");
    return new Intl.DateTimeFormat("es-AR", {
      weekday: "long",
      day: "numeric",
      month: "long",
      year: "numeric",
    }).format(date);
  } catch {
    return iso;
  }
}

const TIPO_LABELS: Record<TipoExpediente, string> = {
  proyecto_ley: "Proyecto de Ley",
  proyecto_resolucion: "Proyecto de Resolución",
  proyecto_declaracion: "Proyecto de Declaración",
  proyecto_comunicacion: "Proyecto de Comunicación",
  mensaje_pe: "Mensaje del PE",
  decreto: "Decreto",
  otro: "Otro",
};

export function formatTipoExpediente(tipo: TipoExpediente): string {
  return TIPO_LABELS[tipo];
}

const PRIORIDAD_LABELS: Record<Prioridad, string> = {
  alta: "Alta",
  media: "Media",
  baja: "Baja",
};

export function formatPrioridad(p: Prioridad): string {
  return PRIORIDAD_LABELS[p];
}

/** Subtítulo de la ficha: "HCDN · Proyecto de Ley · 1497-D-2024" */
export function buildSubtitulo(e: Pick<ExpedienteBase, "numero" | "tipo">): string {
  return [
    e.numero.camara,
    formatTipoExpediente(e.tipo),
    formatNumeroExpediente(e.numero),
  ].join(" · ");
}
