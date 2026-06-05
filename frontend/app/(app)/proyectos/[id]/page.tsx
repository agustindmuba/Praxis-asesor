/**
 * /proyectos/[id] — editor del proyecto con asistentes LLM (feat-42.3).
 *
 * Server Component que trae el proyecto y renderiza el Client
 * Component del editor.
 */
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "lucide-react";

import { ApiError404 } from "@/lib/api/client";
import { getApiContextServer } from "@/lib/api/context-server";
import { getProyectoRedaccion } from "@/lib/api/endpoints";

import { ProyectoEditor } from "./proyecto-editor";

interface PageProps {
  params: Promise<{ id: string }>;
}

export const metadata = { title: "Editor de proyecto" };

export default async function ProyectoEditorPage({ params }: PageProps) {
  const { id } = await params;
  const ctx = await getApiContextServer();
  const proyecto = await getProyectoRedaccion(ctx, id).catch((err) => {
    if (err instanceof ApiError404) return null;
    throw err;
  });
  if (proyecto === null) notFound();

  return (
    <div className="space-y-6">
      <Link
        href="/proyectos"
        className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-3.5" />
        Volver a proyectos
      </Link>
      <ProyectoEditor inicial={proyecto} />
    </div>
  );
}
