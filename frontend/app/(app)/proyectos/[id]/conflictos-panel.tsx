"use client";

/**
 * Panel de Validación de Conflictos Normativos (feat-42.6).
 *
 * Cliente Component que dispara POST /validar-conflictos y muestra:
 * - Botón "Validar conflictos" + estado pending
 * - Lista de conflictos detectados (uno por par artículo-norma), con:
 *   - Badge severidad (conflicto rojo, modificacion ámbar)
 *   - "Artículo N° del proyecto" + "Norma X / Artículo Y"
 *   - Explicación del LLM
 *   - Fragmento de la norma referida (colapsable)
 */
import { useState, useTransition } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  Loader2,
  ShieldCheck,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { useApiContext } from "@/lib/api/context-client";
import { validarConflictosNormativos } from "@/lib/api/endpoints";
import type {
  ConflictoDetectadoDTO,
  ResultadoValidacionDTO,
  SeveridadConflicto,
} from "@/lib/api/types";

const SEVERIDAD_COLOR: Record<SeveridadConflicto, string> = {
  conflicto: "var(--color-praxis-salmon)",
  modificacion: "rgb(217 119 6)", // amber
  complementa: "var(--color-praxis-verde)",
  ninguno: "rgb(100 116 139)",
};

const SEVERIDAD_LABEL: Record<SeveridadConflicto, string> = {
  conflicto: "Conflicto",
  modificacion: "Modificación tácita",
  complementa: "Complementa",
  ninguno: "Sin relación",
};

const FUENTE_LABEL: Record<string, string> = {
  constitucion_nacional: "Constitución Nacional",
  ley_19549_procedimiento_administrativo: "Ley 19.549 Procedimiento Administrativo",
  ley_24156_administracion_financiera: "Ley 24.156 Administración Financiera",
  ley_25188_etica_publica: "Ley 25.188 Ética Pública",
  ley_25326_proteccion_datos_personales: "Ley 25.326 Datos Personales",
  ley_26485_proteccion_mujeres: "Ley 26.485 Violencia hacia las Mujeres",
  ley_26061_proteccion_ninez: "Ley 26.061 Protección Niñez",
  ley_27275_acceso_informacion_publica: "Ley 27.275 Acceso a Info Pública",
  ley_23551_asociaciones_sindicales: "Ley 23.551 Asociaciones Sindicales",
  ley_24522_concursos_quiebras: "Ley 24.522 Concursos y Quiebras",
  ley_26122_regimen_dnu: "Ley 26.122 Régimen DNU",
  ley_20744_contrato_trabajo: "Ley 20.744 Contrato de Trabajo",
  ley_26529_derechos_paciente: "Ley 26.529 Derechos del Paciente",
  ley_16463_medicamentos: "Ley 16.463 Medicamentos",
  ley_26206_educacion_nacional: "Ley 26.206 Educación Nacional",
};

interface Props {
  proyectoId: string;
  articulosCount: number;
}

export function ConflictosPanel({ proyectoId, articulosCount }: Props) {
  const resolveCtx = useApiContext();
  const [isPending, startTransition] = useTransition();
  const [resultado, setResultado] = useState<ResultadoValidacionDTO | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);

  function validar() {
    setError(null);
    startTransition(async () => {
      try {
        const ctx = await resolveCtx();
        const r = await validarConflictosNormativos(ctx, proyectoId);
        setResultado(r);
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Falló la validación de conflictos.",
        );
      }
    });
  }

  if (articulosCount === 0) return null;

  return (
    <Card className="border-border bg-card p-5 shadow-none">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <ShieldCheck className="size-4 text-[var(--color-praxis-azul)]" />
          <p className="text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">
            Validación contra normativa vigente
          </p>
        </div>
        <button
          type="button"
          disabled={isPending}
          onClick={validar}
          className="inline-flex items-center gap-1.5 rounded-md bg-[var(--color-praxis-azul)] px-3 py-1.5 text-[11px] font-semibold text-white transition-opacity disabled:opacity-50"
        >
          {isPending ? (
            <Loader2 className="size-3 animate-spin" />
          ) : (
            <ShieldCheck className="size-3" />
          )}
          {resultado ? "Re-validar" : "Validar contra normativa"}
        </button>
      </div>

      <p className="mt-1.5 text-[11px] italic text-muted-foreground">
        Cruza cada artículo contra el corpus argentino (Constitución + 14
        leyes estructurales, 1.700+ chunks). Costo ~$0.15-0.25 por
        proyecto. Tarda 30-60 segundos.
      </p>

      {error && (
        <p className="mt-2 text-xs text-[var(--color-praxis-salmon)]">
          {error}
        </p>
      )}

      {resultado !== null && (
        <div className="mt-4 space-y-2.5">
          {resultado.sin_conflictos ? (
            <div className="flex items-start gap-2 rounded-md bg-[var(--color-praxis-verde)]/10 px-3 py-2.5">
              <CheckCircle2 className="size-4 flex-shrink-0 text-[var(--color-praxis-verde)]" />
              <div className="text-xs">
                <p className="font-medium text-foreground">
                  Sin conflictos detectados
                </p>
                <p className="mt-0.5 text-muted-foreground">
                  Evaluados {resultado.n_articulos_evaluados} artículos
                  contra el corpus. Ninguno entra en conflicto ni
                  modifica tácitamente la normativa vigente.
                </p>
              </div>
            </div>
          ) : (
            <>
              <p className="text-[11px] text-muted-foreground">
                {resultado.conflictos.length} potenciales conflictos
                detectados en {resultado.n_articulos_evaluados} artículos
                evaluados.
              </p>
              {resultado.conflictos.map((c, i) => (
                <ConflictoCard key={i} conflicto={c} />
              ))}
            </>
          )}
        </div>
      )}
    </Card>
  );
}

function ConflictoCard({ conflicto: c }: { conflicto: ConflictoDetectadoDTO }) {
  const [expanded, setExpanded] = useState(false);
  const color = SEVERIDAD_COLOR[c.severidad];
  const fuenteLegible =
    FUENTE_LABEL[c.fuente] ?? c.fuente.replace(/_/g, " ");

  return (
    <div
      className="rounded-md border border-border bg-background p-3"
      style={{ borderLeftColor: color, borderLeftWidth: 3 }}
    >
      <div className="flex flex-wrap items-start gap-2">
        <Badge
          className="text-[10px] font-semibold uppercase"
          style={{ backgroundColor: color, color: "white" }}
        >
          {SEVERIDAD_LABEL[c.severidad]}
        </Badge>
        <span className="text-[10.5px] uppercase tracking-wider text-muted-foreground">
          Artículo {c.indice_articulo_proyecto + 1} del proyecto
        </span>
      </div>
      <p className="mt-1.5 text-[11px] font-medium text-foreground">
        {fuenteLegible} · {c.articulo_label}
      </p>
      <p className="mt-1 text-xs leading-relaxed text-foreground">
        {c.explicacion}
      </p>
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="mt-1.5 inline-flex items-center gap-1 text-[10.5px] font-medium text-[var(--color-praxis-azul)] hover:underline"
      >
        <ChevronDown
          className={`size-3 transition-transform ${expanded ? "rotate-180" : ""}`}
        />
        {expanded ? "Ocultar" : "Ver"} texto de la norma referida
      </button>
      {expanded && (
        <pre className="mt-2 overflow-x-auto rounded-md bg-muted/40 px-2.5 py-2 text-[10.5px] leading-relaxed text-foreground whitespace-pre-wrap font-mono">
          {c.texto_norma_referida}
        </pre>
      )}
    </div>
  );
}
