/**
 * Panel "Insights del feedback" en /configuracion/perfil-opositor (feat-43.3).
 *
 * Server Component: hace fetch al endpoint y muestra:
 * - Si hay muy poco feedback (< 5 con estado) → mensaje de "marcá más".
 * - Si hay suficiente → distribución por tipo de acción + sugerencias.
 *
 * Las sugerencias son automáticas (umbrales de % ignorado / adaptado /
 * backlog). El asesor decide si actúa sobre ellas editando el perfil arriba.
 */
import { AlertTriangle, BarChart3, Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { getApiContextServer } from "@/lib/api/context-server";
import { getInsightsFeedback } from "@/lib/api/endpoints";
import type {
  AccionSugerida,
  DistribucionAccionDTO,
  SugerenciaInsightDTO,
} from "@/lib/api/types";

const ACCION_LABEL: Record<AccionSugerida, string> = {
  pedido_informes: "Pedido de informes",
  proyecto_contraposicion: "Contraproyecto",
  declaracion_camara: "Declaración",
  silencio_estrategico: "Silencio estratégico",
  retweet_critico: "RT crítico",
  retweet_apoyo: "RT apoyo",
  articulo_opinion: "Artículo de opinión",
  interpelacion: "Interpelación",
  otro: "Otro",
};

const SEVERIDAD_COLOR: Record<string, string> = {
  alta: "var(--color-praxis-salmon)",
  media: "#7C5E1F",
  baja: "rgb(100 116 139)",
};

export async function InsightsFeedbackPanel() {
  const ctx = await getApiContextServer();
  const data = await getInsightsFeedback(ctx).catch(() => null);

  if (data === null) {
    return (
      <Card className="border-border bg-card p-5 shadow-none">
        <p className="text-xs text-muted-foreground">
          No se pudo cargar el feedback.
        </p>
      </Card>
    );
  }

  const necesitaMasFeedback = data.total_con_feedback < 5;

  return (
    <section className="space-y-3">
      <div className="flex items-center gap-2">
        <BarChart3 className="size-4 text-[var(--color-praxis-azul)]" />
        <h3 className="font-display text-sm font-semibold uppercase tracking-wider text-[var(--color-praxis-azul)]">
          Insights del feedback
        </h3>
        <Badge variant="outline" className="text-[10px] uppercase">
          Últimos {data.ventana_dias} días
        </Badge>
      </div>

      {necesitaMasFeedback ? (
        <Card className="border-border bg-card p-5 shadow-none">
          <p className="text-xs leading-relaxed text-muted-foreground">
            Marcaste {data.total_con_feedback} accionable
            {data.total_con_feedback === 1 ? "" : "s"} sobre{" "}
            {data.total_accionables} generado
            {data.total_accionables === 1 ? "" : "s"} en los últimos{" "}
            {data.ventana_dias} días. Necesitás <strong>al menos 5</strong>{" "}
            con estado (✓ Lo hicimos / ✗ Dejar pasar / ✏ Distinto) para que el
            sistema pueda detectar patrones.
          </p>
        </Card>
      ) : (
        <>
          {/* Distribución por acción */}
          <Card className="space-y-3 border-border bg-card p-5 shadow-none">
            <p className="text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">
              Distribución por tipo de acción
            </p>
            <ul className="space-y-2.5">
              {data.distribucion.map((d) => (
                <DistribucionRow key={d.accion} item={d} />
              ))}
            </ul>
            <p className="pt-1 text-[10.5px] italic text-muted-foreground">
              {data.total_con_feedback} accionable
              {data.total_con_feedback === 1 ? "" : "s"} con feedback de un
              total de {data.total_accionables} en la ventana.
            </p>
          </Card>

          {/* Sugerencias */}
          {data.sugerencias.length > 0 && (
            <Card className="space-y-2.5 border-border bg-card p-5 shadow-none">
              <div className="flex items-center gap-1.5">
                <Sparkles className="size-3.5 text-[var(--color-praxis-azul)]" />
                <p className="text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Sugerencias para tu perfil
                </p>
              </div>
              <ul className="space-y-2">
                {data.sugerencias.map((s, i) => (
                  <SugerenciaCard key={i} sug={s} />
                ))}
              </ul>
            </Card>
          )}
        </>
      )}
    </section>
  );
}

function DistribucionRow({ item }: { item: DistribucionAccionDTO }) {
  const cerrados = item.hechos + item.ignorados + item.adaptados;
  return (
    <li className="space-y-1">
      <div className="flex flex-wrap items-baseline justify-between gap-2 text-[11.5px]">
        <span className="font-semibold text-foreground">
          {ACCION_LABEL[item.accion] ?? item.accion}
        </span>
        <span className="font-mono text-[10.5px] text-muted-foreground">
          {item.total} total · {item.pendientes} pend · {cerrados} cerrados
        </span>
      </div>
      {cerrados > 0 ? (
        <div
          className="flex h-2 w-full overflow-hidden rounded-full"
          aria-label="Distribución hecho/ignorado/adaptado"
        >
          <div
            style={{
              width: `${item.pct_hecho * 100}%`,
              backgroundColor: "var(--color-praxis-verde)",
            }}
            title={`${item.hechos} hechos (${Math.round(item.pct_hecho * 100)}%)`}
          />
          <div
            style={{
              width: `${item.pct_adaptado * 100}%`,
              backgroundColor: "var(--color-praxis-salmon)",
            }}
            title={`${item.adaptados} adaptados (${Math.round(item.pct_adaptado * 100)}%)`}
          />
          <div
            style={{
              width: `${item.pct_ignorado * 100}%`,
              backgroundColor: "rgb(100 116 139)",
            }}
            title={`${item.ignorados} ignorados (${Math.round(item.pct_ignorado * 100)}%)`}
          />
        </div>
      ) : (
        <div className="h-2 w-full rounded-full bg-muted/40" />
      )}
    </li>
  );
}

function SugerenciaCard({ sug }: { sug: SugerenciaInsightDTO }) {
  const color = SEVERIDAD_COLOR[sug.severidad] ?? "rgb(100 116 139)";
  return (
    <li
      className="rounded-md border-l-2 bg-muted/30 px-3 py-2 text-xs leading-relaxed"
      style={{ borderLeftColor: color }}
    >
      <div className="mb-0.5 flex items-center gap-1.5">
        <AlertTriangle className="size-3" style={{ color }} />
        <span
          className="text-[9.5px] font-semibold uppercase tracking-wider"
          style={{ color }}
        >
          {sug.severidad}
        </span>
        {sug.accion_objetivo && (
          <Badge variant="outline" className="text-[9.5px]">
            {ACCION_LABEL[sug.accion_objetivo] ?? sug.accion_objetivo}
          </Badge>
        )}
      </div>
      <p className="text-foreground">{sug.mensaje}</p>
    </li>
  );
}
