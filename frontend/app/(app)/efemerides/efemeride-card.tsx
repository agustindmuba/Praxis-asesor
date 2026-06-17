"use client";

/**
 * Card de una efeméride + botón "Generar declaración" (feat-53.5).
 *
 * Al hacer click dispara POST /api/v1/efemerides/{id}/generar-declaracion
 * que llama al LLM y devuelve articulado + fundamentos. El resultado
 * se muestra en un panel desplegable abajo de la card.
 */
import { useState, useTransition } from "react";
import { FileEdit, PenLine, Loader2, AlertCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { useApiContext } from "@/lib/api/context-client";
import {
  generarDeclaracionDesdeEfemeride,
  type EfemerideDTO,
  type GenerarDeclaracionResponse,
} from "@/lib/api/endpoints";


interface Props {
  efemeride: EfemerideDTO;
}

const NOMBRE_MES = [
  "Ene", "Feb", "Mar", "Abr", "May", "Jun",
  "Jul", "Ago", "Sep", "Oct", "Nov", "Dic",
];


function relevanciaColor(relevancia: string): string {
  if (relevancia === "alta") return "var(--color-praxis-azul)";
  if (relevancia === "media") return "var(--color-praxis-salmon)";
  return "var(--color-praxis-verde)";
}


function relevanciaLabel(relevancia: string): string {
  return relevancia.toUpperCase();
}


export function EfemerideCard({ efemeride }: Props) {
  const resolveCtx = useApiContext();
  const [isPending, startTransition] = useTransition();
  const [resultado, setResultado] = useState<GenerarDeclaracionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  function generar() {
    setError(null);
    setResultado(null);
    startTransition(async () => {
      try {
        const ctx = await resolveCtx();
        const r = await generarDeclaracionDesdeEfemeride(ctx, efemeride.id);
        setResultado(r);
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "No se pudo generar la declaración.",
        );
      }
    });
  }

  const color = relevanciaColor(efemeride.relevancia);

  return (
    <Card className="flex flex-col gap-3 border-border bg-card p-4 shadow-none">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-baseline gap-2">
          <span
            className="font-mono text-sm font-bold"
            style={{ color }}
          >
            {efemeride.dia} {NOMBRE_MES[efemeride.mes - 1]}
          </span>
          <Badge
            variant="outline"
            className="text-[10px]"
            style={{ borderColor: color, color }}
          >
            {relevanciaLabel(efemeride.relevancia)}
          </Badge>
        </div>
        <Badge variant="outline" className="text-[10px] text-muted-foreground">
          {efemeride.tipo_label}
        </Badge>
      </div>

      <h3 className="text-sm font-semibold leading-snug">{efemeride.titulo}</h3>

      {efemeride.descripcion && (
        <p className="text-xs text-muted-foreground leading-relaxed">
          {efemeride.descripcion}
        </p>
      )}

      {efemeride.fuente && (
        <p className="text-[10.5px] text-muted-foreground">
          <strong className="font-medium">Fuente:</strong> {efemeride.fuente}
        </p>
      )}

      {efemeride.areas_tematicas.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {efemeride.areas_tematicas.map((a) => (
            <Badge key={a} variant="secondary" className="text-[10px]">
              {a.replace(/_/g, " ")}
            </Badge>
          ))}
        </div>
      )}

      <div className="mt-auto pt-1">
        <button
          type="button"
          disabled={isPending}
          onClick={generar}
          className="inline-flex w-full items-center justify-center gap-1.5 rounded-md bg-[var(--color-praxis-azul)] px-3 py-2 text-[11px] font-semibold text-white transition-opacity disabled:opacity-50"
        >
          {isPending ? (
            <>
              <Loader2 className="size-3.5 animate-spin" />
              Redactando proyecto…
            </>
          ) : (
            <>
              <PenLine className="size-3.5" />
              Generar proyecto de declaración
            </>
          )}
        </button>
      </div>

      {/* Resultado */}
      {error && (
        <div className="flex items-start gap-2 rounded-md border border-[var(--color-praxis-salmon)] bg-[var(--color-praxis-salmon)]/10 p-2 text-[11px] text-[var(--color-praxis-salmon)]">
          <AlertCircle className="size-3.5 shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {resultado && (
        <div className="space-y-2 rounded-md border border-[var(--color-praxis-verde)] bg-[var(--color-praxis-verde)]/5 p-3 text-xs">
          <div className="flex items-center gap-1.5 font-semibold text-[var(--color-praxis-verde)]">
            <FileEdit className="size-3.5" />
            Proyecto generado — {resultado.modelo}
          </div>

          <details open>
            <summary className="cursor-pointer text-[11px] font-medium text-foreground">
              Articulado · {resultado.articulado.length} artículo{resultado.articulado.length === 1 ? "" : "s"}
            </summary>
            <ol className="mt-1.5 space-y-1.5 pl-4 text-[11px]">
              {resultado.articulado.map((art, i) => (
                <li key={i} className="leading-relaxed">{art}</li>
              ))}
            </ol>
          </details>

          <details>
            <summary className="cursor-pointer text-[11px] font-medium text-foreground">
              Fundamentos
            </summary>
            <div className="mt-1.5 whitespace-pre-wrap text-[11px] leading-relaxed text-muted-foreground">
              {resultado.fundamentos}
            </div>
          </details>

          <details>
            <summary className="cursor-pointer text-[10px] font-medium text-muted-foreground">
              Contexto enviado al modelo (debug)
            </summary>
            <pre className="mt-1.5 whitespace-pre-wrap rounded bg-muted/30 p-2 text-[10px] text-muted-foreground">
              {resultado.tema_generado}
            </pre>
          </details>
        </div>
      )}
    </Card>
  );
}
