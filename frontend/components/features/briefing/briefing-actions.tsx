"use client";

/**
 * Botones de acción del briefing: imprimir, descargar HTML, descargar PDF.
 *
 * Es client component porque "imprimir" abre window.print() sobre el iframe.
 */
import { Download, Printer, RefreshCw } from "lucide-react";
import { useTransition } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { briefingHtmlUrl, briefingPdfUrl } from "@/lib/api/endpoints";

interface Props {
  briefingId: string;
  odId: string;
}

export function BriefingActions({ briefingId, odId }: Props) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const htmlUrl = briefingHtmlUrl(briefingId);
  const pdfUrl = briefingPdfUrl(briefingId);

  function handleImprimir() {
    // Abre el HTML en una pestaña nueva y dispara print desde ahí.
    // Más confiable que window.print() del iframe (cross-origin issues).
    const w = window.open(htmlUrl, "_blank");
    if (w) {
      w.addEventListener("load", () => w.print());
    }
  }

  function handleRegenerar() {
    startTransition(() => {
      // El backend regenera al pasar regenerar=true, pero como Next cachea
      // la página, hacemos refresh para que vuelva a fetchear.
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
        <a href={htmlUrl} target="_blank" rel="noopener">
          <Download className="mr-2 size-4" />
          Abrir HTML en pestaña
        </a>
      </Button>
      <Button asChild variant="outline">
        <a href={pdfUrl} target="_blank" rel="noopener">
          <Download className="mr-2 size-4" />
          Descargar PDF (si está disponible)
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
