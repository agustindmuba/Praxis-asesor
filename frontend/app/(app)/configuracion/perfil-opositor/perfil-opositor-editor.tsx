"use client";

/**
 * Editor del perfil opositor (feat-42.1).
 *
 * Estado local con todos los campos del perfil. Botón "Inferir desde
 * huella" llama POST /perfil-opositor/inferir (el bot analiza la DB y
 * devuelve borrador). Botón "Guardar cambios" llama PATCH con los
 * deltas editados.
 */
import { Sparkles, Save, Loader2 } from "lucide-react";
import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { useApiContext } from "@/lib/api/context-client";
import {
  actualizarPerfilOpositor,
  inferirPerfilOpositor,
} from "@/lib/api/endpoints";
import type {
  ConfianzaGlobal,
  FiguraReferidaDTO,
  PerfilOpositorDTO,
  TonoComunicacional,
} from "@/lib/api/types";

const TONOS: { value: TonoComunicacional; label: string }[] = [
  { value: "tecnico-juridico", label: "Técnico-jurídico" },
  { value: "militante-bloque", label: "Militante de bloque" },
  { value: "dialogal-conciliador", label: "Dialogal-conciliador" },
  { value: "frontal-confrontativo", label: "Frontal-confrontativo" },
  { value: "ironico", label: "Irónico" },
  { value: "mixto", label: "Mixto" },
];

const COLOR_CONFIANZA: Record<ConfianzaGlobal, string> = {
  alta: "var(--color-praxis-verde)",
  media: "var(--color-praxis-azul)",
  baja: "var(--color-praxis-salmon)",
};

interface Props {
  inicial: PerfilOpositorDTO | null;
}

export function PerfilOpositorEditor({ inicial }: Props) {
  const router = useRouter();
  const resolveCtx = useApiContext();
  const [isPending, startTransition] = useTransition();

  const [perfil, setPerfil] = useState<PerfilOpositorDTO | null>(inicial);
  const [nombreLeg, setNombreLeg] = useState("JULIANO, PABLO");
  const [error, setError] = useState<string | null>(null);
  const [exitoMsg, setExitoMsg] = useState<string | null>(null);

  function inferir() {
    setError(null);
    setExitoMsg(null);
    startTransition(async () => {
      try {
        const ctx = await resolveCtx();
        const nuevo = await inferirPerfilOpositor(ctx, {
          nombre_legislador: nombreLeg.trim(),
          max_votaciones: 50,
        });
        setPerfil(nuevo);
        setExitoMsg(
          `Borrador generado por ${nuevo.modelo_inferencia ?? "LLM"} — revisalo y editá lo que necesites antes de guardar.`,
        );
        router.refresh();
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "No se pudo inferir el perfil.",
        );
      }
    });
  }

  function guardar() {
    if (!perfil) return;
    setError(null);
    setExitoMsg(null);
    startTransition(async () => {
      try {
        const ctx = await resolveCtx();
        const guardado = await actualizarPerfilOpositor(ctx, {
          bandera_principal: perfil.bandera_principal,
          banderas_secundarias: perfil.banderas_secundarias,
          temas_de_cuidado: perfil.temas_de_cuidado,
          tono_comunicacional: perfil.tono_comunicacional,
          adversarios: perfil.adversarios,
          aliados: perfil.aliados,
          linea_de_bloque: perfil.linea_de_bloque,
        });
        setPerfil(guardado);
        setExitoMsg("Perfil guardado.");
        router.refresh();
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "No se pudo guardar.",
        );
      }
    });
  }

  return (
    <div className="space-y-5">
      {/* Inferir desde huella */}
      <Card className="border-border bg-card p-5 shadow-none">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex-1 space-y-1 text-xs">
            <span className="font-medium text-foreground">
              Legislador a perfilar (substring del nombre tal como
              aparece en HCDN)
            </span>
            <input
              type="text"
              value={nombreLeg}
              onChange={(e) => setNombreLeg(e.target.value)}
              placeholder="JULIANO, PABLO"
              className="w-full rounded-md border border-input bg-background px-2.5 py-1.5 font-mono text-sm"
            />
          </label>
          <button
            type="button"
            disabled={isPending || !nombreLeg.trim()}
            onClick={inferir}
            className="inline-flex items-center gap-1.5 rounded-md bg-[var(--color-praxis-salmon)] px-4 py-2 text-xs font-semibold text-white transition-opacity disabled:opacity-50"
          >
            {isPending ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Sparkles className="size-3.5" />
            )}
            {perfil === null ? "Generar borrador" : "Re-inferir"}
          </button>
        </div>
        <p className="mt-2 text-[11px] text-muted-foreground">
          Re-inferir pisa la línea editada manualmente — guardá antes
          si tenés cambios sin commitear.
        </p>
      </Card>

      {error && (
        <Card className="border-[var(--color-praxis-salmon)]/40 bg-[var(--color-praxis-salmon)]/5 p-3 text-xs text-foreground shadow-none">
          {error}
        </Card>
      )}
      {exitoMsg && (
        <Card className="border-[var(--color-praxis-verde)]/40 bg-[var(--color-praxis-verde)]/5 p-3 text-xs text-foreground shadow-none">
          {exitoMsg}
        </Card>
      )}

      {perfil !== null && (
        <>
          {/* Confianza + advertencias del bot */}
          <Card className="border-border bg-card p-5 shadow-none">
            <div className="flex items-start justify-between gap-3">
              <div className="space-y-1">
                <p className="text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Confianza global de la inferencia
                </p>
                <Badge
                  style={{
                    backgroundColor: COLOR_CONFIANZA[perfil.confianza_global],
                    color: "white",
                  }}
                  className="text-[10.5px] font-semibold uppercase"
                >
                  {perfil.confianza_global}
                </Badge>
              </div>
              <div className="text-right text-[11px] text-muted-foreground">
                {perfil.inferido_en && (
                  <div>Inferido: {formatFecha(perfil.inferido_en)}</div>
                )}
                {perfil.editado_en && (
                  <div>Editado: {formatFecha(perfil.editado_en)}</div>
                )}
                {perfil.modelo_inferencia && (
                  <div className="font-mono">
                    {perfil.modelo_inferencia}
                  </div>
                )}
              </div>
            </div>
            {perfil.advertencias.length > 0 && (
              <div className="mt-3 space-y-1.5">
                <p className="text-[10.5px] font-semibold uppercase tracking-wider text-[var(--color-praxis-salmon)]">
                  Advertencias del bot
                </p>
                <ul className="list-disc space-y-1 pl-5 text-xs text-muted-foreground">
                  {perfil.advertencias.map((a, i) => (
                    <li key={i}>{a}</li>
                  ))}
                </ul>
              </div>
            )}
          </Card>

          {/* Bandera principal */}
          <FieldCard label="Bandera principal">
            <textarea
              value={perfil.bandera_principal}
              onChange={(e) =>
                setPerfil({ ...perfil, bandera_principal: e.target.value })
              }
              rows={2}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            />
          </FieldCard>

          {/* Tono */}
          <FieldCard label="Tono comunicacional">
            <select
              value={perfil.tono_comunicacional}
              onChange={(e) =>
                setPerfil({
                  ...perfil,
                  tono_comunicacional: e.target.value as TonoComunicacional,
                })
              }
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            >
              {TONOS.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </FieldCard>

          {/* Línea de bloque */}
          <FieldCard label="Línea de bloque">
            <textarea
              value={perfil.linea_de_bloque}
              onChange={(e) =>
                setPerfil({ ...perfil, linea_de_bloque: e.target.value })
              }
              rows={2}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            />
          </FieldCard>

          {/* Banderas secundarias (lista editable) */}
          <ListaCard
            label="Banderas secundarias"
            items={perfil.banderas_secundarias}
            placeholder="Otra bandera o causa que el despacho milita activamente"
            onChange={(items) =>
              setPerfil({ ...perfil, banderas_secundarias: items })
            }
          />

          {/* Temas de cuidado */}
          <ListaCard
            label="Temas de cuidado (no tocar)"
            items={perfil.temas_de_cuidado}
            placeholder="Tema donde el silencio es estratégico"
            onChange={(items) =>
              setPerfil({ ...perfil, temas_de_cuidado: items })
            }
          />

          {/* Adversarios */}
          <FigurasCard
            label="Adversarios"
            color="var(--color-praxis-salmon)"
            items={perfil.adversarios}
            onChange={(items) =>
              setPerfil({ ...perfil, adversarios: items })
            }
          />

          {/* Aliados */}
          <FigurasCard
            label="Aliados"
            color="var(--color-praxis-verde)"
            items={perfil.aliados}
            onChange={(items) =>
              setPerfil({ ...perfil, aliados: items })
            }
          />

          {/* Justificación (solo lectura, evidencia del bot) */}
          <Card className="border-border bg-muted/30 p-5 shadow-none">
            <p className="text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">
              Evidencia del bot (solo lectura)
            </p>
            <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">
              {perfil.justificacion_evidencia ||
                "Sin justificación registrada."}
            </p>
          </Card>

          {/* Guardar */}
          <div className="sticky bottom-4 flex justify-end">
            <button
              type="button"
              disabled={isPending}
              onClick={guardar}
              className="inline-flex items-center gap-1.5 rounded-md bg-[var(--color-praxis-azul)] px-5 py-2.5 text-xs font-semibold text-white shadow-md transition-opacity disabled:opacity-50"
            >
              {isPending ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <Save className="size-3.5" />
              )}
              Guardar cambios
            </button>
          </div>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-componentes
// ---------------------------------------------------------------------------

function FieldCard({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <Card className="border-border bg-card p-5 shadow-none">
      <p className="mb-2 text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </p>
      {children}
    </Card>
  );
}

function ListaCard({
  label,
  items,
  placeholder,
  onChange,
}: {
  label: string;
  items: string[];
  placeholder: string;
  onChange: (items: string[]) => void;
}) {
  function update(i: number, v: string) {
    const next = [...items];
    next[i] = v;
    onChange(next);
  }
  function remove(i: number) {
    onChange(items.filter((_, idx) => idx !== i));
  }
  function add() {
    onChange([...items, ""]);
  }
  return (
    <Card className="border-border bg-card p-5 shadow-none">
      <div className="mb-2 flex items-center justify-between">
        <p className="text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">
          {label}
        </p>
        <button
          type="button"
          onClick={add}
          className="text-[11px] font-medium text-[var(--color-praxis-azul)] hover:underline"
        >
          + Agregar
        </button>
      </div>
      <div className="space-y-1.5">
        {items.length === 0 && (
          <p className="text-xs italic text-muted-foreground">
            Sin items. Click en &ldquo;Agregar&rdquo; para sumar.
          </p>
        )}
        {items.map((it, i) => (
          <div key={i} className="flex items-center gap-2">
            <input
              type="text"
              value={it}
              onChange={(e) => update(i, e.target.value)}
              placeholder={placeholder}
              className="flex-1 rounded-md border border-input bg-background px-2.5 py-1.5 text-sm"
            />
            <button
              type="button"
              onClick={() => remove(i)}
              className="text-[11px] text-muted-foreground hover:text-[var(--color-praxis-salmon)]"
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </Card>
  );
}

function FigurasCard({
  label,
  items,
  color,
  onChange,
}: {
  label: string;
  items: FiguraReferidaDTO[];
  color: string;
  onChange: (items: FiguraReferidaDTO[]) => void;
}) {
  function update(i: number, f: FiguraReferidaDTO) {
    const next = [...items];
    next[i] = f;
    onChange(next);
  }
  function remove(i: number) {
    onChange(items.filter((_, idx) => idx !== i));
  }
  function add() {
    onChange([...items, { nombre: "", razon: "" }]);
  }
  return (
    <Card className="border-border bg-card p-5 shadow-none">
      <div className="mb-2 flex items-center justify-between">
        <p
          className="text-[10.5px] font-semibold uppercase tracking-wider"
          style={{ color }}
        >
          {label}
        </p>
        <button
          type="button"
          onClick={add}
          className="text-[11px] font-medium text-[var(--color-praxis-azul)] hover:underline"
        >
          + Agregar
        </button>
      </div>
      <div className="space-y-2">
        {items.length === 0 && (
          <p className="text-xs italic text-muted-foreground">Sin items.</p>
        )}
        {items.map((f, i) => (
          <div key={i} className="space-y-1.5 rounded-md border border-border p-2.5">
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={f.nombre}
                onChange={(e) =>
                  update(i, { ...f, nombre: e.target.value })
                }
                placeholder="Nombre"
                className="flex-1 rounded-md border border-input bg-background px-2.5 py-1.5 text-sm font-medium"
              />
              <button
                type="button"
                onClick={() => remove(i)}
                className="text-[11px] text-muted-foreground hover:text-[var(--color-praxis-salmon)]"
              >
                ×
              </button>
            </div>
            <textarea
              value={f.razon}
              onChange={(e) => update(i, { ...f, razon: e.target.value })}
              placeholder="Razón / evidencia"
              rows={2}
              className="w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-xs"
            />
          </div>
        ))}
      </div>
    </Card>
  );
}

function formatFecha(iso: string): string {
  return new Date(iso).toLocaleString("es-AR", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}
