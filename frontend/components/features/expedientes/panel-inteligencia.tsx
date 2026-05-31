/**
 * Panel de Inteligencia del expediente — Server Component.
 *
 * Render del bundle que devuelve GET /expedientes/{id}/inteligencia.
 * Cubre por ahora 2 de las 5 secciones del plan:
 * 1. Barra de progreso del trámite (las 5 etapas).
 * 2. Comparación con peers (mismo tipo + cámara + estado).
 *
 * Próximas 3 (historial autor, relacionados, acciones) llegan en
 * iteraciones siguientes.
 */
import { AlertTriangle, Check, TrendingDown, TrendingUp } from "lucide-react";

import { Card } from "@/components/ui/card";
import { getApiContextServer } from "@/lib/api/context-server";
import { getInteligenciaExpediente } from "@/lib/api/endpoints";
import type {
  EtapaPipeline,
  EtapaProgresoDTO,
  InteligenciaExpedienteDTO,
} from "@/lib/api/types";
import { cn } from "@/lib/utils";

interface Props {
  expedienteId: string;
}

export async function PanelInteligencia({ expedienteId }: Props) {
  const ctx = await getApiContextServer();
  const data = await getInteligenciaExpediente(ctx, expedienteId);

  return (
    <Card className="space-y-6 p-6">
      <BarraDePipeline data={data} />
      <ComparacionConPeers data={data} />
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Barra de progreso del trámite
// ---------------------------------------------------------------------------

function BarraDePipeline({ data }: { data: InteligenciaExpedienteDTO }) {
  const { progreso } = data;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold">Progreso del trámite</h3>
        <DiasEnEtapa
          dias={progreso.dias_en_etapa_actual}
          etapaActual={progreso.etapa_actual}
          terminado={progreso.terminado}
          motivoTerminacion={progreso.motivo_terminacion}
        />
      </div>

      {/* Pipeline horizontal: 5 dots conectados por líneas */}
      <ol className="grid grid-cols-5 gap-0">
        {progreso.etapas.map((etapa, i) => (
          <EtapaDot
            key={etapa.etapa}
            etapa={etapa}
            esActual={etapa.etapa === progreso.etapa_actual}
            esUltima={i === progreso.etapas.length - 1}
            siguienteAlcanzada={progreso.etapas[i + 1]?.alcanzada ?? false}
          />
        ))}
      </ol>
    </div>
  );
}

function EtapaDot({
  etapa,
  esActual,
  esUltima,
  siguienteAlcanzada,
}: {
  etapa: EtapaProgresoDTO;
  esActual: boolean;
  esUltima: boolean;
  siguienteAlcanzada: boolean;
}) {
  return (
    <li className="relative flex flex-col items-center gap-1.5">
      {/* Línea conectora hacia la derecha */}
      {!esUltima && (
        <div
          className={cn(
            "absolute left-1/2 top-3 h-0.5 w-full",
            siguienteAlcanzada ? "bg-primary" : "bg-border",
          )}
          aria-hidden
        />
      )}

      {/* Dot */}
      <div
        className={cn(
          "relative z-10 flex size-6 items-center justify-center rounded-full border-2 transition-colors",
          etapa.alcanzada
            ? "border-primary bg-primary text-primary-foreground"
            : "border-border bg-background text-muted-foreground",
          esActual && "ring-4 ring-primary/20",
        )}
      >
        {etapa.alcanzada && !esActual ? (
          <Check className="size-3" />
        ) : esActual ? (
          <div className="size-2 rounded-full bg-primary-foreground" />
        ) : null}
      </div>

      {/* Label */}
      <span
        className={cn(
          "text-center text-[10px] font-medium leading-tight",
          etapa.alcanzada ? "text-foreground" : "text-muted-foreground",
          esActual && "font-semibold text-primary",
        )}
      >
        {etapa.label}
      </span>
    </li>
  );
}

function DiasEnEtapa({
  dias,
  etapaActual,
  terminado,
  motivoTerminacion,
}: {
  dias: number | null;
  etapaActual: EtapaPipeline | null;
  terminado: boolean;
  motivoTerminacion: string | null;
}) {
  if (terminado) {
    return (
      <p className="text-xs text-muted-foreground">
        <AlertTriangle className="mr-1 inline size-3" />
        {motivoTerminacion}
      </p>
    );
  }
  if (dias === null || etapaActual === null) {
    return (
      <p className="text-xs text-muted-foreground">Estado actual no clasificable.</p>
    );
  }
  return (
    <p className="text-xs text-muted-foreground">
      Lleva <span className="font-semibold text-foreground">{dias}</span>{" "}
      día{dias === 1 ? "" : "s"} en esta etapa.
    </p>
  );
}

// ---------------------------------------------------------------------------
// Comparación con peers
// ---------------------------------------------------------------------------

function ComparacionConPeers({ data }: { data: InteligenciaExpedienteDTO }) {
  const { peers, progreso } = data;

  // Sin peers o sin etapa actual → no mostramos esta sección.
  if (peers.peer_count === 0 || progreso.etapa_actual === null) {
    return (
      <div className="space-y-1 border-t border-border pt-4">
        <h3 className="text-sm font-semibold">Comparación con peers</h3>
        <p className="text-xs text-muted-foreground">
          No hay suficientes expedientes con el mismo perfil para comparar todavía.
          {peers.peer_count > 0 && ` (Encontramos ${peers.peer_count} candidato${peers.peer_count === 1 ? "" : "s"}, pero estamos esperando más data.)`}
        </p>
      </div>
    );
  }

  // Peers insuficientes para mediana (< 3).
  if (peers.mediana_dias === null) {
    return (
      <div className="space-y-1 border-t border-border pt-4">
        <h3 className="text-sm font-semibold">Comparación con peers</h3>
        <p className="text-xs text-muted-foreground">
          {peers.peer_count} peer{peers.peer_count === 1 ? "" : "s"} con el mismo
          perfil; necesitamos al menos 3 para calcular medianas confiables.
        </p>
      </div>
    );
  }

  // Caso real: tenemos mediana.
  const propio = progreso.dias_en_etapa_actual ?? 0;
  const mediana = peers.mediana_dias;
  const diferencia = peers.diferencia_porcentual ?? 0;
  const masRapido = diferencia < 0;
  const veces = mediana > 0 ? (propio / mediana).toFixed(1) : "—";

  return (
    <div className="space-y-3 border-t border-border pt-4">
      <h3 className="text-sm font-semibold">Comparación con peers</h3>

      <div className="flex flex-col gap-3 sm:flex-row">
        <Stat
          label="Vos"
          value={`${propio} días`}
          tone={masRapido ? "good" : "warn"}
        />
        <Stat
          label="Mediana peers"
          value={`${mediana} días`}
          tone="muted"
        />
        <Stat
          label={masRapido ? "Más rápido" : "Más lento"}
          value={`${Math.abs(Math.round(diferencia))}%`}
          tone={masRapido ? "good" : "warn"}
          icon={masRapido ? <TrendingDown className="size-4" /> : <TrendingUp className="size-4" />}
        />
      </div>

      <p className="text-xs text-muted-foreground">
        Comparado contra <strong>{peers.peer_count}</strong> expedientes con{" "}
        {peers.criterio.toLowerCase()}. {masRapido ? "Avanza más rápido" : "Avanza más lento"}{" "}
        ({veces}× vs mediana).
      </p>
    </div>
  );
}

function Stat({
  label,
  value,
  tone,
  icon,
}: {
  label: string;
  value: string;
  tone: "good" | "warn" | "muted";
  icon?: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "flex-1 rounded-md border px-3 py-2",
        tone === "good" && "border-green-200 bg-green-50",
        tone === "warn" && "border-amber-200 bg-amber-50",
        tone === "muted" && "border-border bg-muted/40",
      )}
    >
      <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <p
        className={cn(
          "mt-0.5 flex items-center gap-1 text-base font-semibold tabular-nums",
          tone === "good" && "text-green-700",
          tone === "warn" && "text-amber-700",
          tone === "muted" && "text-foreground",
        )}
      >
        {icon}
        {value}
      </p>
    </div>
  );
}
