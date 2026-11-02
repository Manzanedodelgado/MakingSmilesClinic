"use client";
import { useEffect, useMemo, useState } from "react";
import { Loader2, Save, Code2, ListChecks, RotateCcw, Plus, Copy, Trash2, Power } from "lucide-react";
import { api, API_BASE } from "@/shared/lib/api";
import { LABEL, DESC, INPUT, SELECT, TEXTAREA, ClinicalButton } from "@/shared/components";
import { DOC_DEFAULTS, CAMPOS_DEFAULT, SAMPLE, renderDoc, type CampoDef } from "./documentTemplates";

/* Config → Admin → Documentos. Réplica de SmilePro. Plantillas en el cerebro
   (configuraciones · documentos.plantillas). Cabecera del preview desde nuestro Centro. */

type Tpl = { nombre: string; baseId: string; html: string; campos: Record<string, string>; activo: boolean; sistema: boolean; orden: number };
const camposDefsFor = (baseId: string): CampoDef[] => DOC_DEFAULTS.find((d) => d.id === baseId)?.campos ?? [];
const newId = () => `doc_${Date.now().toString(36)}${Math.floor(Math.random() * 1e4).toString(36)}`;

// soloBase: si se pasa, la pantalla se acota a un tipo (Consentimientos, Recomendaciones…) y
// oculta el selector de tipo base. Sin prop (Diseño) muestra TODAS las plantillas.
export function ConfigDocumentos({ soloBase }: { soloBase?: string } = {}) {
  const baseInicial = soloBase ?? DOC_DEFAULTS[0].id;
  const [store, setStore] = useState<Record<string, Tpl>>({});
  const [realClinic, setRealClinic] = useState<Record<string, string>>({});
  const [sel, setSel] = useState("");
  const [tab, setTab] = useState<"campos" | "html">("campos");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ t: string; e?: boolean }>({ t: "" });
  const flash = (t: string, e = false) => { setMsg({ t, e }); setTimeout(() => setMsg({ t: "" }), 3000); };

  useEffect(() => {
    (async () => {
      try {
        const { plantillas } = await api.get<{ plantillas: Record<string, Partial<Tpl>> }>("/configuracion/admin/documentos");
        const saved = plantillas || {};
        const init: Record<string, Tpl> = {};
        DOC_DEFAULTS.forEach((d, i) => {
          const s = saved[d.id] ?? {};
          init[d.id] = { nombre: s.nombre ?? d.label, baseId: d.id, html: s.html ?? d.html, campos: { ...CAMPOS_DEFAULT[d.id], ...(s.campos ?? {}) }, activo: s.activo ?? true, sistema: true, orden: s.orden ?? i };
        });
        for (const [id, s] of Object.entries(saved)) {
          if (init[id]) continue;
          const baseId = s.baseId && DOC_DEFAULTS.some((d) => d.id === s.baseId) ? s.baseId : DOC_DEFAULTS[0].id;
          init[id] = { nombre: s.nombre ?? "Documento", baseId, html: s.html ?? DOC_DEFAULTS.find((d) => d.id === baseId)!.html, campos: { ...CAMPOS_DEFAULT[baseId], ...(s.campos ?? {}) }, activo: s.activo ?? true, sistema: false, orden: s.orden ?? 100 };
        }
        setStore(init); setSel(baseInicial);
      } catch { /* sin permiso / error */ }
      try {
        const d = await api.get<{ centro: Record<string, unknown>; razon_social: Record<string, unknown> | null }>("/configuracion/centro");
        const c = d.centro, r = d.razon_social; const rc: Record<string, string> = {};
        const S = (v: unknown) => (v == null ? "" : String(v));
        const put = (k: string, v: string) => { if (v) rc[k] = v; };
        put("clinicName", S(c?.nombre));
        put("clinicFiscal", r ? `${S(r.nombre)}${r.cif ? ` · ${S(r.cif)}` : ""}` : "");
        put("clinicDir", [c?.direccion, c?.cp, c?.poblacion, c?.provincia].map(S).filter(Boolean).join(", "));
        put("clinicTel", [c?.telefono, c?.telefono_movil].map(S).filter(Boolean).join(" · "));
        put("clinicEmail", S(c?.email));
        put("clinicWeb", c?.web ? `<br>${S(c.web)}` : "");
        if (c?.logo_url) rc.clinicLogo = `<img src="${API_BASE}${S(c.logo_url)}" style="height:36px;vertical-align:middle;margin-right:10px">`;
        if (r?.sello_url) rc.sello = `<img src="${API_BASE}${S(r.sello_url)}" style="height:64px;opacity:.9">`;
        setRealClinic(rc);
      } catch { /* preview con datos de muestra */ }
      setLoading(false);
    })();
  }, []);

  const ordered = useMemo(() => Object.entries(store)
    .filter(([, t]) => !soloBase || t.baseId === soloBase)
    .sort((a, b) => a[1].orden - b[1].orden), [store, soloBase]);
  const cur = store[sel];
  const def = cur ? DOC_DEFAULTS.find((d) => d.id === cur.baseId) : null;
  const preview = useMemo(() => (cur ? renderDoc(cur.html, cur.campos, { ...SAMPLE, ...(def?.sample ?? {}), ...realClinic }) : ""), [cur, def, realClinic]);

  const patch = (id: string, p: Partial<Tpl>) => setStore((s) => ({ ...s, [id]: { ...s[id], ...p } }));
  const setCampo = (k: string, v: string) => patch(sel, { campos: { ...cur!.campos, [k]: v } });
  const setHtml = (v: string) => patch(sel, { html: v });
  const resetDoc = () => { if (cur && def) patch(sel, { html: def.html, campos: { ...CAMPOS_DEFAULT[cur.baseId] } }); };
  const crear = () => {
    const baseId = baseInicial; const d = DOC_DEFAULTS.find((x) => x.id === baseId)!; const id = newId();
    const mo = Math.max(0, ...Object.values(store).map((t) => t.orden));
    patch(id, { nombre: "Documento nuevo", baseId, html: d.html, campos: { ...CAMPOS_DEFAULT[baseId] }, activo: true, sistema: false, orden: mo + 1 }); setSel(id);
  };
  const duplicar = (id: string) => {
    const src = store[id]; if (!src) return; const nid = newId();
    const mo = Math.max(0, ...Object.values(store).map((t) => t.orden));
    patch(nid, { ...src, nombre: `${src.nombre} (copia)`, sistema: false, orden: mo + 1 }); setSel(nid);
  };
  const borrar = (id: string) => { if (store[id]?.sistema) return; setStore((s) => { const n = { ...s }; delete n[id]; return n; }); if (sel === id) setSel(baseInicial); };
  const save = async () => {
    setSaving(true);
    try {
      const plantillas = Object.fromEntries(Object.entries(store).map(([id, v]) => [id, { nombre: v.nombre, baseId: v.baseId, html: v.html, campos: v.campos, activo: v.activo, sistema: v.sistema, orden: v.orden }]));
      await api.put("/configuracion/admin/documentos", { plantillas }); flash("Documentos guardados ✓");
    } catch { flash("Error al guardar", true); } finally { setSaving(false); }
  };

  if (loading || !cur || !def) return <div className="flex items-center justify-center py-20"><Loader2 className="w-6 h-6 text-[#1ca0d1] animate-spin" /></div>;

  return (
    <div className="flex flex-col gap-2.5">
      {msg.t && <div className={`fixed top-14 right-6 z-50 px-4 py-2.5 rounded-sm font-semibold text-[12px] shadow-lg ${msg.e ? "bg-[#C026D3] text-white" : "bg-[#2DD9C3] text-[#1500A0]"}`}>{msg.t}</div>}
      <div className="flex items-center justify-end">
        <ClinicalButton variant="save" icon={saving ? Loader2 : Save} onClick={save} disabled={saving}>
          {saving ? "Guardando…" : "Guardar"}
        </ClinicalButton>
      </div>
      <p className={DESC}>Plantillas de los documentos que recibe el paciente o el doctor. Crea, duplica, renombra o desactiva tipos. Los personalizados derivan de un tipo base. Edita los textos en <b>Campos</b> o toda la maqueta en <b>HTML avanzado</b>. La cabecera de la clínica se toma de Config → Centro.</p>

      <div className="flex gap-3 items-start">
        {/* lista + CRUD */}
        <div className="w-56 shrink-0 flex flex-col gap-1.5">
          <div className="flex flex-col gap-1 border border-[#e5e7eb] rounded-sm p-1.5 bg-white">
            {ordered.map(([id, t]) => (
              <div key={id} className="group flex items-center gap-1 rounded-sm" style={{ background: sel === id ? "#1500A0" : "transparent" }}>
                <button onClick={() => setSel(id)} className="flex-1 min-w-0 text-left px-2.5 py-1.5 rounded-sm text-[12px] truncate" style={{ color: sel === id ? "#fff" : t.activo ? "#1500A0" : "#7f8c8d" }}>{t.nombre}{!t.activo && " · off"}</button>
                <div className="flex items-center pr-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button title={t.activo ? "Desactivar" : "Activar"} onClick={() => patch(id, { activo: !t.activo })} className="p-1" style={{ color: sel === id ? "#fff" : "#7f8c8d" }}><Power className="w-3 h-3" /></button>
                  <button title="Duplicar" onClick={() => duplicar(id)} className="p-1" style={{ color: sel === id ? "#fff" : "#7f8c8d" }}><Copy className="w-3 h-3" /></button>
                  {!t.sistema && <button title="Borrar" onClick={() => borrar(id)} className="p-1 text-[#C026D3]"><Trash2 className="w-3 h-3" /></button>}
                </div>
              </div>
            ))}
          </div>
          <ClinicalButton variant="nuevo" icon={Plus} onClick={crear}>Nuevo documento</ClinicalButton>
        </div>

        {/* editor */}
        <div className="flex-1 min-w-0 border border-[#e5e7eb] rounded-sm bg-white">
          <div className="flex items-end gap-3 p-3 border-b border-[#e5e7eb]">
            <div className="flex-1 min-w-0"><label className={LABEL}>Nombre del documento</label><input className={INPUT} value={cur.nombre} onChange={(e) => patch(sel, { nombre: e.target.value })} /></div>
            {!soloBase && (
              <div className="w-52 shrink-0"><label className={LABEL}>Tipo base (datos){cur.sistema ? " · fijo" : ""}</label>
                <select className={SELECT} value={cur.baseId} disabled={cur.sistema} onChange={(e) => patch(sel, { baseId: e.target.value, campos: { ...CAMPOS_DEFAULT[e.target.value], ...cur.campos } })}>
                  {DOC_DEFAULTS.map((d) => <option key={d.id} value={d.id}>{d.label}</option>)}
                </select>
              </div>
            )}
          </div>
          <div className="flex border-b border-[#e5e7eb]">
            <button onClick={() => setTab("campos")} className={`flex items-center gap-1.5 px-3 py-2 text-[12px] font-semibold ${tab === "campos" ? "text-[#1500A0] border-b-2 border-[#1ca0d1]" : "text-[#7f8c8d]"}`}><ListChecks className="w-3.5 h-3.5" /> Campos</button>
            <button onClick={() => setTab("html")} className={`flex items-center gap-1.5 px-3 py-2 text-[12px] font-semibold ${tab === "html" ? "text-[#1500A0] border-b-2 border-[#1ca0d1]" : "text-[#7f8c8d]"}`}><Code2 className="w-3.5 h-3.5" /> HTML avanzado</button>
            <button onClick={resetDoc} title="Restaurar plantilla base" className="ml-auto flex items-center gap-1 px-3 py-2 text-[11px] text-[#7f8c8d] hover:text-[#C026D3]"><RotateCcw className="w-3 h-3" /> Restaurar</button>
          </div>
          <div className="p-3 max-h-[520px] overflow-y-auto">
            {tab === "campos" ? (
              <div className="flex flex-col gap-3">
                {camposDefsFor(cur.baseId).map((c) => (
                  <div key={c.key}><label className={LABEL}>{c.label}</label>
                    {c.multiline ? <textarea rows={3} className={TEXTAREA} value={cur.campos[c.key] ?? ""} onChange={(e) => setCampo(c.key, e.target.value)} />
                      : <input className={INPUT} value={cur.campos[c.key] ?? ""} onChange={(e) => setCampo(c.key, e.target.value)} />}
                  </div>
                ))}
              </div>
            ) : (
              <textarea spellCheck={false} className={`${TEXTAREA} font-mono text-[11px] leading-relaxed`} style={{ minHeight: 480 }} value={cur.html} onChange={(e) => setHtml(e.target.value)} />
            )}
          </div>
        </div>

        {/* vista previa */}
        <div className="w-[420px] shrink-0">
          <div className="text-[10px] font-bold text-[#7f8c8d] uppercase tracking-widest mb-1.5">Vista previa</div>
          <div className="border border-[#e5e7eb] rounded-sm overflow-hidden bg-[#FFFFFF]" style={{ height: 560 }}>
            <iframe title="preview" srcDoc={preview} sandbox="" style={{ width: 794, height: 1123, border: 0, transform: "scale(0.529)", transformOrigin: "top left", background: "#fff" }} />
          </div>
        </div>
      </div>
    </div>
  );
}
