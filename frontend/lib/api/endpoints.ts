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
  apiGetText,
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
  NormaBOAccionableConNormaDTO,
  NormaBODetalleDTO,
  NormaBODTO,
  OrdenDelDiaCrear,
  OrdenDelDiaDTO,
  ReclasificarPerfilResponse,
  ResolverNumerosBody,
  ResolverNumerosResponse,
  ResultadoBusquedaDTO,
  ResumenEjecutivoDTO,
  SeccionBO,
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

export function resolverNumeros(
  ctx: ApiContext,
  body: ResolverNumerosBody,
) {
  return apiPost<ResolverNumerosResponse>(
    "/api/v1/expedientes/resolver-numeros",
    body,
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
 * Fetch del HTML pre-renderizado del briefing.
 *
 * Lo usamos desde el Server Component que renderiza /briefings/[id]:
 * el HTML viaja como string al cliente y se embebe en `<iframe srcDoc>`,
 * lo que evita que el browser tenga que hacer un sub-request al endpoint
 * sin headers de auth.
 */
export function getBriefingHtml(ctx: ApiContext, id: string): Promise<string> {
  return apiGetText(`/api/v1/briefings/${id}/html`, { ctx });
}

/**
 * URLs absolutas al HTML/PDF del briefing (para abrir en pestaña aparte
 * o link de download). Estas URLs NO van a funcionar en un iframe `src`
 * porque el browser no incluye headers de auth — para embebido usar
 * `getBriefingHtml` y srcDoc.
 */
const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function briefingHtmlUrl(id: string): string {
  return `${API_BASE}/api/v1/briefings/${id}/html`;
}

export function briefingPdfUrl(id: string): string {
  return `${API_BASE}/api/v1/briefings/${id}/pdf`;
}

// ---------------------------------------------------------------------------
// /bo (feat-39 — Boletín Oficial)
// ---------------------------------------------------------------------------

export function listarNormasBO(
  ctx: ApiContext,
  fecha: string,
  seccion?: SeccionBO,
) {
  return apiGet<NormaBODTO[]>("/api/v1/bo/normas", {
    ctx,
    params: { fecha, seccion },
    next: { revalidate: 60 },
  });
}

export function getNormaBO(ctx: ApiContext, id: string) {
  return apiGet<NormaBODetalleDTO>(`/api/v1/bo/normas/${id}`, {
    ctx,
    next: { revalidate: 60 },
  });
}

export function listarAccionablesBO(
  ctx: ApiContext,
  fecha: string,
  topN?: number,
) {
  return apiGet<NormaBOAccionableConNormaDTO[]>(
    "/api/v1/bo/accionables",
    {
      ctx,
      params: { fecha, top_n: topN },
      next: { revalidate: 60 },
    },
  );
}

export function reclasificarPerfilBO(ctx: ApiContext, fecha: string) {
  return apiPost<ReclasificarPerfilResponse>(
    `/api/v1/bo/normas/reclasificar-perfil?fecha=${fecha}`,
    {},
    { ctx },
  );
}
