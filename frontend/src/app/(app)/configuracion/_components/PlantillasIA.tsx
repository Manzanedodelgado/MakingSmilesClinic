"use client";
/**
 * Config · IA's · Plantillas WhatsApp — CRUD sobre la tabla `plantillas_mensaje`
 * (endpoints /comunicacion/plantillas). El `disparador` enlaza la plantilla con el
 * motor de automatización (recordatorios/recalls). Fuente de verdad única.
 */
import { useEffect, useState } from "react";
import { X, MessageSquare, Plus, Save, Trash2, Search } from "lucide-react";
import { api } from "@/shared/lib/api";
import { ClinicalCard, SectionHeader, ClinicalButton, INPUT, LABEL, SELECT, TEXTAREA, EMPTY } from "@/shared/components";
import { errMsg } from "@/shared/lib/errores";

type Plantilla = { id?: number; nombre: string; cuerpo: string; disparador: string };
// Disparadores que entiende el motor de automatización (backend automatizacion_service).
const DISPARADORES: [string, string][] = [
  ["", "Sin disparador (manual)"],
  ["recordatorio_24h", "Recordatorio 24h antes"],
  ["recordatorio_hoy", "Recordatorio el mismo día"],
  ["recall_pendiente", "Recall / revisión pendiente"],
];
const dispLabel = (d: string) => DISPARADORES.find(([k]) => k === d)?.[1] ?? "Manual";

export function PlantillasIA() {
  const [lista, setLista] = useState<Plantilla[]>([]);
  const [search, setSearch] = useState("");
  const [sel, setSel] = useState<number | "nuevo" | null>(null);
  const [draft, setDraft] = useState<Plantilla>({ nombre: "", cuerpo: "", disparador: "" });
  const [msg, setMsg] = useState<{ t: string; e?: boolean }>({ t: "" });
  const flash = (t: string, e = false) => { setMsg({ t, e }); setTimeout(() => setMsg({ t: "" }), 3000); };

  async function load() {
    try { const x = await api.get<{ data: Plantilla[] }>("/comunicacion/plantillas"); setLista(x.data); }
    catch (e) { flash(errMsg(e), true); }
  }
  useEffect(() => { load(); }, []);

  const filtrada = lista.filter((p) => !search || `${p.nombre} ${dispLabel(p.disparador)}`.toLowerCase().includes(search.toLowerCase()));

  async function guardar() {
    if (!draft.nombre.trim()) { flash("El nombre es obligatorio", true); return; }
    try { await api.put("/comunicacion/plantillas", draft); flash("Guardado ✓"); setSel(null); load(); }
    catch (e) { flash(errMsg(e), true); }
  }
  async function borrar(p: Plantilla) {
    if (!p.id) { setSel(null); return; }
    try { await api.del(`/comunicacion/plantillas/${p.id}`); flash("Borrada ✓"); setSel(null); load(); }
    catch (e) { flash(errMsg(e), true); }
  }

  return (
    <div className="flex-1">
      {msg.t && <div className={`fixed top-14 right-6 z-50 px-4 py-2.5 rounded-sm text-[12px] font-semibold shadow-lg ${msg.e ? "bg-[#C026D3] text-white" : "bg-[#2DD9C3] text-[#1500A0]"}`}>{msg.t}</div>}

      <div className="grid grid-cols-3 gap-2.5">
        <ClinicalCard noPadding>
          <div className="flex items-center justify-between px-3 py-2 border-b border-[#e5e7eb] bg-[#FFFFFF]">
            <SectionHeader title="Plantillas WhatsApp" icon={MessageSquare} className="mb-0 pb-0 border-0" />
            <ClinicalButton variant="nuevo" icon={Plus} size="sm" onClick={() => { setSel("nuevo"); setDraft({ nombre: "", cuerpo: "", disparador: "" }); }}>Nueva</ClinicalButton>
          </div>
          <div className="flex items-center gap-2 px-3 py-2 border-b border-[#e5e7eb]">
            <Search className="w-3.5 h-3.5 text-[#7f8c8d] shrink-0" />
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Buscar plantilla…" className="text-[12px] outline-none bg-transparent w-full" />
            {search && (
              <button type="button" onClick={() => setSearch("")} className="shrink-0 text-[#7f8c8d] hover:text-[#C026D3]">
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
          <div className="overflow-y-auto max-h-[calc(100vh-260px)]">
            {filtrada.map((p, i) => (
              <div key={p.id ?? i} onClick={() => { setSel(p.id ?? i); setDraft({ ...p }); }} className={`px-3 py-2 border-b border-[#e5e7eb] cursor-pointer ${sel === (p.id ?? i) ? "bg-[#FFFFFF]" : "hover:bg-[#E6EDFF]"}`}>
                <div className="text-[12px] text-[#1500A0] truncate">{p.nombre}</div>
                <div className="text-[10px] text-[#7f8c8d] uppercase">{dispLabel(p.disparador)}</div>
              </div>
            ))}
            {filtrada.length === 0 && <div className="px-3 py-6 text-center"><span className={EMPTY}>Sin plantillas</span></div>}
          </div>
        </ClinicalCard>

        <div className="col-span-2">
          {sel === null ? (
            <ClinicalCard><div className="py-12 text-center"><span className={EMPTY}>Selecciona una plantilla o crea una nueva</span></div></ClinicalCard>
          ) : (
            <ClinicalCard>
              <SectionHeader title={sel === "nuevo" ? "Nueva plantilla" : draft.nombre || "Plantilla"} icon={MessageSquare}
                action={<div className="flex items-center gap-2">
                  {sel !== "nuevo" && <ClinicalButton variant="secondary" size="sm" icon={Trash2} onClick={() => borrar(draft)}>Borrar</ClinicalButton>}
                  <ClinicalButton variant="save" size="sm" icon={Save} onClick={guardar}>Guardar</ClinicalButton>
                </div>} />
              <div className="grid grid-cols-2 gap-3 mb-3">
                <div><label className={LABEL}>Nombre</label><input value={draft.nombre} onChange={(e) => setDraft({ ...draft, nombre: e.target.value })} className={INPUT} /></div>
                <div><label className={LABEL}>Disparador (automatización)</label>
                  <select value={draft.disparador} onChange={(e) => setDraft({ ...draft, disparador: e.target.value })} className={SELECT}>
                    {DISPARADORES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                  </select>
                </div>
              </div>
              <div><label className={LABEL}>Cuerpo del mensaje</label>
                <textarea value={draft.cuerpo} rows={6} placeholder="Hola {{nombre}}, te recordamos tu cita el {{fecha}} a las {{hora}}. ¿Confirmas?" onChange={(e) => setDraft({ ...draft, cuerpo: e.target.value })} className={TEXTAREA} />
                <p className="text-[10px] text-[#7f8c8d] mt-1">Variables: <code className="font-mono text-[#1500A0]">{"{{nombre}}"}</code>, <code className="font-mono text-[#1500A0]">{"{{fecha}}"}</code>, <code className="font-mono text-[#1500A0]">{"{{hora}}"}</code>, <code className="font-mono text-[#1500A0]">{"{{clinica}}"}</code>.</p>
              </div>
            </ClinicalCard>
          )}
        </div>
      </div>
    </div>
  );
}
