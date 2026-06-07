/**
 * Helpers para sincronizar `FiltrosExpediente` con el query string de la URL.
 *
 * La URL es la fuente de verdad: los filtros se guardan ahí para que los
 * links/back-button funcionen y la página sea shareable.
 */
import type {
  AreaTematica,
  Camara,
  EstadoExpediente,
  FiltrosExpediente,
  OrigenExpediente,
  TipoExpediente,
} from "@/lib/api/types";

const AREAS: readonly AreaTematica[] = [
  "salud",
  "educacion",
  "ambiente",
  "trabajo",
  "derechos_humanos",
  "seguridad",
  "transporte",
  "infraestructura",
  "justicia",
  "relaciones_exteriores",
  "economia",
  "otros",
];

const TIPOS: readonly TipoExpediente[] = [
  "proyecto_ley",
  "proyecto_resolucion",
  "proyecto_declaracion",
  "proyecto_comunicacion",
  "mensaje_pe",
  "decreto",
  "otro",
];

const CAMARAS: readonly Camara[] = ["HCDN", "HSN"];

const ORIGENES: readonly OrigenExpediente[] = [
  "D",
  "S",
  "PE",
  "JGM",
  "CD",
  "CS",
  "P",
  "OV",
  "OTRO",
];

const ESTADOS: readonly EstadoExpediente[] = [
  "ingresado",
  "en_comision",
  "con_dictamen",
  "media_sancion_hcdn",
  "media_sancion_hsn",
  "sancionado",
  "archivado",
  "caduco",
  "desconocido",
];

export const LIMIT_DEFAULT = 50;
export const LIMIT_MAX = 200;

/**
 * Parsea los `searchParams` de Next 15 (ya resueltos) en un `FiltrosExpediente`.
 * Valores inválidos se descartan silenciosamente — no levantamos errores para
 * que un usuario con una URL rota igual vea algo.
 */
export function parseFiltrosFromSearchParams(
  raw: Record<string, string | string[] | undefined>,
): FiltrosExpediente {
  const filtros: FiltrosExpediente = {};

  const texto = pickString(raw.texto);
  if (texto) filtros.texto = texto;

  const anio = pickNumber(raw.anio);
  if (anio && anio >= 1983 && anio <= 2100) filtros.anio = anio;

  const tipo = pickEnum(raw.tipo, TIPOS);
  if (tipo) filtros.tipo = tipo;

  const camara = pickEnum(raw.camara, CAMARAS);
  if (camara) filtros.camara = camara;

  const origen = pickEnum(raw.origen, ORIGENES);
  if (origen) filtros.origen = origen;

  const estado = pickEnum(raw.estado, ESTADOS);
  if (estado) filtros.estado = estado;

  const autor = pickString(raw.autor_nombre);
  if (autor) filtros.autor_nombre = autor;

  const comision = pickString(raw.comision);
  if (comision) filtros.comision = comision;

  const desde = pickDate(raw.fecha_ingreso_desde);
  if (desde) filtros.fecha_ingreso_desde = desde;

  const hasta = pickDate(raw.fecha_ingreso_hasta);
  if (hasta) filtros.fecha_ingreso_hasta = hasta;

  // Filtros derivados del despacho (feat-43.1).
  const area = pickEnum(raw.area_tematica, AREAS);
  if (area) filtros.area_tematica = area;

  if (pickString(raw.con_dictamen) === "true") filtros.con_dictamen = true;
  if (pickString(raw.por_caducar) === "true") filtros.por_caducar = true;
  if (pickString(raw.solo_seguidos) === "true") filtros.solo_seguidos = true;
  if (pickString(raw.solo_titular) === "true") filtros.solo_titular = true;

  const dias = pickNumber(raw.por_caducar_dias);
  if (dias && dias >= 1 && dias <= 365) filtros.por_caducar_dias = dias;

  const limit = pickNumber(raw.limit);
  filtros.limit = limit && limit >= 1 && limit <= LIMIT_MAX ? limit : LIMIT_DEFAULT;

  const offset = pickNumber(raw.offset);
  filtros.offset = offset && offset >= 0 ? offset : 0;

  return filtros;
}

/**
 * Serializa un `FiltrosExpediente` en una `URLSearchParams` para construir
 * URLs. Omite las claves null/undefined/""/defaults.
 */
export function filtrosToSearchParams(
  filtros: FiltrosExpediente,
): URLSearchParams {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filtros)) {
    if (value === null || value === undefined || value === "") continue;
    // Booleanos false / defaults: no contaminan la URL.
    if (typeof value === "boolean" && value === false) continue;
    if (key === "limit" && value === LIMIT_DEFAULT) continue;
    if (key === "offset" && value === 0) continue;
    if (key === "por_caducar_dias" && value === 60) continue;
    params.set(key, String(value));
  }
  return params;
}

// ---------------------------------------------------------------------------
// Pickers internos
// ---------------------------------------------------------------------------

function pickString(value: string | string[] | undefined): string | undefined {
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim();
  return trimmed === "" ? undefined : trimmed;
}

function pickNumber(value: string | string[] | undefined): number | undefined {
  const s = pickString(value);
  if (!s) return undefined;
  const n = Number(s);
  return Number.isFinite(n) ? n : undefined;
}

function pickEnum<T extends string>(
  value: string | string[] | undefined,
  allowed: readonly T[],
): T | undefined {
  const s = pickString(value);
  if (!s) return undefined;
  return (allowed as readonly string[]).includes(s) ? (s as T) : undefined;
}

function pickDate(value: string | string[] | undefined): string | undefined {
  const s = pickString(value);
  if (!s) return undefined;
  // Formato ISO YYYY-MM-DD. Si no matchea, ignoramos.
  return /^\d{4}-\d{2}-\d{2}$/.test(s) ? s : undefined;
}
