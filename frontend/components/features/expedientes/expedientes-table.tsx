/**
 * Tabla de expedientes (Server Component).
 *
 * v2 (feat-43.1.2): pasa de tabla excel-style a filas con jerarquía:
 * - Tipo (badge color) a la izquierda → escaneo rápido por categoría.
 * - Título en sentence case → deja de gritar en MAYÚSCULAS.
 * - N° + fecha + cámara en metadata gris debajo del título.
 * - Estado (badge) + bandera de caducidad a la derecha.
 *
 * Las filas siguen siendo clickeables (link al detalle) — mantenemos la
 * affordance, mejoramos el ritmo visual.
 */
import Link from "next/link";
import { ChevronRight, FileText } from "lucide-react";

import { Card } from "@/components/ui/card";
import type { ExpedienteResumen, ResultadoBusquedaDTO } from "@/lib/api/types";

import { CaducidadWarning } from "./caducidad-warning";
import { EstadoBadge } from "./estado-badge";
import { TipoBadge } from "./tipo-badge";

function formatNumero(e: ExpedienteResumen): string {
  if (e.numero.camara === "HCDN") {
    return `${e.numero.numero.toString().padStart(4, "0")}-${e.numero.origen}-${e.numero.anio}`;
  }
  // HSN: formato NNNN/YY
  return `${e.numero.numero}/${(e.numero.anio % 100).toString().padStart(2, "0")}`;
}

const MESES = [
  "ene", "feb", "mar", "abr", "may", "jun",
  "jul", "ago", "sep", "oct", "nov", "dic",
];

function formatFecha(iso: string | null): string {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-");
  const mes = MESES[Number(m) - 1] ?? m;
  return `${d} ${mes} ${y}`;
}

/**
 * Convierte "PEDIDO DE INFORMES AL PODER EJECUTIVO..." a sentence case.
 * Mantiene siglas comunes en mayúsculas (PEN, PE, ANSES, AFIP, INDEC, etc.)
 * para no perder información.
 */
const SIGLAS = new Set([
  "PEN", "PE", "PEJ", "ANSES", "AFIP", "ARCA", "INDEC", "BCRA", "ANMAT",
  "ENACOM", "AABE", "JGM", "HSN", "HCDN", "CSJN", "DNU", "DNI", "DNRPA",
  "OEA", "ONU", "PBI", "PCIA", "PCIAS", "PROV", "S.A", "SA", "SRL", "AMBA",
  "INTA", "INTI", "CONICET", "IAF", "ARSAT", "AYSA", "GBA",
]);

function toSentenceCase(s: string): string {
  if (!s) return s;
  // Si NO está todo en mayúsculas, dejamos como está.
  if (s !== s.toUpperCase()) return s;
  const lower = s.toLowerCase();
  // Capitalizamos: primera letra de la oración + primera de cada token
  // que era una sigla original.
  const tokens = s.split(/(\s+|[.,;:()/-])/);
  const lowerTokens = lower.split(/(\s+|[.,;:()/-])/);
  const out: string[] = [];
  let isStart = true;
  for (let i = 0; i < tokens.length; i++) {
    const original = tokens[i] ?? "";
    const cur = lowerTokens[i] ?? "";
    if (/^\s+$/.test(original) || /^[.,;:()/-]+$/.test(original)) {
      out.push(original);
      if (/[.!?]/.test(original)) isStart = true;
      continue;
    }
    if (!cur) {
      out.push(original);
      continue;
    }
    // Mantener siglas como vinieron.
    if (SIGLAS.has(original)) {
      out.push(original);
      isStart = false;
      continue;
    }
    if (isStart) {
      out.push(cur.charAt(0).toUpperCase() + cur.slice(1));
      isStart = false;
    } else {
      out.push(cur);
    }
  }
  return out.join("");
}

export function ExpedientesTable({
  resultado,
}: {
  resultado: ResultadoBusquedaDTO;
}) {
  if (resultado.items.length === 0) {
    return (
      <Card className="flex flex-col items-center justify-center gap-3 border-border bg-card py-16 text-center shadow-none">
        <FileText className="size-9 text-[var(--color-praxis-salmon)]" />
        <p className="font-display text-base font-semibold text-[var(--color-praxis-azul)]">
          No hay expedientes que matcheen los filtros
        </p>
        <p className="max-w-md text-xs text-muted-foreground">
          Probá con menos filtros o cambiá el texto de búsqueda.
        </p>
      </Card>
    );
  }

  return (
    <Card className="overflow-hidden border-border bg-card p-0 shadow-none">
      <ul className="divide-y divide-border">
        {resultado.items.map((e) => (
          <li key={e.id}>
            <Link
              href={`/expedientes/${e.id}`}
              className="group flex cursor-pointer items-start gap-3 px-4 py-3 transition-colors hover:bg-[var(--color-praxis-crema)]"
            >
              {/* Tipo: chip color a la izquierda — escaneo rápido */}
              <div className="pt-0.5">
                <TipoBadge tipo={e.tipo} />
              </div>

              {/* Título + metadata abajo */}
              <div className="min-w-0 flex-1">
                <p className="line-clamp-2 text-[13.5px] font-medium leading-snug text-foreground">
                  {toSentenceCase(e.titulo)}
                </p>
                {e.sumario && (
                  <p className="mt-0.5 line-clamp-1 text-[11.5px] text-muted-foreground">
                    {toSentenceCase(e.sumario)}
                  </p>
                )}
                <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[10.5px] text-muted-foreground">
                  <span className="font-mono uppercase tracking-wide">
                    {formatNumero(e)}
                  </span>
                  <span className="text-border">·</span>
                  <span className="font-semibold uppercase tracking-wide">
                    {e.numero.camara}
                  </span>
                  <span className="text-border">·</span>
                  <span>{formatFecha(e.fecha_ingreso)}</span>
                </div>
              </div>

              {/* Estado + caducidad a la derecha */}
              <div className="flex shrink-0 flex-col items-end gap-1 pt-0.5">
                <EstadoBadge estado={e.estado} />
                <CaducidadWarning fechaCaducidad={e.fecha_caducidad} />
              </div>

              {/* Caret de "ir al detalle" — aparece on hover */}
              <ChevronRight
                className="mt-1 size-4 shrink-0 text-muted-foreground/40 transition-colors group-hover:text-[var(--color-praxis-azul)]"
                aria-hidden
              />
            </Link>
          </li>
        ))}
      </ul>
    </Card>
  );
}
