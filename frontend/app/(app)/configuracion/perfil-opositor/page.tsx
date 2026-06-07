/**
 * /configuracion/perfil-opositor — perfil narrativo del despacho
 * (feat-42.1).
 *
 * Server Component que hace SSR del perfil actual (o null si nunca
 * se infirió). Renderiza el form como Client Component que tiene
 * estado local + botones de "Inferir desde huella" y "Guardar".
 */
import Link from "next/link";
import { ArrowLeft, Sparkles } from "lucide-react";

import { Card } from "@/components/ui/card";
import { getApiContextServer } from "@/lib/api/context-server";
import { getPerfilOpositor } from "@/lib/api/endpoints";

import { InsightsFeedbackPanel } from "@/components/features/perfil-opositor/insights-feedback-panel";

import { PerfilOpositorEditor } from "./perfil-opositor-editor";

export const metadata = { title: "Perfil opositor" };

export default async function PerfilOpositorPage() {
  const ctx = await getApiContextServer();
  const perfil = await getPerfilOpositor(ctx).catch(() => null);

  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <Link
          href="/configuracion"
          className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-3.5" />
          Volver a configuración
        </Link>
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-[10.5px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
              Despacho · Perfil
            </p>
            <h2 className="mt-1 font-display text-3xl font-bold tracking-tight text-[var(--color-praxis-azul)]">
              Perfil opositor
            </h2>
            <p className="mt-1.5 max-w-3xl text-sm text-muted-foreground">
              Línea política del despacho — qué milita, contra qué, con
              qué tono. Se infiere automáticamente desde proyectos,
              votaciones y cofirmantes registrados en la DB del
              despacho. El asesor edita el borrador antes de aprobarlo.
              Este perfil orienta las acciones sugeridas en BO y
              Noticias.
            </p>
          </div>
        </div>
      </header>

      {perfil === null ? (
        <Card className="border-border bg-card p-6 shadow-none">
          <div className="flex items-start gap-4">
            <div className="rounded-md bg-[var(--color-praxis-salmon)]/10 p-3">
              <Sparkles className="size-6 text-[var(--color-praxis-salmon)]" />
            </div>
            <div className="flex-1">
              <h3 className="font-display text-lg font-semibold text-foreground">
                Sin perfil generado
              </h3>
              <p className="mt-1 text-sm text-muted-foreground">
                Inferí un borrador desde la huella parlamentaria del
                legislador titular. El bot analiza expedientes firmados,
                votaciones y cofirmantes, y te devuelve una propuesta
                editable.
              </p>
              <p className="mt-2 text-xs text-muted-foreground">
                Costo aproximado: $0.06 USD por inferencia.
              </p>
            </div>
          </div>
        </Card>
      ) : null}

      <PerfilOpositorEditor inicial={perfil} />

      {/* Insights del feedback (feat-43.3) — al final del page para
          que el asesor primero vea/edite el perfil y después vea
          cómo el feedback está sugiriendo ajustes. */}
      {perfil !== null && <InsightsFeedbackPanel />}
    </div>
  );
}
