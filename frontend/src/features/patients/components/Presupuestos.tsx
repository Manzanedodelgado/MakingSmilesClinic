"use client";
/**
 * PRESUPUESTOS — workspace de una pantalla (estilo .37): odontograma (base clínica en gris +
 * líneas del presupuesto coloreadas) + DESGLOSE editable en línea del ppto seleccionado, lista
 * de presupuestos con filtros y totales (Presupuestado / Pagado / Pendiente). Solo BBDD nueva.
 * Estados = los reales de la BBDD (estados_presupuesto). PDF/WhatsApp = placeholder (sin backend
 * de documentos). El tratamiento de cada línea es de catálogo (modelo por tratamiento_id).
 */
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Loader2, Check, X, FileText, Plus, Save, Search, Trash2, Printer, Ban, RotateCcw, ClipboardCheck, MessageSquare, Copy, XCircle, LayoutTemplate } from "lucide-react";
import { ClinicalCard, SectionHeader, Modal, ModalBody, ModalButton } from "@/shared/components";
import { useEventStream } from "@/shared/hooks/useEventStream";
import { patientService } from "../services/patientService";
import { useDirtyForm } from "../store/patientSession";
import type { Presupuesto, Presupuestos as TPresupuestos, TratamientoCatalogo, OdontogramaData, PresupuestoPredisenado } from "../types/patient";
import OdontogramaOverlay, { PiezaMarcada } from "./odontograma/OdontogramaOverlay";
import { itemsToPiezas, construirOdontogramaClinico, resolverExclusiones } from "./odontograma/odontogramaData";
import { iconoTratamiento } from "@/shared/lib/iconoTratamiento";
import { imprimirPresupuesto, enviarPresupuestoWhatsApp, piezasDeLinea } from "../lib/presupuestoDoc";
import { ZonaEditor, scopeDeCatalogo, valorInicialAmbito } from "./AmbitoPicker";

const eur = (n: number | null | undefined) => (n ?? 0).toLocaleString("es-ES", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";
// Importe de descuento (€) de una línea: el valor es % sobre el bruto si pct, o € directo si no.
const descImporte = (precio: number, cantidad: number, descuento: number, pct: boolean) => {
  const bruto = precio * (cantidad || 1);
  return Math.min(pct ? bruto * (descuento || 0) / 100 : (descuento || 0), bruto);
};
const netoLinea = (precio: number, cantidad: number, descuento: number, pct: boolean) =>
  Math.max(0, precio * (cantidad || 1) - descImporte(precio, cantidad, descuento, pct));
// Unidades de una línea = nº de dientes (FDI) en "Piezas", o nº de zonas seleccionadas
// (cuadrantes/sextantes/arcadas separados por coma), o 1. Es DERIVADO, no se teclea.
const unidadesLinea = (pieza: string | null, zona_boca?: string | null): number => {
  const fdis = (pieza || "").split(/[^0-9]+/).filter((x) => /^([1-4][1-8]|[5-8][1-5])$/.test(x));
  if (fdis.length) return fdis.length;
  return (zona_boca || "").split(",").filter(Boolean).length || 1;
};
const fechaES = (s: string | null) => (s ? new Date(s).toLocaleDateString("es-ES") : "—");
const isoToInput = (s: string | null) => (s ? s.slice(0, 10) : new Date().toISOString().slice(0, 10));

// Estados reales de estados_presupuesto (BBDD): id → etiqueta.
const ESTADO_LABEL: Record<number, string> = {
  0: "Nuevo", 1: "Entregado", 2: "Anulado", 3: "Aceptado", 4: "En curso", 5: "Finalizado", 6: "Aceptado parcial", 7: "Cancelado",
};
// Protocolo (docs/PROTOCOLO-PRESUPUESTOS.md): editable SOLO Nuevo/Entregado. Un Aceptado/Parcial
// tiene plan (previstos) enlazado a sus líneas → para editarlo hay que Reabrir (retira el plan).
const CERRADOS = [2, 3, 4, 5, 6, 7];
const ESTADO_CLASS: Record<string, string> = {
  Aceptado: "bg-[#FFFFFF] border-[#9FE6DB] text-[#0F8C7D]",
  "Aceptado parcial": "bg-[#FFFFFF] border-[#9FE6DB] text-[#0F8C7D]",
  "En curso": "bg-[#FFFFFF] border-[#7dd3fc] text-[#0369a1]",
  Entregado: "bg-[#FFFFFF] border-[#1ca0d1] text-[#1500A0]",
  Finalizado: "bg-[#FFFFFF] border-[#c4b5fd] text-[#6d28d9]",
  Anulado: "bg-[#FFFFFF] border-[#E9A8F5] text-[#A21CAF]",
  Cancelado: "bg-[#FFFFFF] border-[#C4B5FD] text-[#6D28D9]",
  Nuevo: "bg-[#FFFFFF] border-[#cbd5e1] text-[#64748b]",
};
const FILTROS = ["Todos", "Nuevo", "Entregado", "Aceptado", "Aceptado parcial", "En curso", "Finalizado", "Cancelado", "Anulado"];

type DLinea = { id?: number; estado?: string | null; tratamiento_id: number; tratamiento: string; tipo_actuacion?: string | null; es_mensualidad?: boolean; pieza: string; zona_boca: string | null; colaborador_id: number | null; precio: number; cantidad: number; descuento: number; descuento_pct: boolean };
// Unidades de una línea para precio/total: en mensualidad = nº de mensualidades (cantidad); si no, derivado de piezas/zonas.
const udsLinea = (l: { es_mensualidad?: boolean; cantidad: number; pieza: string; zona_boca: string | null }): number =>
  l.es_mensualidad ? (l.cantidad || 1) : unidadesLinea(l.pieza, l.zona_boca);
type Draft = { id: number | null; num: number | null; titulo: string; notas: string; fecha: string; colaborador_id: number | null; estado_id: number; lineas: DLinea[] };


const draftFrom = (p: Presupuesto): Draft => ({
  id: p.id, num: p.num, titulo: p.titulo ?? "", notas: p.notas ?? "", fecha: isoToInput(p.fecha), colaborador_id: p.colaborador_id ?? null, estado_id: p.estado_id ?? 0,
  lineas: p.lineas.map((l) => ({ id: l.id, estado: l.estado, tratamiento_id: l.tratamiento_id ?? 0, tratamiento: l.tratamiento, tipo_actuacion: l.tipo_actuacion, es_mensualidad: l.es_mensualidad ?? false, pieza: l.pieza ?? "", zona_boca: l.zona_boca, colaborador_id: l.colaborador_id, precio: l.precio, cantidad: l.cantidad, descuento: l.descuento ?? 0, descuento_pct: l.descuento_pct ?? false })),
});
const draftNuevo = (): Draft => ({ id: null, num: null, titulo: "", notas: "", fecha: new Date().toISOString().slice(0, 10), colaborador_id: null, estado_id: 0, lineas: [] });

function BuscadorTrat({ patientId, onPick }: { patientId: number; onPick: (t: TratamientoCatalogo) => void }) {
  const [q, setQ] = useState(""); const [res, setRes] = useState<TratamientoCatalogo[]>([]); const [open, setOpen] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  // El desplegable va en position:fixed anclado al input para que NO lo recorte el overflow
  // de las tarjetas del desglose ni quede detrás de la barra inferior. Abre hacia abajo o
  // hacia arriba según el hueco, con la altura limitada al espacio disponible.
  const [pos, setPos] = useState<{ left: number; width: number; top?: number; bottom?: number; maxH: number } | null>(null);
  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    if (q.trim().length < 2) { setRes([]); setOpen(false); return; }
    timer.current = setTimeout(async () => {
      try { setRes((await patientService.catalogoTratamientos(patientId, q.trim())).tratamientos); setOpen(true); } catch { setRes([]); }
    }, 250);
    return () => { if (timer.current) clearTimeout(timer.current); };
  }, [q, patientId]);
  // Recalcula la posición del desplegable (al abrir, al cambiar resultados, y en scroll/resize).
  useLayoutEffect(() => {
    if (!open) return;
    const upd = () => {
      const el = boxRef.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      const below = window.innerHeight - r.bottom - 8;
      const above = r.top - 8;
      const up = below < 200 && above > below;   // no cabe debajo → abre arriba
      setPos({
        left: r.left, width: r.width, maxH: Math.max(120, Math.min(240, up ? above : below)),
        ...(up ? { bottom: window.innerHeight - r.top + 2 } : { top: r.bottom + 2 }),
      });
    };
    upd();
    window.addEventListener("scroll", upd, true);
    window.addEventListener("resize", upd);
    return () => { window.removeEventListener("scroll", upd, true); window.removeEventListener("resize", upd); };
  }, [open, res]);
  return (
    <div ref={boxRef} className="relative flex-1">
      <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
      <input value={q} onChange={(e) => setQ(e.target.value)} onFocus={() => res.length && setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)} placeholder="Añadir tratamiento del catálogo…"
        className="w-full border border-[#e5e7eb] rounded-sm pl-7 pr-2 py-1 text-[12px] outline-none focus:border-[#1ca0d1]" />
      {open && res.length > 0 && pos && (
        <div style={{ position: "fixed", left: pos.left, top: pos.top, bottom: pos.bottom, width: pos.width, maxHeight: pos.maxH }}
          className="z-[80] overflow-y-auto bg-white border border-[#e5e7eb] rounded-sm shadow-lg">
          {res.map((t) => (
            <button key={t.id} onMouseDown={(e) => e.preventDefault()}
              onClick={() => { onPick(t); setQ(""); setRes([]); setOpen(false); }}
              className="w-full flex items-center gap-2 px-2 py-1.5 text-left hover:bg-[#E6EDFF] text-[12px]">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={iconoTratamiento(t.nombre)} alt="" className="w-5 h-5 shrink-0" />
              <span className="font-mono text-[10px] text-[#1500A0] bg-[#FFFFFF] px-1 rounded-sm">{t.codigo}</span>
              <span className="text-[#333333] flex-1 truncate">{t.nombre}</span>
              <span className="text-slate-500">{eur(t.precio)}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// "Cargar plantilla": botón + MODAL (position fixed → no lo recorta el overflow de la tarjeta)
// con los prediseñados agrupados por categoría; al elegir uno vuelca sus líneas.
function CargarPlantilla({ patientId, onPick }: { patientId: number; onPick: (p: PresupuestoPredisenado) => void }) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<PresupuestoPredisenado[] | null>(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => {   // carga perezosa al abrir
    if (!open || items) return;
    setLoading(true);
    patientService.presupuestosPredisenados(patientId)
      .then((r) => setItems(r.predisenados)).catch(() => setItems([])).finally(() => setLoading(false));
  }, [open, items, patientId]);
  const grupos = useMemo(() => {
    const g: Record<string, PresupuestoPredisenado[]> = {};
    (items ?? []).forEach((p) => { (g[p.categoria] ??= []).push(p); });
    return Object.entries(g).sort((a, b) => a[0].localeCompare(b[0]));
  }, [items]);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)} title="Cargar un presupuesto prediseñado"
        className="flex items-center gap-1 text-[11px] font-semibold text-[#1500A0] bg-[#FFFFFF] hover:bg-[#d6ecfb] border border-[#bfe0f5] rounded-sm px-2 py-1 transition-colors shrink-0">
        <LayoutTemplate className="w-3.5 h-3.5" /> Cargar plantilla
      </button>
      {open && (
        <Modal
          title={<span className="flex items-center gap-2"><LayoutTemplate className="w-4 h-4" /> Cargar plantilla</span>}
          onClose={() => setOpen(false)}
          size="md"
          closeOnBackdrop={false}
        >
          <ModalBody>
            <div className="flex flex-col">
              {loading && <p className="px-3 py-3 text-[12px] text-slate-400">Cargando plantillas…</p>}
              {!loading && grupos.length === 0 && <p className="px-3 py-3 text-[12px] text-slate-400 italic">No hay plantillas.</p>}
              {grupos.map(([cat, ps]) => (
                <div key={cat}>
                  <div className="px-3 py-1 text-[10px] uppercase tracking-wide text-[#21A2E5] font-semibold bg-[#FFFFFF] sticky top-0 border-b border-[#BFE4F7]">{cat}</div>
                  {ps.map((p) => (
                    <button key={p.id} onClick={() => { onPick(p); setOpen(false); }}
                      className="w-full flex items-center justify-between gap-2 px-3 py-2 text-left hover:bg-[#E6EDFF] text-[12px] border-b border-[#f3f5f8]">
                      <span className="text-[#333333] truncate">{p.titulo}</span>
                      <span className="text-[10px] text-slate-400 shrink-0">{p.lineas.length} líneas</span>
                    </button>
                  ))}
                </div>
              ))}
            </div>
          </ModalBody>
        </Modal>
      )}
    </>
  );
}

function Tot({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="flex flex-col px-4 py-1">
      <span className="text-[9px] uppercase tracking-wide text-slate-400">{label}</span>
      <span className="text-[14px] font-semibold leading-tight" style={{ color }}>{value}</span>
    </div>
  );
}

// Badge del estado de una línea (en aceptación parcial).
function LineaBadge({ estado }: { estado?: string | null }) {
  if (estado === "ACEPTADA") return <span className="text-[9px] font-semibold text-[#0F8C7D]" title="Aceptada">✓</span>;
  if (estado === "ANULADA") return <span className="text-[9px] font-semibold text-[#A21CAF]" title="Anulada">✕</span>;
  return null;
}

// Diálogo de aceptación: elige qué líneas acepta el paciente; si es parcial, qué hacer
// con las no aceptadas (anularlas o pasarlas a un presupuesto nuevo).
function AceptarDialog({ lineas, onConfirm, onClose }:
  { lineas: { id: number; tratamiento: string; precio: number; cantidad: number; descuento: number; descuento_pct: boolean }[];
    onConfirm: (ids: number[], resto: "mantener" | "anular") => void; onClose: () => void }) {
  const [sel, setSel] = useState<Set<number>>(new Set(lineas.map((l) => l.id)));
  const [resto, setResto] = useState<"mantener" | "anular">("mantener");
  const toggle = (id: number) => setSel((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const ids = [...sel];
  const parcial = ids.length > 0 && ids.length < lineas.length;
  return (
    <Modal
      title={<span className="flex items-center gap-2"><ClipboardCheck className="w-4 h-4" /> Aceptar presupuesto</span>}
      onClose={onClose}
      size="md"
      closeOnBackdrop={false}
      footer={
        <>
          <ModalButton variant="magenta" icon={X} onClick={onClose}>Cancelar</ModalButton>
          <ModalButton variant="primary" icon={Check} onClick={() => onConfirm(ids, resto)} disabled={ids.length === 0}>
            Confirmar
          </ModalButton>
        </>
      }
    >
      <ModalBody>
        <div className="flex flex-col gap-2">
          <p className="text-[12px] text-[#7f8c8d]">Marca las líneas que el paciente acepta.</p>
          <div className="border border-[#BFE4F7] rounded-md divide-y divide-[#f0f2f5] max-h-[40vh] overflow-y-auto">
            {lineas.map((l) => (
              <label key={l.id} className="flex items-center gap-2 px-2 py-1.5 text-[12px] cursor-pointer hover:bg-[#E6EDFF]">
                <input type="checkbox" checked={sel.has(l.id)} onChange={() => toggle(l.id)} className="accent-[#20BEAB]" />
                <span className="flex-1 truncate">{l.tratamiento}</span>
                <span className="text-slate-500">{eur(netoLinea(l.precio, l.cantidad, l.descuento, l.descuento_pct))}</span>
              </label>
            ))}
          </div>
          {parcial && (
            <div className="rounded-md bg-[#FFFFFF] border border-[#C4B5FD] p-2.5">
              <p className="text-[11px] text-[#5B21B6] font-semibold mb-1.5">Las líneas no aceptadas pasan a un <b>presupuesto nuevo</b>. ¿Qué hago con él?</p>
              <label className="flex items-center gap-2 text-[12px] text-[#333] cursor-pointer">
                <input type="radio" name="resto" checked={resto === "mantener"} onChange={() => setResto("mantener")} className="accent-[#1ca0d1]" />
                Mantenerlo activo (Entregado)
              </label>
              <label className="flex items-center gap-2 text-[12px] text-[#333] cursor-pointer mt-1">
                <input type="radio" name="resto" checked={resto === "anular"} onChange={() => setResto("anular")} className="accent-[#1ca0d1]" />
                Anularlo
              </label>
            </div>
          )}
        </div>
      </ModalBody>
    </Modal>
  );
}

// Cancelar el RESTO no realizado de un presupuesto (Aceptado / En curso / Aceptado parcial) → estado Cancelado.
function CancelarDialog({ lineas, onConfirm, onClose }:
  { lineas: { id: number; tratamiento: string; precio: number; cantidad: number; descuento: number; descuento_pct: boolean }[];
    onConfirm: (ids: number[]) => void; onClose: () => void }) {
  const [sel, setSel] = useState<Set<number>>(new Set(lineas.map((l) => l.id)));
  const toggle = (id: number) => setSel((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const ids = [...sel];
  return (
    <Modal
      title={<span className="flex items-center gap-2"><XCircle className="w-4 h-4" /> Cancelar resto del presupuesto</span>}
      onClose={onClose}
      size="md"
      closeOnBackdrop={false}
      footer={
        <>
          <ModalButton variant="magenta" icon={X} onClick={onClose}>Cerrar</ModalButton>
          <ModalButton variant="primary" icon={XCircle} onClick={() => onConfirm(ids)} disabled={ids.length === 0}>
            Cancelar ({ids.length})
          </ModalButton>
        </>
      }
    >
      <ModalBody>
        <div className="flex flex-col gap-2">
          <p className="text-[12px] text-[#7f8c8d]">Marca las líneas <b>no realizadas</b> que se cancelan. El presupuesto pasará a <b>Cancelado</b>. Las ya realizadas no se tocan.</p>
          {lineas.length === 0 ? (
            <p className="text-[12px] italic text-slate-400 py-3 text-center">No hay líneas pendientes que cancelar (todo realizado o ya cancelado).</p>
          ) : (
            <div className="border border-[#BFE4F7] rounded-md divide-y divide-[#f0f2f5] max-h-[40vh] overflow-y-auto">
              {lineas.map((l) => (
                <label key={l.id} className="flex items-center gap-2 px-2 py-1.5 text-[12px] cursor-pointer hover:bg-[#E6EDFF]">
                  <input type="checkbox" checked={sel.has(l.id)} onChange={() => toggle(l.id)} className="accent-[#6D28D9]" />
                  <span className="flex-1 truncate">{l.tratamiento}</span>
                  <span className="text-slate-500">{eur(netoLinea(l.precio, l.cantidad, l.descuento, l.descuento_pct))}</span>
                </label>
              ))}
            </div>
          )}
        </div>
      </ModalBody>
    </Modal>
  );
}

export function Presupuestos({ patientId }: { patientId: number }) {
  const [data, setData] = useState<TPresupuestos | null>(null);
  const [odo, setOdo] = useState<OdontogramaData | null>(null);   // base = render activo de O1 (hallazgos+realizados)
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filtro, setFiltro] = useState("Todos");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");
  const [edad, setEdad] = useState<number | null>(null);   // dentición infantil/mixta por edad
  const flash = (t: string) => { setMsg(t); setTimeout(() => setMsg(""), 2500); };

  useEffect(() => {
    let alive = true;
    patientService.cabecera(patientId).then((c) => { if (alive) setEdad(c.edad); }).catch(() => {});
    return () => { alive = false; };
  }, [patientId]);

  const cargar = useCallback(async (selId?: number | null) => {
    setLoading(true); setError(null);
    try {
      const r = await patientService.presupuestos(patientId);
      setData(r);
      const sel = selId !== undefined ? r.presupuestos.find((p) => p.id === selId) : r.presupuestos[0];
      setDraft(sel ? draftFrom(sel) : null);
    } catch (e) { setError(e instanceof Error ? e.message : "No se pudieron cargar los presupuestos"); }
    finally { setLoading(false); }
  }, [patientId]);
  useEffect(() => {   // ?pre=<id> (p.ej. al venir de la Escucha) → abre ese presupuesto
    const pre = typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("pre") : null;
    cargar(pre ? Number(pre) : undefined);
  }, [cargar]);

  // Tiempo real: si se crea un presupuesto para este paciente (p.ej. desde otra
  // sesion o la Escucha), la lista se refresca sin recargar la ficha.
  useEventStream({
    "presupuesto.creado": (d) => { if (d.paciente_id === patientId) void cargar(); },
  }, [patientId]);

  useEffect(() => {
    patientService.odontograma(patientId).then(setOdo).catch(() => setOdo(null));
  }, [patientId]);

  const visibles = useMemo(
    () => (data?.presupuestos ?? []).filter((p) => filtro === "Todos" || p.estado === filtro),
    [data, filtro],
  );

  // Odontograma SOLO de este presupuesto (sus líneas, con tratamientos sobre cada pieza/zona).
  const piezasPresupuesto = useMemo<PiezaMarcada[]>(() => {
    const items = (draft?.lineas ?? [])
      .filter((l) => l.estado !== "ANULADA")
      .flatMap((l) => piezasDeLinea(l.pieza, l.zona_boca).map((t) => ({ pieza: t, tratamiento: l.tratamiento })));
    return itemsToPiezas(items);
  }, [draft]);
  const odoRef = useRef<HTMLDivElement>(null);

  const piezasOdo = useMemo<PiezaMarcada[]>(() => {
    // Base = render ACTIVO de O1 (hallazgos INICIAL + realizados, ya resueltos), pintado en gris.
    const base = construirOdontogramaClinico(odo?.teeth ?? [], odo?.realizados ?? [], { soloInicial: true })
      .map((p) => ({ ...p, color: "#c8d2dc", isInicial: true }));
    // + líneas de ESTE presupuesto encima, RESPETANDO las prioridades en la combinación.
    return resolverExclusiones([...base, ...piezasPresupuesto]);
  }, [odo, piezasPresupuesto]);

  const total = useMemo(() => (draft ? draft.lineas.reduce((s, l) => s + netoLinea(l.precio, udsLinea(l), l.descuento, l.descuento_pct), 0) : 0), [draft]);

  // Captura el odontograma del presupuesto (componente real) como PNG para el documento.
  async function capturarOdontograma(): Promise<string> {
    const el = odoRef.current;
    if (!el) return "";
    try {
      const html2canvas = (await import("html2canvas")).default;
      // esperar a que cargue la imagen base del odontograma
      await Promise.all(Array.from(el.querySelectorAll("img")).map((img) =>
        img.complete ? null : new Promise((r) => { img.onload = r; img.onerror = r; })));
      const canvas = await html2canvas(el, { useCORS: true, backgroundColor: "#ffffff", scale: 2, logging: false });
      return canvas.toDataURL("image/png");
    } catch { return ""; }
  }

  const updLinea = (i: number, patch: Partial<DLinea>) =>
    setDraft((d) => (d ? { ...d, lineas: d.lineas.map((l, j) => (j === i ? { ...l, ...patch } : l)) } : d));
  const delLinea = (i: number) => setDraft((d) => (d ? { ...d, lineas: d.lineas.filter((_, j) => j !== i) } : d));
  const addLinea = (t: TratamientoCatalogo) =>
    // El ámbito lo dicta el catálogo (tipo_actuacion): p.ej. una férula entra como Arcada sup. (y queda bloqueado).
    setDraft((d) => (d ? { ...d, lineas: [...d.lineas, { tratamiento_id: t.id, tratamiento: t.nombre, tipo_actuacion: t.tipo_actuacion, es_mensualidad: !!t.es_mensualidad, ...valorInicialAmbito(scopeDeCatalogo(t.tipo_actuacion)), colaborador_id: null, precio: t.precio, cantidad: t.es_mensualidad ? 18 : 1, descuento: 0, descuento_pct: false }] } : d));
  // Cargar plantilla (prediseñado): vuelca sus líneas al desglose con su económico; pone el título si está vacío.
  const cargarPlantilla = (p: PresupuestoPredisenado) =>
    setDraft((d) => (d ? {
      ...d,
      titulo: d.titulo?.trim() ? d.titulo : p.titulo,
      lineas: [...d.lineas, ...p.lineas.map((l) => ({ tratamiento_id: l.tratamiento_id, tratamiento: l.tratamiento, tipo_actuacion: l.tipo_actuacion, es_mensualidad: !!l.es_mensualidad, ...((l.zona_boca || l.pieza) ? { pieza: l.pieza ?? "", zona_boca: l.zona_boca ?? null } : valorInicialAmbito(scopeDeCatalogo(l.tipo_actuacion))), colaborador_id: null, precio: l.precio, cantidad: l.cantidad ?? (l.es_mensualidad ? 18 : 1), descuento: l.descuento ?? 0, descuento_pct: l.descuento_pct ?? false }))],
    } : d));
  const colaboradores = data?.colaboradores ?? [];

  async function guardar() {
    if (!draft) return;
    setSaving(true); setError(null);
    const body = {
      titulo: draft.titulo || null, notas: draft.notas || null, estado_id: draft.estado_id, fecha: draft.fecha,
      colaborador_id: draft.colaborador_id ?? null,
      lineas: draft.lineas.filter((l) => l.tratamiento_id > 0).map((l) => ({ tratamiento_id: l.tratamiento_id, pieza: l.pieza || null, zona_boca: l.zona_boca, colaborador_id: l.colaborador_id, precio: l.precio, cantidad: udsLinea(l), descuento: l.descuento || 0, descuento_pct: l.descuento_pct })),
    };
    try {
      if (draft.id) { await patientService.editarPresupuesto(patientId, draft.id, body); await cargar(draft.id); flash("Presupuesto guardado ✓"); }
      else { const r = await patientService.crearPresupuesto(patientId, body); await cargar(r.id); flash("Presupuesto creado ✓"); }
    } catch (e) { setError(e instanceof Error ? e.message.replace(/^P(OST|UT).*?→ \d+ /, "") : "No se pudo guardar"); }
    finally { setSaving(false); }
  }

  async function borrar(id?: number | null) {
    const pid = id ?? draft?.id;
    if (!pid) { setDraft(null); return; }
    if (!window.confirm("¿Borrar este presupuesto? Esta acción no se puede deshacer.")) return;
    try { await patientService.borrarPresupuesto(patientId, pid); await cargar(); flash("Presupuesto borrado"); }
    catch { flash("No se pudo borrar"); }
  }

  // ── Flujo del presupuesto (entregar / reabrir / anular / aceptar) ──
  const cerrado = draft ? CERRADOS.includes(draft.estado_id) : false;
  const persistido = data?.presupuestos.find((p) => p.id === draft?.id) ?? null;

  // Presupuesto en edición con cambios sin guardar → cuenta para el guard de cierre.
  const dirtyPresu = !!draft && !cerrado && (
    draft.id == null
      ? draft.lineas.length > 0 || !!draft.titulo?.trim() || !!draft.notas?.trim()
      : !!persistido && JSON.stringify(draft) !== JSON.stringify(draftFrom(persistido))
  );
  useDirtyForm("presupuesto", dirtyPresu, guardar);
  const [aceptarOpen, setAceptarOpen] = useState(false);
  const [cancelarOpen, setCancelarOpen] = useState(false);
  const [waBusy, setWaBusy] = useState(false);

  async function accion(p: Promise<unknown>, ok: string) {
    setError(null);
    try { await p; await cargar(draft?.id ?? null); flash(ok); }
    catch (e) { setError(e instanceof Error ? e.message.replace(/^POST.*?→ \d+ /, "") : "No se pudo completar"); }
  }
  async function imprimir() {
    if (!draft?.id) return;
    setError(null);
    try {
      const odo = await capturarOdontograma();   // odontograma de ESTE presupuesto, capturado ahora
      await imprimirPresupuesto(patientId, draft.id, odo);   // documento configurado en Config › Admin
      if (draft.estado_id === 0) await accion(patientService.entregarPresupuesto(patientId, draft.id), "Impreso y entregado ✓");
      else flash("Documento generado ✓");
    } catch (e) { setError(e instanceof Error ? e.message : "No se pudo generar el documento"); }
  }
  async function enviarWhatsApp() {
    if (!draft?.id || waBusy) return;
    if (!window.confirm("¿Enviar el presupuesto por WhatsApp al móvil del paciente?")) return;
    setError(null); setWaBusy(true);
    try {
      const odo = await capturarOdontograma();   // odontograma de ESTE presupuesto, capturado ahora
      await enviarPresupuestoWhatsApp(patientId, draft.id, odo);
      await cargar(draft.id);
      flash("Presupuesto enviado por WhatsApp ✓");
    } catch (e) { setError(e instanceof Error ? e.message.replace(/^POST.*?→ \d+ /, "") : "No se pudo enviar por WhatsApp"); }
    finally { setWaBusy(false); }
  }
  const reabrir = () => draft?.id && accion(patientService.reabrirPresupuesto(patientId, draft.id), "Reabierto para editar ✓");
  const anular = () => { if (draft?.id && window.confirm("¿Anular este presupuesto? Quedará como histórico.")) accion(patientService.anularPresupuesto(patientId, draft.id), "Presupuesto anulado"); };
  const duplicar = () => draft?.id && accion(patientService.duplicarPresupuesto(patientId, draft.id), "Presupuesto duplicado (copia en estado Nuevo) ✓");
  async function confirmarCancelar(ids: number[]) {
    if (!draft?.id) return;
    setCancelarOpen(false);
    await accion(patientService.cancelarPresupuesto(patientId, draft.id, { lineas: ids }), "Resto cancelado · presupuesto Cancelado ✓");
  }
  async function confirmarAceptar(ids: number[], resto: "mantener" | "anular") {
    if (!draft?.id) return;
    setAceptarOpen(false);
    await accion(
      patientService.aceptarPresupuesto(patientId, draft.id, { lineas_aceptadas: ids, resto }).then((r) => {
        if (r.nuevo_presupuesto_id) flash("Aceptado · líneas no aceptadas → nuevo presupuesto ✓");
      }),
      "Presupuesto aceptado ✓",
    );
  }

  if (loading && !data) return <p className="text-[12px] text-slate-400 p-4">Cargando presupuestos…</p>;
  if (error && !data) return <p className="text-[12px] text-[#C026D3] p-4">{error}</p>;
  if (!data) return null;

  return (
    <div className="h-full min-h-0 px-4 pt-1.5 pb-3 flex flex-col gap-2 bg-white overflow-hidden">
      {msg && <div className="fixed top-14 right-6 z-[60] px-4 py-2.5 rounded-sm text-[12px] font-semibold shadow-lg bg-[#2DD9C3] text-[#1500A0]">{msg}</div>}

      {/* Odontograma OCULTO con SOLO las líneas de este presupuesto — fuente de la captura para el documento */}
      {/* Captura para el documento = O5 COMPLETO: base activa de O1 (gris) + líneas de ESTE presupuesto. */}
      <div ref={odoRef} aria-hidden style={{ position: "fixed", left: "-99999px", top: 0, width: 600, pointerEvents: "none" }}>
        <OdontogramaOverlay modo="view" piezasMarcadas={piezasOdo} edad={edad} />
      </div>

      {/* Superior: odontograma + desglose editable. items-stretch → la tarjeta Desglose iguala
          su altura a la izquierda (odontograma+observaciones); su "Total presupuesto" queda fijo abajo. */}
      <div className="shrink-0 flex flex-col xl:flex-row gap-3 items-start xl:items-stretch">
        <ClinicalCard noPadding className="w-full xl:w-[600px] shrink-0">
          {/* ODONTOGRAMA 4 (interno) si es histórico (draft.num) · ODONTOGRAMA 5 si es nuevo presupuesto */}
          <SectionHeader variant="dark" title={`Odontograma — Presupuesto ${draft?.num ? `Nº ${draft.num}` : "(nuevo)"}`} icon={FileText}
            action={<span className="text-[10px] text-white/80 uppercase tracking-wide">{eur(total)}</span>} />
          {/* Odontograma un pelín más pequeño y centrado → deja subir Observaciones, ajustada al render. */}
          <div className="px-3 pt-3 pb-0"><div className="mx-auto w-[90%]"><OdontogramaOverlay modo="view" piezasMarcadas={piezasOdo} edad={edad} /></div></div>
          {draft && (
            <div className="px-3 pb-1 space-y-2">
              <div>
                <label className="block text-[10px] uppercase tracking-wide text-[#1ca0d1] font-semibold mb-1">Observaciones / financiación</label>
                <textarea value={draft.notas} disabled={cerrado} onChange={(e) => setDraft({ ...draft, notas: e.target.value })} rows={2}
                  placeholder="Notas, condiciones de pago, particularidades…"
                  className="w-full border border-[#e5e7eb] rounded-sm px-2 py-1.5 text-[12px] outline-none focus:border-[#1ca0d1] resize-none disabled:opacity-60" />
              </div>
            </div>
          )}
        </ClinicalCard>

        <ClinicalCard noPadding className="flex-1 min-w-0 w-full flex flex-col min-h-0 overflow-hidden">
          {draft ? (
            <>
              <div className="bg-[#1500A0] px-3 py-1.5 flex items-center gap-2 shrink-0">
                <span className="text-white font-semibold text-[12px] uppercase tracking-wide">Desglose</span>
                <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${ESTADO_CLASS[ESTADO_LABEL[draft.estado_id]] ?? ESTADO_CLASS.Nuevo}`}>{ESTADO_LABEL[draft.estado_id] ?? "—"}</span>
                <input type="date" value={draft.fecha} disabled={cerrado} onChange={(e) => setDraft({ ...draft, fecha: e.target.value })}
                  className="bg-transparent text-white text-[11px] border-b border-white/30 outline-none w-28 disabled:opacity-50" />
                <div className="flex-1" />
                {!cerrado && <button onClick={guardar} disabled={saving} title="Guardar" className="text-white hover:text-[#2DD9C3] disabled:opacity-50">{saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}</button>}
                {draft.id && <button onClick={imprimir} title="Imprimir (documento configurado en Config › Admin) · marca Entregado" className="text-white hover:text-[#2DD9C3]"><Printer className="w-4 h-4" /></button>}
                {draft.id && <button onClick={enviarWhatsApp} disabled={waBusy} title="Enviar por WhatsApp (PDF) · marca Entregado" className="text-white hover:text-[#9FE6DB] disabled:opacity-50">{waBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : <MessageSquare className="w-4 h-4" />}</button>}
                {draft.id && (draft.estado_id === 0 || draft.estado_id === 1) && draft.lineas.length > 0 &&
                  <button onClick={() => setAceptarOpen(true)} title="Aceptar presupuesto" className="text-white hover:text-[#9FE6DB]"><ClipboardCheck className="w-4 h-4" /></button>}
                {draft.id && [3, 4, 6].includes(draft.estado_id) && <button onClick={() => setCancelarOpen(true)} title="Cancelar el resto no realizado (→ Cancelado)" className="text-white hover:text-[#C4B5FD]"><XCircle className="w-4 h-4" /></button>}
                {draft.id && cerrado && <button onClick={reabrir} title="Reabrir para editar" className="text-white hover:text-[#2DD9C3]"><RotateCcw className="w-4 h-4" /></button>}
                {draft.id && [0, 1].includes(draft.estado_id) && <button onClick={anular} title="Anular (la oferta decae; para un aceptado usa Cancelar)" className="text-white hover:text-[#E9A8F5]"><Ban className="w-4 h-4" /></button>}
                {draft.id && <button onClick={duplicar} title="Duplicar (copia nueva en estado Nuevo, cualquier estado)" className="text-white hover:text-[#2DD9C3]"><Copy className="w-4 h-4" /></button>}
                {draft.id && <button onClick={() => borrar()} title="Borrar" className="text-white hover:text-[#F3CDF8]"><Trash2 className="w-4 h-4" /></button>}
              </div>
              <div className="p-3 flex-1 flex flex-col min-h-0">
                {/* Título + doctor titular: una fila fina y discreta; lo importante son las líneas de abajo. */}
                <div className="mb-2 shrink-0 flex items-center gap-2">
                  <input value={draft.titulo} disabled={cerrado} onChange={(e) => setDraft({ ...draft, titulo: e.target.value })}
                    placeholder="Título del presupuesto (opcional)"
                    className="flex-1 min-w-0 border border-[#e5e7eb] rounded-sm px-2 py-1 text-[11px] outline-none focus:border-[#1ca0d1] disabled:opacity-60" />
                  {/* Doctor de CABECERA: el que sale impreso (titular = solo doctores; los higienistas solo en las líneas). */}
                  <select value={draft.colaborador_id ?? ""} disabled={cerrado} title="Doctor titular (sale en el presupuesto impreso)"
                    onChange={(e) => setDraft({ ...draft, colaborador_id: e.target.value ? Number(e.target.value) : null })}
                    className="w-48 shrink-0 border border-[#e5e7eb] rounded-sm px-2 py-1 text-[11px] outline-none focus:border-[#1ca0d1] disabled:opacity-60 bg-white text-[#333333]">
                    <option value="">Doctor (impreso)</option>
                    {colaboradores.filter((c) => c.es_doctor).map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}
                  </select>
                </div>
                <div className="border border-[#e5e7eb] rounded-sm overflow-hidden shrink-0">
                  <div className="grid grid-cols-[148px_1fr_132px_44px_58px_84px_70px_28px_20px] gap-1 px-2 py-1 bg-[#FFFFFF] text-[10px] uppercase tracking-wide text-[#1ca0d1] font-semibold shrink-0">
                    <span className="px-1">Zona</span><span className="px-1">Tratamiento</span><span className="px-1">Doctor</span><span className="text-center">Uds</span><span className="text-right px-1">Precio</span><span className="text-right px-1">Dto</span><span className="text-right px-1">Total</span><span className="text-center">Est.</span><span />
                  </div>
                  <div className="max-h-[300px] overflow-y-auto divide-y divide-[#f0f2f5]">
                    {draft.lineas.map((l, i) => (
                      <div key={i} className={`grid grid-cols-[148px_1fr_132px_44px_58px_84px_70px_28px_20px] gap-1 px-2 py-1 items-center ${l.estado === "ANULADA" ? "opacity-50 line-through" : ""}`}>
                        <ZonaEditor pieza={l.pieza} zona_boca={l.zona_boca} disabled={cerrado}
                          lockScope={cerrado ? null : scopeDeCatalogo(l.tipo_actuacion)} onChange={(p) => updLinea(i, p)} />
                        <span className="flex items-center gap-2 min-w-0" title={l.tratamiento}>
                          <span className="w-6 h-6 rounded-md bg-[#FFFFFF] border border-[#e5e7eb] flex items-center justify-center shrink-0">
                            {/* eslint-disable-next-line @next/next/no-img-element */}
                            <img src={iconoTratamiento(l.tratamiento)} alt="" className="w-4 h-4" />
                          </span>
                          <span className="truncate text-[12.5px] font-medium text-[#1a1a1a]">{l.tratamiento}</span>
                        </span>
                        <select value={l.colaborador_id ?? ""} disabled={cerrado} onChange={(e) => updLinea(i, { colaborador_id: e.target.value ? Number(e.target.value) : null })}
                          title={colaboradores.find((c) => c.id === l.colaborador_id)?.nombre || "Doctor de la línea"}
                          className="w-full border border-transparent hover:border-[#e5e7eb] focus:border-[#1ca0d1] rounded-sm pl-[3px] pr-1 py-0.5 text-[11px] outline-none text-[#333333] bg-transparent disabled:opacity-60">
                          <option value="">Doctor</option>
                          {colaboradores.map((c) => <option key={c.id} value={c.id}>{c.corto ?? c.nombre}</option>)}
                        </select>
                        {l.es_mensualidad ? (
                          <input type="number" min={1} step={1} value={l.cantidad} disabled={cerrado} title="Nº de mensualidades (fases al aceptar)"
                            onChange={(e) => updLinea(i, { cantidad: Math.max(1, Math.floor(Number(e.target.value) || 1)) })}
                            className="w-full border border-[#e5e7eb] hover:border-[#1ca0d1] focus:border-[#1ca0d1] rounded-sm px-0.5 py-0.5 text-[11px] text-center outline-none text-[#1500A0] disabled:opacity-60 [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none" />
                        ) : (
                          <span className="w-full text-center text-[11px] text-[#333333] tabular-nums" title="Unidades = nº de piezas de esta línea">{unidadesLinea(l.pieza, l.zona_boca)}</span>
                        )}
                        <input type="number" step="0.01" value={l.precio} disabled={cerrado} onChange={(e) => updLinea(i, { precio: Number(e.target.value) || 0 })}
                          className="w-full border border-transparent hover:border-[#e5e7eb] focus:border-[#1ca0d1] rounded-sm px-1 py-0.5 text-[11px] text-right outline-none text-[#1500A0] disabled:opacity-60" />
                        <div className="flex items-center gap-0.5 min-w-0">
                          <input type="number" step="0.01" min={0} value={l.descuento} disabled={cerrado} title="Descuento de esta línea (€ o %)" onChange={(e) => updLinea(i, { descuento: Math.max(0, Number(e.target.value) || 0) })}
                            className="w-full min-w-0 border border-transparent hover:border-[#e5e7eb] focus:border-[#1ca0d1] rounded-sm px-1 py-0.5 text-[11px] text-right outline-none text-[#0F8C7D] disabled:opacity-60" />
                          <button type="button" disabled={cerrado} title="Cambiar € / %" onClick={() => updLinea(i, { descuento_pct: !l.descuento_pct })}
                            className="shrink-0 w-5 text-[10px] font-semibold rounded-sm border border-[#e5e7eb] text-[#0F8C7D] hover:bg-[#E6EDFF] disabled:opacity-60">{l.descuento_pct ? "%" : "€"}</button>
                        </div>
                        <span className="w-full text-right text-[11px] font-semibold text-[#1500A0] tabular-nums px-1">{eur(netoLinea(l.precio, udsLinea(l), l.descuento, l.descuento_pct))}</span>
                        <span className="flex items-center justify-center"><LineaBadge estado={l.estado} /></span>
                        {!cerrado ? <button onClick={() => delLinea(i)} className="text-slate-400 hover:text-[#C026D3]"><Trash2 className="w-3.5 h-3.5" /></button> : <span />}
                      </div>
                    ))}
                    {draft.lineas.length === 0 && <p className="px-2 py-3 text-[11px] text-slate-400 italic">Sin líneas. Añade tratamientos abajo.</p>}
                  </div>
                </div>
                {!cerrado && (
                  <div className="flex items-center gap-2 mt-1.5 px-0.5 shrink-0">
                    <CargarPlantilla patientId={patientId} onPick={cargarPlantilla} />
                    <Plus className="w-3.5 h-3.5 text-[#1ca0d1]" />
                    <BuscadorTrat patientId={patientId} onPick={addLinea} />
                  </div>
                )}
                {cerrado && <p className="text-[11px] text-slate-400 italic mt-1.5">Presupuesto cerrado. Pulsa «Reabrir» para volver a editarlo.</p>}
                {error && <p className="text-[11px] text-[#C026D3] mt-1">{error}</p>}
              </div>
              {/* Total: celda contenida, anclada abajo; mb afinado para que su base case con Observaciones (izq). */}
              <div className="mx-3 mb-[10px] mt-1 flex items-center justify-between px-4 h-[50px] bg-[#FFFFFF] border border-[#e5e7eb] rounded-sm shrink-0">
                <span className="text-[12px] text-slate-500 uppercase tracking-wide font-semibold">Total presupuesto</span>
                <span className="text-[16px] font-semibold text-[#1500A0]">{eur(total)}</span>
              </div>
            </>
          ) : (
            <p className="text-[12px] text-slate-400 italic p-6 text-center">Selecciona un presupuesto de la lista o crea uno nuevo.</p>
          )}
        </ClinicalCard>
      </div>

      {/* Inferior: lista + filtros — ocupa el alto restante; la TABLA scrollea dentro (una pantalla) */}
      <ClinicalCard noPadding className="flex-1 min-h-0 flex flex-col overflow-hidden">
        {/* Filtro de estado INTEGRADO en la barra (desplegable) + Nuevo presupuesto. */}
        <SectionHeader variant="dark" title="Presupuestos" icon={FileText}
          action={
            <div className="flex items-center gap-2">
              <select value={filtro} onChange={(e) => setFiltro(e.target.value)} title="Filtrar por estado"
                className="text-[11px] bg-white/15 text-white border border-white/30 rounded-sm pl-2 pr-1 py-1 outline-none focus:border-white/70 cursor-pointer">
                {FILTROS.map((f) => <option key={f} value={f} className="bg-white text-[#1500A0]">{f === "Todos" ? "Todos los estados" : f}</option>)}
              </select>
              <button onClick={() => { setDraft(draftNuevo()); setError(null); }}
                className="flex items-center gap-1 text-[10px] uppercase tracking-wide bg-[#2DD9C3] hover:bg-[#2DD9C3]/85 text-[#1500A0] font-semibold px-2 py-1 rounded-sm transition-colors"><Plus className="w-3.5 h-3.5" /> Nuevo presupuesto</button>
            </div>
          } />
        <div className="flex-1 min-h-0 overflow-y-auto">
        <table className="w-full text-[12px] bg-white">
          <thead className="sticky top-0 z-10">
            {/* Cabecera de columnas (#4) — melocotón claro, texto navy, altura reducida */}
            <tr className="bg-[#FFFFFF] text-[11px] uppercase tracking-wide text-[#065AED] border-b border-[#BFE4F7]">
              <th className="text-left px-4 py-1 font-semibold">Nº</th>
              <th className="text-left px-4 py-1 font-semibold">Fecha</th>
              <th className="text-left px-4 py-1 font-semibold">Descripción</th>
              <th className="text-right px-4 py-1 font-semibold">Total</th>
              <th className="text-right px-4 py-1 font-semibold">Pendiente</th>
              <th className="text-center px-4 py-1 font-semibold">Estado</th>
              <th className="text-center px-4 py-1 font-semibold w-16">Acciones</th>
            </tr>
          </thead>
          <tbody>
            {visibles.map((p) => {
              const sel = draft?.id === p.id;
              // Fila seleccionada (#5) — fondo gris, texto oscuro, altura reducida
              return (
              <tr key={p.id} onClick={() => { setDraft(draftFrom(p)); setError(null); }}
                className={`border-b border-[#e5e7eb] cursor-pointer transition-colors ${sel ? "bg-[#FFFFFF]" : "hover:bg-[#E6EDFF]"}`}>
                <td className="px-4 py-1"><span className="font-mono font-semibold text-[#1500A0]">{p.num ?? "—"}</span></td>
                <td className="px-4 py-1"><span className="text-slate-600">{fechaES(p.fecha)}</span></td>
                <td className="px-4 py-1"><span className="block truncate max-w-[220px] text-[#333]">{p.titulo || `Presupuesto ${p.num ?? "—"}`}</span></td>
                <td className="px-4 py-1 text-right"><span className="font-semibold text-[#1500A0]">{eur(p.total)}</span></td>
                <td className="px-4 py-1 text-right"><span className="text-[#1ca0d1]">{eur(p.pendiente)}</span></td>
                <td className="px-4 py-1 text-center"><span className={`inline-flex items-center justify-center px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase border whitespace-nowrap ${ESTADO_CLASS[p.estado] ?? ESTADO_CLASS.Nuevo}`}>{p.estado}</span></td>
                <td className="px-4 py-1 text-center"><button onClick={(e) => { e.stopPropagation(); borrar(p.id); }} className="p-1 rounded-full transition-colors text-[#1500A0] hover:bg-[#1500A0]/10" title="Eliminar presupuesto"><Trash2 className="w-3.5 h-3.5" /></button></td>
              </tr>
              );
            })}
            {visibles.length === 0 && <tr><td colSpan={7} className="px-4 py-6 text-center text-[12px] text-slate-400 italic">Sin presupuestos en este filtro</td></tr>}
          </tbody>
        </table>
        </div>
      </ClinicalCard>

      {/* Totales globales */}
      <ClinicalCard noPadding className="shrink-0">
        <div className="flex items-center divide-x divide-[#eef1f6]">
          <Tot label="Total presupuestado" value={eur(data.total_presupuestado)} color="#065AED" />
          <Tot label="Total pagado" value={eur(data.total_pagado)} color="#2DD9C3" />
          <Tot label="Pendiente" value={eur(data.total_pendiente)} color="#1ca0d1" />
        </div>
      </ClinicalCard>

      {aceptarOpen && persistido && (
        <AceptarDialog
          lineas={persistido.lineas.filter((l) => l.estado !== "ANULADA").map((l) => ({ id: l.id, tratamiento: l.tratamiento, precio: l.precio, cantidad: l.cantidad, descuento: l.descuento ?? 0, descuento_pct: l.descuento_pct ?? false }))}
          onConfirm={confirmarAceptar} onClose={() => setAceptarOpen(false)} />
      )}
      {cancelarOpen && persistido && (
        <CancelarDialog
          lineas={persistido.lineas.filter((l) => l.estado !== "ANULADA" && !l.realizada).map((l) => ({ id: l.id, tratamiento: l.tratamiento, precio: l.precio, cantidad: l.cantidad, descuento: l.descuento ?? 0, descuento_pct: l.descuento_pct ?? false }))}
          onConfirm={confirmarCancelar} onClose={() => setCancelarOpen(false)} />
      )}
    </div>
  );
}
