"use client";

/**
 * Sección "Calendario sincronizado" en /configuracion (feat-54.3).
 *
 * Muestra la URL del feed iCal del despacho para que el asesor la
 * copie en Google/Apple/Outlook. Botón de regenerar token si sospechan
 * filtración. Bandera de "copiado" temporal.
 */
import { useEffect, useState, useTransition } from "react";
import {
  Calendar,
  Copy,
  Check,
  Loader2,
  RotateCw,
  AlertTriangle,
} from "lucide-react";

import { Card } from "@/components/ui/card";
import { useApiContext } from "@/lib/api/context-client";
import {
  getCalendarUrl,
  regenerarCalendarToken,
  type CalendarUrlResponse,
} from "@/lib/api/endpoints";


export function CalendarSection() {
  const resolveCtx = useApiContext();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<CalendarUrlResponse | null>(null);
  const [copied, setCopied] = useState(false);
  const [confirmRotate, setConfirmRotate] = useState(false);
  const [isRotating, startRotate] = useTransition();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const ctx = await resolveCtx();
        const r = await getCalendarUrl(ctx);
        if (!cancelled) setData(r);
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "No se pudo cargar la URL.",
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [resolveCtx]);

  function copiar() {
    if (!data) return;
    navigator.clipboard.writeText(data.url).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  function rotar() {
    setError(null);
    startRotate(async () => {
      try {
        const ctx = await resolveCtx();
        const r = await regenerarCalendarToken(ctx);
        setData(r);
        setConfirmRotate(false);
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "No se pudo regenerar el token.",
        );
      }
    });
  }

  return (
    <Card className="space-y-4 border-border bg-card p-5 shadow-none">
      <div className="flex items-center gap-2">
        <Calendar className="size-4 text-[var(--color-praxis-azul)]" />
        <h3 className="font-display text-sm font-semibold uppercase tracking-wider text-[var(--color-praxis-azul)]">
          Calendario sincronizado
        </h3>
      </div>

      <p className="text-xs text-muted-foreground">
        Suscribite a esta URL desde Google Calendar, Apple Calendar,
        Outlook o cualquier app compatible con iCal. Vas a ver las
        sesiones del Congreso, los vencimientos por caducidad de los
        proyectos del despacho y las efemérides relevantes — siempre
        sincronizados con Praxis.
      </p>

      {loading && (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="size-3.5 animate-spin" />
          Cargando URL del calendario…
        </div>
      )}

      {error && (
        <div className="flex items-start gap-2 rounded-md border border-[var(--color-praxis-salmon)] bg-[var(--color-praxis-salmon)]/10 p-2 text-[11px] text-[var(--color-praxis-salmon)]">
          <AlertTriangle className="size-3.5 shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {data && (
        <>
          {/* URL para copiar */}
          <div className="flex items-stretch gap-2">
            <input
              readOnly
              value={data.url}
              onClick={(e) => (e.target as HTMLInputElement).select()}
              className="flex-1 rounded-md border border-border bg-muted/30 px-2 py-1.5 font-mono text-[11px]"
            />
            <button
              type="button"
              onClick={copiar}
              className="inline-flex items-center gap-1 rounded-md bg-[var(--color-praxis-azul)] px-3 text-[11px] font-semibold text-white transition-opacity hover:opacity-90"
            >
              {copied ? (
                <>
                  <Check className="size-3.5" />
                  Copiado
                </>
              ) : (
                <>
                  <Copy className="size-3.5" />
                  Copiar
                </>
              )}
            </button>
          </div>

          {/* Instrucciones por proveedor */}
          <details className="rounded-md border border-border bg-muted/20 p-3 text-[11px]">
            <summary className="cursor-pointer font-medium text-foreground">
              Cómo suscribirme
            </summary>
            <div className="mt-2 space-y-3 leading-relaxed text-muted-foreground">
              <div>
                <strong className="text-foreground">Google Calendar:</strong>{" "}
                Configuración → Agregar calendario → Suscribirse a un
                calendario → pegá la URL → Agregar calendario.
              </div>
              <div>
                <strong className="text-foreground">Apple Calendar (macOS):</strong>{" "}
                Menú Archivo → Nueva suscripción de calendario → pegá la
                URL → Suscribirse.
              </div>
              <div>
                <strong className="text-foreground">Outlook (web):</strong>{" "}
                Agregar calendario → Suscribirse desde Internet → pegá
                la URL → Importar.
              </div>
            </div>
          </details>

          {/* Regenerar token */}
          <div className="border-t border-border pt-3">
            {!confirmRotate ? (
              <button
                type="button"
                onClick={() => setConfirmRotate(true)}
                className="inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground"
              >
                <RotateCw className="size-3" />
                Regenerar URL (si sospechás que se filtró)
              </button>
            ) : (
              <div className="flex flex-col gap-2 rounded-md border border-[var(--color-praxis-salmon)] bg-[var(--color-praxis-salmon)]/5 p-2 text-[11px]">
                <div className="flex items-start gap-2 text-foreground">
                  <AlertTriangle className="size-3.5 shrink-0 mt-0.5 text-[var(--color-praxis-salmon)]" />
                  <span>
                    La URL actual dejará de funcionar al instante. Vas a
                    tener que volver a suscribir en tus calendarios.
                    ¿Seguro?
                  </span>
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    disabled={isRotating}
                    onClick={rotar}
                    className="rounded-md bg-[var(--color-praxis-salmon)] px-3 py-1 text-[11px] font-semibold text-white disabled:opacity-50"
                  >
                    {isRotating ? "Regenerando…" : "Sí, regenerar"}
                  </button>
                  <button
                    type="button"
                    disabled={isRotating}
                    onClick={() => setConfirmRotate(false)}
                    className="rounded-md border border-border px-3 py-1 text-[11px]"
                  >
                    Cancelar
                  </button>
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </Card>
  );
}
