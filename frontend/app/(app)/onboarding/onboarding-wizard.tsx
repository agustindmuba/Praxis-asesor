"use client";

/**
 * Wizard de 3 pasos del onboarding (feat-44.2).
 *
 * Estado interno: paso actual (1 | 2 | 3) + form data + resultado.
 * Backend: POST /onboarding/configurar-despacho.
 */
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import {
  ArrowRight,
  CheckCircle2,
  Loader2,
  Sparkles,
} from "lucide-react";

import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useApiContext } from "@/lib/api/context-client";
import { configurarDespacho } from "@/lib/api/endpoints";
import type {
  ConfigurarDespachoResponse,
  EstadoOnboardingDTO,
} from "@/lib/api/endpoints";

interface Props {
  estadoInicial: EstadoOnboardingDTO;
}

type Paso = 1 | 2 | 3;

export function OnboardingWizard({ estadoInicial }: Props) {
  const router = useRouter();
  const resolveCtx = useApiContext();
  const [isPending, startTransition] = useTransition();

  // Si el paso 1 ya está hecho, arrancamos en el paso 2 o 3.
  const pasoInicial: Paso = estadoInicial.paso_1_legislador_cargado
    ? estadoInicial.paso_2_perfil_opositor_cargado
      ? 3
      : 2
    : 1;

  const [paso, setPaso] = useState<Paso>(pasoInicial);
  const [slug, setSlug] = useState("");
  const [fotoUrl, setFotoUrl] = useState("");
  const [inferirPerfil, setInferirPerfil] = useState(true);
  const [resultado, setResultado] =
    useState<ConfigurarDespachoResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  function avanzar() {
    setError(null);
    setResultado(null);
    if (!slug.trim()) {
      setError("Necesitamos el nombre del legislador para empezar.");
      return;
    }
    startTransition(async () => {
      try {
        const ctx = await resolveCtx();
        const r = await configurarDespacho(ctx, {
          legislador_titular_slug: slug.trim(),
          foto_url: fotoUrl.trim() || null,
          inferir_perfil: inferirPerfil,
        });
        setResultado(r);
        setPaso(3);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Falló la configuración.");
      }
    });
  }

  return (
    <div className="space-y-4">
      <Stepper paso={paso} />

      {paso === 1 && (
        <Card className="space-y-4 border-border bg-card p-5 shadow-none">
          <div className="space-y-2">
            <h3 className="font-display text-base font-semibold text-[var(--color-praxis-azul)]">
              1 · Quién es el legislador titular
            </h3>
            <p className="text-xs text-muted-foreground">
              Escribí el nombre del legislador titular como te resulte
              natural — <em>Pablo Juliano</em>, <em>Juliano, Pablo</em> o
              el slug del padrón <code className="text-foreground">pjuliano</code>.
              Praxis lo resuelve contra el padrón oficial y lo
              normaliza para que el detector de menciones funcione.
            </p>
          </div>

          <div className="space-y-1.5">
            <label className="text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">
              Nombre del legislador
            </label>
            <Input
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
              placeholder="JULIANO, PABLO"
              autoComplete="off"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">
              URL de foto (opcional)
            </label>
            <Input
              value={fotoUrl}
              onChange={(e) => setFotoUrl(e.target.value)}
              placeholder="https://www.hcdn.gob.ar/diputados/.../foto.jpg"
              autoComplete="off"
            />
            <p className="text-[10.5px] text-muted-foreground">
              Si no la cargás ahora, mostramos las iniciales como
              placeholder en el panel del legislador.
            </p>
          </div>

          <label className="flex items-start gap-2 text-xs">
            <input
              type="checkbox"
              checked={inferirPerfil}
              onChange={(e) => setInferirPerfil(e.target.checked)}
              className="mt-1"
            />
            <span className="text-muted-foreground">
              Inferir el perfil opositor automáticamente con IA.{" "}
              <span className="text-foreground">Recomendado.</span>{" "}
              (Cuesta ~$0.06 USD, tarda 15-30 seg. Después lo editás a
              mano.)
            </span>
          </label>

          {error && (
            <p className="text-xs text-[var(--color-praxis-salmon)]">
              {error}
            </p>
          )}

          <div className="flex justify-end">
            <button
              type="button"
              disabled={isPending || !slug.trim()}
              onClick={avanzar}
              className="inline-flex items-center gap-1.5 rounded-md bg-[var(--color-praxis-azul)] px-3 py-1.5 text-xs font-semibold text-white transition-opacity disabled:opacity-50"
            >
              {isPending ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <Sparkles className="size-3.5" />
              )}
              {inferirPerfil ? "Inferir perfil y avanzar" : "Guardar y avanzar"}
            </button>
          </div>
        </Card>
      )}

      {paso === 2 && (
        <Card className="space-y-3 border-border bg-card p-5 shadow-none">
          <h3 className="font-display text-base font-semibold text-[var(--color-praxis-azul)]">
            2 · Inferir perfil opositor
          </h3>
          <p className="text-xs text-muted-foreground">
            Tu legislador ya está cargado pero no tenés perfil. El bot
            puede inferirlo desde su huella parlamentaria.
          </p>
          <button
            type="button"
            disabled={isPending}
            onClick={avanzar}
            className="inline-flex items-center gap-1.5 self-start rounded-md bg-[var(--color-praxis-azul)] px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
          >
            {isPending ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Sparkles className="size-3.5" />
            )}
            Inferir perfil
          </button>
        </Card>
      )}

      {paso === 3 && (
        <Card className="space-y-3 border-border bg-card p-5 shadow-none">
          <div className="flex items-start gap-3">
            <CheckCircle2 className="size-6 shrink-0 text-[var(--color-praxis-verde)]" />
            <div className="flex-1 space-y-1.5">
              <h3 className="font-display text-base font-semibold text-[var(--color-praxis-azul)]">
                3 · Listo
              </h3>
              {resultado && (
                <p className="text-xs text-foreground">{resultado.mensaje}</p>
              )}
              {resultado?.error_inferencia && (
                <p className="text-xs text-[var(--color-praxis-salmon)]">
                  {resultado.error_inferencia}
                </p>
              )}
              <ul className="space-y-0.5 pt-1 text-xs text-muted-foreground">
                <li>· Las fuentes de noticias y BO ya están sembradas.</li>
                <li>· El primer ciclo del scraper corre en menos de 1h.</li>
                <li>· Mañana 8 ART recibís el primer briefing por WhatsApp.</li>
              </ul>
            </div>
          </div>

          <div className="flex flex-wrap gap-2 pt-1">
            <button
              type="button"
              onClick={() => router.push("/dashboard")}
              className="inline-flex items-center gap-1.5 rounded-md bg-[var(--color-praxis-azul)] px-3 py-1.5 text-xs font-semibold text-white"
            >
              Ir al dashboard
              <ArrowRight className="size-3.5" />
            </button>
            <button
              type="button"
              onClick={() => router.push("/configuracion/perfil-opositor")}
              className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground"
            >
              Revisar perfil opositor
            </button>
          </div>
        </Card>
      )}
    </div>
  );
}

function Stepper({ paso }: { paso: Paso }) {
  const steps: { n: Paso; label: string }[] = [
    { n: 1, label: "Legislador" },
    { n: 2, label: "Perfil opositor" },
    { n: 3, label: "Listo" },
  ];
  return (
    <ol className="flex items-center gap-1 text-[11px]">
      {steps.map((s, i) => {
        const active = s.n === paso;
        const done = s.n < paso;
        return (
          <li key={s.n} className="flex items-center gap-1">
            <span
              className={
                "inline-flex size-5 items-center justify-center rounded-full text-[10px] font-semibold " +
                (done
                  ? "bg-[var(--color-praxis-verde)] text-white"
                  : active
                    ? "bg-[var(--color-praxis-azul)] text-white"
                    : "border border-border text-muted-foreground")
              }
            >
              {done ? "✓" : s.n}
            </span>
            <span
              className={
                active
                  ? "font-semibold text-foreground"
                  : "text-muted-foreground"
              }
            >
              {s.label}
            </span>
            {i < steps.length - 1 && (
              <span className="mx-1 text-border">·</span>
            )}
          </li>
        );
      })}
    </ol>
  );
}
