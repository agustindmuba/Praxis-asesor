/**
 * Avatar de usuario en la topbar. Doble vida:
 * - Modo Clerk: muestra el `<UserButton>` con menú de Clerk.
 * - Modo dev: muestra dropdown propio con "Salir" que llama devLogoutAction.
 *
 * Detección por `NEXT_PUBLIC_DEV_MODE` (idéntico al check del root layout).
 */
"use client";

import { LogOut, User as UserIcon } from "lucide-react";

import { devLogoutAction } from "@/app/actions/despacho";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const isDevMode = process.env.NEXT_PUBLIC_DEV_MODE === "true";

interface Props {
  nombre: string;
  email: string;
}

export function UserAvatar({ nombre, email }: Props) {
  if (isDevMode) {
    return <DevAvatar nombre={nombre} email={email} />;
  }
  // Carga dinámica de UserButton solo si NO estamos en dev mode.
  // (Evita que se importe @clerk/nextjs y se monten sus efectos.)
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { UserButton } = require("@clerk/nextjs") as typeof import("@clerk/nextjs");
  return <UserButton afterSignOutUrl="/sign-in" />;
}

function DevAvatar({ nombre, email }: { nombre: string; email: string }) {
  const inicial = nombre.slice(0, 1).toUpperCase();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="flex size-8 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
        {inicial || <UserIcon className="size-4" />}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel>
          <div className="text-sm font-medium">{nombre}</div>
          <div className="text-xs text-muted-foreground">{email}</div>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <form action={devLogoutAction}>
          <DropdownMenuItem asChild>
            <button type="submit" className="w-full cursor-pointer text-left">
              <LogOut className="mr-1.5 size-4" />
              Salir (modo dev)
            </button>
          </DropdownMenuItem>
        </form>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
