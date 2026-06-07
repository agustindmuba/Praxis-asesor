/**
 * Badge para el estado del expediente. Mapea cada estado a una variante
 * visual con la paleta Praxis (feat/33).
 *
 * Convención cromática:
 * - Verde (#3B6652) → estados positivos (sancionado, media sanción).
 * - Azul (#2A3D75) → estados de tránsito activos (con dictamen, en comisión).
 * - Salmón (#D48D7C) → atención (caduco, archivado).
 * - Crema/muted → neutros (ingresado, desconocido).
 */
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
  // "desconocido" en la DB significa: no tenemos eventos de trámite
  // suficientes para inferir un estado preciso. Para el asesor, la
  // info útil es "está vivo en algún punto del proceso" → "En trámite".
  desconocido: "En trámite",
};

const STYLES: Record<EstadoExpediente, { bg: string; fg: string; ring?: string }> = {
  ingresado: { bg: "#F0EAE8", fg: "#3B362F", ring: "#D8CFCB" },
  en_comision: { bg: "#F0F3FA", fg: "#2A3D75", ring: "#D8DFF0" },
  con_dictamen: { bg: "#2A3D75", fg: "#FFFFFF" },
  media_sancion_hcdn: { bg: "#3B6652", fg: "#FFFFFF" },
  media_sancion_hsn: { bg: "#3B6652", fg: "#FFFFFF" },
  sancionado: { bg: "#3B6652", fg: "#FFFFFF" },
  archivado: { bg: "#FBF3F0", fg: "#9A5F4F", ring: "#E8C7BB" },
  caduco: { bg: "#D48D7C", fg: "#FFFFFF" },
  // "En trámite" en azul Praxis suave — comunica "activo, en proceso"
  // sin gritar como un estado puntual confirmado.
  desconocido: { bg: "#EEF1F8", fg: "#2A3D75", ring: "#D8DFF0" },
};

export function EstadoBadge({ estado }: { estado: EstadoExpediente }) {
  const s = STYLES[estado];
  return (
    <span
      className="inline-flex items-center whitespace-nowrap rounded-md px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-wide"
      style={{
        backgroundColor: s.bg,
        color: s.fg,
        boxShadow: s.ring ? `inset 0 0 0 1px ${s.ring}` : undefined,
      }}
    >
      {LABELS[estado]}
    </span>
  );
}
