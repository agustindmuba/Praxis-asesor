/**
 * Cliente HTTP del backend Praxis Asesor.
 *
 * Diseño:
 * - Funciona en RSC (Server Components) y en Client Components.
 * - Inyecta `Authorization: Bearer <jwt>` desde Clerk.
 * - Inyecta `X-Despacho-Id` desde el despacho activo (cookie HttpOnly en server,
 *   Zustand store en client).
 * - Mapea status codes a errores tipados (ApiError401, ApiError403, etc.).
 *
 * Uso típico:
 *
 *   const me = await apiGet<MeResponse>("/api/v1/me");
 *   const r = await apiPost<SeguimientoDTO>("/api/v1/seguimientos", { expediente_id });
 */

import type { ApiContext } from "./context";

const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ---------------------------------------------------------------------------
// Errores tipados
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: unknown,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export class ApiError401 extends ApiError {
  constructor(body: unknown) {
    super(401, body, "No autenticado");
    this.name = "ApiError401";
  }
}

export class ApiError403 extends ApiError {
  constructor(body: unknown) {
    super(403, body, "Sin permisos en este despacho");
    this.name = "ApiError403";
  }
}

export class ApiError404 extends ApiError {
  constructor(body: unknown) {
    super(404, body, "Recurso no encontrado");
    this.name = "ApiError404";
  }
}

export class ApiError409 extends ApiError {
  constructor(body: unknown) {
    super(409, body, "Conflicto");
    this.name = "ApiError409";
  }
}

// ---------------------------------------------------------------------------
// Core
// ---------------------------------------------------------------------------

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  /**
   * Contexto auth — `{ token, despachoId }`. En RSC: leído de Clerk + cookie.
   * En client: leído de Clerk hook + Zustand store.
   * Si null, no se inyectan headers de auth (útil para endpoints públicos).
   */
  ctx?: ApiContext | null;
  /** Query string params. Se ignoran null/undefined. */
  params?: Record<string, string | number | boolean | null | undefined>;
  /** Pasamos a fetch — útil para cache/revalidate en RSC. */
  next?: NextFetchRequestConfig;
  signal?: AbortSignal;
}

function buildUrl(
  path: string,
  params?: RequestOptions["params"],
): string {
  const url = new URL(path.startsWith("http") ? path : BASE_URL + path);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== null && value !== undefined && value !== "") {
        url.searchParams.set(key, String(value));
      }
    }
  }
  return url.toString();
}

async function request<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const url = buildUrl(path, options.params);
  const headers: Record<string, string> = {
    Accept: "application/json",
  };

  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  if (options.ctx) {
    if (options.ctx.token) {
      headers["Authorization"] = `Bearer ${options.ctx.token}`;
    }
    if (options.ctx.despachoId) {
      headers["X-Despacho-Id"] = options.ctx.despachoId;
    }
  }

  const res = await fetch(url, {
    method: options.method ?? "GET",
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    signal: options.signal,
    next: options.next,
  });

  // 204 no tiene body.
  if (res.status === 204) {
    return undefined as T;
  }

  const contentType = res.headers.get("content-type") ?? "";
  const isJson = contentType.includes("application/json");
  const body: unknown = isJson ? await res.json() : await res.text();

  if (!res.ok) {
    switch (res.status) {
      case 401:
        throw new ApiError401(body);
      case 403:
        throw new ApiError403(body);
      case 404:
        throw new ApiError404(body);
      case 409:
        throw new ApiError409(body);
      default:
        throw new ApiError(res.status, body, `HTTP ${res.status}`);
    }
  }

  return body as T;
}

// ---------------------------------------------------------------------------
// API pública
// ---------------------------------------------------------------------------

export function apiGet<T>(
  path: string,
  opts: Omit<RequestOptions, "method" | "body"> = {},
): Promise<T> {
  return request<T>(path, { ...opts, method: "GET" });
}

export function apiPost<T>(
  path: string,
  body: unknown,
  opts: Omit<RequestOptions, "method" | "body"> = {},
): Promise<T> {
  return request<T>(path, { ...opts, method: "POST", body });
}

export function apiPatch<T>(
  path: string,
  body: unknown,
  opts: Omit<RequestOptions, "method" | "body"> = {},
): Promise<T> {
  return request<T>(path, { ...opts, method: "PATCH", body });
}

export function apiDelete<T>(
  path: string,
  opts: Omit<RequestOptions, "method" | "body"> = {},
): Promise<T> {
  return request<T>(path, { ...opts, method: "DELETE" });
}

/**
 * Fetch de un endpoint que devuelve HTML / texto plano.
 *
 * Usado por el render del briefing: el endpoint /briefings/{id}/html
 * devuelve `text/html` y necesita ir embebido en un iframe via `srcDoc`
 * (cargar la URL directo en `<iframe src>` no funciona porque el
 * browser no incluye los headers de auth en sub-requests del iframe).
 */
export async function apiGetText(
  path: string,
  opts: Omit<RequestOptions, "method" | "body"> = {},
): Promise<string> {
  const url = buildUrl(path, opts.params);
  const headers: Record<string, string> = { Accept: "text/html" };
  if (opts.ctx?.token) {
    headers["Authorization"] = `Bearer ${opts.ctx.token}`;
  }
  if (opts.ctx?.despachoId) {
    headers["X-Despacho-Id"] = opts.ctx.despachoId;
  }
  const res = await fetch(url, {
    method: "GET",
    headers,
    signal: opts.signal,
    next: opts.next,
  });
  const body = await res.text();
  if (!res.ok) {
    switch (res.status) {
      case 401:
        throw new ApiError401(body);
      case 403:
        throw new ApiError403(body);
      case 404:
        throw new ApiError404(body);
      default:
        throw new ApiError(res.status, body, `HTTP ${res.status}`);
    }
  }
  return body;
}
