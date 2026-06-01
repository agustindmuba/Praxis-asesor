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
import {
  crearOrdenDelDia,
  listarSeguimientos,
  resolverNumeros,
} from "@/lib/api/endpoints";
import type { Camara } from "@/lib/api/types";

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

// Acepta formatos HCDN: "13-D-2024" / "0013-D-2024" o HSN "239/24"
const NUMERO_HCDN_RE = /^\d{1,5}-[A-Za-z]{1,3}-\d{4}$/;
const NUMERO_HSN_RE = /^\d{1,5}\/\d{2}$/;

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

    const tokens = expedientesRaw
      .split(/[\s,;]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (tokens.length === 0) {
      setError("Cargá al menos un expediente.");
      return;
    }

    // Particionar en UUIDs (directos) vs números (a resolver) vs basura.
    const uuids: string[] = [];
    const numeros: string[] = [];
    const basura: string[] = [];
    for (const t of tokens) {
      if (UUID_RE.test(t)) {
        uuids.push(t);
      } else if (NUMERO_HCDN_RE.test(t) || NUMERO_HSN_RE.test(t)) {
        numeros.push(t);
      } else {
        basura.push(t);
      }
    }
    if (basura.length) {
      setError(
        `Hay ${basura.length} entrada(s) que no son UUID ni número HCDN/HSN. ` +
          `Primero: "${basura[0]?.slice(0, 30)}"`,
      );
      return;
    }

    setSubmitting(true);
    try {
      const ctx = await getCtx();

      let idsFinales = [...uuids];
      if (numeros.length) {
        const resol = await resolverNumeros(ctx, { numeros });
        if (resol.no_encontrados.length || resol.invalidos.length) {
          const faltantes = [...resol.no_encontrados, ...resol.invalidos];
          setError(
            `${faltantes.length} número(s) no encontrado(s) en DB: ` +
              `${faltantes.slice(0, 3).join(", ")}` +
              (faltantes.length > 3 ? ` y ${faltantes.length - 3} más…` : ""),
          );
          setSubmitting(false);
          return;
        }
        idsFinales = [...idsFinales, ...resol.resueltos.map((r) => r.expediente_id)];
      }

      const od = await crearOrdenDelDia(ctx, {
        camara,
        fecha_sesion: fechaSesion,
        titulo: titulo.trim() || undefined,
        expedientes_ids: idsFinales,
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
              Números o UUIDs (uno por línea, coma o espacio)
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
              "13-D-2024\n0092-D-2024, 1497-D-2024\n239/24 (HSN)\n\n# o pegar UUIDs si los tenés a mano:\n019e7585-7515-7f73-8f7e-a410e29a8435"
            }
            className="block w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
          <p className="text-xs text-muted-foreground">
            Aceptamos formato HCDN (<code>NNNN-X-YYYY</code>, ej <code>13-D-2024</code>),
            HSN (<code>NNNN/YY</code>) o UUIDs internos. El sistema resuelve los
            números contra el catálogo y avisa si alguno no está cargado.
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
