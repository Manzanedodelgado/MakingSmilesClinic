"use client";
/** DentIA · Paso 3 «Plan»: tratamiento por hallazgo y tabla del plan (precios de la tarifa del paciente). */
import { useEffect, useRef, useState } from "react";
import { Loader2, Plus, X } from "lucide-react";
import { patientService } from "../../services/patientService";
import type { DentiaLineaPlan, DentiaPatron, TratamientoCatalogo } from "../../types/patient";
import { CATEGORIAS, OPCIONES, OPCIONES_DEFECTO } from "./categorias";

const eur = (n: number) => n.toLocaleString("es-ES", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";
export const importeLinea = (l: DentiaLineaPlan) => {
  const bruto = l.precio * l.cantidad;
  const dto = l.descuento_pct ? bruto * (l.descuento / 100) : l.descuento;
  return Math.max(0, bruto - dto);
};

/** Buscador del catálogo de la tarifa del paciente. */
function Buscador({ patientId, q0, onPick }: { patientId: number; q0: string; onPick: (t: TratamientoCatalogo) => void }) {
  const [q, setQ] = useState(q0);
  const [res, setRes] = useState<TratamientoCatalogo[]>([]);
  const [cargando, setCargando] = useState(false);
  const t = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (t.current) clearTimeout(t.current);
    if (q.trim().length < 2) { setRes([]); return; }
    t.current = setTimeout(async () => {
      setCargando(true);
      try { setRes((await patientService.catalogoTratamientos(patientId, q.trim())).tratamientos); }
      catch { setRes([]); } finally { setCargando(false); }
    }, 250);
    return () => { if (t.current) clearTimeout(t.current); };
  }, [q, patientId]);
  return (
    <div className="mt-2">
      <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar tratamiento…"
        className="w-full h-9 rounded-md border border-sky-200 bg-white px-3 text-[13px] outline-none focus:border-sky-500" />
      <div className="mt-1 max-h-48 overflow-auto rounded-md border border-sky-100 bg-white">
        {cargando && <div className="p-2 text-[12px] text-slate-400 flex items-center gap-1.5"><Loader2 className="w-3.5 h-3.5 animate-spin" /> Buscando…</div>}
        {!cargando && q.trim().length >= 2 && res.length === 0 && <div className="p-2 text-[12px] text-slate-400">Sin coincidencias en la tarifa</div>}
        {res.map((t) => (
          <button key={t.id} type="button" onClick={() => onPick(t)}
            className="w-full text-left px-3 py-1.5 text-[12.5px] hover:bg-sky-50 flex justify-between gap-3 border-b border-slate-50 last:border-0">
            <span>{t.nombre}</span><span className="text-slate-500 shrink-0">{eur(t.precio)}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

/** «Guardar presupuesto DentIA» — opciones de tratamiento del hallazgo → tratamiento de la tarifa. */
export function ModalHallazgo({ patientId, patron, onAdd, onClose }: {
  patientId: number; patron: DentiaPatron; onAdd: (l: DentiaLineaPlan) => void; onClose: () => void;
}) {
  const opciones = OPCIONES[patron.categoria] ?? OPCIONES_DEFECTO;
  const [sel, setSel] = useState<number | null>(null);
  return (
    <div className="fixed inset-0 z-50 bg-slate-900/40 flex items-start justify-center pt-24" onClick={onClose}>
      <div className="w-[520px] max-w-[94vw] rounded-lg bg-white shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between px-4 py-3 border-b border-sky-100">
          <div>
            <div className="text-[15px] font-semibold text-sky-700">Guardar presupuesto DentIA</div>
            <div className="text-[11.5px] text-slate-500">
              {CATEGORIAS[patron.categoria]?.nombre ?? patron.categoria}{patron.pieza ? ` · pieza ${patron.pieza}` : ""}
            </div>
          </div>
          <button type="button" onClick={onClose} aria-label="Cerrar" className="text-slate-400 hover:text-slate-700"><X className="w-4 h-4" /></button>
        </div>
        <div className="p-4 bg-sky-50/60">
          {opciones.map((o, i) => (
            <label key={o.etiqueta} className="block py-1">
              <input type="radio" name="opcion" checked={sel === i} onChange={() => setSel(i)} className="mr-2" />
              <span className="text-[13px] font-semibold text-slate-700">{o.etiqueta}</span>
              {sel === i && (
                <Buscador patientId={patientId} q0={o.q} onPick={(t) => {
                  onAdd({ patron_id: patron.id, tratamiento_id: t.id, tratamiento: t.nombre, codigo: t.codigo,
                          pieza: patron.pieza ?? null, precio: t.precio, cantidad: 1, descuento: 0, descuento_pct: false });
                  onClose();
                }} />
              )}
            </label>
          ))}
        </div>
      </div>
    </div>
  );
}

/** Tabla del plan: una fila por tratamiento, con descuento editable. */
export function TablaPlan({ patientId, plan, tarifa, onChange }: {
  patientId: number; plan: DentiaLineaPlan[]; tarifa: string; onChange: (p: DentiaLineaPlan[]) => void;
}) {
  const [añadiendo, setAñadiendo] = useState(false);
  const hoy = new Date().toLocaleDateString("es-ES");
  const total = plan.reduce((s, l) => s + importeLinea(l), 0);
  const upd = (i: number, parche: Partial<DentiaLineaPlan>) => onChange(plan.map((l, j) => (j === i ? { ...l, ...parche } : l)));
  const th = "px-2 py-1.5 text-left font-semibold";
  return (
    <div className="px-4 pb-4">
      <div className="flex items-center gap-2 py-2">
        <button type="button" onClick={() => setAñadiendo((v) => !v)}
          className="h-8 px-3 rounded-md border border border-sky-200 bg-white text-[12px] font-semibold text-sky-700 flex items-center gap-1.5 hover:bg-sky-50">
          <Plus className="w-3.5 h-3.5" /> Añadir tratamiento
        </button>
        <span className="text-[11.5px] text-slate-500">Tarifa: {tarifa || "—"}</span>
      </div>
      {añadiendo && (
        <div className="mb-2 max-w-md">
          <Buscador patientId={patientId} q0="" onPick={(t) => {
            onChange([...plan, { tratamiento_id: t.id, tratamiento: t.nombre, codigo: t.codigo, pieza: null, precio: t.precio,
                                 cantidad: 1, descuento: 0, descuento_pct: false }]);
            setAñadiendo(false);
          }} />
        </div>
      )}
      <div className="rounded-md overflow-hidden border border-sky-200 text-[12px]">
        <table className="w-full bg-white">
          <thead className="bg-sky-600 text-white">
            <tr>
              <th className={th}>Fecha</th><th className={th}>Código</th><th className={th}>Tratamiento</th><th className={th}>Tarifa</th>
              <th className={th}>Piezas</th><th className={th}>Actos</th><th className={`${th} text-right`}>Importe unitario</th>
              <th className={`${th} text-right`}>% descuento</th><th className={`${th} text-right`}>Descuento</th>
              <th className={`${th} text-right`}>Importe línea</th><th className="w-6" />
            </tr>
          </thead>
          <tbody>
            {plan.length === 0 && (
              <tr><td colSpan={11} className="px-3 py-3 text-center text-slate-500 bg-sky-50">No se han encontrado coincidencias</td></tr>
            )}
            {plan.map((l, i) => {
              const bruto = l.precio * l.cantidad;
              const pct = l.descuento_pct ? l.descuento : bruto ? (l.descuento / bruto) * 100 : 0;
              return (
                <tr key={`${l.tratamiento_id}-${i}`} className="border-t border-slate-100">
                  <td className="px-2 py-1.5 whitespace-nowrap">{hoy}</td>
                  <td className="px-2 py-1.5 whitespace-nowrap">{l.codigo ?? ""}</td>
                  <td className="px-2 py-1.5">{l.tratamiento}</td>
                  <td className="px-2 py-1.5 whitespace-nowrap">{tarifa}</td>
                  <td className="px-2 py-1.5">
                    <input value={l.pieza ?? ""} onChange={(e) => upd(i, { pieza: e.target.value.slice(0, 10) || null })}
                      className="w-14 h-6 rounded border border-slate-200 px-1 text-[12px]" aria-label="Pieza" />
                  </td>
                  <td className="px-2 py-1.5">
                    <input type="number" min={1} max={100} value={l.cantidad}
                      onChange={(e) => upd(i, { cantidad: Math.min(100, Math.max(1, Number(e.target.value) || 1)) })}
                      className="w-12 h-6 rounded border border-slate-200 px-1 text-[12px]" aria-label="Actos" />
                  </td>
                  <td className="px-2 py-1.5 text-right whitespace-nowrap">{eur(l.precio)}</td>
                  <td className="px-2 py-1.5 text-right">
                    <input type="number" min={0} max={100} value={Number(pct.toFixed(2))}
                      onChange={(e) => upd(i, { descuento: Math.min(100, Math.max(0, Number(e.target.value) || 0)), descuento_pct: true })}
                      className="w-16 h-6 rounded border border-slate-200 px-1 text-[12px] text-right" aria-label="Porcentaje de descuento" />
                  </td>
                  <td className="px-2 py-1.5 text-right whitespace-nowrap">{eur(bruto - importeLinea(l))}</td>
                  <td className="px-2 py-1.5 text-right whitespace-nowrap font-semibold">{eur(importeLinea(l))}</td>
                  <td className="px-1">
                    <button type="button" onClick={() => onChange(plan.filter((_, j) => j !== i))} aria-label="Quitar línea"
                      className="text-slate-300 hover:text-fuchsia-600"><X className="w-3.5 h-3.5" /></button>
                  </td>
                </tr>
              );
            })}
          </tbody>
          <tfoot>
            <tr className="bg-sky-50 text-sky-800 font-semibold border-t border-sky-200">
              <td colSpan={9} className="px-2 py-1.5 text-right">Totales: {plan.length} {plan.length === 1 ? "acto" : "actos"}</td>
              <td className="px-2 py-1.5 text-right whitespace-nowrap">{eur(total)}</td><td />
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}
