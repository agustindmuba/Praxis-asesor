/**
 * Shell visual de la app autenticada: sidebar de marca + topbar + content.
 *
 * Aplica el sistema visual Praxis (feat/33):
 * - Sidebar en azul corporativo #2A3D75, tipografía Space Grotesk.
 * - Topbar discreto sobre fondo crema.
 * - Geometría blanda (radius 0.625rem), sin sombras pesadas.
 */
import Image from "next/image";
import Link from "next/link";
import {
  BookOpen,
  FileText,
  LayoutDashboard,
  ListChecks,
  MessageSquare,
  Newspaper,
  Radio,
  Settings,
  Wand2,
} from "lucide-react";

import { UserAvatar } from "@/components/user-avatar";
import type { MeResponse } from "@/lib/api/types";

interface Props {
  me: MeResponse;
  children: React.ReactNode;
}

interface NavItem {
  href: string;
  label: string;
  icon: typeof LayoutDashboard;
  comingSoon?: boolean;
}

const NAV: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/expedientes", label: "Expedientes", icon: FileText },
  { href: "/proyectos", label: "Redactor de proyectos", icon: Wand2 },
  { href: "/briefings", label: "Briefings", icon: Newspaper },
  { href: "/bo", label: "Boletín Oficial", icon: BookOpen },
  { href: "/noticias", label: "Noticias", icon: Radio },
  { href: "/menciones", label: "Menciones", icon: MessageSquare },
  { href: "/configuracion", label: "Configuración", icon: Settings },
  {
    href: "/seguimientos",
    label: "Seguimientos",
    icon: ListChecks,
    comingSoon: true,
  },
];

export function AppShell({ me, children }: Props) {
  return (
    <div className="flex min-h-screen bg-background">
      {/* Sidebar — fondo azul corporativo Praxis */}
      <aside
        className="flex w-60 flex-col text-white"
        style={{ backgroundColor: "var(--color-praxis-azul)" }}
      >
        {/* Header con logo sobre fondo blanco (embebido en el sidebar azul). */}
        <div className="flex items-center justify-center bg-white px-4 py-6">
          <Image
            src="/logo-praxis-asesor.png"
            alt="Praxis Asesor"
            width={800}
            height={208}
            priority
            className="h-16 w-auto"
          />
        </div>
        <div className="border-b border-white/10 px-5 py-4">
          <p className="text-[11px] uppercase tracking-[0.14em] text-white/55">
            Asesor parlamentario
          </p>
          <div className="mt-3 border-t border-white/10 pt-3">
            <p className="text-xs font-medium text-white/85">
              {me.despacho.nombre}
            </p>
            <p className="mt-0.5 text-[10.5px] uppercase tracking-wide text-white/45">
              {me.rol.replace("_", " ")}
            </p>
          </div>
        </div>

        <nav className="flex-1 space-y-0.5 p-3">
          {NAV.map((item) =>
            item.comingSoon ? (
              <div
                key={item.href}
                className="flex cursor-not-allowed items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-white/40"
                title="Próximamente"
              >
                <item.icon className="size-4 text-white/30" />
                <span className="flex-1">{item.label}</span>
                <span className="rounded-sm bg-white/10 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-white/55">
                  Soon
                </span>
              </div>
            ) : (
              <Link
                key={item.href}
                href={item.href}
                className="group flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-white/75 transition-colors hover:bg-white/10 hover:text-white"
              >
                <item.icon className="size-4 text-white/55 group-hover:text-[var(--color-praxis-salmon)]" />
                {item.label}
              </Link>
            ),
          )}
        </nav>

        <div className="px-5 py-4 text-[10.5px] uppercase tracking-[0.14em] text-white/35">
          Decisiones estratégicas
          <br />
          basadas en datos
        </div>
      </aside>

      {/* Main */}
      <div className="flex flex-1 flex-col">
        {/* Topbar — discreto sobre crema */}
        <header className="flex h-14 items-center justify-between border-b border-border bg-card/80 px-6 backdrop-blur">
          <div className="text-sm text-muted-foreground">
            <span className="text-foreground">{me.usuario.nombre}</span> ·{" "}
            <span className="capitalize">{me.rol.replace("_", " ")}</span>
          </div>
          <UserAvatar nombre={me.usuario.nombre} email={me.usuario.email} />
        </header>

        {/* Content */}
        <main className="flex-1 overflow-auto p-8">{children}</main>
      </div>
    </div>
  );
}
