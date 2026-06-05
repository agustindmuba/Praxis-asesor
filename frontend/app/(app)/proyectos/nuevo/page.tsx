/**
 * /proyectos/nuevo — form para crear un proyecto en redacción.
 *
 * Server Component que renderiza el Client Component del form.
 */
import Link from "next/link";
import { ArrowLeft } from "lucide-react";

import { NuevoProyectoForm } from "./nuevo-proyecto-form";

export const metadata = { title: "Nuevo proyecto" };

export default function NuevoProyectoPage() {
  return (
    <div className="space-y-6">
      <Link
        href="/proyectos"
        className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-3.5" />
        Volver a proyectos
      </Link>
      <header>
        <p className="text-[10.5px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
          Despacho · Redacción
        </p>
        <h2 className="mt-1 font-display text-3xl font-bold tracking-tight text-[var(--color-praxis-azul)]">
          Nuevo proyecto
        </h2>
        <p className="mt-1.5 text-sm text-muted-foreground">
          Elegí tipo, escribí el título y el objeto. El bot después te
          asiste con articulado y fundamentos.
        </p>
      </header>
      <NuevoProyectoForm />
    </div>
  );
}
