/**
 * Panel "Huella del legislador titular" (feat-46).
 *
 * Server Component. Se monta en /dashboard (arriba del Hub diario).
 *
 * Estructura:
 * - Avatar (foto del legislador o iniciales si no hay) + nombre + bloque + distrito.
 * - Stat "X proyectos firmados".
 * - Barra apilada 100% con la distribución por estado de avance.
 *   Diferencia explícitamente:
 *     - Sancionado (verde fuerte)
 *     - Media sanción HCDN (verde suave)
 *     - Media sanción HSN (verde suave, otro tono)
 *     - Con dictamen (azul Praxis)
 *     - En comisión (azul claro)
 *     - Ingresado / En trámite (crema)
 *     - Caduco / Archivado (salmón)
 * - Distribución por tipo de proyecto y top 6 áreas con sus %.
 */
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { getApiContextServer } from "@/lib/api/context-server";
import { getHuellaLegislador } from "@/lib/api/endpoints";
import type {
  AreaTematica,
  CategoriaConPctDTO,
  EstadoExpediente,
  HuellaLegisladorDTO,
  TipoExpediente,
} from "@/lib/api/types";

/** Color por estado. Verdes para sanciones, azules para tránsito, etc. */
const ESTADO_COLOR: Record<string, { bg: string; label: string }> = {
  sancionado: { bg: "#2E5A45", label: "Sancionado" },
  media_sancion_hcdn: { bg: "#3B6652", label: "Media sanción HCDN" },
  media_sancion_hsn: { bg: "#4D7A6A", label: "Media sanción HSN" },
  con_dictamen: { bg: "#2A3D75", label: "Con dictamen" },
  en_comision: { bg: "#7889B5", label: "En comisión" },
  ingresado: { bg: "#A89F9B", label: "Ingresado" },
  desconocido: { bg: "#C9C3C1", label: "En trámite" },
  archivado: { bg: "#E8C7BB", label: "Archivado" },
  caduco: { bg: "#D48D7C", label: "Caduco" },
};

const TIPO_LABEL: Record<string, string> = {
  proyecto_ley: "Ley",
  proyecto_resolucion: "Resolución",
  proyecto_declaracion: "Declaración",
  proyecto_comunicacion: "Comunicación",
  mensaje_pe: "Mensaje PE",
  decreto: "Decreto",
  otro: "Otro",
};

const AREA_LABEL: Record<string, string> = {
  salud: "Salud",
  educacion: "Educación",
  ambiente: "Ambiente",
  trabajo: "Trabajo",
  derechos_humanos: "DDHH",
  seguridad: "Seguridad",
  transporte: "Transporte",
  infraestructura: "Infraestructura",
  justicia: "Justicia",
  relaciones_exteriores: "Rel. Exteriores",
  economia: "Economía",
  otros: "Otros",
};

export async function HuellaLegisladorPanel() {
  const ctx = await getApiContextServer();
  const huella = await getHuellaLegislador(ctx).catch(() => null);

  if (huella === null || huella.total_firmados === 0) {
    return (
      <Card className="border-border bg-card p-5 shadow-none">
        <p className="text-xs text-muted-foreground">
          Sin datos de huella parlamentaria. Cargá el slug del legislador
          titular en <code>/configuracion</code>.
        </p>
      </Card>
    );
  }

  return (
    <Card className="space-y-4 border-border bg-card p-5 shadow-none">
      {/* Header: foto + identidad */}
      <div className="flex items-start gap-4">
        <AvatarLegislador
          fotoUrl={huella.foto_url}
          nombre={huella.nombre ?? huella.slug ?? "?"}
        />
        <div className="min-w-0 flex-1">
          <p className="text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">
            Legislador titular del despacho
          </p>
          <h3 className="mt-0.5 font-display text-lg font-bold tracking-tight text-[var(--color-praxis-azul)]">
            {formatNombre(huella.nombre ?? huella.slug ?? "?")}
          </h3>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            {huella.bloque_dominante && (
              <Badge variant="outline" className="text-[10px]">
                {huella.bloque_dominante}
              </Badge>
            )}
            {huella.distrito_dominante && (
              <Badge variant="outline" className="text-[10px]">
                {huella.distrito_dominante}
              </Badge>
            )}
            <span className="text-[10.5px] text-muted-foreground">
              {huella.total_firmados} proyecto
              {huella.total_firmados === 1 ? "" : "s"} firmado
              {huella.total_firmados === 1 ? "" : "s"}
            </span>
          </div>
        </div>
      </div>

      {/* Barra apilada por estado */}
      <div>
        <p className="text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">
          Estado de avance ({huella.total_firmados} = 100%)
        </p>
        <BarraApilada items={huella.por_estado} colors={ESTADO_COLOR} />
        <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[10.5px]">
          {huella.por_estado.map((c) => (
            <LegendItem
              key={c.key}
              color={ESTADO_COLOR[c.key]?.bg ?? "#999"}
              label={ESTADO_COLOR[c.key]?.label ?? c.key}
              total={c.total}
              pct={c.pct}
            />
          ))}
        </div>
      </div>

      {/* Distribución por tipo y áreas */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <DistribucionMini
          title="Por tipo de proyecto"
          items={huella.por_tipo}
          labelMap={TIPO_LABEL}
        />
        <DistribucionMini
          title="Top áreas temáticas"
          items={huella.por_area}
          labelMap={AREA_LABEL}
        />
      </div>
    </Card>
  );
}

function AvatarLegislador({
  fotoUrl,
  nombre,
}: {
  fotoUrl: string | null;
  nombre: string;
}) {
  if (fotoUrl) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={fotoUrl}
        alt={`Foto de ${nombre}`}
        className="size-16 shrink-0 rounded-full border-2 border-[var(--color-praxis-azul)] object-cover"
      />
    );
  }
  return (
    <div
      className="flex size-16 shrink-0 items-center justify-center rounded-full border-2 border-[var(--color-praxis-azul)] bg-[var(--color-praxis-crema)] font-display text-base font-bold text-[var(--color-praxis-azul)]"
      title={`Sin foto cargada — setear en /configuracion`}
    >
      {iniciales(nombre)}
    </div>
  );
}

function BarraApilada({
  items,
  colors,
}: {
  items: CategoriaConPctDTO[];
  colors: Record<string, { bg: string; label: string }>;
}) {
  if (items.length === 0) {
    return <div className="mt-1.5 h-3 w-full rounded-full bg-muted/40" />;
  }
  return (
    <div className="mt-1.5 flex h-3 w-full overflow-hidden rounded-full">
      {items.map((c) => {
        const color = colors[c.key]?.bg ?? "#999";
        const label = colors[c.key]?.label ?? c.key;
        return (
          <div
            key={c.key}
            style={{ width: `${c.pct * 100}%`, backgroundColor: color }}
            title={`${label}: ${c.total} (${Math.round(c.pct * 100)}%)`}
          />
        );
      })}
    </div>
  );
}

function LegendItem({
  color,
  label,
  total,
  pct,
}: {
  color: string;
  label: string;
  total: number;
  pct: number;
}) {
  return (
    <span className="inline-flex items-center gap-1 whitespace-nowrap">
      <span
        className="inline-block size-2 shrink-0 rounded-sm"
        style={{ backgroundColor: color }}
        aria-hidden
      />
      <span className="text-foreground">{label}</span>
      <span className="font-mono text-muted-foreground">
        {total} · {Math.round(pct * 100)}%
      </span>
    </span>
  );
}

function DistribucionMini({
  title,
  items,
  labelMap,
}: {
  title: string;
  items: CategoriaConPctDTO[];
  labelMap: Record<string, string>;
}) {
  if (items.length === 0) return null;
  return (
    <div>
      <p className="text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">
        {title}
      </p>
      <ul className="mt-1.5 space-y-1">
        {items.map((c) => (
          <li key={c.key} className="space-y-0.5">
            <div className="flex items-center justify-between gap-2 text-[11px]">
              <span className="font-medium text-foreground">
                {labelMap[c.key] ?? c.key}
              </span>
              <span className="font-mono text-[10.5px] text-muted-foreground">
                {c.total} · {Math.round(c.pct * 100)}%
              </span>
            </div>
            <div className="h-1.5 w-full rounded-full bg-muted/40">
              <div
                className="h-1.5 rounded-full bg-[var(--color-praxis-azul)]"
                style={{ width: `${c.pct * 100}%` }}
              />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function formatNombre(s: string): string {
  // "JULIANO, PABLO" → "Pablo Juliano" para que se lea más amable
  const [apellido, nombre] = s.split(",").map((p) => p.trim());
  const cap = (w: string) =>
    w
      .toLowerCase()
      .split(" ")
      .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
      .join(" ");
  if (apellido && nombre) {
    return `${cap(nombre)} ${cap(apellido)}`;
  }
  return cap(s);
}

function iniciales(s: string): string {
  const [apellido, nombre] = s.split(",").map((p) => p.trim());
  if (apellido && nombre) {
    return (nombre.charAt(0) + apellido.charAt(0)).toUpperCase();
  }
  const partes = s.trim().split(" ").filter(Boolean);
  return (
    (partes[0]?.charAt(0) ?? "?") +
    (partes[1]?.charAt(0) ?? "")
  ).toUpperCase();
}
