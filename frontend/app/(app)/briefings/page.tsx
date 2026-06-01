/**
 * Página /briefings — lista de órdenes del día del despacho.
 *
 * Server Component. Lista los OD existentes y ofrece "Nuevo briefing".
 * El briefing se genera desde la página de detalle del OD.
 */
import Link from "next/link";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { getApiContextServer } from "@/lib/api/context-server";
import { listarOrdenesDelDia } from "@/lib/api/endpoints";

export const metadata = { title: "Briefings" };

export default async function BriefingsPage() {
  const ctx = await getApiContextServer();
  const ods = await listarOrdenesDelDia(ctx);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Briefings pre-sesión</h2>
          <p className="text-sm text-muted-foreground">
            Generá un briefing para cada sesión del recinto. Cargás el orden del día y
            el sistema arma las alertas, argumentos, cofirmantes y antecedentes.
          </p>
        </div>
        <Button asChild>
          <Link href="/briefings/nuevo">Nuevo briefing</Link>
        </Button>
      </div>

      {ods.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <p className="text-sm font-medium">Todavía no generaste ningún briefing</p>
            <p className="mx-auto mt-2 max-w-md text-xs text-muted-foreground">
              Empezá creando un orden del día con los números de expediente que vas a
              tratar la próxima sesión. El briefing se genera a partir de ahí.
            </p>
            <Button asChild className="mt-4">
              <Link href="/briefings/nuevo">Crear el primer briefing</Link>
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {ods.map((od) => (
            <Link key={od.id} href={`/briefings/${od.id}`} className="block">
              <Card className="transition-colors hover:bg-accent/50">
                <CardHeader className="pb-2">
                  <CardTitle className="text-base font-semibold">
                    {od.titulo || `Sesión ${od.camara} del ${od.fecha_sesion}`}
                  </CardTitle>
                </CardHeader>
                <CardContent className="flex items-center justify-between gap-4 pt-0 text-sm text-muted-foreground">
                  <div className="flex items-center gap-4">
                    <span>{od.camara}</span>
                    <span>{od.fecha_sesion}</span>
                    {od.hora_sesion ? <span>{od.hora_sesion}</span> : null}
                    <span>{od.expedientes_ids.length} expedientes</span>
                  </div>
                  <span className="text-xs uppercase tracking-wide">
                    {od.fuente === "upload_manual" ? "Manual" : "Auto"}
                  </span>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
