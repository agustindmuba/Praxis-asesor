/**
 * Barra de filtros sobre la tabla de expedientes.
 *
 * Client Component: el form actualiza el URL via `router.push`, lo que
 * dispara un re-render del Server Component padre que vuelve a hacer la
 * búsqueda con los nuevos filtros.
 */
"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { AreaTematica, FiltrosExpediente } from "@/lib/api/types";
import { filtrosToSearchParams } from "@/lib/filtros-url";

interface Props {
  initial: FiltrosExpediente;
}

/** Sentinel para representar "sin filtro" en los <Select>. */
const NONE = "__none__";

const AREAS_LABEL: Record<AreaTematica, string> = {
  salud: "Salud",
  educacion: "Educación",
  ambiente: "Ambiente",
  trabajo: "Trabajo",
  derechos_humanos: "DDHH",
  seguridad: "Seguridad",
  transporte: "Transporte",
  infraestructura: "Infraestructura",
  justicia: "Justicia",
  relaciones_exteriores: "Relaciones Ext.",
  economia: "Economía",
  otros: "Otros",
};

export function FiltrosBar({ initial }: Props) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();

  const [texto, setTexto] = useState(initial.texto ?? "");
  const [anio, setAnio] = useState(initial.anio?.toString() ?? "");
  const [autor, setAutor] = useState(initial.autor_nombre ?? "");
  const [comision, setComision] = useState(initial.comision ?? "");
  const [tipo, setTipo] = useState<string>(initial.tipo ?? NONE);
  const [camara, setCamara] = useState<string>(initial.camara ?? NONE);
  const [estado, setEstado] = useState<string>(initial.estado ?? NONE);
  // Filtros derivados del despacho (feat-43.1).
  const [area, setArea] = useState<string>(initial.area_tematica ?? NONE);
  const [soloTitular, setSoloTitular] = useState(initial.solo_titular ?? false);
  const [soloSeguidos, setSoloSeguidos] = useState(
    initial.solo_seguidos ?? false,
  );
  const [conDictamen, setConDictamen] = useState(initial.con_dictamen ?? false);
  const [porCaducar, setPorCaducar] = useState(initial.por_caducar ?? false);

  function apply(e: React.FormEvent) {
    e.preventDefault();
    const filtros: FiltrosExpediente = {};
    if (texto.trim()) filtros.texto = texto.trim();
    if (anio.trim()) {
      const n = Number(anio);
      if (Number.isFinite(n)) filtros.anio = n;
    }
    if (autor.trim()) filtros.autor_nombre = autor.trim();
    if (comision.trim()) filtros.comision = comision.trim();
    if (tipo !== NONE) filtros.tipo = tipo as FiltrosExpediente["tipo"];
    if (camara !== NONE) filtros.camara = camara as FiltrosExpediente["camara"];
    if (estado !== NONE) filtros.estado = estado as FiltrosExpediente["estado"];
    if (area !== NONE) filtros.area_tematica = area as AreaTematica;
    if (soloTitular) filtros.solo_titular = true;
    if (soloSeguidos) filtros.solo_seguidos = true;
    if (conDictamen) filtros.con_dictamen = true;
    if (porCaducar) filtros.por_caducar = true;
    // Aplicar filtros vuelve a la primera página.
    filtros.offset = 0;

    const qs = filtrosToSearchParams(filtros).toString();
    startTransition(() => {
      router.push(qs ? `/expedientes?${qs}` : "/expedientes");
    });
  }

  function clear() {
    setTexto("");
    setAnio("");
    setAutor("");
    setComision("");
    setTipo(NONE);
    setCamara(NONE);
    setEstado(NONE);
    setArea(NONE);
    setSoloTitular(false);
    setSoloSeguidos(false);
    setConDictamen(false);
    setPorCaducar(false);
    startTransition(() => router.push("/expedientes"));
  }

  return (
    <form
      onSubmit={apply}
      className="space-y-3 rounded-lg border border-border bg-card p-4 shadow-none"
    >
      {/* Fila 1: texto + año */}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-[2fr_1fr_1fr]">
        <Input
          placeholder="Buscar texto en título o sumario..."
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
        />
        <Input
          placeholder="Año (ej. 2024)"
          value={anio}
          onChange={(e) => setAnio(e.target.value)}
          type="number"
          min={1983}
          max={2100}
        />
        <Select value={camara} onValueChange={setCamara}>
          <SelectTrigger>
            <SelectValue placeholder="Cámara" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={NONE}>Todas las cámaras</SelectItem>
            <SelectItem value="HCDN">HCDN</SelectItem>
            <SelectItem value="HSN">HSN</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Fila 2: tipo + estado + autor + comisión */}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
        <Select value={tipo} onValueChange={setTipo}>
          <SelectTrigger>
            <SelectValue placeholder="Tipo" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={NONE}>Todos los tipos</SelectItem>
            <SelectItem value="proyecto_ley">Proyecto de Ley</SelectItem>
            <SelectItem value="proyecto_resolucion">Proyecto de Resolución</SelectItem>
            <SelectItem value="proyecto_declaracion">Proyecto de Declaración</SelectItem>
            <SelectItem value="proyecto_comunicacion">Proyecto de Comunicación</SelectItem>
            <SelectItem value="mensaje_pe">Mensaje del PE</SelectItem>
            <SelectItem value="decreto">Decreto</SelectItem>
            <SelectItem value="otro">Otro</SelectItem>
          </SelectContent>
        </Select>
        <Select value={estado} onValueChange={setEstado}>
          <SelectTrigger>
            <SelectValue placeholder="Estado" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={NONE}>Todos los estados</SelectItem>
            <SelectItem value="ingresado">Ingresado</SelectItem>
            <SelectItem value="en_comision">En comisión</SelectItem>
            <SelectItem value="con_dictamen">Con dictamen</SelectItem>
            <SelectItem value="media_sancion_hcdn">Media sanción HCDN</SelectItem>
            <SelectItem value="media_sancion_hsn">Media sanción HSN</SelectItem>
            <SelectItem value="sancionado">Sancionado</SelectItem>
            <SelectItem value="caduco">Caduco</SelectItem>
            <SelectItem value="archivado">Archivado</SelectItem>
            <SelectItem value="desconocido">Desconocido</SelectItem>
          </SelectContent>
        </Select>
        <Input
          placeholder="Autor (nombre del firmante)"
          value={autor}
          onChange={(e) => setAutor(e.target.value)}
        />
        <Input
          placeholder="Comisión"
          value={comision}
          onChange={(e) => setComision(e.target.value)}
        />
      </div>

      {/* Fila 3: chips contextuales del despacho + dropdown área (feat-43.1) */}
      <div className="flex flex-wrap items-center gap-2 pt-1">
        <FiltroChip
          label="Mi legislador"
          active={soloTitular}
          onClick={() => setSoloTitular((v) => !v)}
        />
        <FiltroChip
          label="Mis seguimientos"
          active={soloSeguidos}
          onClick={() => setSoloSeguidos((v) => !v)}
        />
        <FiltroChip
          label="Con dictamen"
          active={conDictamen}
          onClick={() => setConDictamen((v) => !v)}
        />
        <FiltroChip
          label="Por caducar (60 días)"
          active={porCaducar}
          onClick={() => setPorCaducar((v) => !v)}
        />
        <div className="ml-auto min-w-[180px]">
          <Select value={area} onValueChange={setArea}>
            <SelectTrigger>
              <SelectValue placeholder="Área temática" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>Todas las áreas</SelectItem>
              {Object.entries(AREAS_LABEL).map(([key, label]) => (
                <SelectItem key={key} value={key}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Acciones */}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={clear} disabled={isPending}>
          Limpiar
        </Button>
        <Button type="submit" disabled={isPending}>
          {isPending ? "Buscando..." : "Filtrar"}
        </Button>
      </div>
    </form>
  );
}

interface FiltroChipProps {
  label: string;
  active: boolean;
  onClick: () => void;
}

/**
 * Toggle tipo "chip" usado para los filtros derivados del despacho.
 * Sin shadcn Checkbox: usamos un botón nativo con estados de color.
 */
function FiltroChip({ label, active, onClick }: FiltroChipProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={
        "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[11px] font-medium transition-colors " +
        (active
          ? "border-[var(--color-praxis-azul)] bg-[var(--color-praxis-azul)] text-white"
          : "border-border bg-card text-muted-foreground hover:border-[var(--color-praxis-azul)] hover:text-foreground")
      }
    >
      {active && <span aria-hidden>✓</span>}
      {label}
    </button>
  );
}
