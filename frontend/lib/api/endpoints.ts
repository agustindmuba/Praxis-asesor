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
  BriefingCrear,
  BriefingDTO,
  CrearSeguimientoBody,
  ExpedienteFicha,
  FiltrosExpediente,
  InteligenciaExpedienteDTO,
  MeResponse,
  OrdenDelDiaCrear,
  OrdenDelDiaDTO,
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

// ---------------------------------------------------------------------------
// /ordenes-del-dia
// ---------------------------------------------------------------------------

export function crearOrdenDelDia(ctx: ApiContext, body: OrdenDelDiaCrear) {
  return apiPost<OrdenDelDiaDTO>("/api/v1/ordenes-del-dia", body, { ctx });
}

export function listarOrdenesDelDia(ctx: ApiContext) {
  return apiGet<OrdenDelDiaDTO[]>("/api/v1/ordenes-del-dia", { ctx });
}

export function getOrdenDelDia(ctx: ApiContext, id: string) {
  return apiGet<OrdenDelDiaDTO>(`/api/v1/ordenes-del-dia/${id}`, { ctx });
}

// ---------------------------------------------------------------------------
// /briefings
// ---------------------------------------------------------------------------

export function generarBriefing(ctx: ApiContext, body: BriefingCrear) {
  return apiPost<BriefingDTO>("/api/v1/briefings", body, { ctx });
}

export function getBriefing(ctx: ApiContext, id: string) {
  return apiGet<BriefingDTO>(`/api/v1/briefings/${id}`, { ctx });
}

/**
 * URLs absolutas al HTML/PDF del briefing (para iframe o link de download).
 * No invocan el endpoint — solo arman la URL contra la API pública.
 */
const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function briefingHtmlUrl(id: string): string {
  return `${API_BASE}/api/v1/briefings/${id}/html`;
}

export function briefingPdfUrl(id: string): string {
  return `${API_BASE}/api/v1/briefings/${id}/pdf`;
}
