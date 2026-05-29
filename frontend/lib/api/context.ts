/**
 * `ApiContext` = lo que cada request HTTP necesita inyectar (token + despacho_id).
 *
 * Hay dos sabores de resolución:
 * - Server-side (RSC, Server Actions): leer Clerk via `auth()` + cookie del despacho.
 * - Client-side: usar `useAuth()` hook + Zustand store.
 *
 * Este archivo expone solo el tipo. Los resolvers están en context-server.ts
 * y context-client.ts respectivamente, separados para evitar bundlear código
 * de servidor en el cliente.
 */

export interface ApiContext {
  /** JWT firmado por Clerk. */
  token: string | null;
  /** UUID del despacho activo del usuario. */
  despachoId: string | null;
}
