"use client";
/* Config → Admin → Plantillas de presupuesto (presupuestos prediseñados).
   CRUD de plantillas: título + categoría + notas + líneas de tratamiento. Origen GELITE
   PresuTipo/PresuTipoTto. Se cargan en un presupuesto nuevo desde el editor ("Cargar plantilla"). */
import { useEffect, useMemo, useRef, useState } from "react";
import { Loader2, ChevronUp, ChevronDown, Save, Plus, Trash2, Power, Search, LayoutTemplate } from "lucide-react";
import { api } from "@/shared/lib/api";
import { LABEL, DESC, INPUT, SELECT, TEXTAREA, ClinicalButton } from "@/shared/components";
import { ZonaEditor, scopeDeCatalogo, valorInicialAmbito } from "@/features/patients/components/AmbitoPicker";
import { iconoTratamiento } from "@/shared/lib/iconoTratamiento";

type TratBusca = { id: number; codigo: string | null; nombre: string; tipo_actuacion: string | null; es_mensualidad?: boolean };
type PredLinea = { tratamiento_id: number; nombre: string; codigo: string | null; tipo_actuacion: string | null; es_mensualidad: boolean; pieza: string; zona_boca: string | null; precio: number | null; cantidad: number; descuento: number; descuento_pct: boolean; orden: number };
type PredAdmin = { id: number; titulo: string; categoria: string | null; notas: string | null; activo: boolean; lineas: PredLinea[] };
type Draft = { id?: number; titulo: string; categoria: string; notas: string; activo: boolean; lineas: PredLinea[] };

const draftDe = (p: PredAdmin): Draft => ({ id: p.id, titulo: p.titulo, categoria: p.categoria ?? "", notas: p.notas ?? "", activo: p.activo, lineas: p.lineas.map((l) => ({ ...l, pieza: l.pieza ?? "", zona_boca: l.zona_boca ?? null, precio: l.precio ?? null, cantidad: l.cantidad ?? 1, descuento: l.descuento ?? 0, descuento_pct: l.descuento_pct ?? false, es_mensualidad: l.es_mensualidad ?? false })) });
const draftNuevo = (): Draft => ({ titulo: "", categoria: "", notas: "", activo: true, lineas: [] });

// Buscador de tratamientos (typeahead) para añadir líneas a la plantilla.
function BuscadorTrat({ onPick }: { onPick: (t: TratBusca) => void }) {
  const [q, setQ] = useState(""); const [res, setRes] = useState<TratBusca[]>([]); const [open, setOpen] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    if (q.trim().length < 2) { setRes([]); return; }
    timer.current = setTimeout(async () => {
      try { const r = await api.get<{ tratamientos: TratBusca[] }>(`/configuracion/admin/predisenados-tratamientos?q=${encodeURIComponent(q.trim())}`); setRes(r.tratamientos); setOpen(true); } catch { setRes([]); }
    }, 250);
    return () => { if (timer.current) clearTimeout(timer.current); };
  }, [q]);
  return (
    <div className="relative flex-1">
      <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Añadir tratamiento del catálogo…"
        className="w-full border border-[#e5e7eb] rounded-sm pl-7 pr-2 py-1.5 text-[12px] outline-none focus:border-[#1ca0d1]" />
      {open && res.length > 0 && (
        <div className="absolute z-30 left-0 right-0 top-full mt-0.5 max-h-60 overflow-y-auto bg-white border border-[#e5e7eb] rounded-sm shadow-lg">
          {res.map((t) => (
            <button key={t.id} onClick={() => { onPick(t); setQ(""); setRes([]); setOpen(false); }}
              className="w-full flex items-center gap-2 px-2 py-1.5 text-left hover:bg-[#E6EDFF] text-[12px]">
              <span className="font-mono text-[10px] text-[#1500A0] bg-[#FFFFFF] px-1 rounded-sm shrink-0">{t.codigo}</span>
              <span className="text-[#333333] flex-1 truncate">{t.nombre}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function ConfigPresupuestos() {
  const [list, setList] = useState<PredAdmin[]>([]);
  const [cats, setCats] = useState<string[]>([]);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ t: string; e?: boolean }>({ t: "" });
  const flash = (t: string, e = false) => { setMsg({ t, e }); setTimeout(() => setMsg({ t: "" }), 3000); };

  const cargar = async (selId?: number) => {
    const d = await api.get<{ categorias: string[]; predisenados: PredAdmin[] }>("/configuracion/admin/presupuestos-predisenados");
    setCats(d.categorias || []); setList(d.predisenados || []);
    if (selId != null) { const p = d.predisenados.find((x) => x.id === selId); if (p) setDraft(draftDe(p)); }
    return d.predisenados;
  };
  useEffect(() => { (async () => { try { await cargar(); } catch { /* sin permiso */ } setLoading(false); })(); }, []);

  // Lista agrupada por categoría (orden de cats, "Otros"/sin categoría al final).
  const grupos = useMemo(() => {
    const g: Record<string, PredAdmin[]> = {};
    list.forEach((p) => { (g[p.categoria || "Otros"] ??= []).push(p); });
    const orden = [...cats]; if (!orden.includes("Otros")) orden.push("Otros");
    return Object.entries(g).sort((a, b) => (orden.indexOf(a[0]) + 1 || 99) - (orden.indexOf(b[0]) + 1 || 99));
  }, [list, cats]);

  const updLinea = (i: number, p: Partial<PredLinea>) => setDraft((d) => d ? { ...d, lineas: d.lineas.map((l, j) => j === i ? { ...l, ...p } : l) } : d);
  const delLinea = (i: number) => setDraft((d) => d ? { ...d, lineas: d.lineas.filter((_, j) => j !== i) } : d);
  const moveLinea = (i: number, dir: -1 | 1) => setDraft((d) => {
    if (!d) return d; const j = i + dir; if (j < 0 || j >= d.lineas.length) return d;
    const ls = [...d.lineas];[ls[i], ls[j]] = [ls[j], ls[i]]; return { ...d, lineas: ls.map((l, k) => ({ ...l, orden: k })) };
  });
  const addLinea = (t: TratBusca) => setDraft((d) => d ? { ...d, lineas: [...d.lineas, { tratamiento_id: t.id, nombre: t.nombre, codigo: t.codigo, tipo_actuacion: t.tipo_actuacion, es_mensualidad: !!t.es_mensualidad, ...valorInicialAmbito(scopeDeCatalogo(t.tipo_actuacion)), precio: null, cantidad: t.es_mensualidad ? 18 : 1, descuento: 0, descuento_pct: false, orden: d.lineas.length }] } : d);

  const guardar = async () => {
    if (!draft) return;
    if (!draft.titulo.trim()) { flash("Pon un título a la plantilla", true); return; }
    setSaving(true);
    const body = { titulo: draft.titulo.trim(), categoria: draft.categoria || null, notas: draft.notas || null, activo: draft.activo, lineas: draft.lineas.map((l, i) => ({ tratamiento_id: l.tratamiento_id, pieza: l.pieza || null, zona_boca: l.zona_boca, precio: l.precio, cantidad: l.cantidad || 1, descuento: l.descuento || 0, descuento_pct: l.descuento_pct, orden: i })) };
    try {
      if (draft.id) { await api.put(`/configuracion/admin/presupuestos-predisenados/${draft.id}`, body); await cargar(draft.id); flash("Plantilla guardada ✓"); }
      else { const r = await api.post<{ id: number }>("/configuracion/admin/presupuestos-predisenados", body); await cargar(r.id); flash("Plantilla creada ✓"); }
    } catch { flash("Error al guardar", true); } finally { setSaving(false); }
  };
  const borrar = async (id?: number) => {
    if (!id) { setDraft(null); return; }
    if (!window.confirm("¿Borrar esta plantilla? No afecta a presupuestos ya creados.")) return;
    try { await api.del(`/configuracion/admin/presupuestos-predisenados/${id}`); await cargar(); setDraft(null); flash("Plantilla borrada"); }
    catch { flash("No se pudo borrar", true); }
  };
  const toggleActivo = async (p: PredAdmin) => {
    try { await api.put(`/configuracion/admin/presupuestos-predisenados/${p.id}`, { titulo: p.titulo, categoria: p.categoria, notas: p.notas, activo: !p.activo, lineas: p.lineas.map((l, i) => ({ tratamiento_id: l.tratamiento_id, pieza: l.pieza ?? null, zona_boca: l.zona_boca ?? null, precio: l.precio ?? null, cantidad: l.cantidad ?? 1, descuento: l.descuento ?? 0, descuento_pct: l.descuento_pct ?? false, orden: i })) }); await cargar(draft?.id); }
    catch { flash("No se pudo cambiar", true); }
  };

  if (loading) return <div className="flex items-center justify-center py-20"><Loader2 className="w-6 h-6 text-[#1ca0d1] animate-spin" /></div>;

  return (
    <div className="flex flex-col gap-2.5">
      {msg.t && <div className={`fixed top-14 right-6 z-50 px-4 py-2.5 rounded-sm font-semibold text-[12px] shadow-lg ${msg.e ? "bg-[#C026D3] text-white" : "bg-[#2DD9C3] text-[#1500A0]"}`}>{msg.t}</div>}
      <p className={DESC}>Plantillas de presupuesto (prediseñados): un título, una categoría y un conjunto de tratamientos. En el editor de un presupuesto nuevo se cargan con <b>«Cargar plantilla»</b>, que vuelca sus líneas con el precio de la tarifa del paciente.</p>

      <div className="flex gap-3 items-start">
        {/* Lista por categoría + nueva */}
        <div className="w-64 shrink-0 flex flex-col gap-1.5">
          <div className="flex flex-col gap-2 border border-[#e5e7eb] rounded-sm p-1.5 bg-white max-h-[560px] overflow-y-auto">
            {grupos.map(([cat, ps]) => (
              <div key={cat}>
                <div className="px-1.5 py-1 text-[10px] uppercase tracking-wide text-[#1ca0d1] font-semibold">{cat}</div>
                {ps.map((p) => (
                  <div key={p.id} className="group flex items-center gap-1 rounded-sm" style={{ background: draft?.id === p.id ? "#1500A0" : "transparent" }}>
                    <button onClick={() => setDraft(draftDe(p))} className="flex-1 min-w-0 text-left px-2 py-1.5 rounded-sm text-[12px] truncate" style={{ color: draft?.id === p.id ? "#fff" : p.activo ? "#333" : "#9ca3af" }}>
                      {p.titulo}<span className="text-[10px] opacity-60"> · {p.lineas.length}</span>{!p.activo && " · off"}
                    </button>
                    <div className="flex items-center pr-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button title={p.activo ? "Desactivar" : "Activar"} onClick={() => toggleActivo(p)} className="p-1" style={{ color: draft?.id === p.id ? "#fff" : "#7f8c8d" }}><Power className="w-3 h-3" /></button>
                      <button title="Borrar" onClick={() => borrar(p.id)} className="p-1 text-[#C026D3]"><Trash2 className="w-3 h-3" /></button>
                    </div>
                  </div>
                ))}
              </div>
            ))}
            {list.length === 0 && <p className="px-2 py-3 text-[11px] text-slate-400 italic">Sin plantillas todavía.</p>}
          </div>
          <ClinicalButton variant="nuevo" icon={Plus} onClick={() => setDraft(draftNuevo())}>Nueva plantilla</ClinicalButton>
        </div>

        {/* Editor */}
        <div className="flex-1 min-w-0 border border-[#e5e7eb] rounded-sm bg-white">
          {!draft ? (
            <p className="text-[12px] text-slate-400 italic p-6 text-center">Selecciona una plantilla de la lista o crea una nueva.</p>
          ) : (
            <>
              <div className="bg-[#1500A0] px-3 py-2 flex items-center gap-2">
                <LayoutTemplate className="w-4 h-4 text-white" />
                <span className="text-white font-semibold text-[12px] uppercase tracking-wide flex-1">{draft.id ? "Editar plantilla" : "Nueva plantilla"}</span>
                <button onClick={guardar} disabled={saving} title="Guardar" className="flex items-center gap-1 text-[11px] font-semibold bg-[#2DD9C3] hover:bg-[#20BEAB] text-[#1500A0] px-2 py-1 rounded-sm disabled:opacity-50">{saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <><Save className="w-3.5 h-3.5" /> Guardar</>}</button>
                {draft.id && <button onClick={() => borrar(draft.id)} title="Borrar" className="text-white/80 hover:text-[#F3CDF8]"><Trash2 className="w-4 h-4" /></button>}
              </div>
              <div className="p-3 flex flex-col gap-3">
                <div className="flex items-end gap-3">
                  <div className="flex-1 min-w-0"><label className={LABEL}>Título de la plantilla</label>
                    <input className={INPUT} value={draft.titulo} placeholder="Ej: Implante titanio con corona de zirconio" onChange={(e) => setDraft({ ...draft, titulo: e.target.value })} /></div>
                  <div className="w-56 shrink-0"><label className={LABEL}>Categoría</label>
                    <select className={SELECT} value={draft.categoria} onChange={(e) => setDraft({ ...draft, categoria: e.target.value })}>
                      <option value="">— Sin categoría —</option>
                      {cats.map((c) => <option key={c} value={c}>{c}</option>)}
                    </select>
                  </div>
                </div>
                <div><label className={LABEL}>Notas (opcional)</label>
                  <textarea rows={2} className={TEXTAREA} value={draft.notas} placeholder="Condiciones, observaciones de la plantilla…" onChange={(e) => setDraft({ ...draft, notas: e.target.value })} /></div>

                {/* Líneas */}
                <div>
                  <label className={LABEL}>Tratamientos de la plantilla</label>
                  {/* Líneas como en el desglose: Zona · Tratamiento · Uds/Mens · Precio · Dto · acciones. */}
                  <div className="border border-[#e5e7eb] rounded-sm overflow-hidden">
                    <div className="grid grid-cols-[140px_1fr_52px_64px_78px_56px] gap-1 px-2 py-1 bg-[#FFFFFF] text-[10px] uppercase tracking-wide text-[#1ca0d1] font-semibold">
                      <span className="px-1">Zona</span><span className="px-1">Tratamiento</span><span className="text-center" title="Unidades · en mensualidades = nº de mensualidades">Uds</span><span className="text-right px-1">Precio</span><span className="text-right px-1">Dto</span><span />
                    </div>
                    <div className="max-h-[300px] overflow-y-auto divide-y divide-[#f0f2f5]">
                      {draft.lineas.map((l, i) => (
                        <div key={i} className="grid grid-cols-[140px_1fr_52px_64px_78px_56px] gap-1 px-2 py-1 items-center">
                          <ZonaEditor pieza={l.pieza} zona_boca={l.zona_boca} lockScope={scopeDeCatalogo(l.tipo_actuacion)} onChange={(p) => updLinea(i, p)} />
                          <span className="flex items-center gap-1.5 text-[12px] text-[#333333] min-w-0" title={l.nombre}>
                            {/* eslint-disable-next-line @next/next/no-img-element */}
                            <img src={iconoTratamiento(l.nombre)} alt="" className="w-4 h-4 shrink-0" />
                            <span className="truncate">{l.nombre}</span>
                            {l.es_mensualidad && <span className="text-[9px] font-semibold text-[#7C3AED] bg-[#FFFFFF] border border-[#DDD6FE] rounded-sm px-1 shrink-0">mens.</span>}
                          </span>
                          {/* Uds: en mensualidad = nº de mensualidades (editable, def. 18); si no, 1 */}
                          {l.es_mensualidad ? (
                            <input type="number" min={1} step={1} value={l.cantidad} title="Nº de mensualidades (fases)"
                              onChange={(e) => updLinea(i, { cantidad: Math.max(1, Math.floor(Number(e.target.value) || 1)) })}
                              className="w-full border border-[#e5e7eb] hover:border-[#1ca0d1] focus:border-[#1ca0d1] rounded-sm px-1 py-0.5 text-[11px] text-center outline-none text-[#1500A0]" />
                          ) : <span className="text-center text-[11px] text-slate-400">1</span>}
                          <input type="number" step="0.01" value={l.precio ?? ""} placeholder="tarifa" title="Precio por unidad (vacío = tarifa del paciente)"
                            onChange={(e) => updLinea(i, { precio: e.target.value === "" ? null : Number(e.target.value) || 0 })}
                            className="w-full border border-transparent hover:border-[#e5e7eb] focus:border-[#1ca0d1] rounded-sm px-1 py-0.5 text-[11px] text-right outline-none text-[#1500A0]" />
                          <div className="flex items-center gap-0.5 min-w-0">
                            <input type="number" step="0.01" min={0} value={l.descuento} title="Descuento por línea (€ o %)"
                              onChange={(e) => updLinea(i, { descuento: Math.max(0, Number(e.target.value) || 0) })}
                              className="w-full min-w-0 border border-transparent hover:border-[#e5e7eb] focus:border-[#1ca0d1] rounded-sm px-1 py-0.5 text-[11px] text-right outline-none text-[#0F8C7D]" />
                            <button type="button" title="Cambiar € / %" onClick={() => updLinea(i, { descuento_pct: !l.descuento_pct })}
                              className="shrink-0 w-5 text-[10px] font-semibold rounded-sm border border-[#e5e7eb] text-[#0F8C7D] hover:bg-[#E6EDFF]">{l.descuento_pct ? "%" : "€"}</button>
                          </div>
                          <div className="flex items-center justify-end gap-0.5">
                            <button onClick={() => moveLinea(i, -1)} disabled={i === 0} className="text-slate-400 hover:text-[#1500A0] disabled:opacity-30"><ChevronUp className="w-3.5 h-3.5" /></button>
                            <button onClick={() => moveLinea(i, 1)} disabled={i === draft.lineas.length - 1} className="text-slate-400 hover:text-[#1500A0] disabled:opacity-30"><ChevronDown className="w-3.5 h-3.5" /></button>
                            <button onClick={() => delLinea(i)} className="text-slate-400 hover:text-[#C026D3]"><Trash2 className="w-3.5 h-3.5" /></button>
                          </div>
                        </div>
                      ))}
                      {draft.lineas.length === 0 && <p className="px-2 py-3 text-[11px] text-slate-400 italic">Sin tratamientos. Añade abajo.</p>}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 mt-1.5">
                    <Plus className="w-3.5 h-3.5 text-[#1ca0d1]" />
                    <BuscadorTrat onPick={addLinea} />
                  </div>
                </div>
                <label className="flex items-center gap-2 text-[12px] text-[#333] cursor-pointer w-fit">
                  <input type="checkbox" checked={draft.activo} onChange={(e) => setDraft({ ...draft, activo: e.target.checked })} /> Activa (visible en «Cargar plantilla»)
                </label>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
