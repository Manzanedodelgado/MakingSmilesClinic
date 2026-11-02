"use client";
/** Selector de nivel de acceso por área: Sin acceso · Ver · Editar. `max` limita hasta dónde se
 * puede subir (techo del rol): lo que lo supera se ve atenuado y no se puede pulsar. */
export type Nivel = "none" | "ver" | "editar";
const ORDEN: Record<Nivel, number> = { none: 0, ver: 1, editar: 2 };

export function NivelPicker({ nivel, onChange, soloVer, max = "editar" }: {
  nivel: Nivel; onChange: (n: Nivel) => void; soloVer?: boolean; max?: Nivel;
}) {
  const opts: { id: Nivel; label: string; cls: string }[] = [
    { id: "none", label: "Sin acceso", cls: "bg-[#FFFFFF] text-[#64748b]" },
    { id: "ver", label: "Ver", cls: "bg-[#1ca0d1] text-white" },
    ...(soloVer ? [] : [{ id: "editar" as Nivel, label: "Editar", cls: "bg-[#1500A0] text-white" }]),
  ];
  return (
    <div className="inline-flex rounded-sm border border-[#e5e7eb] overflow-hidden">
      {opts.map((o) => {
        const bloqueado = ORDEN[o.id] > ORDEN[max];
        return (
          <button key={o.id} type="button" disabled={bloqueado} onClick={() => onChange(o.id)}
            title={bloqueado ? "Su rol no incluye este nivel" : undefined}
            className={`px-3 py-1 text-[11.5px] font-semibold transition-colors border-l first:border-l-0 border-[#e5e7eb] ${
              bloqueado ? "bg-white text-[#cbd5e1] cursor-not-allowed line-through"
                : nivel === o.id ? o.cls : "bg-white text-[#94a3b8] hover:text-[#1500A0]"}`}>{o.label}</button>
        );
      })}
    </div>
  );
}

/** Nivel actual de un área según los códigos marcados (editar implica ver). */
export function nivelDeArea(a: { ver?: string; editar?: string }, permisos: string[]): Nivel {
  return (a.editar && permisos.includes(a.editar)) ? "editar" : (a.ver && permisos.includes(a.ver)) ? "ver" : "none";
}

export type TabDef = { codigo: string; nombre: string; subs?: { codigo: string; nombre: string }[] };
type AreaConTabs = { ver?: string; editar?: string; tabs?: TabDef[] };

/** Todos los códigos de pestaña y sección de un área. */
export const codigosTabs = (tabs?: TabDef[]): string[] => (tabs ?? []).flatMap((t) => [t.codigo, ...(t.subs ?? []).map((x) => x.codigo)]);

/** Reescribe solo los códigos de ESA área dejando el resto intactos. Al pasar de «Sin acceso» a
 * Ver/Editar se activan sus pestañas y secciones (las que permita `techo`, si lo hay); al quitar
 * el acceso se quitan también. */
export function conNivel(a: AreaConTabs, permisos: string[], nivel: Nivel, techo?: string[] | null): string[] {
  const todos = codigosTabs(a.tabs);
  const tenia = nivelDeArea(a, permisos) !== "none";
  let cur = permisos.filter((c) => c !== a.ver && c !== a.editar && (nivel !== "none" || !todos.includes(c)));
  if (nivel === "ver" && a.ver) cur = [...cur, a.ver];
  if (nivel === "editar") cur = [...cur, ...(a.ver ? [a.ver] : []), ...(a.editar ? [a.editar] : [])];
  if (nivel !== "none" && !tenia) cur = [...new Set([...cur, ...todos.filter((c) => !techo || techo.includes(c))])];
  return cur;
}

/** Activa/desactiva una PESTAÑA entera con todas sus secciones (las que permita `techo`). */
export function conPestana(t: TabDef, permisos: string[], on: boolean, techo?: string[] | null): string[] {
  const cods = [t.codigo, ...(t.subs ?? []).map((x) => x.codigo)];
  const sin = permisos.filter((c) => !cods.includes(c));
  return on ? [...new Set([...sin, ...cods.filter((c) => !techo || techo.includes(c))])] : sin;
}

/** Activa/desactiva UNA sección; la pestaña se enciende con la primera y se apaga con la última. */
export function conSeccion(t: TabDef, codigo: string, permisos: string[], on: boolean): string[] {
  let cur = on ? [...new Set([...permisos, codigo, t.codigo])] : permisos.filter((c) => c !== codigo);
  if (!on && !(t.subs ?? []).some((x) => cur.includes(x.codigo))) cur = cur.filter((c) => c !== t.codigo);
  return cur;
}
