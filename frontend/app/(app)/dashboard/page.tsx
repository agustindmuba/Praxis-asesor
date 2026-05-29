/**
 * Dashboard placeholder — bootstrap PR.
 *
 * Server Component que llama al backend con el ApiContext del request.
 * El PR siguiente (feat/20-frontend-busqueda y feat/21-frontend-ficha) trae
 * cards reales con seguimientos agrupados por prioridad.
 */
import { getApiContextServer } from "@/lib/api/context-server";
import { listarSeguimientos } from "@/lib/api/endpoints";

export const metadata = {
  title: "Dashboard",
};

export default async function DashboardPage() {
  const ctx = await getApiContextServer();
  const seguimientos = await listarSeguimientos(ctx);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold tracking-tight">Dashboard</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Resumen de tu trabajo en este despacho.
        </p>
      </div>

      <div className="rounded-lg border border-border bg-card p-6">
        <h3 className="text-base font-semibold">Mis seguimientos</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          {seguimientos.length === 0
            ? "Todavía no marcaste ningún expediente."
            : `${seguimientos.length} expedientes seguidos.`}
        </p>
        {seguimientos.length > 0 && (
          <ul className="mt-4 space-y-2 text-sm">
            {seguimientos.map((s) => (
              <li key={s.id} className="flex items-center justify-between">
                <span className="font-mono text-xs text-muted-foreground">
                  {s.expediente_id.slice(0, 8)}…
                </span>
                <span className="text-xs capitalize">{s.prioridad}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="rounded-lg border border-dashed border-border bg-card p-6 text-center text-sm text-muted-foreground">
        Más cards (actividad reciente, alertas, etc.) llegan con feat/21.
      </div>
    </div>
  );
}
