"use client";

/**
 * Editor del proyecto en redacción con 3 asistentes LLM:
 * - Botón "Generar articulado" (sobre el sumario actual).
 * - Botón "Generar fundamentos" (sobre el articulado).
 * - Botón "Refinar" por artículo / por fundamentos.
 *
 * Auto-save al PATCH cuando el usuario hace blur de un input.
 */
import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import {
  Loader2,
  Save,
  PenLine,
  Trash2,
  FileEdit,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { useApiContext } from "@/lib/api/context-client";
import {
  actualizarProyectoRedaccion,
  asistirArticulado,
  asistirFundamentos,
  refinarTexto,
} from "@/lib/api/endpoints";

import { ConflictosPanel } from "./conflictos-panel";
import type {
  EstadoProyecto,
  ProyectoRedaccionDTO,
  TipoProyecto,
} from "@/lib/api/types";

const TIPO_LABEL: Record<TipoProyecto, string> = {
  ley: "Proyecto de Ley",
  resolucion: "Proyecto de Resolución",
  comunicacion: "Proyecto de Comunicación",
  declaracion: "Proyecto de Declaración",
};

const ESTADOS: { value: EstadoProyecto; label: string }[] = [
  { value: "borrador", label: "Borrador" },
  { value: "listo", label: "Listo para firmar" },
  { value: "presentado", label: "Presentado" },
];

interface Props {
  inicial: ProyectoRedaccionDTO;
}

export function ProyectoEditor({ inicial }: Props) {
  const router = useRouter();
  const resolveCtx = useApiContext();
  const [proyecto, setProyecto] = useState<ProyectoRedaccionDTO>(inicial);
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  function guardar(parcial: Partial<ProyectoRedaccionDTO>) {
    setError(null);
    startTransition(async () => {
      try {
        const ctx = await resolveCtx();
        const next = await actualizarProyectoRedaccion(ctx, proyecto.id, {
          tipo: parcial.tipo,
          titulo: parcial.titulo,
          sumario: parcial.sumario,
          articulado: parcial.articulado,
          fundamentos: parcial.fundamentos,
          cofirmantes_sugeridos: parcial.cofirmantes_sugeridos,
          estado: parcial.estado,
          autor_legislador: parcial.autor_legislador,
        });
        setProyecto(next);
        setMsg("Guardado.");
        setTimeout(() => setMsg(null), 1500);
      } catch (err) {
        setError(err instanceof Error ? err.message : "No se pudo guardar.");
      }
    });
  }

  function generarArticulado() {
    setError(null);
    setMsg("Generando articulado con LLM…");
    startTransition(async () => {
      try {
        const ctx = await resolveCtx();
        const next = await asistirArticulado(ctx, proyecto.id);
        setProyecto(next);
        setMsg(`Articulado generado (${next.modelo_asistente ?? "LLM"}).`);
        router.refresh();
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Falló la generación.",
        );
        setMsg(null);
      }
    });
  }

  function generarFundamentos() {
    setError(null);
    setMsg("Generando fundamentos con LLM…");
    startTransition(async () => {
      try {
        const ctx = await resolveCtx();
        const next = await asistirFundamentos(ctx, proyecto.id);
        setProyecto(next);
        setMsg("Fundamentos generados.");
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Falló la generación.",
        );
        setMsg(null);
      }
    });
  }

  return (
    <div className="space-y-5">
      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline" className="text-[10px] uppercase">
            {TIPO_LABEL[proyecto.tipo]}
          </Badge>
          <select
            value={proyecto.estado}
            onChange={(e) =>
              guardar({ estado: e.target.value as EstadoProyecto })
            }
            disabled={isPending}
            className="rounded-md border border-input bg-background px-2 py-0.5 text-[10px] font-semibold uppercase"
          >
            {ESTADOS.map((e) => (
              <option key={e.value} value={e.value}>
                {e.label}
              </option>
            ))}
          </select>
          <span className="text-[10.5px] text-muted-foreground">
            Autor: {proyecto.autor_legislador || "—"}
          </span>
        </div>
        <input
          type="text"
          value={proyecto.titulo}
          onChange={(e) => setProyecto({ ...proyecto, titulo: e.target.value })}
          onBlur={() => guardar({ titulo: proyecto.titulo })}
          className="w-full bg-transparent font-display text-2xl font-bold tracking-tight text-[var(--color-praxis-azul)] focus:outline-none"
        />
      </header>

      {error && (
        <Card className="border-[var(--color-praxis-salmon)]/40 bg-[var(--color-praxis-salmon)]/5 p-3 text-xs text-foreground shadow-none">
          {error}
        </Card>
      )}
      {msg && (
        <Card className="border-[var(--color-praxis-verde)]/40 bg-[var(--color-praxis-verde)]/5 p-3 text-xs text-foreground shadow-none">
          {msg}
        </Card>
      )}

      {/* Sumario / Objeto */}
      <Card className="border-border bg-card p-5 shadow-none">
        <div className="flex items-center justify-between gap-3">
          <p className="text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">
            Objeto del proyecto
          </p>
          <button
            type="button"
            disabled={isPending || !proyecto.sumario.trim()}
            onClick={generarArticulado}
            className="inline-flex items-center gap-1.5 rounded-md bg-[var(--color-praxis-salmon)] px-3 py-1.5 text-[11px] font-semibold text-white transition-opacity disabled:opacity-50"
          >
            {isPending ? (
              <Loader2 className="size-3 animate-spin" />
            ) : (
              <PenLine className="size-3" />
            )}
            {proyecto.articulado.length === 0
              ? "Generar articulado"
              : "Re-generar articulado"}
          </button>
        </div>
        <textarea
          value={proyecto.sumario}
          onChange={(e) =>
            setProyecto({ ...proyecto, sumario: e.target.value })
          }
          onBlur={() => guardar({ sumario: proyecto.sumario })}
          rows={3}
          className="mt-2 w-full rounded-md border border-input bg-background px-3 py-2 text-sm leading-relaxed"
        />
      </Card>

      {/* Articulado */}
      <Card className="border-border bg-card p-5 shadow-none">
        <div className="mb-3 flex items-center justify-between gap-3">
          <p className="text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">
            Articulado ({proyecto.articulado.length})
          </p>
          {proyecto.articulado.length > 0 && (
            <button
              type="button"
              disabled={isPending}
              onClick={generarFundamentos}
              className="inline-flex items-center gap-1.5 rounded-md bg-[var(--color-praxis-salmon)] px-3 py-1.5 text-[11px] font-semibold text-white transition-opacity disabled:opacity-50"
            >
              {isPending ? (
                <Loader2 className="size-3 animate-spin" />
              ) : (
                <PenLine className="size-3" />
              )}
              {proyecto.fundamentos
                ? "Re-generar fundamentos"
                : "Generar fundamentos"}
            </button>
          )}
        </div>
        {proyecto.articulado.length === 0 ? (
          <p className="text-xs italic text-muted-foreground">
            Sin articulado todavía. Generalo con el botón de arriba.
          </p>
        ) : (
          <ul className="space-y-3">
            {proyecto.articulado.map((art, i) => (
              <ArticuloEdit
                key={i}
                texto={art}
                onChange={(t) => {
                  const next = [...proyecto.articulado];
                  next[i] = t;
                  setProyecto({ ...proyecto, articulado: next });
                }}
                onBlur={(t) => {
                  const next = [...proyecto.articulado];
                  next[i] = t;
                  guardar({ articulado: next });
                }}
                onDelete={() => {
                  const next = proyecto.articulado.filter((_, idx) => idx !== i);
                  setProyecto({ ...proyecto, articulado: next });
                  guardar({ articulado: next });
                }}
                onRefinar={async (instruccion) => {
                  try {
                    const ctx = await resolveCtx();
                    const r = await refinarTexto(ctx, {
                      texto: art,
                      instruccion,
                    });
                    const next = [...proyecto.articulado];
                    next[i] = r.texto_refinado;
                    setProyecto({ ...proyecto, articulado: next });
                    guardar({ articulado: next });
                  } catch (err) {
                    setError(
                      err instanceof Error
                        ? err.message
                        : "Falló el refinar.",
                    );
                  }
                }}
              />
            ))}
          </ul>
        )}
      </Card>

      {/* Validación de conflictos normativos */}
      {proyecto.articulado.length > 0 && (
        <ConflictosPanel
          proyectoId={proyecto.id}
          articulosCount={proyecto.articulado.length}
        />
      )}

      {/* Fundamentos */}
      {proyecto.articulado.length > 0 && (
        <Card className="border-border bg-card p-5 shadow-none">
          <p className="text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">
            Fundamentos
          </p>
          <textarea
            value={proyecto.fundamentos}
            onChange={(e) =>
              setProyecto({ ...proyecto, fundamentos: e.target.value })
            }
            onBlur={() => guardar({ fundamentos: proyecto.fundamentos })}
            rows={20}
            placeholder="Generá los fundamentos con el botón arriba, o escribilos a mano. Soporta Markdown."
            className="mt-2 w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs leading-relaxed"
          />
        </Card>
      )}

      {/* Footer save sticky */}
      <div className="sticky bottom-3 flex justify-end">
        <button
          type="button"
          disabled={isPending}
          onClick={() => guardar(proyecto)}
          className="inline-flex items-center gap-1.5 rounded-md bg-[var(--color-praxis-azul)] px-4 py-2 text-xs font-semibold text-white shadow-md transition-opacity disabled:opacity-50"
        >
          {isPending ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <Save className="size-3.5" />
          )}
          Guardar cambios
        </button>
      </div>
    </div>
  );
}

function ArticuloEdit({
  texto,
  onChange,
  onBlur,
  onDelete,
  onRefinar,
}: {
  texto: string;
  onChange: (t: string) => void;
  onBlur: (t: string) => void;
  onDelete: () => void;
  onRefinar: (instruccion: string) => Promise<void>;
}) {
  const [refinarOpen, setRefinarOpen] = useState(false);
  const [instruccion, setInstruccion] = useState("");
  const [pending, setPending] = useState(false);

  async function aplicarRefinar() {
    if (!instruccion.trim()) return;
    setPending(true);
    try {
      await onRefinar(instruccion);
      setRefinarOpen(false);
      setInstruccion("");
    } finally {
      setPending(false);
    }
  }

  return (
    <li className="rounded-md border border-border p-2.5">
      <textarea
        value={texto}
        onChange={(e) => onChange(e.target.value)}
        onBlur={(e) => onBlur(e.target.value)}
        rows={Math.max(3, Math.ceil(texto.length / 100))}
        className="w-full bg-transparent text-xs leading-relaxed text-foreground focus:outline-none"
      />
      <div className="mt-1.5 flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={() => setRefinarOpen(!refinarOpen)}
          className="inline-flex items-center gap-1 text-[10.5px] font-medium text-[var(--color-praxis-azul)] hover:underline"
        >
          <FileEdit className="size-3" />
          Refinar
        </button>
        <button
          type="button"
          onClick={onDelete}
          className="inline-flex items-center gap-1 text-[10.5px] text-muted-foreground hover:text-[var(--color-praxis-salmon)]"
        >
          <Trash2 className="size-3" />
          Quitar
        </button>
      </div>
      {refinarOpen && (
        <div className="mt-2 space-y-1.5 rounded-md bg-muted/30 p-2">
          <input
            type="text"
            value={instruccion}
            onChange={(e) => setInstruccion(e.target.value)}
            placeholder='Ej. "Hacelo más corto" / "Agregá referencia a Ley X" / "Tono más técnico"'
            className="w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-[11px]"
          />
          <div className="flex justify-end gap-1.5">
            <button
              type="button"
              onClick={() => setRefinarOpen(false)}
              className="text-[10.5px] text-muted-foreground hover:text-foreground"
            >
              Cancelar
            </button>
            <button
              type="button"
              disabled={pending || !instruccion.trim()}
              onClick={aplicarRefinar}
              className="inline-flex items-center gap-1 rounded-md bg-[var(--color-praxis-azul)] px-2 py-0.5 text-[10.5px] font-semibold text-white disabled:opacity-50"
            >
              {pending && <Loader2 className="size-2.5 animate-spin" />}
              Aplicar
            </button>
          </div>
        </div>
      )}
    </li>
  );
}
