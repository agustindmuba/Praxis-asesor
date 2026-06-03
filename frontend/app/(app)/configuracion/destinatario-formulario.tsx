"use client";

/**
 * Formulario inline para crear destinatarios WhatsApp (feat-41.5).
 *
 * Client Component porque tiene estado local + form handler que
 * llama al endpoint POST. Usa el cliente API con el context resuelto
 * desde el provider de contexto del cliente.
 */
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { Card } from "@/components/ui/card";
import { useApiContext } from "@/lib/api/context-client";
import { crearDestinatario } from "@/lib/api/endpoints";
import type { RolDestinatario } from "@/lib/api/types";

const ROLES: { value: RolDestinatario; label: string }[] = [
  { value: "legislador", label: "Legislador" },
  { value: "jefe_asesores", label: "Jefe de asesores" },
  { value: "asesor", label: "Asesor" },
  { value: "otro", label: "Otro" },
];

export function DestinatarioFormulario() {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const resolveCtx = useApiContext();

  const [nombre, setNombre] = useState("");
  const [rol, setRol] = useState<RolDestinatario>("asesor");
  const [telefono, setTelefono] = useState("");
  const [briefing, setBriefing] = useState(true);
  const [menciones, setMenciones] = useState(true);
  const [otras, setOtras] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function reset() {
    setNombre("");
    setRol("asesor");
    setTelefono("");
    setBriefing(true);
    setMenciones(true);
    setOtras(false);
    setError(null);
  }

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    startTransition(async () => {
      try {
        const ctx = await resolveCtx();
        await crearDestinatario(ctx, {
          nombre: nombre.trim(),
          rol_interno: rol,
          telefono_e164: telefono.trim(),
          recibe_briefing_diario: briefing,
          recibe_alertas_menciones: menciones,
          recibe_alertas_otras: otras,
        });
        reset();
        router.refresh();
      } catch (err) {
        if (err instanceof Error) {
          setError(err.message);
        } else {
          setError("No se pudo crear el destinatario.");
        }
      }
    });
  }

  return (
    <Card className="border-border bg-card p-5 shadow-none">
      <form className="space-y-3" onSubmit={handleSubmit}>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <label className="space-y-1 text-xs">
            <span className="font-medium text-foreground">Nombre</span>
            <input
              type="text"
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              required
              placeholder="Pablo Juliano"
              className="w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-sm"
            />
          </label>
          <label className="space-y-1 text-xs">
            <span className="font-medium text-foreground">Rol</span>
            <select
              value={rol}
              onChange={(e) => setRol(e.target.value as RolDestinatario)}
              className="w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-sm"
            >
              {ROLES.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-1 text-xs">
            <span className="font-medium text-foreground">
              Teléfono (E.164)
            </span>
            <input
              type="tel"
              value={telefono}
              onChange={(e) => setTelefono(e.target.value)}
              required
              placeholder="+5491155551234"
              className="w-full rounded-md border border-input bg-background px-2.5 py-1.5 font-mono text-sm"
            />
          </label>
        </div>

        <fieldset className="space-y-1.5">
          <legend className="text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">
            Canales que recibe
          </legend>
          <div className="flex flex-wrap gap-3">
            <label className="flex items-center gap-1.5 text-xs">
              <input
                type="checkbox"
                checked={briefing}
                onChange={(e) => setBriefing(e.target.checked)}
              />
              Briefing diario
            </label>
            <label className="flex items-center gap-1.5 text-xs">
              <input
                type="checkbox"
                checked={menciones}
                onChange={(e) => setMenciones(e.target.checked)}
              />
              Alertas de menciones
            </label>
            <label className="flex items-center gap-1.5 text-xs">
              <input
                type="checkbox"
                checked={otras}
                onChange={(e) => setOtras(e.target.checked)}
              />
              Otras alertas (BO)
            </label>
          </div>
        </fieldset>

        {error && (
          <p className="text-xs text-[var(--color-praxis-salmon)]">{error}</p>
        )}

        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={isPending}
            className="inline-flex items-center justify-center gap-1.5 rounded-md bg-[var(--color-praxis-azul)] px-4 py-1.5 text-xs font-semibold text-white transition-opacity disabled:opacity-50"
          >
            {isPending ? "Guardando…" : "Agregar destinatario"}
          </button>
          <p className="text-[11px] text-muted-foreground">
            El destinatario queda en{" "}
            <span className="font-medium">pendiente opt-in</span> hasta
            que confirme por WhatsApp.
          </p>
        </div>
      </form>
    </Card>
  );
}
