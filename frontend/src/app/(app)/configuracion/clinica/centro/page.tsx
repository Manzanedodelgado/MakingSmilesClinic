"use client";
/**
 * Config · Clínica · Centro.
 *
 * Aspecto: el del Centro del 28/09 (capturas en Uploads) — tarjetas con borde izquierdo
 * e icono circular de color por familia de datos, guardar como círculo teal con borde
 * marino, campos compactos en fila, horario y festivos juntos. Colores muestreados de
 * esa captura. Las listas (gabinetes) siguen Config Agenda:
 * cabecera en texto gris sin relleno, filas finas, casilla #81C3E0, "+" circular.
 *
 * Color = familia de datos: azul centro · rojo fiscal · dorado terceros (gestoría) ·
 * marino operación (horario, festivos, gabinetes). Estados de cita viven en Config
 * Agenda, integraciones en Conectores y el motor IA en Agentes IA.
 *
 * Formatos de datos: son los que ya consumen la Agenda de citas y el backend —
 * centro.horario = { dias: [{abierto, t1a, t1b, t2a, t2b}] × 7 (0 = lunes) },
 * centro.festivos = ["YYYY-MM-DD"], gestoria.asesoria = { email, contacto, telefono, nif, frecuencia }.
 * Al guardar se conservan las demás claves que ya hubiera en cada objeto.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import GridLayout, { getCompactor, useContainerWidth } from "react-grid-layout";
import "react-grid-layout/css/styles.css";
import { GripVertical, Minus, Armchair, Briefcase, Building2, CircleX, Clock, Image as ImageIcon, Landmark, LayoutDashboard, Plus, Save, X } from "lucide-react";
import { api, API_BASE } from "@/shared/lib/api";
import { GeoCascada, Modal, ModalBody, ModalButton } from "@/shared/components";
import { errMsg } from "@/shared/lib/errores";
import { RolesPermisos } from "./RolesPermisos";

type Centro = {
  id: number; nombre: string; codigo?: string | null; direccion?: string | null; cp?: string | null;
  poblacion?: string | null; provincia?: string | null; telefono?: string | null; telefono_movil?: string | null;
  email?: string | null; web?: string | null; instagram?: string | null; logo_url?: string | null;
  icono_url?: string | null; num_gabinetes?: number | null; razon_social_compartida_id?: number | null;
};
type RazonSocial = {
  id: number; centro_id: number; nombre: string; cif?: string | null; licencia_sanitaria?: string | null;
  direccion?: string | null; cp?: string | null; poblacion?: string | null; provincia?: string | null;
  serie?: string | null; iban?: string | null; sello_url?: string | null;
};
type Dia = { abierto: boolean; t1a: string; t1b: string; t2a: string; t2b: string };
type Gabinete = { id: number; nombre: string; activo: boolean };
type Gestoria = Record<string, unknown> & { email?: string; contacto?: string; nombre?: string; telefono?: string; nif?: string; frecuencia?: string };
type CentroResp = {
  centro: Centro; razon_social: RazonSocial | null;
  config: { "centro.horario": ({ dias?: Dia[] } & Record<string, unknown>) | null; "centro.festivos": string[] | null; "gestoria.asesoria": Gestoria | null };
  gabinetes: Gabinete[];
};

// Distribución editable de cada caja: cada pieza (campo, imagen, tabla…) tiene posición y tamaño editables en
// una cuadrícula (columna, fila, ancho y alto). Se guarda por centro en
// la config genérica: PUT /config { clave: "ui.centro.layout" }.
type Pos = { id: string; span: number; col: number; row: number; rows: number };
type CajaId = "centro" | "fiscal" | "horario" | "gestoria" | "gabinetes";
type Layout = Record<CajaId, Pos[]>;
const COLS: Record<CajaId, number> = { centro: 8, fiscal: 8, horario: 12, gestoria: 4, gabinetes: 6 };
const MAX_TILE_ROWS = 6;
const ETIQUETAS: Record<CajaId, Record<string, string>> = {
  centro: { nombre: "Nombre", codigo: "Código", telefono: "Tel. fijo", movil: "Tel. móvil", email: "Email", web: "Web", instagram: "Instagram",
    direccion: "Dirección", pais: "País", provincia: "Provincia", ciudad: "Ciudad", cp: "CP", icono: "Icono", logo: "Logo (documentos)" },
  fiscal: { razon: "Razón social", cif: "CIF", iban: "IBAN", licencia: "Licencia sanitaria", serie: "Serie", direccion: "Dirección fiscal",
    pais: "País", provincia: "Provincia", ciudad: "Ciudad", cp: "CP", sello: "Sello (razón social)" },
  horario: { tabla: "Horario semanal", festivos: "Días festivos / cerrados" },
  gestoria: { email: "Email", contacto: "Contacto", telefono: "Teléfono", nif: "NIF", frecuencia: "Frecuencia" },
  gabinetes: { lista: "Gabinetes", nuevo: "Añadir gabinete" },
};
// [id, ancho, columna, fila, alto]
const DEF: Record<CajaId, [string, number, number, number, number][]> = {
  centro: [["nombre", 3, 1, 1, 1], ["codigo", 1, 4, 1, 1], ["telefono", 1, 5, 1, 1], ["movil", 1, 6, 1, 1],
    ["email", 2, 1, 2, 1], ["web", 2, 3, 2, 1], ["instagram", 2, 5, 2, 1],
    ["direccion", 2, 1, 3, 1], ["pais", 1, 3, 3, 1], ["provincia", 1, 4, 3, 1], ["ciudad", 1, 5, 3, 1], ["cp", 1, 6, 3, 1],
    ["icono", 1, 7, 1, 3], ["logo", 1, 8, 1, 3]],
  fiscal: [["razon", 4, 1, 1, 1], ["cif", 2, 5, 1, 1], ["iban", 3, 1, 2, 1], ["licencia", 2, 4, 2, 1], ["serie", 1, 6, 2, 1],
    ["direccion", 2, 1, 3, 1], ["pais", 1, 3, 3, 1], ["provincia", 1, 4, 3, 1], ["ciudad", 1, 5, 3, 1], ["cp", 1, 6, 3, 1],
    ["sello", 2, 7, 1, 3]],
  horario: [["tabla", 9, 1, 1, 1], ["festivos", 3, 10, 1, 1]],
  gestoria: [["email", 2, 1, 1, 1], ["contacto", 2, 3, 1, 1], ["telefono", 1, 1, 2, 1], ["nif", 1, 2, 2, 1], ["frecuencia", 2, 3, 2, 1]],
  gabinetes: [["lista", 6, 1, 1, 1], ["nuevo", 3, 1, 2, 1]],
};
const choca = (lista: Pos[], id: string, col: number, row: number, span: number, rows: number) =>
  lista.some((p) => p.id !== id && col < p.col + p.span && p.col < col + span && row < p.row + p.rows && p.row < row + rows);
/** Primer hueco libre (de arriba abajo, de izquierda a derecha) donde cabe una pieza de ese tamaño. */
function hueco(lista: Pos[], span: number, rows: number, cols: number): { col: number; row: number } {
  for (let row = 1; ; row++)
    for (let col = 1; col + span - 1 <= cols; col++)
      if (!choca(lista, "", col, row, span, rows)) return { col, row };
}
const LAYOUT_DEF = Object.fromEntries((Object.keys(DEF) as CajaId[]).map((c) =>
  [c, DEF[c].map(([id, span, col, row, rows]) => ({ id, span, col, row, rows }))])) as Layout;
/** Ajusta una distribución guardada a las piezas actuales: descarta ids desconocidos o solapados,
 *  acota anchos/posiciones y coloca en el primer hueco libre las piezas que falten. */
function normaliza(l: unknown): Layout {
  const src = (l && typeof l === "object" ? l : {}) as Partial<Record<CajaId, Partial<Pos>[]>>;
  const out = {} as Layout;
  (Object.keys(LAYOUT_DEF) as CajaId[]).forEach((c) => {
    const cols = COLS[c];
    const def = new Map(LAYOUT_DEF[c].map((p) => [p.id, p]));
    const lista: Pos[] = [];
    const pendientes: Pos[] = [];
    const visto = (id: string) => lista.some((x) => x.id === id) || pendientes.some((x) => x.id === id);
    (Array.isArray(src[c]) ? src[c]! : []).forEach((p) => {
      if (!p?.id || !def.has(p.id) || visto(p.id)) return;
      const rows = Math.max(1, Math.min(MAX_TILE_ROWS, Math.round(Number(p.rows) || def.get(p.id)!.rows)));
      const span = Math.max(1, Math.min(cols, Math.round(Number(p.span) || 1)));
      const col = Math.round(Number(p.col)), row = Math.round(Number(p.row));
      const pos = { id: p.id, span, rows, col: Math.max(1, Math.min(cols - span + 1, col || 1)), row: Math.max(1, row || 1) };
      if (col >= 1 && row >= 1 && !choca(lista, pos.id, pos.col, pos.row, span, rows)) lista.push(pos); else pendientes.push(pos);
    });
    LAYOUT_DEF[c].forEach((p) => {
      if (visto(p.id)) return;
      if (!choca(lista, p.id, p.col, p.row, p.span, p.rows)) lista.push({ ...p }); else pendientes.push({ ...p });
    });
    pendientes.forEach((p) => lista.push({ ...p, ...hueco(lista, p.span, p.rows, cols) }));
    out[c] = lista;
  });
  return out;
}
// Las propias cajas viven en un "muro": rejilla muy fina (COLS_MURO columnas, filas de FILA_MURO px, pasos
// de ~4 px) donde cada caja se arrastra a donde se quiera y se estira por cualquier borde, sin saltos visibles.
// Sin compactación y con superposición: la caja se queda exactamente donde se suelta, aunque pise otra (nada
// empuja a nada). El orden del array es el orden de apilado: la última caja que se coge queda encima. La separación entre cajas NO es el margen de la librería (con tantas columnas
// dejaría columnas de ancho negativo) sino un relleno de cada caja: margen/2 por lado = margen entre dos cajas.
// Se guarda en la misma clave, bajo `cajas` + `colsMuro`. Sin muro guardado, cada caja toma el alto de su contenido.
type CajaMuro = { i: CajaId; x: number; y: number; w: number; h: number };
const COLS_MURO = 384, FILA_MURO = 4, MIN_W = 16, MIN_H = 12, MAX_H = 1000, ANCHO_MURO_MIN = 1024;
// Separación entre cajas (px), elegible en "Editar distribución"; se guarda en la misma clave, bajo `margen`.
const MARGENES = [0, 4, 8, 12, 16, 24, 32];
const MARGEN_DEF = 12;
const normalizaMargen = (v: unknown) => (typeof v === "number" && MARGENES.includes(v) ? v : MARGEN_DEF);
const PAD_CAJA = 32; // p-4 arriba + abajo
const MURO_DEF: CajaMuro[] = [
  // El muro ocupa también el margen de la página; por defecto las cajas lo dejan libre, pero se pueden meter en él.
  { i: "centro", x: 4, y: 0, w: 188, h: 77 }, { i: "fiscal", x: 192, y: 0, w: 188, h: 77 },
  { i: "horario", x: 4, y: 77, w: 220, h: 99 }, { i: "gestoria", x: 224, y: 77, w: 156, h: 50 }, { i: "gabinetes", x: 224, y: 127, w: 156, h: 50 },
];
/** Filas de muro que necesita una caja cuyo contenido mide `px` (el relleno de separación también ocupa). */
const filasMuro = (px: number, margen: number) => Math.max(MIN_H, Math.min(MAX_H, Math.ceil((px + margen) / FILA_MURO)));
const COMPACTOR = getCompactor(null, true);
/** Colocación por defecto: sube cada caja (de arriba abajo) hasta el primer sitio libre sin montarse. */
function apilar(l: CajaMuro[]): CajaMuro[] {
  const hecho: CajaMuro[] = [];
  [...l].sort((a, b) => a.y - b.y || a.x - b.x).forEach((c) => {
    const choca = (y: number) => hecho.some((o) => c.x < o.x + o.w && o.x < c.x + c.w && y < o.y + o.h && o.y < y + c.h);
    let y = 0;
    while (choca(y)) y++;
    hecho.push({ ...c, y });
  });
  return hecho;
}
/** Valida un muro guardado: descarta ids desconocidos o repetidos y valores no enteros, acota a la
 *  rejilla y añade al final las cajas que falten. null = no hay muro guardado utilizable.
 *  Muros de versiones anteriores (12 o 96 columnas, filas de 10 px + margen) se escalan a la rejilla fina. */
function normalizaMuro(v: unknown, cols: unknown, margen: number): CajaMuro[] | null {
  if (!Array.isArray(v)) return null;
  const actual = cols === COLS_MURO;
  const kx = actual ? 1 : COLS_MURO / (cols === 96 ? 96 : 12);
  const ky = actual ? 1 : (10 + margen) / FILA_MURO;
  const entero = (n: unknown): n is number => typeof n === "number" && Number.isInteger(n);
  const out: CajaMuro[] = [];
  v.forEach((it) => {
    const c = (it ?? {}) as Partial<CajaMuro>;
    if (!MURO_DEF.some((d) => d.i === c.i) || out.some((o) => o.i === c.i) || ![c.x, c.y, c.w, c.h].every(entero)) return;
    const w = Math.max(MIN_W, Math.min(COLS_MURO, Math.round(c.w! * kx)));
    out.push({ i: c.i!, w, x: Math.max(0, Math.min(COLS_MURO - w, Math.round(c.x! * kx))),
      y: Math.max(0, Math.round(c.y! * ky)), h: Math.max(MIN_H, Math.min(MAX_H, Math.ceil(c.h! * ky))) });
  });
  if (!out.length) return null;
  MURO_DEF.forEach((d) => { if (!out.some((o) => o.i === d.i)) out.push({ ...d, y: Math.max(...out.map((o) => o.y + o.h)) }); });
  return out;
}

// Los 4 selectores de GeoCascada no se pueden envolver uno a uno: su posición llega por variables CSS.
const GEO_W = {
  wPais: "min-w-0 [grid-column:var(--pais-c)/span_var(--pais-s)] [grid-row:var(--pais-r)]",
  wProvincia: "min-w-0 [grid-column:var(--provincia-c)/span_var(--provincia-s)] [grid-row:var(--provincia-r)]",
  wCiudad: "min-w-0 [grid-column:var(--ciudad-c)/span_var(--ciudad-s)] [grid-row:var(--ciudad-r)]",
  wCp: "min-w-0 [grid-column:var(--cp-c)/span_var(--cp-s)] [grid-row:var(--cp-r)]",
};

const C = { azul: "#2D88C0", rojo: "#C026D3", dorado: "#8B5CF6", marino: "#0d2b5c" };
const DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"];
const DIA_ABIERTO: Dia = { abierto: true, t1a: "10:00", t1b: "14:00", t2a: "16:00", t2b: "20:00" };
const DIA_CERRADO: Dia = { abierto: false, t1a: "", t1b: "", t2a: "", t2b: "" };
const HORAS = Array.from({ length: (22 - 7) * 4 + 1 }, (_, i) => {
  const m = 7 * 60 + i * 15;
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
});

const LB = "block text-[11px] font-medium text-[#475569] mb-0.5";
const IN = "w-full border border-[#e5e7eb] rounded-md outline-none bg-white text-[#1e293b] text-[12px] px-2 py-1 hover:border-[#94a3b8] focus:border-[#2D88C0] focus:ring-1 focus:ring-[#2D88C0]/20 disabled:bg-[#FFFFFF] disabled:text-[#94a3b8]";
const UP = `${IN} uppercase placeholder:normal-case`;
const TH = "text-[11px] font-medium text-[#475569]";
// GeoCascada trae etiquetas cian en versalitas (config-styles); aquí se igualan al resto de etiquetas de la página.
const GEO = "contents [&_label]:!text-[11px] [&_label]:!font-medium [&_label]:!text-[#475569] [&_label]:!normal-case [&_label]:!tracking-normal";

const img = (u?: string | null) => (u ? `${API_BASE}${u}` : "");
function fechaCorta(iso: string) {
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  const txt = d.toLocaleDateString("es-ES", { day: "numeric", month: "short" }).replace(".", "");
  return d.getFullYear() === new Date().getFullYear() ? txt : `${txt} ${d.getFullYear()}`;
}

/** `medir` recibe el contenido sin estirar (para calcular el alto natural de la caja); `mover` marca la
 *  caja como arrastrable (se coge por cualquier zona que no sea un campo o una pieza). */
function Card({ color, icon: Icon, title, onSave, saving, mover, medir, children }: {
  color: string; icon: React.ElementType; title: string; onSave?: () => void; saving?: boolean;
  mover?: boolean; medir?: (el: HTMLDivElement | null) => void; children: React.ReactNode;
}) {
  return (
    <section className={`h-full overflow-auto bg-white rounded-lg shadow-sm border-l-[3px] p-4 min-w-0 ${mover ? "ring-1 ring-[#2D88C0]/40 cursor-move" : ""}`} style={{ borderLeftColor: color }}>
      <div ref={medir}>
      <header className={`flex items-center justify-between mb-3 ${mover ? "select-none -mx-2 -mt-2 px-2 pt-2 pb-1 rounded-md bg-[#2D88C0]/[0.07]" : ""}`}
        title={mover ? "Arrastra para mover la caja" : undefined}>
        <div className="flex items-center gap-2.5">
          {mover && <GripVertical className="w-4 h-4 text-[#94a3b8] shrink-0" />}
          <span className="w-7 h-7 rounded-full flex items-center justify-center text-white shrink-0" style={{ background: color }}>
            <Icon className="w-3.5 h-3.5" />
          </span>
          <h2 className="text-[14px] font-semibold text-[#1e293b]">{title}</h2>
        </div>
        {onSave && (
          <button type="button" onClick={onSave} disabled={saving} title="Guardar" aria-label={`Guardar ${title}`}
            className="w-7 h-7 rounded-full bg-[#2DD9C3] border-2 border-[#0d2b5c] text-[#0d2b5c] flex items-center justify-center hover:opacity-90 active:scale-95 transition disabled:opacity-50">
            <Save className="w-3.5 h-3.5" />
          </button>
        )}
      </header>
      {children}
      </div>
    </section>
  );
}

/** El muro de cajas. Componente aparte (como FichaGrid en la ficha) para que `useContainerWidth`
 *  se monte cuando el contenedor ya existe. Por debajo de ANCHO_MURO_MIN las cajas se apilan a todo
 *  el ancho en el orden del muro: el muro no cabe en una pantalla estrecha. */
function Muro({ layout, margen, editando, onChange, cajas }: {
  layout: CajaMuro[]; margen: number; editando: boolean; onChange: (l: CajaMuro[]) => void; cajas: Record<CajaId, React.ReactNode>;
}) {
  const { width, containerRef, mounted } = useContainerWidth();
  const orden = [...layout].sort((a, b) => a.y - b.y || a.x - b.x);
  return (
    <div ref={containerRef}>
      {mounted && width >= ANCHO_MURO_MIN ? (
        <GridLayout width={width} layout={layout.map((c) => ({ ...c, minW: MIN_W, minH: MIN_H, maxH: MAX_H }))}
          gridConfig={{ cols: COLS_MURO, rowHeight: FILA_MURO, margin: [0, 0], containerPadding: [0, 0] }}
          compactor={COMPACTOR}
          dragConfig={{ enabled: editando, cancel: "[data-tile],[data-redim],button,input,select,textarea,a,label" }}
          resizeConfig={{ enabled: editando, handles: ["n", "s", "e", "w", "ne", "nw", "se", "sw"] }}
          onDragStart={(_l, _antes, item) => { if (item) onChange([...layout.filter((c) => c.i !== item.i), layout.find((c) => c.i === item.i)!]); }}
          onLayoutChange={(l) => {
            if (!editando) return;
            // Respeta el orden de apilado propio (el de `layout`), no el que devuelva la librería.
            const pos = new Map(l.map((it) => [it.i, it]));
            onChange(layout.map((c) => { const it = pos.get(c.i); return it ? { i: c.i, x: it.x, y: it.y, w: it.w, h: it.h } : c; }));
          }}>
          {layout.map((c) => <div key={c.i}><div className="h-full" style={{ padding: margen / 2 }}>{cajas[c.i]}</div></div>)}
        </GridLayout>
      ) : (
        <div className="flex flex-col px-5" style={{ gap: margen }}>{orden.map((c) => <div key={c.i}>{cajas[c.i]}</div>)}</div>
      )}
    </div>
  );
}

function Campo({ label, className = "", style, children }: { label: string; className?: string; style?: React.CSSProperties; children: React.ReactNode }) {
  return <div className={`min-w-0 ${className}`} style={style}><label className={LB}>{label}</label>{children}</div>;
}

function Check({ on, onClick, label }: { on: boolean; onClick?: () => void; label: string }) {
  return (
    <span role="checkbox" aria-checked={on} aria-label={label} tabIndex={onClick ? 0 : -1} onClick={onClick}
      onKeyDown={(e) => { if (onClick && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); onClick(); } }}
      className={`inline-flex w-[18px] h-[18px] rounded items-center justify-center outline-none focus-visible:ring-2 focus-visible:ring-[#2D88C0] ${onClick ? "cursor-pointer" : ""}`}
      style={{ background: on ? "#81C3E0" : "#FFFFFF" }}>
      {on && <svg width="11" height="9" viewBox="0 0 11 9"><path d="M1 4.5L4 7.5L10 1" stroke="white" strokeWidth="1.6" fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>}
    </span>
  );
}

function AddBtn({ onClick, label }: { onClick: () => void; label: string }) {
  return (
    <button type="button" onClick={onClick} title={label} aria-label={label}
      className="w-8 h-8 rounded-full bg-[#1500A0] text-white flex items-center justify-center shrink-0 hover:opacity-90 active:scale-95 transition">
      <span className="w-5 h-5 rounded-full border border-white/70 flex items-center justify-center"><Plus className="w-3 h-3" /></span>
    </button>
  );
}

function Quitar({ onClick, label }: { onClick: () => void; label: string }) {
  return (
    <button type="button" onClick={onClick} title={label} aria-label={label} className="text-[#94a3b8] hover:text-[#C026D3] transition-colors">
      <CircleX className="w-3.5 h-3.5" />
    </button>
  );
}

function Hora({ value, onChange, label }: { value: string; onChange: (v: string) => void; label: string }) {
  const opts = value && !HORAS.includes(value) ? [value, ...HORAS] : HORAS;
  return (
    <select aria-label={label} value={value} onChange={(e) => onChange(e.target.value)}
      className="w-[86px] border border-[#e5e7eb] rounded-md bg-white text-[12px] text-[#1e293b] px-1.5 py-1 outline-none focus:border-[#2D88C0] cursor-pointer">
      <option value="">Cerrado</option>
      {opts.map((h) => <option key={h} value={h}>{h}</option>)}
    </select>
  );
}

function Imagen({ label, url, onPick, onClear, className = "", style }: {
  label: string; url: string; onPick: (f: File) => void; onClear: () => void; className?: string; style?: React.CSSProperties;
}) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <div className={`flex flex-col min-w-0 ${className}`} style={style}>
      <label className={LB}>{label}</label>
      <div className="flex-1 min-h-[96px] flex flex-col gap-1.5 border border-[#e5e7eb] rounded-md bg-white p-1.5">
        <span className="relative flex-1 min-h-[48px] rounded bg-[#FFFFFF]/50 flex items-center justify-center overflow-hidden">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          {url ? <img src={url} alt={label} className="absolute inset-0 m-auto max-h-full max-w-full object-contain p-1" /> : <ImageIcon className="w-5 h-5 text-[#94a3b8]" />}
        </span>
        <input ref={ref} type="file" accept="image/*" className="hidden"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) onPick(f); e.target.value = ""; }} />
        <span className="flex items-center justify-center flex-wrap gap-x-2 gap-y-1">
          <button type="button" onClick={() => ref.current?.click()}
            className="px-2 py-0.5 rounded bg-[#2D88C0] text-white text-[11px] font-semibold hover:opacity-90 whitespace-nowrap">
            {url ? "Cambiar" : "Seleccionar"}
          </button>
          {url && <button type="button" onClick={onClear} className="text-[11px] text-[#94a3b8] hover:text-[#C026D3]">Quitar</button>}
        </span>
      </div>
    </div>
  );
}

const GAP = 12, FILA = 46;
function EditorRejilla({ cols, items, etiquetas, onChange }: {
  cols: number; items: Pos[]; etiquetas: Record<string, string>; onChange: (l: Pos[]) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const itemsRef = useRef(items);
  itemsRef.current = items;
  const [drag, setDrag] = useState<{ id: string; dx: number; dy: number; col: number; row: number; ok: boolean } | null>(null);
  const filas = Math.max(1, ...items.map((p) => p.row + p.rows - 1)) + 1; // siempre una fila libre al final
  const paso = () => {
    const r = ref.current!.getBoundingClientRect();
    return { r, x: (r.width - GAP * (cols - 1)) / cols + GAP, y: FILA + GAP };
  };
  const maxSpan = (lista: Pos[], it: Pos) => {
    const sig = lista.filter((p) => p.id !== it.id && p.col > it.col && it.row < p.row + p.rows && p.row < it.row + it.rows).map((p) => p.col);
    return (sig.length ? Math.min(...sig) : cols + 1) - it.col;
  };
  const maxRows = (lista: Pos[], it: Pos) => {
    const sig = lista.filter((p) => p.id !== it.id && it.col < p.col + p.span && p.col < it.col + it.span && p.row > it.row).map((p) => p.row);
    const limite = sig.length ? Math.min(...sig) - it.row : MAX_TILE_ROWS;
    return Math.max(1, Math.min(MAX_TILE_ROWS, limite));
  };
  const ancho = (it: Pos, span: number) => {
    const lista = itemsRef.current;
    const actual = lista.find((p) => p.id === it.id) ?? it;
    const nuevo = Math.max(1, Math.min(maxSpan(lista, actual), span));
    if (nuevo !== actual.span) onChange(lista.map((p) => (p.id === it.id ? { ...p, span: nuevo } : p)));
  };
  const alto = (it: Pos, rows: number) => {
    const lista = itemsRef.current;
    const actual = lista.find((p) => p.id === it.id) ?? it;
    const nuevo = Math.max(1, Math.min(maxRows(lista, actual), rows));
    if (nuevo !== actual.rows && !choca(lista, actual.id, actual.col, actual.row, actual.span, nuevo)) {
      onChange(lista.map((p) => (p.id === it.id ? { ...p, rows: nuevo } : p)));
    }
  };
  function empezar(e: React.PointerEvent<HTMLDivElement>, it: Pos) {
    if (e.button !== 0 || (e.target as HTMLElement).closest("button,[data-redim]")) return;
    e.preventDefault();
    const t = e.currentTarget.getBoundingClientRect();
    const offX = e.clientX - t.left, offY = e.clientY - t.top, x0 = e.clientX, y0 = e.clientY;
    let estado: { id: string; dx: number; dy: number; col: number; row: number; ok: boolean } | null = null;
    const mv = (ev: PointerEvent) => {
      if (!estado && Math.hypot(ev.clientX - x0, ev.clientY - y0) < 4) return;
      const { r, x, y } = paso();
      const col = Math.max(1, Math.min(cols - it.span + 1, Math.round((ev.clientX - offX - r.left) / x) + 1));
      const row = Math.max(1, Math.min(filas, Math.round((ev.clientY - offY - r.top) / y) + 1));
      estado = { id: it.id, dx: ev.clientX - x0, dy: ev.clientY - y0, col, row, ok: !choca(itemsRef.current, it.id, col, row, it.span, it.rows) };
      setDrag(estado);
    };
    const up = () => {
      window.removeEventListener("pointermove", mv); window.removeEventListener("pointerup", up);
      const fin = estado;
      if (fin?.ok) onChange(itemsRef.current.map((p) => (p.id === it.id ? { ...p, col: fin.col, row: fin.row } : p)));
      setDrag(null);
    };
    window.addEventListener("pointermove", mv);
    window.addEventListener("pointerup", up);
  }
  function redimensionar(e: React.PointerEvent, it: Pos) {
    e.preventDefault(); e.stopPropagation();
    const x0 = e.clientX, s0 = it.span;
    const mv = (ev: PointerEvent) => ancho(it, Math.round(s0 + (ev.clientX - x0) / paso().x));
    const up = () => { window.removeEventListener("pointermove", mv); window.removeEventListener("pointerup", up); };
    window.addEventListener("pointermove", mv);
    window.addEventListener("pointerup", up);
  }
  function redimensionarAlto(e: React.PointerEvent, it: Pos) {
    e.preventDefault(); e.stopPropagation();
    const y0 = e.clientY, rows0 = it.rows;
    const mv = (ev: PointerEvent) => alto(it, Math.round(rows0 + (ev.clientY - y0) / paso().y));
    const up = () => { window.removeEventListener("pointermove", mv); window.removeEventListener("pointerup", up); };
    window.addEventListener("pointermove", mv);
    window.addEventListener("pointerup", up);
  }
  const arrastrado = drag && items.find((p) => p.id === drag.id);
  return (
    <div ref={ref} className="grid select-none" style={{ gap: GAP, gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`, gridTemplateRows: `repeat(${filas}, ${FILA}px)` }}>
      {Array.from({ length: filas * cols }, (_, k) => (
        <div key={`g${k}`} aria-hidden className="rounded bg-[#2D88C0]/[0.07] pointer-events-none"
          style={{ gridColumn: (k % cols) + 1, gridRow: Math.floor(k / cols) + 1 }} />
      ))}
      {drag && arrastrado && (
        <div aria-hidden className={`rounded-md border-2 pointer-events-none ${drag.ok ? "border-[#2D88C0] bg-[#2D88C0]/15" : "border-[#C026D3] bg-[#C026D3]/10"}`}
          style={{ gridColumn: `${drag.col} / span ${arrastrado.span}`, gridRow: `${drag.row} / span ${arrastrado.rows}` }} />
      )}
      {items.map((it) => {
        const moviendo = drag?.id === it.id;
        return (
          <div key={it.id} data-tile={it.id} onPointerDown={(e) => empezar(e, it)}
            style={{ gridColumn: `${it.col} / span ${it.span}`, gridRow: `${it.row} / span ${it.rows}`,
              transform: moviendo ? `translate(${drag!.dx}px, ${drag!.dy}px)` : undefined, zIndex: moviendo ? 10 : undefined }}
            className={`relative min-w-0 rounded-md border-2 border-dashed bg-white flex flex-col justify-center gap-0.5 pl-1 pr-3 touch-none ${moviendo ? "cursor-grabbing border-[#2D88C0] shadow-lg opacity-90" : "cursor-grab border-[#94a3b8] hover:border-[#2D88C0]"}`}>
            <span className="flex items-center gap-0.5 min-w-0">
              <GripVertical className="w-3.5 h-3.5 text-[#94a3b8] shrink-0" />
              <span className="min-w-0 truncate text-[11px] font-medium text-[#1e293b]" title={etiquetas[it.id]}>{etiquetas[it.id]}</span>
            </span>
            <span className="flex items-center justify-end">
              <button type="button" aria-label={`Estrechar ${etiquetas[it.id]}`} onClick={() => ancho(it, it.span - 1)} disabled={it.span <= 1}
                className="w-4 h-4 rounded flex items-center justify-center text-[#475569] hover:bg-[#E6EDFF] disabled:opacity-30"><Minus className="w-3 h-3" /></button>
              <span className="w-7 text-center text-[10px] tabular-nums text-[#475569]">{it.span}/{cols}</span>
              <button type="button" aria-label={`Ensanchar ${etiquetas[it.id]}`} onClick={() => ancho(it, it.span + 1)} disabled={it.span >= maxSpan(items, it)}
                className="w-4 h-4 rounded flex items-center justify-center text-[#475569] hover:bg-[#E6EDFF] disabled:opacity-30"><Plus className="w-3 h-3" /></button>
            </span>
            <span data-redim onPointerDown={(e) => redimensionar(e, it)} title="Arrastra para cambiar el ancho"
              className="absolute -right-[3px] top-0 bottom-0 w-2 cursor-col-resize flex items-center justify-center">
              <span className="w-[3px] h-5 rounded-full bg-[#2D88C0]" />
            </span>
            <button type="button" data-redim role="slider" aria-orientation="vertical"
              aria-label={`Alto de ${etiquetas[it.id]}`} aria-valuemin={1} aria-valuemax={maxRows(items, it)}
              aria-valuenow={it.rows} aria-valuetext={`${it.rows} filas`}
              onPointerDown={(e) => redimensionarAlto(e, it)}
              onKeyDown={(e) => {
                if (e.key === "ArrowUp") { e.preventDefault(); alto(it, it.rows - 1); }
                if (e.key === "ArrowDown") { e.preventDefault(); alto(it, it.rows + 1); }
                if (e.key === "Home") { e.preventDefault(); alto(it, 1); }
                if (e.key === "End") { e.preventDefault(); alto(it, maxRows(items, it)); }
              }}
              title="Arrastra para cambiar el alto; flechas arriba/abajo para ajustar"
              className="absolute -bottom-[4px] left-1/2 -translate-x-1/2 w-8 h-2 rounded-full bg-[#2D88C0] cursor-row-resize focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#0d2b5c]" />
          </div>
        );
      })}
    </div>
  );
}

function Confirmar({ texto, onCancelar, onConfirmar }: { texto: string; onCancelar: () => void; onConfirmar: () => void }) {
  return (
    <Modal
      title="Confirmar"
      onClose={onCancelar}
      size="sm"
      footer={
        <>
          <ModalButton variant="outline" icon={X} onClick={onCancelar}>Cancelar</ModalButton>
          <ModalButton variant="magenta" onClick={onConfirmar}>Eliminar</ModalButton>
        </>
      }
    >
      <ModalBody>
        <p className="text-[13px] text-[#1e293b] border-l-[3px] border-l-[#C026D3] pl-3">{texto}</p>
      </ModalBody>
    </Modal>
  );
}

export default function CentroPage() {
  const [data, setData] = useState<CentroResp | null>(null);
  const [datos, setDatos] = useState<Centro | null>(null);
  const [razon, setRazon] = useState<RazonSocial | null>(null);
  const [horarioExtra, setHorarioExtra] = useState<Record<string, unknown>>({});
  const [dias, setDias] = useState<Dia[]>([]);
  const [festivos, setFestivos] = useState<string[]>([]);
  const [nuevoFestivo, setNuevoFestivo] = useState("");
  const [gestoria, setGestoria] = useState<Gestoria>({});
  const [gabinetes, setGabinetes] = useState<Gabinete[]>([]);
  const [nuevoGabinete, setNuevoGabinete] = useState("");
  const [borrar, setBorrar] = useState<Gabinete | null>(null);
  const [saving, setSaving] = useState<string | null>(null);
  const [layout, setLayout] = useState<Layout>(LAYOUT_DEF);
  const [draft, setDraft] = useState<Layout>(LAYOUT_DEF);
  const [editando, setEditando] = useState(false);
  const [muro, setMuro] = useState<CajaMuro[] | null>(null);
  const [draftMuro, setDraftMuro] = useState<CajaMuro[]>(MURO_DEF);
  const [margen, setMargen] = useState(MARGEN_DEF);
  const [draftMargen, setDraftMargen] = useState(MARGEN_DEF);
  // Las acciones de distribución van en la barra superior de la app (hueco #barra-acciones del layout),
  // para que encima del muro no quede ninguna franja ocupada.
  const [barra, setBarra] = useState<HTMLElement | null>(null);
  useEffect(() => { setBarra(document.getElementById("barra-acciones")); }, []);
  const [msg, setMsg] = useState<{ t: string; e?: boolean }>({ t: "" });
  const flash = (t: string, e = false) => { setMsg({ t, e }); setTimeout(() => setMsg({ t: "" }), 3000); };

  // Alto natural (en px) del contenido de cada caja, medido fuera del modo edición: con él se calcula
  // el alto por defecto de las cajas cuando no hay muro guardado (y al pulsar Restablecer).
  const [altos, setAltos] = useState<Partial<Record<CajaId, number>>>({});
  const editandoRef = useRef(editando);
  editandoRef.current = editando;
  const naturales = useRef<Partial<Record<CajaId, HTMLDivElement>>>({});
  const observador = useRef<ResizeObserver | null>(null);
  const medir = useMemo(() => {
    const leer = () => {
      if (editandoRef.current) return;
      const n: Partial<Record<CajaId, number>> = {};
      (Object.keys(naturales.current) as CajaId[]).forEach((id) => { n[id] = naturales.current[id]!.offsetHeight; });
      setAltos((a) => (JSON.stringify(a) === JSON.stringify(n) ? a : n));
    };
    return Object.fromEntries(MURO_DEF.map(({ i: id }) => [id, (el: HTMLDivElement | null) => {
      observador.current ??= new ResizeObserver(leer);
      const prev = naturales.current[id];
      if (prev === el) return;
      if (prev) observador.current.unobserve(prev);
      if (el) { naturales.current[id] = el; observador.current.observe(el); } else delete naturales.current[id];
    }])) as Record<CajaId, (el: HTMLDivElement | null) => void>;
  }, []);
  useEffect(() => () => observador.current?.disconnect(), []);
  const ajustar = (base: CajaMuro[], m: number, compactar = false) => {
    const l = base.map((c) => (altos[c.i] ? { ...c, h: filasMuro(altos[c.i]! + PAD_CAJA, m) } : c));
    return compactar ? apilar(l) : l;
  };
  const cambiarMargen = (m: number) => setDraftMargen(m);

  const load = useCallback(async () => {
    const d = await api.get<CentroResp>("/configuracion/centro");
    setData(d); setDatos(d.centro); setRazon(d.razon_social);
    const { dias: ds, ...resto } = d.config["centro.horario"] ?? {};
    setHorarioExtra(resto);
    setDias(DIAS.map((_, i) => ({ ...DIA_CERRADO, ...(ds?.[i] ?? (i < 5 ? DIA_ABIERTO : DIA_CERRADO)) })));
    setFestivos([...(d.config["centro.festivos"] ?? [])].sort());
    const g = d.config["gestoria.asesoria"] ?? {};
    setGestoria({ ...g, contacto: g.contacto ?? g.nombre ?? "" });
    setGabinetes(d.gabinetes);
  }, []);
  useEffect(() => { load().catch((e) => flash(errMsg(e), true)); }, [load]);
  useEffect(() => {
    api.get<{ valores: Record<string, unknown> }>("/config")
      .then((c) => {
        const v = c.valores?.["ui.centro.layout"] as { cajas?: unknown; colsMuro?: unknown; margen?: unknown } | undefined;
        setLayout(normaliza(v)); const m = normalizaMargen(v?.margen); setMuro(normalizaMuro(v?.cajas, v?.colsMuro, m)); setMargen(m);
      })
      .catch(() => { /* sin distribución guardada: se usa la de por defecto */ });
  }, []);
  async function guardarLayout() {
    setSaving("layout");
    try {
      await api.put("/config", { clave: "ui.centro.layout", valor: { ...draft, cajas: draftMuro, colsMuro: COLS_MURO, margen: draftMargen } });
      setLayout(draft); setMuro(draftMuro); setMargen(draftMargen); setEditando(false); flash("Distribución guardada ✓");
    }
    catch (e) { flash(errMsg(e), true); }
    finally { setSaving(null); }
  }

  async function guardar(clave: string, fn: () => Promise<unknown>, ok: string) {
    setSaving(clave);
    try { await fn(); flash(`${ok} ✓`); await load(); }
    catch (e) { flash(errMsg(e), true); }
    finally { setSaving(null); }
  }
  const putDatos = () => { const { id: _i, razon_social_compartida_id: _r, ...body } = datos as Centro; return api.put("/configuracion/centro/datos", body); };
  const putRazon = () => { const { id, centro_id: _c, ...body } = razon as RazonSocial; return api.put(`/configuracion/centro/razon-social/${id}`, body); };
  const putConfig = (clave: string, valor: unknown) => api.put("/configuracion/centro/config", { clave, valor });

  async function subir(f: File, aplicar: (url: string) => void) {
    try { const { url } = await api.upload("/uploads", f); aplicar(url); flash("Imagen subida — pulsa guardar para aplicarla"); }
    catch (e) { flash(errMsg(e), true); }
  }
  async function altaGabinete() {
    if (!nuevoGabinete.trim()) return;
    try { await api.post("/configuracion/centro/gabinete", { nombre: nuevoGabinete.trim(), activo: true }); setNuevoGabinete(""); flash("Gabinete creado ✓"); load(); }
    catch (e) { flash(errMsg(e), true); }
  }
  async function bajaGabinete() {
    if (!borrar) return;
    try { await api.delete(`/configuracion/centro/gabinete/${borrar.id}`); flash("Gabinete eliminado ✓"); load(); }
    catch (e) { flash(errMsg(e), true); }
    finally { setBorrar(null); }
  }

  if (!data || !datos) return <div className="p-5 text-[12px] text-[#94a3b8]">Cargando…</div>;
  const razonPropia = !datos.razon_social_compartida_id && !!razon;
  const setD = (k: keyof Centro, v: unknown) => setDatos({ ...datos, [k]: v });
  const setR = (k: keyof RazonSocial, v: unknown) => razon && setRazon({ ...razon, [k]: v });
  const at = (c: CajaId, id: string): React.CSSProperties => {
    const p = layout[c].find((x) => x.id === id);
    return p ? { gridColumn: `${p.col} / span ${p.span}`, gridRow: `${p.row} / span ${p.rows}` } : {};
  };
  const geoVars = (c: CajaId) => Object.fromEntries(["pais", "provincia", "ciudad", "cp"].flatMap((id) => {
    const p = layout[c].find((x) => x.id === id) ?? { col: 1, span: 1, row: 1 };
    return [[`--${id}-c`, p.col], [`--${id}-s`, p.span], [`--${id}-r`, p.row]];
  })) as React.CSSProperties;
  const rejilla = (c: CajaId): React.CSSProperties => ({ gridTemplateColumns: `repeat(${COLS[c]}, minmax(0, 1fr))`, gridAutoRows: "minmax(46px, auto)" });
  const editor = (c: CajaId) => (
    <EditorRejilla cols={COLS[c]} items={draft[c]} etiquetas={ETIQUETAS[c]} onChange={(l) => setDraft((d) => ({ ...d, [c]: l }))} />
  );
  const setDia = (i: number, patch: Partial<Dia>) => setDias(dias.map((d, j) => (j === i ? { ...d, ...patch } : d)));

  const BTN = "h-6 px-2.5 rounded border border-white/40 bg-white/10 text-[11px] font-semibold text-white hover:bg-white/20 inline-flex items-center gap-1.5 whitespace-nowrap";
  const acciones = editando ? (
    <>
      <span className="hidden 2xl:block min-w-0 truncate text-[11px] text-white/80"
        title="Cajas: arrástralas desde cualquier zona libre y suéltalas donde quieras; estira cualquiera de sus bordes o esquinas. Piezas: arrástralas para moverlas; los bordes azules ajustan ancho y alto.">
        Arrastra las cajas donde quieras y estira sus bordes
      </span>
      <label className="inline-flex items-center gap-1 text-[11px] font-semibold text-white whitespace-nowrap" title="Separación entre cajas">
        Separación
        <select value={draftMargen} onChange={(e) => cambiarMargen(Number(e.target.value))}
          className="h-6 rounded border border-white/40 bg-white text-[11px] text-[#1e293b] px-1 outline-none cursor-pointer">
          {MARGENES.map((m) => <option key={m} value={m}>{m} px</option>)}
        </select>
      </label>
      <button type="button" className={BTN} onClick={() => setDraftMuro((m) => ajustar(m, draftMargen))} title="Ajusta el alto de cada caja a su contenido">Ajustar altos</button>
      <button type="button" className={BTN} onClick={() => { setDraft(LAYOUT_DEF); setDraftMargen(MARGEN_DEF); setDraftMuro(ajustar(MURO_DEF, MARGEN_DEF, true)); }}>Restablecer</button>
      <button type="button" className={BTN} onClick={() => setEditando(false)}>Cancelar</button>
      <button type="button" disabled={saving === "layout"} onClick={guardarLayout}
        className="h-6 px-2.5 rounded bg-[#2DD9C3] border border-[#0d2b5c] text-[#0d2b5c] text-[11px] font-semibold hover:opacity-90 disabled:opacity-50 whitespace-nowrap">Guardar distribución</button>
    </>
  ) : (
    <button type="button" title="Editar distribución" aria-label="Editar distribución"
      className="w-7 h-7 rounded flex items-center justify-center text-white hover:bg-white/15 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#00e5ff]"
      onClick={() => { setDraft(layout); setDraftMargen(margen); setDraftMuro(muro ?? ajustar(MURO_DEF, margen, true)); setEditando(true); }}>
      <LayoutDashboard className="w-[18px] h-[18px]" />
    </button>
  );

  return (
    <div className="-m-5 p-5 min-h-full bg-[#FFFFFF]">
      {msg.t && (
        <div role="status" className={`fixed top-14 right-6 z-50 px-4 py-2 rounded-md text-[12px] font-semibold shadow-lg ${msg.e ? "bg-[#C026D3] text-white" : "bg-[#2DD9C3] text-[#0d2b5c]"}`}>{msg.t}</div>
      )}

      {barra && createPortal(acciones, barra)}

      <div className="-mx-5 -mt-5">
      <Muro layout={editando ? draftMuro : (muro ?? ajustar(MURO_DEF, margen, true))} margen={editando ? draftMargen : margen} editando={editando} onChange={setDraftMuro} cajas={{
        centro: (
        <Card color={C.azul} icon={Building2} title="Información del centro" mover={editando} medir={medir.centro} saving={saving === "centro"}
          onSave={() => guardar("centro", putDatos, "Información del centro guardada")}>
          {editando ? editor("centro") : (
          <div className="grid gap-3" style={rejilla("centro")}>
            <Campo label="Nombre" style={at("centro", "nombre")}><input className={UP} value={datos.nombre || ""} onChange={(e) => setD("nombre", e.target.value)} /></Campo>
            <Campo label="Código" style={at("centro", "codigo")}><input className={UP} disabled readOnly title="Solo se edita desde Superusuario" value={datos.codigo || ""} /></Campo>
            <Campo label="Tel. fijo" style={at("centro", "telefono")}><input className={IN} value={datos.telefono || ""} onChange={(e) => setD("telefono", e.target.value)} /></Campo>
            <Campo label="Tel. móvil" style={at("centro", "movil")}><input className={IN} value={datos.telefono_movil || ""} onChange={(e) => setD("telefono_movil", e.target.value)} /></Campo>
            <Campo label="Email" style={at("centro", "email")}><input type="email" className={IN} value={datos.email || ""} onChange={(e) => setD("email", e.target.value)} /></Campo>
            <Campo label="Web" style={at("centro", "web")}><input className={IN} value={datos.web || ""} onChange={(e) => setD("web", e.target.value)} /></Campo>
            <Campo label="Instagram" style={at("centro", "instagram")}><input className={IN} value={datos.instagram || ""} onChange={(e) => setD("instagram", e.target.value)} /></Campo>
            <Campo label="Dirección" style={at("centro", "direccion")}><input className={UP} value={datos.direccion || ""} onChange={(e) => setD("direccion", e.target.value)} /></Campo>
            <div className={GEO} style={geoVars("centro")}>
              <GeoCascada provincia={datos.provincia || ""} poblacion={datos.poblacion || ""} cp={datos.cp || ""}
                onChange={(g) => setDatos({ ...datos, ...g })} {...GEO_W} />
            </div>
            <Imagen label="Icono" style={at("centro", "icono")} url={img(datos.icono_url)} onPick={(f) => subir(f, (u) => setD("icono_url", u))} onClear={() => setD("icono_url", "")} />
            <Imagen label="Logo (documentos)" style={at("centro", "logo")} url={img(datos.logo_url)} onPick={(f) => subir(f, (u) => setD("logo_url", u))} onClear={() => setD("logo_url", "")} />
          </div>
          )}
        </Card>
        ),
        fiscal: (
        <Card color={C.rojo} icon={Landmark} title="Información fiscal" mover={editando} medir={medir.fiscal} saving={saving === "fiscal"}
          onSave={razonPropia ? () => guardar("fiscal", putRazon, "Información fiscal guardada") : undefined}>
          {editando ? editor("fiscal") : (
          <div className="grid gap-3" style={rejilla("fiscal")}>
            <Campo label="Razón social" style={at("fiscal", "razon")}><input className={UP} disabled readOnly title="Solo se edita desde Superusuario" value={razon?.nombre || ""} /></Campo>
            <Campo label="CIF" style={at("fiscal", "cif")}><input className={UP} disabled readOnly title="Solo se edita desde Superusuario" value={razon?.cif || ""} /></Campo>
            <Campo label="IBAN" style={at("fiscal", "iban")}><input className={`${UP} tabular-nums`} disabled={!razonPropia} value={razon?.iban || ""} onChange={(e) => setR("iban", e.target.value)} /></Campo>
            <Campo label="Licencia sanitaria" style={at("fiscal", "licencia")}><input className={UP} disabled={!razonPropia} value={razon?.licencia_sanitaria || ""} onChange={(e) => setR("licencia_sanitaria", e.target.value)} /></Campo>
            <Campo label="Serie" style={at("fiscal", "serie")}><input className={UP} disabled={!razonPropia} value={razon?.serie || ""} onChange={(e) => setR("serie", e.target.value)} /></Campo>
            <Campo label="Dirección fiscal" style={at("fiscal", "direccion")}><input className={UP} disabled={!razonPropia} value={razon?.direccion || ""} onChange={(e) => setR("direccion", e.target.value)} /></Campo>
            {razonPropia && razon ? (
              <div className={GEO} style={geoVars("fiscal")}>
                <GeoCascada provincia={razon.provincia || ""} poblacion={razon.poblacion || ""} cp={razon.cp || ""}
                  onChange={(g) => setRazon({ ...razon, ...g })} {...GEO_W} />
              </div>
            ) : null}
            {razonPropia
              ? <Imagen label="Sello (razón social)" style={at("fiscal", "sello")} url={img(razon?.sello_url)} onPick={(f) => subir(f, (u) => setR("sello_url", u))} onClear={() => setR("sello_url", "")} />
              : <p className="text-[11px] text-[#94a3b8] italic" style={at("fiscal", "sello")}>Este centro factura con la razón social de otro centro asociado; los datos fiscales se editan allí.</p>}
          </div>
          )}
        </Card>
        ),
        horario: (
        <Card color={C.marino} icon={Clock} title="Horario del centro" mover={editando} medir={medir.horario} saving={saving === "horario"}
          onSave={() => guardar("horario", async () => {
            await putConfig("centro.horario", { ...horarioExtra, dias });
            await putConfig("centro.festivos", [...festivos].sort());
          }, "Horario y festivos guardados")}>
          {editando ? editor("horario") : (
          <div className="grid gap-3" style={rejilla("horario")}>
            <div className="min-w-0 overflow-x-auto" style={at("horario", "tabla")}>
              <div className="grid grid-cols-[96px_64px_auto_auto] gap-x-4 items-end pb-1.5 border-b border-[#e5e7eb]">
                <span className={TH}>Día</span><span className={TH}>Abierto</span><span className={TH}>Mañana</span><span className={TH}>Tarde</span>
              </div>
              {dias.map((d, i) => (
                <div key={DIAS[i]} className="grid grid-cols-[96px_64px_auto_auto] gap-x-4 items-center py-1.5 border-b border-[#EFF2F7] last:border-0">
                  <span className="text-[12px] text-[#1e293b]">{DIAS[i]}</span>
                  <Check on={d.abierto} label={`${DIAS[i]} abierto`} onClick={() => setDia(i, d.abierto ? DIA_CERRADO : (d.t1a || d.t2a ? { abierto: true } : DIA_ABIERTO))} />
                  {d.abierto ? (
                    <>
                      <div className="flex items-center gap-1.5 text-[#94a3b8]">
                        <Hora label={`${DIAS[i]} mañana desde`} value={d.t1a} onChange={(v) => setDia(i, { t1a: v })} />–
                        <Hora label={`${DIAS[i]} mañana hasta`} value={d.t1b} onChange={(v) => setDia(i, { t1b: v })} />
                      </div>
                      <div className="flex items-center gap-1.5 text-[#94a3b8]">
                        <Hora label={`${DIAS[i]} tarde desde`} value={d.t2a} onChange={(v) => setDia(i, { t2a: v })} />–
                        <Hora label={`${DIAS[i]} tarde hasta`} value={d.t2b} onChange={(v) => setDia(i, { t2b: v })} />
                      </div>
                    </>
                  ) : <span className="col-span-2 text-[12px] italic text-[#94a3b8]">Cerrado</span>}
                </div>
              ))}
            </div>
            <div className="min-w-0" style={at("horario", "festivos")}>
              <span className={TH}>Días festivos / cerrados</span>
              <div className="flex items-center gap-2 mt-1.5">
                <input type="date" aria-label="Nuevo festivo" className={`${IN} flex-1 min-w-0 max-w-[220px]`} value={nuevoFestivo} onChange={(e) => setNuevoFestivo(e.target.value)} />
                <AddBtn label="Añadir festivo" onClick={() => {
                  if (!nuevoFestivo || festivos.includes(nuevoFestivo)) return;
                  setFestivos([...festivos, nuevoFestivo].sort()); setNuevoFestivo("");
                }} />
              </div>
              <div className="flex flex-wrap gap-1.5 mt-2.5">
                {festivos.map((f) => (
                  <span key={f} title={f} className="inline-flex items-center gap-1 pl-2 pr-1 py-0.5 rounded-full bg-[#FFF59D] border border-[#0d2b5c] text-[#0d2b5c] text-[11px] font-semibold">
                    {fechaCorta(f)}
                    <Quitar label={`Quitar festivo ${f}`} onClick={() => setFestivos(festivos.filter((x) => x !== f))} />
                  </span>
                ))}
                {festivos.length === 0 && <span className="text-[11px] italic text-[#94a3b8]">Sin festivos</span>}
              </div>
            </div>
          </div>
          )}
        </Card>
        ),
        gestoria: (
        <Card color={C.dorado} icon={Briefcase} title="Gestoría" mover={editando} medir={medir.gestoria} saving={saving === "gestoria"}
          onSave={() => guardar("gestoria", () => putConfig("gestoria.asesoria", gestoria), "Gestoría guardada")}>
          {editando ? editor("gestoria") : (
          <div className="grid gap-3" style={rejilla("gestoria")}>
            <Campo label="Email" style={at("gestoria", "email")}><input type="email" className={IN} value={gestoria.email || ""} onChange={(e) => setGestoria({ ...gestoria, email: e.target.value })} /></Campo>
            <Campo label="Contacto" style={at("gestoria", "contacto")}><input className={UP} value={gestoria.contacto || ""} onChange={(e) => setGestoria({ ...gestoria, contacto: e.target.value })} /></Campo>
            <Campo label="Teléfono" style={at("gestoria", "telefono")}><input className={IN} value={gestoria.telefono || ""} onChange={(e) => setGestoria({ ...gestoria, telefono: e.target.value })} /></Campo>
            <Campo label="NIF" style={at("gestoria", "nif")}><input className={UP} placeholder="B12345678" value={gestoria.nif || ""} onChange={(e) => setGestoria({ ...gestoria, nif: e.target.value })} /></Campo>
            <Campo label="Frecuencia" style={at("gestoria", "frecuencia")}>
              <select className={`${IN} cursor-pointer`} value={gestoria.frecuencia || ""} onChange={(e) => setGestoria({ ...gestoria, frecuencia: e.target.value })}>
                <option value="">—</option><option value="mensual">Mensual</option><option value="trimestral">Trimestral</option>
              </select>
            </Campo>
          </div>
          )}
          <p className="text-[11px] text-[#94a3b8] mt-2">El correo sale con el SMTP de <a href="/configuracion/conectores/mail" className="text-[#2D88C0] font-semibold hover:underline">Conectores → Mail</a>.</p>
        </Card>
        ),
        gabinetes: (
        <Card color={C.marino} icon={Armchair} title="Gabinetes" mover={editando} medir={medir.gabinetes}>
          {editando ? editor("gabinetes") : (
          <div className="grid gap-3 items-center" style={rejilla("gabinetes")}>
            <div className="min-w-0 flex flex-wrap items-center gap-2" style={at("gabinetes", "lista")}>
              {gabinetes.map((g) => (
                <span key={g.id} className="inline-flex items-center gap-2 h-[28px] px-1.5 rounded-md border border-[#e5e7eb] bg-white">
                  <Check on={g.activo} label={`${g.nombre} activo`} />
                  <span className="text-[12px] text-[#1e293b] uppercase">{g.nombre}</span>
                  <Quitar label={`Eliminar ${g.nombre}`} onClick={() => setBorrar(g)} />
                </span>
              ))}
              {gabinetes.length === 0 && <span className="text-[12px] italic text-[#94a3b8]">Sin gabinetes</span>}
            </div>
            <div className="min-w-0 flex items-center gap-2" style={at("gabinetes", "nuevo")}>
              <input aria-label="Nuevo gabinete" placeholder="Nuevo gabinete" className={UP} value={nuevoGabinete}
                onChange={(e) => setNuevoGabinete(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") altaGabinete(); }} />
              <AddBtn label="Añadir gabinete" onClick={altaGabinete} />
            </div>
          </div>
          )}
        </Card>
        ),
      }} />
      </div>

      <RolesPermisos />

      {borrar && <Confirmar texto={`¿Eliminar el gabinete "${borrar.nombre}"? No se puede deshacer.`} onCancelar={() => setBorrar(null)} onConfirmar={bajaGabinete} />}
    </div>
  );
}
