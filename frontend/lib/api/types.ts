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

export interface CrearSeguimientoBody {
  expediente_id: string;
  prioridad?: Prioridad;
}

export interface ActualizarSeguimientoBody {
  responsable_id?: string | null;
  archivado?: boolean;
}
