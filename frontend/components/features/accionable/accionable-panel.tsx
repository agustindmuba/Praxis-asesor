"use client";

/**
 * Panel desplegable de Accionable enriquecido con perfil opositor
 * (feat-42.2 — A+B+F).
 *
 * Reusable entre BO y Noticias. Recibe:
 * - tipo + eventoId: para fetchear / generar el accionable
 * - inicial: el accionable cacheado si lo había, o null
 *
 * Muestra:
 * - Si null → CTA "Generar acción" que dispara POST /generar
 * - Si existe → razón política, acción sugerida (badge), explicación,
 *   tweets sugeridos con copy-to-clipboard
 * - Botón "Re-generar" para forzar nueva inferencia
 */
import { useState, useTransition } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Copy,
  Loader2,
  RefreshCw,
  Sparkles,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { useApiContext } from "@/lib/api/context-client";
import {
  generarAccionableArticulo,
  generarAccionableBo,
} from "@/lib/api/endpoints";
import type {
  AccionableDTO,
  AccionSugerida,
  ConfianzaAccionable,
  TipoEvento,
} from "@/lib/api/types";

import { FeedbackButtons } from "./feedback-buttons";

const ACCION_LABEL: Record<AccionSugerida, string> = {
  pedido_informes: "Pedido de informes",
  proyecto_contraposicion: "Proyecto de contraposición",
  declaracion_camara: "Declaración de la cámara",
  silencio_estrategico: "Silencio estratégico",
  retweet_critico: "RT con comentario crítico",
  retweet_apoyo: "RT con comentario de apoyo",
  articulo_opinion: "Artículo de opinión",
  interpelacion: "Interpelación / citación",
  otro: "Otro",
};

const ACCION_COLOR: Record<AccionSugerida, string> = {
  pedido_informes: "var(--color-praxis-azul)",
  proyecto_contraposicion: "var(--color-praxis-azul)",
  declaracion_camara: "var(--color-praxis-azul)",
  silencio_estrategico: "var(--color-praxis-salmon)",
  retweet_critico: "var(--color-praxis-salmon)",
  retweet_apoyo: "var(--color-praxis-verde)",
  articulo_opinion: "var(--color-praxis-azul)",
  interpelacion: "var(--color-praxis-salmon)",
  otro: "rgb(100 116 139)",
};

const CONFIANZA_COLOR: Record<ConfianzaAccionable, string> = {
  alta: "var(--color-praxis-verde)",
  media: "var(--color-praxis-azul)",
  baja: "var(--color-praxis-salmon)",
};

interface Props {
  tipo: TipoEvento;
  eventoId: string;
  inicial: AccionableDTO | null;
}

export function AccionablePanel({ tipo, eventoId, inicial }: Props) {
  const resolveCtx = useApiContext();
  const [accionable, setAccionable] = useState<AccionableDTO | null>(inicial);
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  function generar(regenerar = false) {
    setError(null);
    startTransition(async () => {
      try {
        const ctx = await resolveCtx();
        const fn =
          tipo === "norma_bo"
            ? generarAccionableBo
            : generarAccionableArticulo;
        const acc = await fn(ctx, eventoId, { regenerar });
        setAccionable(acc);
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Falló la generación.";
        setError(
          msg.includes("perfil opositor")
            ? "Cargá el perfil opositor del despacho desde Configuración primero."
            : msg,
        );
      }
    });
  }

  if (accionable === null) {
    return (
      <div className="mt-3 flex flex-wrap items-center gap-2 rounded-md border border-dashed border-border bg-muted/30 px-3 py-2.5">
        <span className="text-[11px] text-muted-foreground">
          Sin acción analizada.
        </span>
        <button
          type="button"
          disabled={isPending}
          onClick={() => generar(false)}
          className="ml-auto inline-flex items-center gap-1 rounded-md bg-[var(--color-praxis-salmon)] px-2.5 py-1 text-[11px] font-semibold text-white transition-opacity disabled:opacity-50"
        >
          {isPending ? (
            <Loader2 className="size-3 animate-spin" />
          ) : (
            <Sparkles className="size-3" />
          )}
          Generar acción
        </button>
        {error && (
          <p className="basis-full pt-1 text-[11px] text-[var(--color-praxis-salmon)]">
            {error}
          </p>
        )}
      </div>
    );
  }

  const isSilencio = accionable.accion_sugerida === "silencio_estrategico";

  return (
    <div
      className="mt-3 space-y-2.5 rounded-md border border-border bg-card p-3"
      style={{ borderLeftColor: ACCION_COLOR[accionable.accion_sugerida], borderLeftWidth: 3 }}
    >
      <div className="flex flex-wrap items-start gap-2">
        <Badge
          className="text-[10px] font-semibold uppercase"
          style={{
            backgroundColor: ACCION_COLOR[accionable.accion_sugerida],
            color: "white",
          }}
        >
          {ACCION_LABEL[accionable.accion_sugerida]}
        </Badge>
        <Badge
          variant="outline"
          className="border-current text-[10px] font-semibold"
          style={{ color: CONFIANZA_COLOR[accionable.confianza] }}
        >
          Confianza: {accionable.confianza}
        </Badge>
        <button
          type="button"
          disabled={isPending}
          onClick={() => generar(true)}
          className="ml-auto inline-flex items-center gap-1 text-[10.5px] font-medium text-muted-foreground hover:text-[var(--color-praxis-azul)]"
          title="Forzar nueva inferencia (cuesta ~$0.03)"
        >
          {isPending ? (
            <Loader2 className="size-3 animate-spin" />
          ) : (
            <RefreshCw className="size-3" />
          )}
          Re-generar
        </button>
      </div>

      <div className="space-y-1">
        <p className="text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">
          Por qué importa
        </p>
        <p className="text-xs leading-relaxed text-foreground">
          {accionable.razon_para_despacho}
        </p>
      </div>

      <div className="space-y-1">
        <p className="text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">
          Qué hacer
        </p>
        <p className="text-xs leading-relaxed text-foreground">
          {accionable.explicacion_accion}
        </p>
      </div>

      {!isSilencio && accionable.tweets_sugeridos.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">
            Tweets sugeridos
          </p>
          {accionable.tweets_sugeridos.map((t, i) => (
            <TweetCard key={i} tono={t.tono} texto={t.texto} caracteres={t.caracteres} />
          ))}
        </div>
      )}

      {isSilencio && (
        <p className="flex items-center gap-1.5 text-[11px] italic text-muted-foreground">
          <AlertCircle className="size-3.5 text-[var(--color-praxis-salmon)]" />
          Recomendación: no twittear, no responder, dejar pasar. El bot
          considera que tocar este tema desgasta al despacho.
        </p>
      )}

      {error && (
        <p className="text-[11px] text-[var(--color-praxis-salmon)]">{error}</p>
      )}

      {/* Feedback del asesor (feat-43.2) — sólo si ya tiene id (estoy
          viendo un accionable persistido, no uno recién generado en
          memoria). */}
      {accionable.id && (
        <FeedbackButtons
          accionable={accionable}
          onUpdated={(next) => setAccionable(next)}
        />
      )}
    </div>
  );
}

function TweetCard({
  tono,
  texto,
  caracteres,
}: {
  tono: string;
  texto: string;
  caracteres: number;
}) {
  const [copied, setCopied] = useState(false);

  function copy() {
    navigator.clipboard.writeText(texto).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

  return (
    <div className="rounded-md border border-border bg-background px-2.5 py-2 text-xs">
      <div className="mb-1 flex items-center justify-between gap-2">
        <Badge variant="outline" className="text-[9.5px] uppercase">
          {tono}
        </Badge>
        <div className="flex items-center gap-2">
          <span
            className={`text-[10px] tabular-nums ${caracteres > 280 ? "text-[var(--color-praxis-salmon)] font-semibold" : "text-muted-foreground"}`}
          >
            {caracteres}/280
          </span>
          <button
            type="button"
            onClick={copy}
            className="inline-flex items-center gap-1 text-[10px] font-medium text-muted-foreground hover:text-[var(--color-praxis-azul)]"
          >
            {copied ? (
              <>
                <CheckCircle2 className="size-3 text-[var(--color-praxis-verde)]" />
                Copiado
              </>
            ) : (
              <>
                <Copy className="size-3" />
                Copiar
              </>
            )}
          </button>
        </div>
      </div>
      <p className="leading-relaxed text-foreground">{texto}</p>
    </div>
  );
}
