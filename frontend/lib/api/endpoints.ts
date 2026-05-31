/**
 * Funciones tipadas por endpoint. Wraps sobre el cliente HTTP genérico.
 *
 * Estas funciones reciben `ApiContext` como argumento explícito → trabajan
 * tanto en server (RSC) como en client (con un context resuelto del hook).
 */

import type { ApiContext } from "./context";
import {
  apiDelete,
  apiGet,
  apiPatch,
  apiPost,
} from "./client";
import type {
  ActualizarSeguimientoBody,
  CrearSeguimientoBody,
  ExpedienteFicha,
  FiltrosExpediente,
  InteligenciaExpedienteDTO,
  MeResponse,
  ResultadoBusquedaDTO,
  ResumenEjecutivoDTO,
  SeguimientoDTO,
} from "./types";

// ---------------------------------------------------------------------------
// /me
// ---------------------------------------------------------------------------

export function getMe(ctx: ApiContext) {
  return apiGet<MeResponse>("/api/v1/me", { ctx });
}

// ---------------------------------------------------------------------------
// /expedientes
// ---------------------------------------------------------------------------

export function buscarExpedientes(
  ctx: ApiContext,
  filtros: FiltrosExpediente = {},
) {
  return apiGet<ResultadoBusquedaDTO>("/api/v1/expedientes", {
    ctx,
    params: filtros as Record<string, string | number | boolean | undefined>,
    next: { revalidate: 30 },
  });
}

export function getExpediente(ctx: ApiContext, id: string) {
  return apiGet<ExpedienteFicha>(`/api/v1/expedientes/${id}`, {
    ctx,
    next: { revalidate: 30 },
  });
}

export function resumirExpediente(ctx: ApiContext, id: string) {
  return apiPost<ResumenEjecutivoDTO>(
    `/api/v1/expedientes/${id}/resumir`,
    {},
    { ctx },
  );
}

export function getInteligenciaExpediente(ctx: ApiContext, id: string) {
  return apiGet<InteligenciaExpedienteDTO>(
    `/api/v1/expedientes/${id}/inteligencia`,
    { ctx, next: { revalidate: 60 } },
  );
}

// ---------------------------------------------------------------------------
// /seguimientos
// ---------------------------------------------------------------------------

export function listarSeguimientos(
  ctx: ApiContext,
  opts: { incluirArchivados?: boolean } = {},
) {
  return apiGet<SeguimientoDTO[]>("/api/v1/seguimientos", {
    ctx,
    params: { incluir_archivados: opts.incluirArchivados ?? false },
  });
}

export function crearSeguimiento(
  ctx: ApiContext,
  body: CrearSeguimientoBody,
) {
  return apiPost<SeguimientoDTO>("/api/v1/seguimientos", body, { ctx });
}

export function actualizarSeguimiento(
  ctx: ApiContext,
  id: string,
  body: ActualizarSeguimientoBody,
) {
  return apiPatch<SeguimientoDTO>(`/api/v1/seguimientos/${id}`, body, {
    ctx,
  });
}

export function archivarSeguimiento(ctx: ApiContext, id: string) {
  return apiDelete<void>(`/api/v1/seguimientos/${id}`, { ctx });
}
