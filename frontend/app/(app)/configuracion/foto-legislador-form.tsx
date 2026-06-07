"use client";

/**
 * Form para setear/borrar la URL pública de la foto del legislador
 * titular (feat-47.C).
 *
 * Tira PATCH /legislador-titular/foto con `{foto_url}`. La foto se ve
 * en el panel huella del legislador en /dashboard.
 */
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { Image as ImageIcon, Loader2, Save, Trash2 } from "lucide-react";

import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useApiContext } from "@/lib/api/context-client";
import { setFotoLegislador } from "@/lib/api/endpoints";

interface Props {
  fotoActual: string | null;
  nombreLegislador: string | null;
}

export function FotoLegisladorForm({ fotoActual, nombreLegislador }: Props) {
  const router = useRouter();
  const resolveCtx = useApiContext();
  const [isPending, startTransition] = useTransition();

  const [url, setUrl] = useState(fotoActual ?? "");
  const [mensaje, setMensaje] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function guardar(nuevaUrl: string | null) {
    setError(null);
    setMensaje(null);
    startTransition(async () => {
      try {
        const ctx = await resolveCtx();
        await setFotoLegislador(ctx, nuevaUrl);
        setMensaje(
          nuevaUrl ? "Foto actualizada." : "Foto borrada — vuelve al placeholder.",
        );
        router.refresh();
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "No se pudo actualizar la foto.",
        );
      }
    });
  }

  return (
    <Card className="space-y-3 border-border bg-card p-5 shadow-none">
      <div className="flex items-center gap-2">
        <ImageIcon className="size-4 text-[var(--color-praxis-azul)]" />
        <h3 className="font-display text-sm font-semibold uppercase tracking-wider text-[var(--color-praxis-azul)]">
          Foto del legislador titular
        </h3>
      </div>
      {nombreLegislador && (
        <p className="text-[11px] text-muted-foreground">
          Para: <strong>{nombreLegislador}</strong>
        </p>
      )}

      <div className="flex items-start gap-3">
        {fotoActual ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={fotoActual}
            alt="Foto actual"
            className="size-16 shrink-0 rounded-full border-2 border-[var(--color-praxis-azul)] object-cover"
          />
        ) : (
          <div className="flex size-16 shrink-0 items-center justify-center rounded-full border-2 border-dashed border-border bg-muted/20 text-[10.5px] uppercase tracking-wider text-muted-foreground">
            sin foto
          </div>
        )}
        <div className="flex-1 space-y-2">
          <Input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://www.hcdn.gob.ar/diputados/.../foto.jpg"
            autoComplete="off"
          />
          <p className="text-[10.5px] text-muted-foreground">
            URL pública de la foto del legislador. Si la dejás vacía, se
            muestra el placeholder con iniciales en el panel huella.
          </p>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={isPending || !url.trim()}
          onClick={() => guardar(url.trim())}
          className="inline-flex items-center gap-1.5 rounded-md bg-[var(--color-praxis-azul)] px-3 py-1.5 text-[11px] font-semibold text-white transition-opacity disabled:opacity-50"
        >
          {isPending ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <Save className="size-3.5" />
          )}
          Guardar
        </button>
        {fotoActual && (
          <button
            type="button"
            disabled={isPending}
            onClick={() => {
              setUrl("");
              guardar(null);
            }}
            className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-[11px] font-medium text-muted-foreground"
          >
            <Trash2 className="size-3.5" />
            Borrar foto
          </button>
        )}
      </div>

      {mensaje && (
        <p className="text-[11px] text-[var(--color-praxis-verde)]">{mensaje}</p>
      )}
      {error && (
        <p className="text-[11px] text-[var(--color-praxis-salmon)]">{error}</p>
      )}
    </Card>
  );
}
