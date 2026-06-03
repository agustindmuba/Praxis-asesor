"use client";

/**
 * Botones de acción del briefing: imprimir, recargar.
 *
 * Es client component porque "imprimir" llama window.print() sobre el
 * iframe del briefing (que tiene un srcDoc same-origin, así que la
 * cross-frame call está permitida).
 *
 * El botón "Descargar PDF" se sirve desde la propia app vía un route
 * handler interno que proxya al backend con auth — el browser no podría
 * agregar el header Authorization a un click en `<a href>`.
 */
import { FileDown, Printer, RefreshCw } from "lucide-react";
import { useTransition } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";

interface Props {
  briefingId: string;
  odId: string;
}

export function BriefingActions({ briefingId, odId }: Props) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();

  function handleImprimir() {
    // Buscar el iframe del briefing en la página y disparar print sobre él.
    // El srcDoc es same-origin para JS access (lo carga el browser desde un
    // string en memoria, no via red).
    const iframe = document.querySelector<HTMLIFrameElement>(
      'iframe[title^="Briefing"]',
    );
    if (iframe?.contentWindow) {
      iframe.contentWindow.focus();
      iframe.contentWindow.print();
    } else {
      // Fallback: print de la página entera.
      window.print();
    }
  }

  function handleRegenerar() {
    startTransition(() => {
      router.refresh();
    });
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button onClick={handleImprimir} variant="default">
        <Printer className="mr-2 size-4" />
        Imprimir / guardar como PDF
      </Button>
      <Button asChild variant="outline">
        <a
          href={`/briefings/${briefingId}/pdf`}
          target="_blank"
          rel="noopener"
        >
          <FileDown className="mr-2 size-4" />
          Descargar PDF
        </a>
      </Button>
      <Button
        onClick={handleRegenerar}
        variant="ghost"
        disabled={isPending}
        className="ml-auto"
      >
        <RefreshCw className="mr-2 size-4" />
        Recargar
      </Button>
      <span className="hidden text-xs text-muted-foreground" title={odId}>
        OD: {odId.slice(0, 8)}…
      </span>
    </div>
  );
}
