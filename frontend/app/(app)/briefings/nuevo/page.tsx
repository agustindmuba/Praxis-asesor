/**
 * Página /briefings/nuevo — wizard de creación de OrdenDelDia.
 *
 * Server Component que solo renderiza el form (client). La lógica de
 * submit vive en el componente cliente para usar fetch desde browser.
 */
import { NuevoBriefingForm } from "@/components/features/briefing/nuevo-briefing-form";

export const metadata = { title: "Nuevo briefing" };

export default function NuevoBriefingPage() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold tracking-tight">Nuevo briefing pre-sesión</h2>
        <p className="text-sm text-muted-foreground">
          Pegá la lista de expedientes que se van a tratar en la sesión. El sistema cruza
          con tus seguimientos y genera el briefing.
        </p>
      </div>
      <NuevoBriefingForm />
    </div>
  );
}
