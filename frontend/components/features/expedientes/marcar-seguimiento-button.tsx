/**
 * Botón con dropdown para marcar/desmarcar seguimiento + cambiar prioridad.
 *
 * Client Component que usa TanStack Query mutations contra el backend.
 * Después de un cambio:
 * 1. Invalida `["expediente", id]` para que la ficha re-fetchee.
 * 2. Invalida `["seguimientos"]` para que el dashboard se actualice.
 * 3. Muestra un toast.
 */
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Star, StarOff } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useApiContext } from "@/lib/api/context-client";
import {
  archivarSeguimiento,
  crearSeguimiento,
  actualizarSeguimiento,
} from "@/lib/api/endpoints";
import type { Prioridad, SeguimientoDTO } from "@/lib/api/types";

interface Props {
  expedienteId: string;
  /** Si null, no hay seguimiento todavía. Si viene, el botón muestra estado. */
  seguimiento: SeguimientoDTO | null;
}

export function MarcarSeguimientoButton({ expedienteId, seguimiento }: Props) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const getCtx = useApiContext();
  const [open, setOpen] = useState(false);

  const marcado = !!seguimiento && !seguimiento.archivado;

  // ---- Mutations -----------------------------------------------------------

  const crear = useMutation({
    mutationFn: async (prioridad: Prioridad) => {
      const ctx = await getCtx();
      return crearSeguimiento(ctx, { expediente_id: expedienteId, prioridad });
    },
    onSuccess: () => {
      toast.success("Expediente marcado para seguimiento");
      queryClient.invalidateQueries({ queryKey: ["seguimientos"] });
      router.refresh();
    },
    onError: () => toast.error("No se pudo marcar el expediente"),
  });

  const actualizar = useMutation({
    mutationFn: async (prioridad: Prioridad) => {
      if (!seguimiento) throw new Error("No hay seguimiento para actualizar");
      const ctx = await getCtx();
      // El endpoint PATCH no acepta prioridad todavía (TODO en backend).
      // Por ahora, archivamos + creamos con nueva prioridad → side-effect:
      // se pierde el id. Workaround aceptable hasta que el endpoint exponga
      // el cambio de prioridad.
      await archivarSeguimiento(ctx, seguimiento.id);
      return crearSeguimiento(ctx, { expediente_id: expedienteId, prioridad });
    },
    onSuccess: () => {
      toast.success("Prioridad actualizada");
      queryClient.invalidateQueries({ queryKey: ["seguimientos"] });
      router.refresh();
    },
    onError: () => toast.error("No se pudo actualizar la prioridad"),
  });

  const desmarcar = useMutation({
    mutationFn: async () => {
      if (!seguimiento) throw new Error("Nada que desmarcar");
      const ctx = await getCtx();
      return archivarSeguimiento(ctx, seguimiento.id);
    },
    onSuccess: () => {
      toast.success("Expediente desmarcado");
      queryClient.invalidateQueries({ queryKey: ["seguimientos"] });
      router.refresh();
    },
    onError: () => toast.error("No se pudo desmarcar el expediente"),
  });

  // Para uso futuro — se va a habilitar cuando exista responsable_id UI.
  void actualizarSeguimiento;

  // ---- Render --------------------------------------------------------------

  if (!marcado) {
    // No marcado: dropdown para elegir prioridad inicial.
    return (
      <DropdownMenu open={open} onOpenChange={setOpen}>
        <DropdownMenuTrigger asChild>
          <Button variant="default" size="sm" disabled={crear.isPending}>
            <Star className="mr-1.5 size-4" />
            {crear.isPending ? "Marcando..." : "Marcar"}
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuLabel>Prioridad</DropdownMenuLabel>
          <DropdownMenuItem onClick={() => crear.mutate("alta")}>Alta</DropdownMenuItem>
          <DropdownMenuItem onClick={() => crear.mutate("media")}>Media</DropdownMenuItem>
          <DropdownMenuItem onClick={() => crear.mutate("baja")}>Baja</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    );
  }

  // Marcado: muestra estado + dropdown para cambiar prioridad o desmarcar.
  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <Button
          variant="secondary"
          size="sm"
          disabled={actualizar.isPending || desmarcar.isPending}
        >
          <Star className="mr-1.5 size-4 fill-current" />
          Siguiendo (
          {seguimiento ? seguimiento.prioridad : "—"})
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel>Cambiar prioridad</DropdownMenuLabel>
        <DropdownMenuItem
          onClick={() => actualizar.mutate("alta")}
          disabled={seguimiento?.prioridad === "alta"}
        >
          Alta
        </DropdownMenuItem>
        <DropdownMenuItem
          onClick={() => actualizar.mutate("media")}
          disabled={seguimiento?.prioridad === "media"}
        >
          Media
        </DropdownMenuItem>
        <DropdownMenuItem
          onClick={() => actualizar.mutate("baja")}
          disabled={seguimiento?.prioridad === "baja"}
        >
          Baja
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onClick={() => desmarcar.mutate()}
          className="text-destructive focus:bg-destructive/10 focus:text-destructive"
        >
          <StarOff className="mr-1.5 size-4" />
          Desmarcar
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
