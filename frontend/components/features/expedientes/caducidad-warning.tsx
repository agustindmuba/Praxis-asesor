/**
 * Bandera de caducidad por Ley 13.640 (feat-43.1.2).
 *
 * Si el expediente vence en <= 60 días, mostramos un warning con dos
 * intensidades:
 * - 31-60 días: amarillo suave (heads up, hay margen).
 * - 0-30 días: rojo (urgente, hay que actuar).
 *
 * Si ya pasó la fecha o no hay caducidad, devuelve null (no renderiza).
 */
import { AlertTriangle } from "lucide-react";

const UMBRAL_DIAS = 60;
const UMBRAL_URGENTE = 30;

function diasDesde(iso: string | null): number | null {
  if (!iso) return null;
  // Parseo simple YYYY-MM-DD evitando problemas de timezone.
  const [y, m, d] = iso.split("-").map(Number);
  if (!y || !m || !d) return null;
  const fecha = new Date(y, m - 1, d).getTime();
  const hoy = new Date();
  hoy.setHours(0, 0, 0, 0);
  const ms = fecha - hoy.getTime();
  return Math.round(ms / 86_400_000);
}

export function CaducidadWarning({
  fechaCaducidad,
}: {
  fechaCaducidad: string | null;
}) {
  const dias = diasDesde(fechaCaducidad);
  if (dias === null || dias > UMBRAL_DIAS || dias < 0) return null;

  const urgente = dias <= UMBRAL_URGENTE;
  const palabra = dias === 1 ? "día" : "días";
  const texto = dias === 0 ? "Caduca hoy" : `Caduca en ${dias} ${palabra}`;

  return (
    <span
      className="inline-flex items-center gap-1 whitespace-nowrap rounded-md px-2 py-0.5 text-[10.5px] font-semibold"
      style={{
        backgroundColor: urgente ? "#D48D7C" : "#FBE8C6",
        color: urgente ? "#FFFFFF" : "#7C5E1F",
        boxShadow: urgente ? undefined : "inset 0 0 0 1px #E8D5A8",
      }}
      title={`Ley 13.640: pierde estado parlamentario el ${fechaCaducidad}`}
    >
      <AlertTriangle className="size-3" />
      {texto}
    </span>
  );
}
