"use client";

/**
 * Card de comisión con expansión para ver integrantes (feat-61.7).
 *
 * Lazy load: el listado de integrantes se trae solo cuando el usuario
 * abre el detalle, no antes (evita 46 fetches innecesarios).
 */
import { useState, useTransition } from "react";
import { ChevronDown, Loader2, ExternalLink } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { useApiContext } from "@/lib/api/context-client";
import {
  detalleComision,
  type ComisionDTO,
  type IntegranteDTO,
} from "@/lib/api/endpoints";


interface Props {
  comision: ComisionDTO;
}


function nombreCorto(nombre: string): string {
  // "ASUNTOS CONSTITUCIONALES" → "Asuntos Constitucionales"
  return nombre
    .split(" ")
    .map(
      (w) =>
        w.length <= 2
          ? w.toLowerCase()
          : w.charAt(0) + w.slice(1).toLowerCase(),
    )
    .join(" ");
}


export function ComisionCard({ comision }: Props) {
  const resolveCtx = useApiContext();
  const [abierto, setAbierto] = useState(false);
  const [integrantes, setIntegrantes] = useState<IntegranteDTO[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function toggle() {
    const proximo = !abierto;
    setAbierto(proximo);
    if (proximo && integrantes === null && !isPending) {
      startTransition(async () => {
        try {
          const ctx = await resolveCtx();
          const det = await detalleComision(ctx, comision.id);
          setIntegrantes(det.integrantes);
        } catch (err) {
          setError(
            err instanceof Error
              ? err.message
              : "No se pudieron cargar los integrantes.",
          );
        }
      });
    }
  }

  return (
    <Card className="border-border bg-card p-4 shadow-none">
      <button
        type="button"
        onClick={toggle}
        className="flex w-full items-start justify-between gap-2 text-left"
      >
        <div className="space-y-1">
          <h3 className="text-sm font-semibold text-foreground">
            {nombreCorto(comision.nombre)}
          </h3>
          <Badge variant="outline" className="text-[10px]">
            {comision.tipo}
          </Badge>
        </div>
        <ChevronDown
          className={
            "size-4 shrink-0 text-muted-foreground transition-transform " +
            (abierto ? "rotate-180" : "")
          }
        />
      </button>

      {abierto && (
        <div className="mt-3 space-y-2 border-t border-border pt-3">
          <a
            href={comision.url_oficial}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-[10.5px] text-[var(--color-praxis-azul)]"
          >
            <ExternalLink className="size-3" />
            Ver en HCDN
          </a>

          {isPending && (
            <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
              <Loader2 className="size-3 animate-spin" />
              Cargando integrantes…
            </div>
          )}

          {error && (
            <p className="text-[11px] text-[var(--color-praxis-salmon)]">
              {error}
            </p>
          )}

          {integrantes && (
            <div className="space-y-2 pt-1">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                {integrantes.length} integrantes
              </div>
              <ul className="space-y-1 text-[11px]">
                {integrantes.map((i) => (
                  <li
                    key={i.id}
                    className="flex items-baseline justify-between gap-2"
                  >
                    <div className="flex-1">
                      <span className="font-medium">{i.nombre_diputado}</span>
                      {i.partido && (
                        <span className="ml-2 text-muted-foreground">
                          ({i.partido})
                        </span>
                      )}
                    </div>
                    <Badge
                      variant="secondary"
                      className="shrink-0 text-[9.5px]"
                    >
                      {i.cargo}
                    </Badge>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
