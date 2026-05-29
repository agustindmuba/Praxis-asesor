/**
 * Página /expedientes — búsqueda + tabla + paginación.
 *
 * Server Component que:
 * 1. Lee `searchParams` (Next 15: es Promise).
 * 2. Los parsea en un `FiltrosExpediente` (ignorando valores inválidos).
 * 3. Hace `buscarExpedientes(ctx, filtros)` con el ApiContext del request.
 * 4. Renderiza `FiltrosBar` + `ExpedientesTable` + `Paginator`.
 */
import { getApiContextServer } from "@/lib/api/context-server";
import { buscarExpedientes } from "@/lib/api/endpoints";
import {
  filtrosToSearchParams,
  parseFiltrosFromSearchParams,
} from "@/lib/filtros-url";

import { ExpedientesTable } from "@/components/features/expedientes/expedientes-table";
import { FiltrosBar } from "@/components/features/expedientes/filtros-bar";
import { Paginator } from "@/components/features/expedientes/paginator";

export const metadata = { title: "Expedientes" };

interface PageProps {
  // Next 15: searchParams llega como Promise.
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}

export default async function ExpedientesPage({ searchParams }: PageProps) {
  const raw = await searchParams;
  const filtros = parseFiltrosFromSearchParams(raw);

  const ctx = await getApiContextServer();
  const resultado = await buscarExpedientes(ctx, filtros);

  // Para el paginator: query string actual sin el `offset` (lo reescribe).
  const paramsSinOffset = filtrosToSearchParams({ ...filtros, offset: 0 });
  paramsSinOffset.delete("offset");
  const qsSinOffset = paramsSinOffset.toString();

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Expedientes</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Buscá expedientes del catálogo y marcalos para seguimiento.
          </p>
        </div>
      </div>

      <FiltrosBar initial={filtros} />

      <ExpedientesTable resultado={resultado} />

      <Paginator
        total={resultado.total}
        limit={resultado.limit}
        offset={resultado.offset}
        currentQueryStringSinOffset={qsSinOffset}
      />
    </div>
  );
}
