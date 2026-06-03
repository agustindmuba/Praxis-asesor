/**
 * Proxy del PDF del briefing.
 *
 * El backend devuelve `application/pdf` desde
 * `GET /api/v1/briefings/{id}/pdf` con auth Bearer + X-Despacho-Id.
 *
 * Un `<a href>` desde el browser no puede agregar esos headers, así que
 * pasamos por este route handler de Next que:
 * 1. Resuelve el ApiContext server-side (cookies de Clerk / dev-login).
 * 2. Hace fetch al backend con los headers correctos.
 * 3. Devuelve el binario al cliente con el mismo Content-Type.
 *
 * Si el backend tira 501 (weasyprint no disponible), propagamos el JSON
 * con el mensaje para que el usuario sepa que hay que instalar la dep.
 */
import { NextResponse } from "next/server";

import { getApiContextServer } from "@/lib/api/context-server";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const ctx = await getApiContextServer();

  const headers: Record<string, string> = {
    Accept: "application/pdf",
  };
  if (ctx.token) headers["Authorization"] = `Bearer ${ctx.token}`;
  if (ctx.despachoId) headers["X-Despacho-Id"] = ctx.despachoId;

  const upstream = await fetch(`${API_BASE}/api/v1/briefings/${id}/pdf`, {
    headers,
  });

  if (!upstream.ok) {
    const text = await upstream.text();
    return new NextResponse(text, {
      status: upstream.status,
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  }

  const buffer = await upstream.arrayBuffer();
  return new NextResponse(buffer, {
    status: 200,
    headers: {
      "Content-Type":
        upstream.headers.get("Content-Type") ?? "application/pdf",
      "Content-Disposition":
        upstream.headers.get("Content-Disposition") ??
        `inline; filename="briefing-${id}.pdf"`,
    },
  });
}
