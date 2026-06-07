"use client";

/**
 * Botones de feedback del asesor sobre el accionable (feat-43.2).
 *
 * 3 estados accionables:
 * - ✓ Hecho     → el asesor ejecutó la acción tal cual la sugirió el bot.
 * - ✗ Ignorar   → el asesor decidió NO actuar.
 * - ✏ Diferente → el asesor hizo algo distinto + nota explicando qué.
 *
 * Si el accionable ya tiene estado, mostramos el estado actual con un
 * link sutil "cambiar". Eso evita que el panel se desordene con 3
 * botones cuando ya está decidido.
 *
 * El feedback alimenta el perfil opositor en feat-43.3.
 */
import { useState, useTransition } from "react";
import { CheckCircle2, Edit3, Loader2, X } from "lucide-react";

import { useApiContext } from "@/lib/api/context-client";
import { marcarEstadoAccionable } from "@/lib/api/endpoints";
import type {
  AccionableDTO,
  EstadoAccionable,
} from "@/lib/api/types";

interface Props {
  accionable: AccionableDTO;
  /** Callback opcional cuando el estado cambia (para refrescar la UI padre). */
  onUpdated?: (next: AccionableDTO) => void;
}

const ESTADO_LABEL: Record<EstadoAccionable, string> = {
  pendiente: "Pendiente",
  hecho: "Lo hicimos",
  ignorado: "Lo dejamos pasar",
  adaptado: "Lo hicimos distinto",
};

const ESTADO_COLOR: Record<EstadoAccionable, string> = {
  pendiente: "var(--color-praxis-azul)",
  hecho: "var(--color-praxis-verde)",
  ignorado: "rgb(100 116 139)",
  adaptado: "var(--color-praxis-salmon)",
};

export function FeedbackButtons({ accionable, onUpdated }: Props) {
  const resolveCtx = useApiContext();
  const [isPending, startTransition] = useTransition();
  const [estado, setEstado] = useState(accionable.estado);
  const [nota, setNota] = useState(accionable.nota_asesor ?? "");
  const [mostrandoNota, setMostrandoNota] = useState(false);
  const [mostrandoOpciones, setMostrandoOpciones] = useState(
    estado === "pendiente",
  );
  const [error, setError] = useState<string | null>(null);

  function aplicar(nuevoEstado: EstadoAccionable, notaTexto?: string) {
    if (!accionable.id) return;
    setError(null);
    startTransition(async () => {
      try {
        const ctx = await resolveCtx();
        const nextAcc = await marcarEstadoAccionable(ctx, accionable.id!, {
          estado: nuevoEstado,
          nota: notaTexto,
        });
        setEstado(nextAcc.estado);
        setMostrandoNota(false);
        setMostrandoOpciones(false);
        if (notaTexto !== undefined) setNota(notaTexto);
        onUpdated?.(nextAcc);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "No se pudo guardar el feedback.",
        );
      }
    });
  }

  // Caso 1: ya tiene estado decidido → mostrar pill + "cambiar"
  if (!mostrandoOpciones && estado !== "pendiente") {
    return (
      <div className="flex flex-wrap items-center gap-2 border-t border-border pt-2.5">
        <span className="text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">
          Estado:
        </span>
        <span
          className="inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-wide text-white"
          style={{ backgroundColor: ESTADO_COLOR[estado] }}
        >
          {ESTADO_LABEL[estado]}
        </span>
        {estado === "adaptado" && nota && (
          <span className="basis-full text-[11px] italic text-muted-foreground">
            «{nota}»
          </span>
        )}
        <button
          type="button"
          onClick={() => setMostrandoOpciones(true)}
          className="ml-auto text-[10.5px] font-medium text-muted-foreground underline-offset-2 hover:underline"
          disabled={isPending}
        >
          Cambiar
        </button>
      </div>
    );
  }

  // Caso 2: pendiente o cambiando → mostrar los 3 botones
  return (
    <div className="space-y-2 border-t border-border pt-2.5">
      <p className="text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">
        ¿Qué hiciste con este accionable?
      </p>
      <div className="flex flex-wrap gap-1.5">
        <FeedbackBtn
          icon={<CheckCircle2 className="size-3.5" />}
          label="Lo hicimos"
          color="var(--color-praxis-verde)"
          disabled={isPending}
          onClick={() => aplicar("hecho")}
          active={estado === "hecho"}
        />
        <FeedbackBtn
          icon={<X className="size-3.5" />}
          label="Dejarlo pasar"
          color="rgb(100 116 139)"
          disabled={isPending}
          onClick={() => aplicar("ignorado")}
          active={estado === "ignorado"}
        />
        <FeedbackBtn
          icon={<Edit3 className="size-3.5" />}
          label="Lo hicimos distinto"
          color="var(--color-praxis-salmon)"
          disabled={isPending}
          onClick={() => setMostrandoNota(true)}
          active={estado === "adaptado" || mostrandoNota}
        />
        {isPending && (
          <Loader2 className="ml-1 size-3.5 animate-spin self-center text-muted-foreground" />
        )}
      </div>

      {mostrandoNota && (
        <div className="space-y-1.5">
          <textarea
            value={nota}
            onChange={(e) => setNota(e.target.value)}
            placeholder="¿Qué hicieron en su lugar? Ej. 'En vez de pedido de informes mandamos un tweet apuntando al ministro'"
            rows={2}
            className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-xs"
          />
          <div className="flex gap-1.5">
            <button
              type="button"
              disabled={isPending || !nota.trim()}
              onClick={() => aplicar("adaptado", nota.trim())}
              className="inline-flex items-center gap-1 rounded-md bg-[var(--color-praxis-salmon)] px-2.5 py-1 text-[10.5px] font-semibold text-white disabled:opacity-50"
            >
              Guardar
            </button>
            <button
              type="button"
              disabled={isPending}
              onClick={() => {
                setMostrandoNota(false);
                setNota(accionable.nota_asesor ?? "");
              }}
              className="rounded-md border border-border px-2.5 py-1 text-[10.5px] font-medium text-muted-foreground"
            >
              Cancelar
            </button>
          </div>
        </div>
      )}

      {error && (
        <p className="text-[11px] text-[var(--color-praxis-salmon)]">{error}</p>
      )}
    </div>
  );
}

function FeedbackBtn({
  icon,
  label,
  color,
  disabled,
  onClick,
  active,
}: {
  icon: React.ReactNode;
  label: string;
  color: string;
  disabled?: boolean;
  onClick: () => void;
  active?: boolean;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className="inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-[10.5px] font-semibold transition-colors disabled:opacity-50"
      style={{
        borderColor: active ? color : "var(--border)",
        backgroundColor: active ? color : "transparent",
        color: active ? "#FFFFFF" : color,
      }}
    >
      {icon}
      {label}
    </button>
  );
}
