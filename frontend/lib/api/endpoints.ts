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

// ---------------------------------------------------------------------------
// /noticias + /menciones + /fuentes (feat-40 — spec 16)
// ---------------------------------------------------------------------------

import type {
  ArticuloDetalleDTO,
  ArticuloRelevanteConArticuloDTO,
  FuenteNoticiaDTO,
  MencionConArticuloDTO,
  TonoMencion,
} from "./types";

export function listarNoticiasRelevantes(ctx: ApiContext, topN?: number) {
  return apiGet<ArticuloRelevanteConArticuloDTO[]>(
    "/api/v1/noticias",
    {
      ctx,
      params: { top_n: topN },
      next: { revalidate: 60 },
    },
  );
}

export function getNoticiaDetalle(ctx: ApiContext, id: string) {
  return apiGet<ArticuloDetalleDTO>(`/api/v1/noticias/${id}`, {
    ctx,
    next: { revalidate: 60 },
  });
}

export interface FiltrosMenciones {
  desde?: string;
  hasta?: string;
  tono?: TonoMencion;
  fuente_id?: string;
}

export function listarMenciones(ctx: ApiContext, filtros?: FiltrosMenciones) {
  return apiGet<MencionConArticuloDTO[]>("/api/v1/menciones", {
    ctx,
    params: { ...filtros },
    next: { revalidate: 60 },
  });
}

export function getMencionDetalle(ctx: ApiContext, id: string) {
  return apiGet<MencionConArticuloDTO>(`/api/v1/menciones/${id}`, {
    ctx,
    next: { revalidate: 60 },
  });
}

export function listarFuentesNoticias(ctx: ApiContext) {
  return apiGet<FuenteNoticiaDTO[]>("/api/v1/fuentes", {
    ctx,
    next: { revalidate: 3600 },
  });
}

// ---------------------------------------------------------------------------
// /destinatarios + /envios-whatsapp + /plantillas (feat-41.5)
// ---------------------------------------------------------------------------

import type {
  ActualizarDestinatarioBody,
  CrearDestinatarioBody,
  DestinatarioDTO,
  EnvioWhatsAppDTO,
  PlantillaWhatsAppDTO,
  TipoEnvioWhatsApp,
} from "./types";

export function listarDestinatarios(
  ctx: ApiContext,
  opts?: { soloActivos?: boolean },
) {
  return apiGet<DestinatarioDTO[]>("/api/v1/destinatarios", {
    ctx,
    params: { solo_activos: opts?.soloActivos },
    next: { revalidate: 30 },
  });
}

export function crearDestinatario(
  ctx: ApiContext,
  body: CrearDestinatarioBody,
) {
  return apiPost<DestinatarioDTO>("/api/v1/destinatarios", body, { ctx });
}

export function actualizarDestinatario(
  ctx: ApiContext,
  id: string,
  body: ActualizarDestinatarioBody,
) {
  return apiPatch<DestinatarioDTO>(`/api/v1/destinatarios/${id}`, body, {
    ctx,
  });
}

export function eliminarDestinatario(ctx: ApiContext, id: string) {
  return apiDelete<void>(`/api/v1/destinatarios/${id}`, { ctx });
}

export interface FiltrosEnviosWhatsApp {
  desde?: string;
  hasta?: string;
  tipo?: TipoEnvioWhatsApp;
}

export function listarEnviosWhatsApp(
  ctx: ApiContext,
  filtros?: FiltrosEnviosWhatsApp,
) {
  return apiGet<EnvioWhatsAppDTO[]>("/api/v1/envios-whatsapp", {
    ctx,
    params: { ...filtros },
    next: { revalidate: 30 },
  });
}

export function listarPlantillasWhatsApp(
  ctx: ApiContext,
  opts?: { soloAprobadas?: boolean },
) {
  return apiGet<PlantillaWhatsAppDTO[]>("/api/v1/plantillas", {
    ctx,
    params: { solo_aprobadas: opts?.soloAprobadas },
    next: { revalidate: 3600 },
  });
}

// ---------------------------------------------------------------------------
// /perfil-opositor (feat-42.1)
// ---------------------------------------------------------------------------

import type {
  ActualizarPerfilBody,
  InferirPerfilBody,
  PerfilOpositorDTO,
} from "./types";

export function getPerfilOpositor(ctx: ApiContext) {
  return apiGet<PerfilOpositorDTO | null>("/api/v1/perfil-opositor", { ctx });
}

export function inferirPerfilOpositor(
  ctx: ApiContext,
  body: InferirPerfilBody,
) {
  return apiPost<PerfilOpositorDTO>(
    "/api/v1/perfil-opositor/inferir",
    body,
    { ctx },
  );
}

export function actualizarPerfilOpositor(
  ctx: ApiContext,
  body: ActualizarPerfilBody,
) {
  return apiPatch<PerfilOpositorDTO>("/api/v1/perfil-opositor", body, {
    ctx,
  });
}

// ---------------------------------------------------------------------------
// /accionables (feat-42.2)
// ---------------------------------------------------------------------------

import type { AccionableDTO } from "./types";

export function getAccionableBo(ctx: ApiContext, normaId: string) {
  return apiGet<AccionableDTO | null>(`/api/v1/accionables/bo/${normaId}`, {
    ctx,
  });
}

export function generarAccionableBo(
  ctx: ApiContext,
  normaId: string,
  opts?: { regenerar?: boolean },
) {
  return apiPost<AccionableDTO>(
    `/api/v1/accionables/bo/${normaId}/generar?regenerar=${opts?.regenerar ?? false}`,
    {},
    { ctx },
  );
}

export function getAccionableArticulo(ctx: ApiContext, articuloId: string) {
  return apiGet<AccionableDTO | null>(
    `/api/v1/accionables/articulo/${articuloId}`,
    { ctx },
  );
}

export function generarAccionableArticulo(
  ctx: ApiContext,
  articuloId: string,
  opts?: { regenerar?: boolean },
) {
  return apiPost<AccionableDTO>(
    `/api/v1/accionables/articulo/${articuloId}/generar?regenerar=${opts?.regenerar ?? false}`,
    {},
    { ctx },
  );
}

// ---------------------------------------------------------------------------
// /briefing-diario/preview (feat-42.4)
// ---------------------------------------------------------------------------

import type { BriefingDiarioPreviewDTO } from "./types";

export function previewBriefingDiario(
  ctx: ApiContext,
  opts?: { fecha?: string },
) {
  return apiGet<BriefingDiarioPreviewDTO>(
    "/api/v1/briefing-diario/preview",
    { ctx, params: { fecha: opts?.fecha } },
  );
}

// ---------------------------------------------------------------------------
// /hub-diario (feat-42.5)
// ---------------------------------------------------------------------------

import type { HubDiarioDTO } from "./types";

export function getHubDiario(ctx: ApiContext) {
  return apiGet<HubDiarioDTO>("/api/v1/hub-diario", {
    ctx,
    next: { revalidate: 30 },
  });
}
