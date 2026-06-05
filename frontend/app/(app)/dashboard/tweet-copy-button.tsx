"use client";

/**
 * Botón inline para copiar un tweet al portapapeles con feedback visual.
 * Client Component aislado para que el resto del Hub diario sea Server.
 */
import { useState } from "react";
import { CheckCircle2, Copy } from "lucide-react";

export function TweetCopyButton({ texto }: { texto: string }) {
  const [copied, setCopied] = useState(false);

  function copy() {
    navigator.clipboard.writeText(texto).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

  return (
    <button
      type="button"
      onClick={copy}
      className="inline-flex items-center gap-1 text-[10px] font-medium text-muted-foreground hover:text-[var(--color-praxis-azul)]"
    >
      {copied ? (
        <>
          <CheckCircle2 className="size-3 text-[var(--color-praxis-verde)]" />
          Copiado
        </>
      ) : (
        <>
          <Copy className="size-3" />
          Copiar
        </>
      )}
    </button>
  );
}
