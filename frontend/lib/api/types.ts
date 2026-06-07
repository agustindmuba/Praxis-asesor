/**
 * Tipos mínimos del contrato API, escritos a mano hasta que tengamos
 * `pnpm gen:api-types` generando desde `/openapi.json` del backend.
 *
 * Convención: nombres alineados con los DTOs del backend
 * (`praxis/api/schemas/`). Si el backend cambia, hay que regenerar.
 */

export type Camara = "HCDN" | "HSN";

export type OrigenExpediente =
  | "D"
  | "S"
  | "PE"
  | "JGM"
  | "CD"
  | "CS"
  | "P"
  | "OV"
  | "OTRO";

export type TipoExpediente =
  | "proyecto_ley"
  | "proyecto_resolucion"
  | "proyecto_declaracion"
  | "proyecto_comunicacion"
  | "mensaje_pe"
  | "decreto"
  | "otro";

export type EstadoExpediente =
  | "ingresado"
  | "en_comision"
  | "con_dictamen"
  | "media_sancion_hcdn"
  | "media_sancion_hsn"
  | "sancionado"
  | "archivado"
  | "caduco"
  | "desconocido";

export type Rol = "jefe_asesores" | "asesor" | "lector";

export type Prioridad = "alta" | "media" | "baja";

// ---------------------------------------------------------------------------
// /me
// ---------------------------------------------------------------------------

export interface UsuarioDTO {
  id: string;
  email: string;
  nombre: string;
}

export interface DespachoDTO {
  id: string;
  nombre: string;
}

export interface MeResponse {
  usuario: UsuarioDTO;
  despacho: DespachoDTO;
  rol: Rol;
}

// ---------------------------------------------------------------------------
// /expedientes
// ---------------------------------------------------------------------------

export interface NumeroExpedienteDTO {
  numero: number;
  origen: OrigenExpediente;
  anio: number;
  camara: Camara;
}

export interface FirmanteDTO {
  nombre: string;
  distrito: string | null;
  bloque: string | null;
  orden: number;
}

export interface GiroDTO {
  comision: string;
  fecha_ingreso: string | null;
  fecha_egreso: string | null;
  orden: number | null;
}

export interface TramiteEventoDTO {
  fecha: string | null;
  camara: Camara;
  evento: string;
  detalle: string | null;
  fuente: string | null;
}

export interface ExpedienteBase {
  id: string;
  numero: NumeroExpedienteDTO;
  tipo: TipoExpediente;
  titulo: string;
  sumario: string | null;
  fecha_ingreso: string | null;
  estado: EstadoExpediente;
  fecha_caducidad: string | null;
  fecha_caducidad_original: string | null;
  prorrogado: boolean;
  texto_url: string | null;
  fuente_url: string | null;
}

export type ExpedienteResumen = ExpedienteBase;

export interface ExpedienteFicha extends ExpedienteBase {
  firmantes: FirmanteDTO[];
  giros: GiroDTO[];
  tramite: TramiteEventoDTO[];
  seguimiento: SeguimientoDTO | null;
}

export interface ResultadoBusquedaDTO {
  items: ExpedienteResumen[];
  total: number;
  limit: number;
  offset: number;
}

export interface FiltrosExpediente {
  texto?: string;
  anio?: number;
  tipo?: TipoExpediente;
  camara?: Camara;
  origen?: OrigenExpediente;
  estado?: EstadoExpediente;
  autor_nombre?: string;
  comision?: string;
  fecha_ingreso_desde?: string;
  fecha_ingreso_hasta?: string;
  // Filtros derivados del despacho activo (feat-43.1).
  area_tematica?: AreaTematica;
  con_dictamen?: boolean;
  por_caducar?: boolean;
  por_caducar_dias?: number;
  solo_seguidos?: boolean;   // con seguimiento del despacho actual
  solo_titular?: boolean;    // firmados por el legislador titular
  limit?: number;
  offset?: number;
}

// ---------------------------------------------------------------------------
// /seguimientos
// ---------------------------------------------------------------------------

export interface SeguimientoDTO {
  id: string;
  expediente_id: string;
  responsable_id: string | null;
  prioridad: Prioridad;
  archivado: boolean;
}

// ---------------------------------------------------------------------------
// /expedientes/{id}/resumir
// ---------------------------------------------------------------------------

export interface ResumenEjecutivoDTO {
  id: string;
  expediente_id: string;
  contenido_md: string;
  modelo: string;
  prompt_version: string;
  generado_en: string;
}

// ---------------------------------------------------------------------------
// /expedientes/{id}/inteligencia
// ---------------------------------------------------------------------------

export type EtapaPipeline =
  | "ingresado"
  | "en_comision"
  | "con_dictamen"
  | "media_sancion"
  | "sancionado";

export interface EtapaProgresoDTO {
  etapa: EtapaPipeline;
  label: string;
  alcanzada: boolean;
  fecha: string | null;
}

export interface ProgresoTramiteDTO {
  etapa_actual: EtapaPipeline | null;
  etapas: EtapaProgresoDTO[];
  dias_en_etapa_actual: number | null;
  terminado: boolean;
  motivo_terminacion: string | null;
}

export interface ComparacionPeersDTO {
  peer_count: number;
  mediana_dias: number | null;
  diferencia_porcentual: number | null;
  criterio: string;
}

export interface InteligenciaExpedienteDTO {
  progreso: ProgresoTramiteDTO;
  peers: ComparacionPeersDTO;
}

export interface CrearSeguimientoBody {
  expediente_id: string;
  prioridad?: Prioridad;
}

export interface ActualizarSeguimientoBody {
  responsable_id?: string | null;
  archivado?: boolean;
}

// ---------------------------------------------------------------------------
// /ordenes-del-dia + /briefings (feat/29 + feat/30)
// ---------------------------------------------------------------------------

export type FuenteOd = "upload_manual" | "scraping_hcdn";

export interface OrdenDelDiaCrear {
  camara: Camara;
  fecha_sesion: string; // YYYY-MM-DD
  expedientes_ids: string[];
  hora_sesion?: string; // HH:MM
  titulo?: string;
}

export interface OrdenDelDiaDTO {
  id: string;
  camara: Camara;
  fecha_sesion: string;
  hora_sesion: string | null;
  titulo: string | null;
  fuente: FuenteOd;
  expedientes_ids: string[];
  creado_en: string | null;
}

export type AreaTematica =
  | "educacion"
  | "salud"
  | "trabajo"
  | "seguridad"
  | "justicia"
  | "economia"
  | "ambiente"
  | "derechos_humanos"
  | "infraestructura"
  | "transporte"
  | "relaciones_exteriores"
  | "otros";

export type PrioridadAlerta = "alta" | "media" | "baja";
export type RolEnDespacho = "autor" | "cofirmante";
export type RecomendacionVoto =
  | "a_favor"
  | "abstencion"
  | "en_contra"
  | "sin_recomendacion";

export interface AlertaDTO {
  prioridad: PrioridadAlerta;
  titulo: string;
  detalle: string;
  expediente_id: string | null;
}

export interface CofirmanteSugeridoDTO {
  nombre: string;
  bloque: string | null;
  distrito: string | null;
  proyectos_similares_firmados: number;
  razon: string;
}

export interface AntecedenteParecidoDTO {
  numero: NumeroExpedienteDTO;
  titulo: string;
  estado_terminal: EstadoExpediente;
  similitud: number;
}

export interface SeccionProyectoDTO {
  expediente_id: string;
  numero: NumeroExpedienteDTO;
  titulo: string;
  estado: EstadoExpediente;
  tipo: TipoExpediente;
  rol_despacho: RolEnDespacho;
  area: AreaTematica;
  dias_en_etapa: number | null;
  argumentos: string[];
  contraargumentos: string[];
  cofirmantes_naturales: CofirmanteSugeridoDTO[];
  antecedente: AntecedenteParecidoDTO | null;
}

export interface ProyectoEnAreaDTO {
  expediente_id: string;
  numero: NumeroExpedienteDTO;
  titulo: string;
  autor_principal: string | null;
  bloque_autor: string | null;
  recomendacion: RecomendacionVoto;
  razon: string;
}

export interface SeccionAreaDTO {
  area: AreaTematica;
  proyectos: ProyectoEnAreaDTO[];
}

export interface BriefingCrear {
  orden_del_dia_id: string;
  regenerar?: boolean;
}

export interface ResolverNumerosBody {
  numeros: string[];
}

export interface NumeroResueltoDTO {
  numero_raw: string;
  expediente_id: string;
  titulo: string;
}

export interface ResolverNumerosResponse {
  resueltos: NumeroResueltoDTO[];
  no_encontrados: string[];
  invalidos: string[];
}

export interface BriefingDTO {
  id: string;
  despacho_id: string;
  orden_del_dia_id: string;
  modelo_llm: string;
  prompt_version: string;
  generado_en: string | null;
  proyectos_del_despacho_total: number;
  proyectos_como_autor: number;
  proyectos_como_cofirmante: number;
  alertas: AlertaDTO[];
  secciones_proyectos: SeccionProyectoDTO[];
  secciones_areas: SeccionAreaDTO[];
}

// ---------------------------------------------------------------------------
// Boletín Oficial (spec 15, feat-39)
// ---------------------------------------------------------------------------

export type SeccionBO = "legislacion" | "designaciones" | "avisos_oficiales";

export type PrioridadAccionabilidad = "alta" | "media" | "baja";

export interface NormaBODTO {
  id: string;
  fecha_publicacion: string; // YYYY-MM-DD
  seccion: SeccionBO;
  tipo_norma: string;
  numero_norma: string;
  organismo_emisor: string;
  sumario: string;
  url_oficial: string;
  capturado_en: string;
}

export interface ClasificacionNormaBODTO {
  area_tematica: AreaTematica;
  palabras_clave: string[];
  afecta_expedientes_hcdn: boolean;
  referencias_legales: string[];
}

export interface NormaBODetalleDTO {
  norma: NormaBODTO;
  clasificacion: ClasificacionNormaBODTO | null;
}

export interface NormaBOAccionableDTO {
  norma_id: string;
  despacho_id: string;
  score: number;
  prioridad: PrioridadAccionabilidad;
  razon: string;
  expedientes_tocados: string[];
  generado_en: string | null;
}

export interface NormaBOAccionableConNormaDTO {
  accionable: NormaBOAccionableDTO;
  norma: NormaBODTO;
}

export interface ReclasificarPerfilResponse {
  fecha: string;
  accionables_recalculadas: number;
}

// ---------------------------------------------------------------------------
// Noticias + Menciones (feat-40 — spec 16)
// ---------------------------------------------------------------------------

export type TipoFuenteNoticia = "nacional" | "politico" | "distrital";
export type AlcanceMedio = "nacional" | "provincial" | "nicho";
export type ModoAccesoFuente = "rss" | "sitemap" | "scraping";
export type TonoMencion = "positivo" | "neutro" | "negativo";

export interface FuenteNoticiaDTO {
  id: string;
  nombre: string;
  dominio: string;
  tipo: TipoFuenteNoticia;
  alcance: AlcanceMedio;
  modo_acceso: ModoAccesoFuente;
  distrito: string | null;
  activa: boolean;
}

export interface ArticuloDTO {
  id: string;
  fuente_id: string;
  url: string;
  titulo: string;
  bajada_propia: string | null;
  publicado_en: string | null;
  capturado_en: string;
}

export interface ClasificacionArticuloDTO {
  area_tematica: AreaTematica;
  palabras_clave: string[];
}

export interface ArticuloRelevanteDTO {
  articulo_id: string;
  despacho_id: string;
  score: number;
  razon: string;
  expedientes_tocados: string[];
  generado_en: string | null;
}

export interface ArticuloRelevanteConArticuloDTO {
  relevante: ArticuloRelevanteDTO;
  articulo: ArticuloDTO;
  fuente: FuenteNoticiaDTO;
  clasificacion: ClasificacionArticuloDTO | null;
}

export interface MencionDTO {
  id: string;
  articulo_id: string;
  legislador_id: string;
  despacho_id: string;
  snippet_contexto: string;
  tono: TonoMencion;
  confianza_tono: number;
  alcance_medio: AlcanceMedio;
  detectado_en: string | null;
  notificada: boolean;
}

export interface MencionConArticuloDTO {
  mencion: MencionDTO;
  articulo: ArticuloDTO;
  fuente: FuenteNoticiaDTO;
}

export interface ArticuloDetalleDTO {
  articulo: ArticuloDTO;
  fuente: FuenteNoticiaDTO;
  clasificacion: ClasificacionArticuloDTO | null;
  relevante: ArticuloRelevanteDTO | null;
  menciones: MencionDTO[];
}

// ---------------------------------------------------------------------------
// WhatsApp / Configuración (feat-41)
// ---------------------------------------------------------------------------

export type RolDestinatario =
  | "legislador"
  | "jefe_asesores"
  | "asesor"
  | "otro";

export type EstadoEnvioWhatsApp =
  | "pendiente"
  | "enviado"
  | "entregado"
  | "leido"
  | "fallido"
  | "rechazado";

export type EstadoMetaPlantilla =
  | "pendiente_aprobacion"
  | "aprobada"
  | "rechazada"
  | "pausada"
  | "desconocida";

export type TipoEnvioWhatsApp =
  | "briefing_diario"
  | "alerta_mencion"
  | "alerta_bo"
  | "otro";

export interface DestinatarioDTO {
  id: string;
  despacho_id: string;
  usuario_id: string | null;
  nombre: string;
  rol_interno: RolDestinatario;
  telefono_e164: string;
  recibe_briefing_diario: boolean;
  recibe_alertas_menciones: boolean;
  recibe_alertas_otras: boolean;
  opt_in_en: string | null;
  opt_out_en: string | null;
  activo: boolean;
}

export interface CrearDestinatarioBody {
  nombre: string;
  rol_interno: RolDestinatario;
  telefono_e164: string;
  recibe_briefing_diario?: boolean;
  recibe_alertas_menciones?: boolean;
  recibe_alertas_otras?: boolean;
}

export interface ActualizarDestinatarioBody {
  nombre?: string;
  rol_interno?: RolDestinatario;
  telefono_e164?: string;
  recibe_briefing_diario?: boolean;
  recibe_alertas_menciones?: boolean;
  recibe_alertas_otras?: boolean;
}

export interface EnvioWhatsAppDTO {
  id: string;
  destinatario_id: string;
  despacho_id: string;
  plantilla_name: string;
  tipo: TipoEnvioWhatsApp;
  payload_params: Record<string, unknown>;
  correlativo_id: string | null;
  enviado_en: string | null;
  estado: EstadoEnvioWhatsApp;
  message_id_meta: string | null;
  error: string | null;
}

export interface PlantillaWhatsAppDTO {
  name: string;
  idioma: string;
  categoria: string;
  body_params: string[];
  estado_meta: EstadoMetaPlantilla;
  aprobada_en: string | null;
  contenido_referencia: string;
}

// ---------------------------------------------------------------------------
// Perfil opositor (feat-42.1)
// ---------------------------------------------------------------------------

export type TonoComunicacional =
  | "tecnico-juridico"
  | "militante-bloque"
  | "dialogal-conciliador"
  | "frontal-confrontativo"
  | "ironico"
  | "mixto";

export type ConfianzaGlobal = "alta" | "media" | "baja";

export interface FiguraReferidaDTO {
  nombre: string;
  razon: string;
}

export interface PerfilOpositorDTO {
  despacho_id: string;
  bandera_principal: string;
  banderas_secundarias: string[];
  temas_de_cuidado: string[];
  tono_comunicacional: TonoComunicacional;
  adversarios: FiguraReferidaDTO[];
  aliados: FiguraReferidaDTO[];
  linea_de_bloque: string;
  justificacion_evidencia: string;
  advertencias: string[];
  confianza_global: ConfianzaGlobal;
  inferido_en: string | null;
  editado_en: string | null;
  modelo_inferencia: string | null;
  prompt_version: string;
}

export interface InferirPerfilBody {
  nombre_legislador: string;
  max_votaciones?: number;
}

export interface ActualizarPerfilBody {
  bandera_principal?: string;
  banderas_secundarias?: string[];
  temas_de_cuidado?: string[];
  tono_comunicacional?: TonoComunicacional;
  adversarios?: FiguraReferidaDTO[];
  aliados?: FiguraReferidaDTO[];
  linea_de_bloque?: string;
}

// ---------------------------------------------------------------------------
// Accionables (feat-42.2)
// ---------------------------------------------------------------------------

export type TipoEvento = "norma_bo" | "articulo";

export type AccionSugerida =
  | "pedido_informes"
  | "proyecto_contraposicion"
  | "declaracion_camara"
  | "silencio_estrategico"
  | "retweet_critico"
  | "retweet_apoyo"
  | "articulo_opinion"
  | "interpelacion"
  | "otro";

export type ConfianzaAccionable = "alta" | "media" | "baja";

export interface TweetSugeridoDTO {
  tono: string;
  texto: string;
  caracteres: number;
}

export type EstadoAccionable = "pendiente" | "hecho" | "ignorado" | "adaptado";

export interface AccionableDTO {
  id: string | null;
  despacho_id: string;
  tipo_evento: TipoEvento;
  evento_id: string;
  razon_para_despacho: string;
  accion_sugerida: AccionSugerida;
  explicacion_accion: string;
  tweets_sugeridos: TweetSugeridoDTO[];
  confianza: ConfianzaAccionable;
  generado_en: string | null;
  editado_en: string | null;
  modelo: string | null;
  prompt_version: string;
  // Feedback del asesor (feat-43.2).
  estado: EstadoAccionable;
  nota_asesor: string | null;
  marcado_en: string | null;
}

export interface EstadoAccionableUpdate {
  estado: EstadoAccionable;
  nota?: string;        // obligatoria si estado=adaptado
}

// ---------------------------------------------------------------------------
// Briefing diario preview (feat-42.4)
// ---------------------------------------------------------------------------

export interface BriefingDiarioItemDTO {
  titulo_corto: string;
  accion: AccionSugerida | null;
  razon_breve: string | null;
}

export interface BriefingDiarioPreviewDTO {
  fecha: string;
  despacho_id: string;
  sin_contenido: boolean;
  resumen_corto: string;
  body_rich: string;
  items_bo: BriefingDiarioItemDTO[];
  items_noticias: BriefingDiarioItemDTO[];
}

// ---------------------------------------------------------------------------
// Hub diario (feat-42.5)
// ---------------------------------------------------------------------------

export interface TweetSugeridoBreveDTO {
  tono: string;
  texto: string;
  caracteres: number;
}

export interface HubItemDTO {
  tipo_evento: TipoEvento;
  evento_id: string;
  titulo: string;
  url_detalle: string;
  fuente_o_organismo: string;
  accion: AccionSugerida;
  confianza: ConfianzaAccionable;
  razon_breve: string;
  tweets: TweetSugeridoBreveDTO[];
}

export interface ProximaSesionDTO {
  id: string;
  titulo: string | null;
  camara: "HCDN" | "HSN";
  fecha_sesion: string;
  expedientes_count: number;
  briefing_id: string | null;
}

export interface HubStatsDTO {
  bo_total_hoy: number;
  bo_accionables: number;
  noticias_relevantes_24h: number;
  menciones_24h: number;
}

export interface HubDiarioDTO {
  fecha: string;
  perfil_opositor_cargado: boolean;
  accion_requerida: HubItemDTO[];
  silenciar: HubItemDTO[];
  proxima_sesion: ProximaSesionDTO | null;
  stats: HubStatsDTO;
}

// ---------------------------------------------------------------------------
// Proyectos en redacción (feat-42.3)
// ---------------------------------------------------------------------------

export type TipoProyecto =
  | "ley"
  | "resolucion"
  | "comunicacion"
  | "declaracion";

export type EstadoProyecto = "borrador" | "listo" | "presentado";

export interface ProyectoRedaccionDTO {
  id: string;
  despacho_id: string;
  tipo: TipoProyecto;
  titulo: string;
  sumario: string;
  articulado: string[];
  fundamentos: string;
  cofirmantes_sugeridos: string[];
  estado: EstadoProyecto;
  autor_legislador: string;
  creado_en: string | null;
  actualizado_en: string | null;
  modelo_asistente: string | null;
  prompt_version: string;
}

export interface CrearProyectoBody {
  tipo: TipoProyecto;
  titulo: string;
  sumario: string;
  autor_legislador?: string;
}

export interface ActualizarProyectoBody {
  tipo?: TipoProyecto;
  titulo?: string;
  sumario?: string;
  articulado?: string[];
  fundamentos?: string;
  cofirmantes_sugeridos?: string[];
  estado?: EstadoProyecto;
  autor_legislador?: string;
}

export interface RefinarTextoBody {
  texto: string;
  instruccion: string;
}

export interface TextoRefinadoDTO {
  texto_refinado: string;
  modelo: string;
}

// ---------------------------------------------------------------------------
// Normativa + Validación de conflictos (feat-42.6)
// ---------------------------------------------------------------------------

export type SeveridadConflicto =
  | "conflicto"
  | "modificacion"
  | "complementa"
  | "ninguno";

export interface ConflictoDetectadoDTO {
  indice_articulo_proyecto: number;
  fuente: string;
  articulo_label: string;
  severidad: SeveridadConflicto;
  explicacion: string;
  texto_norma_referida: string;
}

export interface ResultadoValidacionDTO {
  proyecto_id: string;
  n_articulos_evaluados: number;
  conflictos: ConflictoDetectadoDTO[];
  sin_conflictos: boolean;
}

// ---------------------------------------------------------------------------
// Briefing diario — enviar ahora (feat-41.7)
// ---------------------------------------------------------------------------

export interface ResultadoEnvioAhoraDTO {
  despacho_id: string;
  destinatarios_objetivo: number;
  enviados_ok: number;
  fallidos_transitorios: number;
  rechazados: number;
  sin_contenido: boolean;
  sender_real: boolean;
  errores: string[];
}
