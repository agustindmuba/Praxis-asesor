/**
 * Header de la página de detalle del briefing.
 *
 * Solo es info — el render del briefing en sí vive en el iframe del HTML.
 */
import type { BriefingDTO, OrdenDelDiaDTO } from "@/lib/api/types";

interface Props {
  od: OrdenDelDiaDTO;
  briefing: BriefingDTO;
}

export function BriefingHeader({ od, briefing }: Props) {
  return (
    <div className="space-y-1">
      <h2 className="text-2xl font-bold tracking-tight">
        {od.titulo || `Sesión ${od.camara} del ${od.fecha_sesion}`}
      </h2>
      <p className="text-sm text-muted-foreground">
        {od.camara} · {od.fecha_sesion}
        {od.hora_sesion ? ` ${od.hora_sesion}` : ""} ·{" "}
        {od.expedientes_ids.length} expedientes en el OD ·{" "}
        {briefing.proyectos_del_despacho_total} del despacho (
        {briefing.proyectos_como_autor} autor /{" "}
        {briefing.proyectos_como_cofirmante} cofirmante)
      </p>
    </div>
  );
}
