/**
 * /onboarding — wizard de primer uso (feat-44).
 *
 * Server Component que pide el estado del onboarding y delega el
 * stepper a un Client Component. Si todo está listo, ofrece un link
 * directo al dashboard.
 */
import Link from "next/link";
import { CheckCircle2 } from "lucide-react";

import { Card } from "@/components/ui/card";
import { getApiContextServer } from "@/lib/api/context-server";
import { getEstadoOnboarding } from "@/lib/api/endpoints";

import { OnboardingWizard } from "./onboarding-wizard";

export const metadata = { title: "Onboarding" };

export default async function OnboardingPage() {
  const ctx = await getApiContextServer();
  const estado = await getEstadoOnboarding(ctx).catch(() => null);

  if (estado === null) {
    return (
      <Card className="border-border bg-card p-6 shadow-none">
        <p className="text-xs text-muted-foreground">
          No se pudo cargar el estado del onboarding.
        </p>
      </Card>
    );
  }

  if (estado.todo_listo) {
    return (
      <div className="space-y-6">
        <header className="space-y-2">
          <p className="text-[10.5px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
            Onboarding
          </p>
          <h2 className="font-display text-3xl font-bold tracking-tight text-[var(--color-praxis-azul)]">
            Despacho configurado
          </h2>
        </header>
        <Card className="border-border bg-card p-6 shadow-none">
          <div className="flex items-start gap-4">
            <CheckCircle2 className="size-7 text-[var(--color-praxis-verde)]" />
            <div className="flex-1 space-y-2">
              <p className="text-sm text-foreground">
                Tu despacho ya está configurado y el bot está activo.
              </p>
              <ul className="text-xs text-muted-foreground">
                <li>✓ Legislador titular cargado</li>
                <li>✓ Perfil opositor inferido</li>
                {estado.paso_3_destinatarios_cargados && (
                  <li>✓ Destinatarios WhatsApp activos</li>
                )}
                {estado.paso_4_primer_accionable && (
                  <li>✓ Accionables generándose</li>
                )}
              </ul>
              <div className="pt-3">
                <Link
                  href="/dashboard"
                  className="inline-flex items-center gap-1.5 rounded-md bg-[var(--color-praxis-azul)] px-3 py-1.5 text-xs font-semibold text-white"
                >
                  Ir al dashboard
                </Link>
              </div>
            </div>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <p className="text-[10.5px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
          Onboarding
        </p>
        <h2 className="font-display text-3xl font-bold tracking-tight text-[var(--color-praxis-azul)]">
          Configurá tu despacho en 30 segundos
        </h2>
        <p className="max-w-2xl text-sm text-muted-foreground">
          Decinos quién es el legislador titular y el bot infiere el
          perfil opositor desde su huella parlamentaria (proyectos
          firmados, votaciones, cofirmantes). Después podés editarlo a
          mano.
        </p>
      </header>

      <OnboardingWizard estadoInicial={estado} />
    </div>
  );
}
