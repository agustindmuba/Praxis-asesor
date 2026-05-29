/**
 * Shell visual de la app autenticada: sidebar fijo + topbar + content.
 *
 * Bootstrap mínimo. PR siguiente (feat/20) trae componentes shadcn reales,
 * Cmd+K, atajos, etc.
 */
import Link from "next/link";
import { FileText, LayoutDashboard, ListChecks } from "lucide-react";

import { UserAvatar } from "@/components/user-avatar";
import type { MeResponse } from "@/lib/api/types";

interface Props {
  me: MeResponse;
  children: React.ReactNode;
}

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/expedientes", label: "Expedientes", icon: FileText },
  { href: "/seguimientos", label: "Seguimientos", icon: ListChecks },
];

export function AppShell({ me, children }: Props) {
  return (
    <div className="flex min-h-screen bg-background">
      {/* Sidebar */}
      <aside className="flex w-56 flex-col border-r border-border bg-card">
        <div className="border-b border-border p-4">
          <h1 className="text-base font-semibold tracking-tight">Praxis Asesor</h1>
          <p className="mt-0.5 text-xs text-muted-foreground">{me.despacho.nombre}</p>
        </div>
        <nav className="flex-1 space-y-0.5 p-2">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            >
              <item.icon className="size-4" />
              {item.label}
            </Link>
          ))}
        </nav>
      </aside>

      {/* Main */}
      <div className="flex flex-1 flex-col">
        {/* Topbar */}
        <header className="flex h-14 items-center justify-between border-b border-border bg-card px-6">
          <div className="text-sm text-muted-foreground">
            {me.usuario.nombre} · <span className="capitalize">{me.rol.replace("_", " ")}</span>
          </div>
          <UserAvatar nombre={me.usuario.nombre} email={me.usuario.email} />
        </header>

        {/* Content */}
        <main className="flex-1 overflow-auto p-6">{children}</main>
      </div>
    </div>
  );
}
