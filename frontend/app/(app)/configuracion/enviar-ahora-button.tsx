"use client";

/**
 * Botón "Enviar ahora" del briefing diario (feat-41.7).
 *
 * Dispara POST /briefing-diario/enviar-ahora. Muestra confirmación con
 * los contadores y avisa si el sender fue real (Meta) o fake.
 */
import { useState, useTransition } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Loader2,
  Send,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { useApiContext } from "@/lib/api/context-client";
import { enviarBriefingAhora } from "@/lib/api/endpoints";
import type { ResultadoEnvioAhoraDTO } from "@/lib/api/types";

export function EnviarAhoraButton() {
  const resolveCtx = useApiContext();
  const [isPending, startTransition] = useTransition();
  const [resultado, setResultado] = useState<ResultadoEnvioAhoraDTO | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);

  function enviar() {
    setError(null);
    setResultado(null);
    startTransition(async () => {
      try {
        const ctx = await resolveCtx();
        const r = await enviarBriefingAhora(ctx);
        setResultado(r);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Falló el envío.",
        );
      }
    });
  }

  return (
    <Card className="border-border bg-card p-4 shadow-none">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Send className="size-4 text-[var(--color-praxis-azul)]" />
          <p className="text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">
            Enviar briefing ahora (no esperar al cron 7am)
          </p>
        </div>
        <button
          type="button"
          disabled={isPending}
          onClick={enviar}
          className="inline-flex items-center gap-1.5 rounded-md bg-[var(--color-praxis-azul)] px-3 py-1.5 text-[11px] font-semibold text-white transition-opacity disabled:opacity-50"
        >
          {isPending ? (
            <Loader2 className="size-3 animate-spin" />
          ) : (
            <Send className="size-3" />
          )}
          Enviar ahora
        </button>
      </div>

      {error && (
        <p className="mt-2 text-xs text-[var(--color-praxis-salmon)]">
          {error}
        </p>
      )}

      {resultado && (
        <div className="mt-3 space-y-1.5 rounded-md border border-border bg-muted/30 px-3 py-2 text-xs">
          <div className="flex items-center gap-2">
            {resultado.enviados_ok > 0 ? (
              <CheckCircle2 className="size-3.5 text-[var(--color-praxis-verde)]" />
            ) : (
              <AlertCircle className="size-3.5 text-[var(--color-praxis-salmon)]" />
            )}
            <p className="font-medium text-foreground">
              {resultado.enviados_ok} enviado{resultado.enviados_ok !== 1 ? "s" : ""}{" "}
              · {resultado.fallidos_transitorios} fallidos transitorios ·{" "}
              {resultado.rechazados} rechazados
            </p>
            {resultado.sender_real ? (
              <Badge className="bg-[var(--color-praxis-verde)] text-[9.5px] text-white">
                Meta real
              </Badge>
            ) : (
              <Badge variant="outline" className="text-[9.5px]">
                Fake sender
              </Badge>
            )}
          </div>
          <p className="text-muted-foreground">
            Destinatarios objetivo: {resultado.destinatarios_objetivo}
          </p>
          {resultado.sin_contenido && (
            <p className="text-muted-foreground">
              Sin contenido para hoy — el briefing no se mandó.
            </p>
          )}
          {resultado.errores.length > 0 && (
            <details className="mt-1">
              <summary className="cursor-pointer text-[10.5px] text-muted-foreground">
                {resultado.errores.length} errores (click)
              </summary>
              <ul className="mt-1 ml-3 list-disc text-[10.5px] text-muted-foreground">
                {resultado.errores.map((e, i) => (
                  <li key={i}>{e}</li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </Card>
  );
}
