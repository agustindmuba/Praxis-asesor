/**
 * /configuracion — destinatarios WhatsApp + histórico de envíos
 * (feat-41.5).
 *
 * Server Component. Server-side fetch de destinatarios + envíos
 * recientes. El form de creación/edición es un Client Component
 * separado.
 */
import Link from "next/link";
import {
  ExternalLink,
  MessageCircle,
  Send,
  Sparkles,
  UserPlus,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { getApiContextServer } from "@/lib/api/context-server";
import {
  getHuellaLegislador,
  listarDestinatarios,
  listarEnviosWhatsApp,
} from "@/lib/api/endpoints";
import type {
  DestinatarioDTO,
  EnvioWhatsAppDTO,
  EstadoEnvioWhatsApp,
  TipoEnvioWhatsApp,
} from "@/lib/api/types";

import { BriefingPreviewSection } from "./briefing-preview";
import { DestinatarioFormulario } from "./destinatario-formulario";
import { FotoLegisladorForm } from "./foto-legislador-form";

export const metadata = { title: "Configuración" };

const ESTADO_LABEL: Record<EstadoEnvioWhatsApp, string> = {
  pendiente: "Pendiente",
  enviado: "Enviado",
  entregado: "Entregado",
  leido: "Leído",
  fallido: "Fallido",
  rechazado: "Rechazado",
};

const ESTADO_COLOR: Record<EstadoEnvioWhatsApp, string> = {
  pendiente: "var(--color-praxis-salmon)",
  enviado: "var(--color-praxis-azul)",
  entregado: "var(--color-praxis-azul)",
  leido: "var(--color-praxis-verde)",
  fallido: "var(--color-praxis-salmon)",
  rechazado: "var(--color-praxis-salmon)",
};

const TIPO_LABEL: Record<TipoEnvioWhatsApp, string> = {
  briefing_diario: "Briefing diario",
  alerta_mencion: "Alerta de mención",
  alerta_bo: "Alerta BO",
  otro: "Otro",
};

function formatFecha(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("es-AR", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatRol(rol: string): string {
  return rol.replace(/_/g, " ");
}

export default async function ConfiguracionPage() {
  const ctx = await getApiContextServer();

  const [destinatarios, envios, huella] = await Promise.all([
    listarDestinatarios(ctx).catch(() => []),
    listarEnviosWhatsApp(ctx).catch(() => []),
    getHuellaLegislador(ctx).catch(() => null),
  ]);

  return (
    <div className="space-y-10">
      <header>
        <p className="text-[10.5px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
          Despacho · Configuración
        </p>
        <h2 className="mt-1 font-display text-3xl font-bold tracking-tight text-[var(--color-praxis-azul)]">
          Destinatarios y envíos
        </h2>
        <p className="mt-1.5 text-sm text-muted-foreground">
          Gestioná quiénes reciben briefings y alertas por WhatsApp, y
          revisá el histórico de envíos.
        </p>
      </header>

      <PerfilOpositorLink />

      <FotoLegisladorForm
        fotoActual={huella?.foto_url ?? null}
        nombreLegislador={huella?.nombre ?? null}
      />

      <BriefingPreviewSection />

      <DestinatariosSection destinatarios={destinatarios} />

      <EnviosSection envios={envios} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Perfil opositor (link a /configuracion/perfil-opositor)
// ---------------------------------------------------------------------------

function PerfilOpositorLink() {
  return (
    <Link
      href="/configuracion/perfil-opositor"
      className="block"
    >
      <Card className="group border-border bg-card p-5 shadow-none transition-colors hover:border-[var(--color-praxis-salmon)]">
        <div className="flex items-start gap-3">
          <div className="rounded-md bg-[var(--color-praxis-salmon)]/10 p-2.5">
            <Sparkles className="size-5 text-[var(--color-praxis-salmon)]" />
          </div>
          <div className="flex-1">
            <h3 className="font-display text-sm font-semibold uppercase tracking-wider text-[var(--color-praxis-azul)] group-hover:underline">
              Perfil opositor
            </h3>
            <p className="mt-1 text-xs text-muted-foreground">
              Línea política del despacho — bandera principal, tono,
              adversarios, aliados, temas de cuidado. Se infiere desde
              proyectos + votaciones; lo editás vos.
            </p>
          </div>
          <ExternalLink className="size-3.5 text-muted-foreground" />
        </div>
      </Card>
    </Link>
  );
}

// ---------------------------------------------------------------------------
// Destinatarios
// ---------------------------------------------------------------------------

function DestinatariosSection({
  destinatarios,
}: {
  destinatarios: DestinatarioDTO[];
}) {
  return (
    <section className="space-y-3">
      <div className="flex items-center gap-2">
        <UserPlus className="size-4 text-[var(--color-praxis-azul)]" />
        <h3 className="font-display text-sm font-semibold uppercase tracking-wider text-[var(--color-praxis-azul)]">
          Destinatarios WhatsApp
        </h3>
        <span className="text-xs font-medium text-muted-foreground">
          {destinatarios.length}
        </span>
      </div>

      <DestinatarioFormulario />

      {destinatarios.length === 0 ? (
        <Card className="border-border bg-card p-6 text-center shadow-none">
          <UserPlus className="mx-auto size-8 text-[var(--color-praxis-salmon)]" />
          <p className="mt-2.5 text-sm font-medium text-foreground">
            Sin destinatarios cargados
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            Agregá uno con el formulario de arriba — al menos el tuyo, para
            recibir el briefing diario en tu WhatsApp.
          </p>
        </Card>
      ) : (
        <Card className="overflow-hidden border-border bg-card p-0 shadow-none">
          <ul className="divide-y divide-border">
            {destinatarios.map((d) => (
              <DestinatarioItem key={d.id} dest={d} />
            ))}
          </ul>
        </Card>
      )}
    </section>
  );
}

function DestinatarioItem({ dest }: { dest: DestinatarioDTO }) {
  const colorEstado = dest.activo
    ? "var(--color-praxis-verde)"
    : dest.opt_out_en
      ? "var(--color-praxis-salmon)"
      : "var(--color-praxis-azul)";
  const labelEstado = dest.activo
    ? "ACTIVO"
    : dest.opt_out_en
      ? "OPT-OUT"
      : "PENDIENTE OPT-IN";

  return (
    <li className="flex flex-wrap items-start gap-3 px-5 py-4">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2.5">
          <span className="font-medium text-foreground">{dest.nombre}</span>
          <Badge
            className="text-[10px] font-semibold"
            style={{ backgroundColor: colorEstado, color: "white" }}
          >
            {labelEstado}
          </Badge>
          <span className="text-[10.5px] uppercase tracking-wider text-muted-foreground">
            {formatRol(dest.rol_interno)}
          </span>
        </div>
        <p className="mt-0.5 font-mono text-xs text-muted-foreground">
          {dest.telefono_e164}
        </p>
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {dest.recibe_briefing_diario && (
            <Badge variant="outline" className="text-[10px]">
              Briefing diario
            </Badge>
          )}
          {dest.recibe_alertas_menciones && (
            <Badge variant="outline" className="text-[10px]">
              Alertas menciones
            </Badge>
          )}
          {dest.recibe_alertas_otras && (
            <Badge variant="outline" className="text-[10px]">
              Otras alertas
            </Badge>
          )}
        </div>
      </div>
    </li>
  );
}

// ---------------------------------------------------------------------------
// Envíos
// ---------------------------------------------------------------------------

function EnviosSection({ envios }: { envios: EnvioWhatsAppDTO[] }) {
  return (
    <section className="space-y-3">
      <div className="flex items-center gap-2">
        <Send className="size-4 text-[var(--color-praxis-salmon)]" />
        <h3 className="font-display text-sm font-semibold uppercase tracking-wider text-[var(--color-praxis-azul)]">
          Histórico de envíos (últimos 30 días)
        </h3>
        <span className="text-xs font-medium text-muted-foreground">
          {envios.length}
        </span>
      </div>

      {envios.length === 0 ? (
        <Card className="border-border bg-card p-6 text-center shadow-none">
          <MessageCircle className="mx-auto size-8 text-[var(--color-praxis-salmon)]" />
          <p className="mt-2.5 text-sm font-medium text-foreground">
            Sin envíos por ahora
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            El briefing diario corre todos los días a las 7:00 ART una
            vez que haya destinatarios activos con opt-in.
          </p>
        </Card>
      ) : (
        <Card className="overflow-hidden border-border bg-card p-0 shadow-none">
          <ul className="divide-y divide-border">
            {envios.map((e) => (
              <EnvioItem key={e.id} envio={e} />
            ))}
          </ul>
        </Card>
      )}
    </section>
  );
}

function EnvioItem({ envio }: { envio: EnvioWhatsAppDTO }) {
  return (
    <li className="flex flex-wrap items-start gap-3 px-5 py-3.5">
      <Badge
        className="text-[10px] font-semibold"
        style={{
          backgroundColor: ESTADO_COLOR[envio.estado],
          color: "white",
        }}
      >
        {ESTADO_LABEL[envio.estado].toUpperCase()}
      </Badge>
      <div className="min-w-0 flex-1">
        <p className="text-[13.5px] font-medium text-foreground">
          {TIPO_LABEL[envio.tipo]}
        </p>
        <p className="text-xs text-muted-foreground">
          Plantilla: {envio.plantilla_name} · {formatFecha(envio.enviado_en)}
        </p>
        {envio.error && (
          <p className="mt-1 text-xs text-[var(--color-praxis-salmon)]">
            Error: {envio.error}
          </p>
        )}
      </div>
      {envio.message_id_meta && (
        <span className="flex items-center gap-1 text-[10px] text-muted-foreground">
          <ExternalLink className="size-3" />
          {envio.message_id_meta.slice(0, 12)}…
        </span>
      )}
    </li>
  );
}
