"use client";

/**
 * Form para crear un OrdenDelDia y disparar la generación de briefing.
 *
 * v1: el asesor pega los UUIDs de los expedientes del OD (uno por línea).
 * Botón "Incluir seguimientos" trae automáticamente los IDs del despacho.
 *
 * v2: parser de "0013-D-2024" → UUID con resolución contra /expedientes.
 */
import { useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useApiContext } from "@/lib/api/context-client";
import { crearOrdenDelDia, listarSeguimientos } from "@/lib/api/endpoints";
import type { Camara } from "@/lib/api/types";

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const inputCls =
  "h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring";

const labelCls = "block text-sm font-medium text-foreground";

export function NuevoBriefingForm() {
  const router = useRouter();
  const getCtx = useApiContext();

  const [camara, setCamara] = useState<Camara>("HCDN");
  const [fechaSesion, setFechaSesion] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() + ((3 - d.getDay() + 7) % 7 || 7));
    return d.toISOString().slice(0, 10);
  });
  const [titulo, setTitulo] = useState("");
  const [expedientesRaw, setExpedientesRaw] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleIncluirSeguimientos() {
    setError(null);
    try {
      const ctx = await getCtx();
      const segs = await listarSeguimientos(ctx);
      const ids = segs.map((s) => s.expediente_id).join("\n");
      setExpedientesRaw((prev) => (prev.trim() ? prev + "\n" + ids : ids));
    } catch {
      setError("No se pudieron cargar los seguimientos del despacho.");
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    const ids = expedientesRaw
      .split(/[\s,;]+/)
      .map((s) => s.trim())
      .filter(Boolean);

    const invalidos = ids.filter((id) => !UUID_RE.test(id));
    if (invalidos.length) {
      setError(
        `Hay ${invalidos.length} UUID inválido(s). Primero: ${invalidos[0]?.slice(0, 30)}…`,
      );
      return;
    }
    if (ids.length === 0) {
      setError("Cargá al menos un expediente.");
      return;
    }

    setSubmitting(true);
    try {
      const ctx = await getCtx();
      const od = await crearOrdenDelDia(ctx, {
        camara,
        fecha_sesion: fechaSesion,
        titulo: titulo.trim() || undefined,
        expedientes_ids: ids,
      });
      router.push(`/briefings/${od.id}`);
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : "Error desconocido al crear el OD.";
      setError(msg);
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Datos de la sesión</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1">
            <label htmlFor="camara" className={labelCls}>
              Cámara
            </label>
            <select
              id="camara"
              value={camara}
              onChange={(e) => setCamara(e.target.value as Camara)}
              className={inputCls}
            >
              <option value="HCDN">HCDN — Diputados</option>
              <option value="HSN">HSN — Senado</option>
            </select>
          </div>
          <div className="space-y-1">
            <label htmlFor="fecha" className={labelCls}>
              Fecha de la sesión
            </label>
            <Input
              id="fecha"
              type="date"
              value={fechaSesion}
              onChange={(e) => setFechaSesion(e.target.value)}
              required
            />
          </div>
          <div className="space-y-1 sm:col-span-2">
            <label htmlFor="titulo" className={labelCls}>
              Título (opcional)
            </label>
            <Input
              id="titulo"
              type="text"
              value={titulo}
              placeholder="Ej. Sesión Ordinaria N° 7"
              onChange={(e) => setTitulo(e.target.value)}
              maxLength={200}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Expedientes del orden del día</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center justify-between">
            <label htmlFor="expedientes" className={labelCls}>
              UUIDs (uno por línea)
            </label>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleIncluirSeguimientos}
            >
              Incluir mis seguimientos
            </Button>
          </div>
          <textarea
            id="expedientes"
            value={expedientesRaw}
            onChange={(e) => setExpedientesRaw(e.target.value)}
            rows={10}
            placeholder={
              "019e7585-7515-7f73-8f7e-a410e29a8435\n01a1b2c3-..."
            }
            className="block w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
          <p className="text-xs text-muted-foreground">
            v1: pegar UUIDs. La búsqueda por número (&quot;13-D-2024&quot;) llega
            con feat/31. Mientras tanto usar &ldquo;Incluir mis seguimientos&rdquo; o
            copiarlos desde la lista de expedientes.
          </p>
        </CardContent>
      </Card>

      {error ? (
        <Card className="border-destructive bg-destructive/5">
          <CardContent className="py-3 text-sm text-destructive">{error}</CardContent>
        </Card>
      ) : null}

      <div className="flex items-center justify-end gap-2">
        <Button type="submit" disabled={submitting}>
          {submitting ? "Generando…" : "Crear briefing"}
        </Button>
      </div>
    </form>
  );
}
