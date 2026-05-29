/**
 * Paginator simple para la tabla.
 *
 * Recibe `total/limit/offset` y los `searchParams` actuales para construir
 * URLs preservando los demás filtros.
 *
 * Client Component porque usa el router para navegar, pero también podríamos
 * hacerlo con <Link> puros — usamos botones para deshabilitar cuando estás
 * en el borde.
 */
"use client";

import Link from "next/link";
import { ChevronLeft, ChevronRight } from "lucide-react";

import { Button } from "@/components/ui/button";

interface Props {
  total: number;
  limit: number;
  offset: number;
  /** Query string actual sin los params `offset` — para preservar filtros. */
  currentQueryStringSinOffset: string;
}

export function Paginator({
  total,
  limit,
  offset,
  currentQueryStringSinOffset,
}: Props) {
  if (total <= limit) {
    return (
      <p className="text-xs text-muted-foreground">
        Mostrando {total} de {total} expedientes.
      </p>
    );
  }

  const desde = offset + 1;
  const hasta = Math.min(offset + limit, total);
  const haySiguiente = hasta < total;
  const hayAnterior = offset > 0;

  function urlConOffset(newOffset: number): string {
    const params = new URLSearchParams(currentQueryStringSinOffset);
    if (newOffset > 0) params.set("offset", String(newOffset));
    const qs = params.toString();
    return qs ? `/expedientes?${qs}` : "/expedientes";
  }

  return (
    <div className="flex items-center justify-between">
      <p className="text-xs text-muted-foreground">
        Mostrando <span className="font-medium text-foreground">{desde}–{hasta}</span> de{" "}
        <span className="font-medium text-foreground">{total}</span> expedientes.
      </p>
      <div className="flex gap-1">
        <Button asChild variant="outline" size="sm" disabled={!hayAnterior}>
          {hayAnterior ? (
            <Link href={urlConOffset(Math.max(0, offset - limit))}>
              <ChevronLeft className="size-4" />
              Anterior
            </Link>
          ) : (
            <span className="pointer-events-none opacity-50">
              <ChevronLeft className="size-4" />
              Anterior
            </span>
          )}
        </Button>
        <Button asChild variant="outline" size="sm" disabled={!haySiguiente}>
          {haySiguiente ? (
            <Link href={urlConOffset(offset + limit)}>
              Siguiente
              <ChevronRight className="size-4" />
            </Link>
          ) : (
            <span className="pointer-events-none opacity-50">
              Siguiente
              <ChevronRight className="size-4" />
            </span>
          )}
        </Button>
      </div>
    </div>
  );
}
