/**
 * Badge para el tipo de expediente (feat-43.1.2).
 *
 * Color por tipo, alineado con la paleta Praxis (feat/33). El asesor
 * distingue de un vistazo qué clase de pieza parlamentaria es:
 *
 * - Azul Praxis  → Proyecto de Ley (la pieza pesada).
 * - Verde        → Proyecto de Resolución (la cámara expresa voluntad).
 * - Salmón       → Pedido de Informes / Comunicación (control PEN).
 * - Gris         → Declaración (declarativo, no obliga).
 * - Crema/muted  → Mensaje PE, decreto, otro.
 */
import type { TipoExpediente } from "@/lib/api/types";

const LABELS: Record<TipoExpediente, string> = {
  proyecto_ley: "Ley",
  proyecto_resolucion: "Resolución",
  proyecto_declaracion: "Declaración",
  proyecto_comunicacion: "Comunicación",
  mensaje_pe: "Mensaje PE",
  decreto: "Decreto",
  otro: "Otro",
};

const STYLES: Record<TipoExpediente, { bg: string; fg: string; ring?: string }> = {
  proyecto_ley: { bg: "#2A3D75", fg: "#FFFFFF" },
  proyecto_resolucion: { bg: "#3B6652", fg: "#FFFFFF" },
  proyecto_declaracion: { bg: "#E6E0DE", fg: "#5A5D6E", ring: "#C9C3C1" },
  proyecto_comunicacion: { bg: "#D48D7C", fg: "#FFFFFF" },
  mensaje_pe: { bg: "#F0EAE8", fg: "#3B362F", ring: "#D8CFCB" },
  decreto: { bg: "#F0EAE8", fg: "#3B362F", ring: "#D8CFCB" },
  otro: { bg: "#F0EAE8", fg: "#5A5D6E", ring: "#D8CFCB" },
};

export function TipoBadge({ tipo }: { tipo: TipoExpediente }) {
  const s = STYLES[tipo];
  return (
    <span
      className="inline-flex w-[88px] items-center justify-center whitespace-nowrap rounded-md px-2 py-1 text-[10.5px] font-semibold uppercase tracking-wide"
      style={{
        backgroundColor: s.bg,
        color: s.fg,
        boxShadow: s.ring ? `inset 0 0 0 1px ${s.ring}` : undefined,
      }}
    >
      {LABELS[tipo]}
    </span>
  );
}
