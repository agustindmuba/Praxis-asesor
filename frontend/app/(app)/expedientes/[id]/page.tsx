/**
 * Página /expedientes/[id] — ficha completa.
 *
 * Server Component que hace el fetch en RSC. Si el expediente no existe,
 * tira 404 con `notFound()`.
 */
import { notFound } from "next/navigation";

import { ApiError404 } from "@/lib/api/client";
import { getApiContextServer } from "@/lib/api/context-server";
import { getExpediente } from "@/lib/api/endpoints";

import { FichaHeader } from "@/components/features/expedientes/ficha-header";
import { FichaFirmantes } from "@/components/features/expedientes/ficha-firmantes";
import { FichaResumen } from "@/components/features/expedientes/ficha-resumen";
import { FichaTramite } from "@/components/features/expedientes/ficha-tramite";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";

interface PageProps {
  params: Promise<{ id: string }>;
}

export async function generateMetadata({ params }: PageProps) {
  const { id } = await params;
  return { title: `Expediente ${id.slice(0, 8)}…` };
}

export default async function FichaPage({ params }: PageProps) {
  const { id } = await params;
  const ctx = await getApiContextServer();

  let expediente;
  try {
    expediente = await getExpediente(ctx, id);
  } catch (err) {
    if (err instanceof ApiError404) {
      notFound();
    }
    throw err;
  }

  return (
    <div className="space-y-6">
      <FichaHeader expediente={expediente} />

      <Tabs defaultValue="resumen">
        <TabsList>
          <TabsTrigger value="resumen">Resumen</TabsTrigger>
          <TabsTrigger value="tramite">
            Trámite{" "}
            <span className="ml-1 text-xs text-muted-foreground">
              ({expediente.tramite.length})
            </span>
          </TabsTrigger>
          <TabsTrigger value="firmantes">
            Firmantes{" "}
            <span className="ml-1 text-xs text-muted-foreground">
              ({expediente.firmantes.length})
            </span>
          </TabsTrigger>
          <TabsTrigger value="notas">Notas internas</TabsTrigger>
        </TabsList>

        <TabsContent value="resumen" className="mt-4">
          <FichaResumen expediente={expediente} />
        </TabsContent>

        <TabsContent value="tramite" className="mt-4">
          <FichaTramite tramite={expediente.tramite} />
        </TabsContent>

        <TabsContent value="firmantes" className="mt-4">
          <FichaFirmantes firmantes={expediente.firmantes} giros={expediente.giros} />
        </TabsContent>

        <TabsContent value="notas" className="mt-4">
          <div className="rounded-lg border border-dashed border-border bg-card p-12 text-center">
            <p className="text-sm font-medium">Notas internas del despacho</p>
            <p className="mt-2 text-xs text-muted-foreground">
              Esta sección llega con feat/22. Vas a poder agregar comentarios privados
              de tu despacho, asignarlos a un responsable, y referenciar eventos del trámite.
            </p>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
