"use client";

/**
 * Form de creación de proyecto. Después de crear, redirige a /proyectos/[id].
 */
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { Loader2 } from "lucide-react";

import { Card } from "@/components/ui/card";
import { useApiContext } from "@/lib/api/context-client";
import { crearProyectoRedaccion } from "@/lib/api/endpoints";
import type { TipoProyecto } from "@/lib/api/types";

const TIPOS: { value: TipoProyecto; label: string }[] = [
  { value: "ley", label: "Proyecto de Ley" },
  { value: "resolucion", label: "Proyecto de Resolución" },
  { value: "comunicacion", label: "Proyecto de Comunicación (pedido de informes)" },
  { value: "declaracion", label: "Proyecto de Declaración" },
];

export function NuevoProyectoForm() {
  const router = useRouter();
  const resolveCtx = useApiContext();
  const [isPending, startTransition] = useTransition();

  const [tipo, setTipo] = useState<TipoProyecto>("ley");
  const [titulo, setTitulo] = useState("");
  const [sumario, setSumario] = useState("");
  const [autor, setAutor] = useState("JULIANO, PABLO");
  const [error, setError] = useState<string | null>(null);

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    startTransition(async () => {
      try {
        const ctx = await resolveCtx();
        const proyecto = await crearProyectoRedaccion(ctx, {
          tipo,
          titulo: titulo.trim(),
          sumario: sumario.trim(),
          autor_legislador: autor.trim(),
        });
        router.push(`/proyectos/${proyecto.id}`);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "No se pudo crear el proyecto.",
        );
      }
    });
  }

  return (
    <Card className="border-border bg-card p-6 shadow-none">
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-1.5">
          <label className="text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">
            Tipo de proyecto
          </label>
          <select
            value={tipo}
            onChange={(e) => setTipo(e.target.value as TipoProyecto)}
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
          >
            {TIPOS.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </div>

        <div className="space-y-1.5">
          <label className="text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">
            Título corto
          </label>
          <input
            type="text"
            value={titulo}
            onChange={(e) => setTitulo(e.target.value)}
            required
            minLength={3}
            placeholder="Ej. Registro Nacional de Medicamentos Críticos"
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
          />
        </div>

        <div className="space-y-1.5">
          <label className="text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">
            Objeto / sumario (qué propone el proyecto)
          </label>
          <textarea
            value={sumario}
            onChange={(e) => setSumario(e.target.value)}
            required
            minLength={10}
            rows={5}
            placeholder="Describí en 2-4 oraciones qué propone el proyecto. El bot usa esto para generar el articulado."
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm leading-relaxed"
          />
        </div>

        <div className="space-y-1.5">
          <label className="text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">
            Autor (legislador titular del despacho)
          </label>
          <input
            type="text"
            value={autor}
            onChange={(e) => setAutor(e.target.value)}
            placeholder="APELLIDO, NOMBRE"
            className="w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-sm"
          />
        </div>

        {error && (
          <p className="text-xs text-[var(--color-praxis-salmon)]">{error}</p>
        )}

        <div className="flex items-center justify-end gap-2 pt-2">
          <button
            type="submit"
            disabled={isPending || !titulo.trim() || !sumario.trim()}
            className="inline-flex items-center gap-1.5 rounded-md bg-[var(--color-praxis-azul)] px-5 py-2 text-xs font-semibold text-white transition-opacity disabled:opacity-50"
          >
            {isPending && <Loader2 className="size-3.5 animate-spin" />}
            Crear proyecto
          </button>
        </div>
      </form>
    </Card>
  );
}
