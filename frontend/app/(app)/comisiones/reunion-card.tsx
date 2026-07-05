/**
 * Card de una reunión de comisión.
 *
 * Muestra: hora · sala · tipo · convoca · tema · expedientes · oportunidad
 * política · acción sugerida. El análisis se hace en background; la UI
 * solo presenta el resultado al asesor.
 */
import {
  ExternalLink,
  Clock,
  MapPin,
  Users as UsersIcon,
  FileText,
  Target,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { ReunionConComisionDTO } from "@/lib/api/endpoints";


interface Props {
  reunion: ReunionConComisionDTO;
}


export function ReunionCard({ reunion }: Props) {
  return (
    <li className="space-y-2 border-l-2 border-[var(--color-praxis-azul)]/30 pl-3 text-xs">
      {/* Header: comisión + rol */}
      <div className="flex flex-wrap items-baseline gap-2">
        <div className="font-semibold text-foreground">
          {reunion.comision_nombre}
        </div>
        {reunion.rol_legislador && (
          <Badge variant="secondary" className="text-[9.5px]">
            Rol: {reunion.rol_legislador}
          </Badge>
        )}
        {reunion.tipo_reunion && (
          <Badge
            variant="outline"
            className="text-[9.5px] border-[var(--color-praxis-azul)] text-[var(--color-praxis-azul)]"
          >
            {reunion.tipo_reunion}
          </Badge>
        )}
      </div>

      {/* Hora · Sala (datos parseados, siempre presentes si el portal los expone) */}
      {(reunion.hora || reunion.sala) && (
        <div className="flex flex-wrap items-center gap-3 text-[10.5px] text-muted-foreground">
          {reunion.hora && (
            <span className="inline-flex items-center gap-1">
              <Clock className="size-3" /> {reunion.hora}
            </span>
          )}
          {reunion.sala && (
            <span className="inline-flex items-center gap-1">
              <MapPin className="size-3" /> {reunion.sala}
            </span>
          )}
        </div>
      )}

      {/* Tema (LLM) o descripción cruda */}
      {reunion.tema_corto ? (
        <p className="leading-relaxed text-foreground">{reunion.tema_corto}</p>
      ) : (
        reunion.descripcion && (
          <p className="leading-relaxed text-muted-foreground">
            {reunion.descripcion}
          </p>
        )
      )}

      {/* Convoca (LLM) */}
      {reunion.convocada_por && (
        <div className="inline-flex items-center gap-1 text-[10.5px] text-muted-foreground">
          <UsersIcon className="size-3" />
          <span>
            <span className="font-medium">Convoca:</span>{" "}
            {reunion.convocada_por}
          </span>
        </div>
      )}

      {/* Expedientes citados */}
      {reunion.expedientes_citados.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 text-[10.5px]">
          <FileText className="size-3 text-muted-foreground" />
          <span className="text-muted-foreground">Expedientes:</span>
          {reunion.expedientes_citados.slice(0, 6).map((e) => (
            <Badge
              key={e}
              variant="outline"
              className="font-mono text-[9.5px]"
            >
              {e}
            </Badge>
          ))}
          {reunion.expedientes_citados.length > 6 && (
            <span className="text-muted-foreground">
              +{reunion.expedientes_citados.length - 6}
            </span>
          )}
        </div>
      )}

      {/* Oportunidad política */}
      {reunion.oportunidad_politica && (
        <div className="rounded-md border border-[var(--color-praxis-verde)]/40 bg-[var(--color-praxis-verde)]/5 p-2.5">
          <div className="mb-1 flex items-center gap-1 text-[10.5px] font-semibold uppercase tracking-wider text-[var(--color-praxis-verde)]">
            <Target className="size-3" /> Oportunidad política
          </div>
          <p className="leading-relaxed text-[11px] text-foreground">
            {reunion.oportunidad_politica}
          </p>
          {reunion.accion_sugerida && (
            <p className="mt-1.5 text-[11px]">
              <span className="font-semibold text-[var(--color-praxis-verde)]">
                Acción sugerida:
              </span>{" "}
              {reunion.accion_sugerida}
            </p>
          )}
        </div>
      )}

      {reunion.citacion_pdf_url && (
        <div className="pt-1">
          <a
            href={reunion.citacion_pdf_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 rounded-md border border-border bg-white px-2 py-1 text-[10.5px] font-medium text-[var(--color-praxis-azul)]"
          >
            <ExternalLink className="size-3" />
            Citación oficial (PDF)
          </a>
        </div>
      )}
    </li>
  );
}
