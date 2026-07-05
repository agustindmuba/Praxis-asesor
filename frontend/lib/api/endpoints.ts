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

/** Feedback del asesor sobre un accionable (feat-43.2). */
export function marcarEstadoAccionable(
  ctx: ApiContext,
  accionableId: string,
  body: import("./types").EstadoAccionableUpdate,
) {
  return apiPost<AccionableDTO>(
    `/api/v1/accionables/${accionableId}/estado`,
    body,
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

// ---------------------------------------------------------------------------
// /proyectos-redaccion (feat-42.3)
// ---------------------------------------------------------------------------

import type {
  ActualizarProyectoBody,
  CrearProyectoBody,
  ProyectoRedaccionDTO,
  RefinarTextoBody,
  TextoRefinadoDTO,
} from "./types";

export function listarProyectosRedaccion(ctx: ApiContext) {
  return apiGet<ProyectoRedaccionDTO[]>("/api/v1/proyectos-redaccion", { ctx });
}

export function crearProyectoRedaccion(
  ctx: ApiContext, body: CrearProyectoBody,
) {
  return apiPost<ProyectoRedaccionDTO>(
    "/api/v1/proyectos-redaccion", body, { ctx },
  );
}

export function getProyectoRedaccion(ctx: ApiContext, id: string) {
  return apiGet<ProyectoRedaccionDTO>(
    `/api/v1/proyectos-redaccion/${id}`, { ctx },
  );
}

export function actualizarProyectoRedaccion(
  ctx: ApiContext, id: string, body: ActualizarProyectoBody,
) {
  return apiPatch<ProyectoRedaccionDTO>(
    `/api/v1/proyectos-redaccion/${id}`, body, { ctx },
  );
}

export function asistirArticulado(
  ctx: ApiContext, id: string, opts?: { temaOverride?: string },
) {
  return apiPost<ProyectoRedaccionDTO>(
    `/api/v1/proyectos-redaccion/${id}/asistir/articulado`,
    { tema_override: opts?.temaOverride },
    { ctx },
  );
}

export function asistirFundamentos(ctx: ApiContext, id: string) {
  return apiPost<ProyectoRedaccionDTO>(
    `/api/v1/proyectos-redaccion/${id}/asistir/fundamentos`,
    {},
    { ctx },
  );
}

export function refinarTexto(ctx: ApiContext, body: RefinarTextoBody) {
  return apiPost<TextoRefinadoDTO>(
    "/api/v1/proyectos-redaccion/asistir/refinar", body, { ctx },
  );
}

import type { ResultadoValidacionDTO } from "./types";

export function validarConflictosNormativos(ctx: ApiContext, id: string) {
  return apiPost<ResultadoValidacionDTO>(
    `/api/v1/proyectos-redaccion/${id}/validar-conflictos`,
    {},
    { ctx },
  );
}

import type { ResultadoEnvioAhoraDTO } from "./types";

export function enviarBriefingAhora(ctx: ApiContext) {
  return apiPost<ResultadoEnvioAhoraDTO>(
    "/api/v1/briefing-diario/enviar-ahora",
    {},
    { ctx },
  );
}


/** Insights del feedback (feat-43.3). */
export function getInsightsFeedback(ctx: ApiContext) {
  return apiGet<import("./types").InsightsFeedbackDTO>(
    "/api/v1/perfil-opositor/insights-feedback",
    { ctx },
  );
}


/** Huella del legislador titular (feat-46). */
export function getHuellaLegislador(ctx: ApiContext) {
  return apiGet<import("./types").HuellaLegisladorDTO>(
    "/api/v1/legislador-titular/huella",
    { ctx },
  );
}

export function setFotoLegislador(ctx: ApiContext, fotoUrl: string | null) {
  return apiPatch<void>(
    "/api/v1/legislador-titular/foto",
    { foto_url: fotoUrl },
    { ctx },
  );
}


/** Onboarding (feat-44). */
export interface EstadoOnboardingDTO {
  despacho_id: string;
  paso_1_legislador_cargado: boolean;
  paso_2_perfil_opositor_cargado: boolean;
  paso_3_destinatarios_cargados: boolean;
  paso_4_primer_accionable: boolean;
  todo_listo: boolean;
}

export interface ConfigurarDespachoBody {
  legislador_titular_slug: string;
  camara?: "HCDN" | "HSN";
  foto_url?: string | null;
  inferir_perfil?: boolean;
}

export interface ConfigurarDespachoResponse {
  despacho_id: string;
  legislador_titular_slug: string;
  foto_url: string | null;
  perfil_inferido: boolean;
  perfil_id: string | null;
  mensaje: string;
  error_inferencia: string | null;
}

export function getEstadoOnboarding(ctx: ApiContext) {
  return apiGet<EstadoOnboardingDTO>("/api/v1/onboarding/estado", { ctx });
}

export function configurarDespacho(
  ctx: ApiContext, body: ConfigurarDespachoBody,
) {
  return apiPost<ConfigurarDespachoResponse>(
    "/api/v1/onboarding/configurar-despacho",
    body,
    { ctx },
  );
}

// ---------------------------------------------------------------------------
// /efemerides (feat-53)
// ---------------------------------------------------------------------------

export interface EfemerideDTO {
  id: string;
  mes: number;
  dia: number;
  fecha_corta: string;
  titulo: string;
  tipo: string;
  tipo_label: string;
  relevancia: string;
  descripcion: string | null;
  fuente: string | null;
  areas_tematicas: string[];
  anio_unico: number | null;
  es_recurrente: boolean;
}

export interface GenerarDeclaracionResponse {
  efemeride: EfemerideDTO;
  tema_generado: string;
  articulado: string[];
  fundamentos: string;
  modelo: string;
}

export function listarEfemerides(
  ctx: ApiContext,
  opts: { tipo?: string; relevancia?: string } = {},
) {
  return apiGet<EfemerideDTO[]>("/api/v1/efemerides", {
    ctx,
    params: opts as Record<string, string | number | undefined>,
  });
}

export function proximasEfemerides(
  ctx: ApiContext,
  opts: { dias?: number; relevancia_minima?: string } = {},
) {
  return apiGet<EfemerideDTO[]>("/api/v1/efemerides/proximas", {
    ctx,
    params: {
      dias: opts.dias ?? 30,
      relevancia_minima: opts.relevancia_minima ?? "media",
    } as Record<string, string | number | undefined>,
  });
}

export function generarDeclaracionDesdeEfemeride(
  ctx: ApiContext,
  efemerideId: string,
) {
  return apiPost<GenerarDeclaracionResponse>(
    `/api/v1/efemerides/${efemerideId}/generar-declaracion`,
    {},
    { ctx },
  );
}

export async function descargarDeclaracionDocx(
  ctx: ApiContext,
  payload: {
    titulo_efemeride: string;
    articulado: string[];
    fundamentos: string;
  },
): Promise<void> {
  const url = `${API_BASE}/api/v1/efemerides/exportar-docx`;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept:
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  };
  if (ctx.token) {
    headers["Authorization"] = `Bearer ${ctx.token}`;
  }
  if (ctx.despachoId) {
    headers["X-Despacho-Id"] = ctx.despachoId;
  }
  const res = await fetch(url, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(`No se pudo descargar el .docx (HTTP ${res.status})`);
  }
  const blob = await res.blob();
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objectUrl;
  a.download =
    "proyecto_declaracion_" +
    payload.titulo_efemeride
      .toLowerCase()
      .replace(/\s+/g, "_")
      .replace(/[^\w-]+/g, "")
      .slice(0, 60) +
    ".docx";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(objectUrl);
}

// ---------------------------------------------------------------------------
// /calendar (feat-54)
// ---------------------------------------------------------------------------

export interface CalendarUrlResponse {
  url: string;
  token: string;
}

export function getCalendarUrl(ctx: ApiContext) {
  return apiGet<CalendarUrlResponse>("/api/v1/calendar/url", { ctx });
}

export function regenerarCalendarToken(ctx: ApiContext) {
  return apiPost<CalendarUrlResponse>(
    "/api/v1/calendar/regenerar-token",
    {},
    { ctx },
  );
}


// ---------------------------------------------------------------------------
// /comisiones (feat-61.6)
// ---------------------------------------------------------------------------

export interface ComisionDTO {
  id: string;
  camara: string;
  slug: string;
  nombre: string;
  tipo: string;
  url_oficial: string;
}

export interface IntegranteDTO {
  id: string;
  nombre_diputado: string;
  cargo: string;
  partido: string | null;
  distrito: string | null;
}

export interface ComisionDetalleDTO extends ComisionDTO {
  integrantes: IntegranteDTO[];
}

export interface ReunionConComisionDTO {
  id: string;
  fecha: string;
  titulo: string;
  citacion_pdf_url: string | null;
  comision_id: string;
  comision_nombre: string;
  rol_legislador: string | null;
  hora: string | null;
  sala: string | null;
  descripcion: string | null;
  tema_corto: string | null;
  tipo_reunion: string | null;
  convocada_por: string | null;
  oportunidad_politica: string | null;
  accion_sugerida: string | null;
  expedientes_citados: string[];
  enriquecida_en: string | null;
}

export function listarComisiones(ctx: ApiContext) {
  return apiGet<ComisionDTO[]>("/api/v1/comisiones", { ctx });
}

export function comisionesDelDespacho(ctx: ApiContext) {
  return apiGet<ComisionDTO[]>("/api/v1/comisiones/del-despacho", { ctx });
}

export function agendaDelDespacho(ctx: ApiContext, opts: { dias?: number } = {}) {
  return apiGet<ReunionConComisionDTO[]>(
    "/api/v1/comisiones/agenda-del-despacho",
    { ctx, params: { dias: opts.dias ?? 30 } as Record<string, number> },
  );
}

export function detalleComision(ctx: ApiContext, comisionId: string) {
  return apiGet<ComisionDetalleDTO>(
    `/api/v1/comisiones/${comisionId}`,
    { ctx },
  );
}


// ---------------------------------------------------------------------------
// /comisiones — extensión enriquecimiento (feat-61.4.B)
// ---------------------------------------------------------------------------

export interface ReunionEnriquecidaDTO {
  id: string;
  fecha: string;
  hora: string | null;
  sala: string | null;
  titulo: string;
  descripcion: string | null;
  comisiones_invitadas: string[];
  citacion_pdf_url: string | null;
  tema_corto: string | null;
  tipo_reunion: string | null;
  convocada_por: string | null;
  expedientes_citados: string[];
  oportunidad_politica: string | null;
  accion_sugerida: string | null;
  huella_historica: string | null;
  enriquecida_en: string | null;
}

export function enriquecerReunion(ctx: ApiContext, reunionId: string) {
  return apiPost<ReunionEnriquecidaDTO>(
    `/api/v1/comisiones/reuniones/${reunionId}/enriquecer`,
    {},
    { ctx },
  );
}
