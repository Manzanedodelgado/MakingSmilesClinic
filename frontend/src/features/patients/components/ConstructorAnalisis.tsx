"use client";
/**
 * CONSTRUCTOR DE ANÁLISIS CEFALOMÉTRICO A MEDIDA — el centro define sus propios puntos y fórmulas
 * (ángulos, distancias). Se guardan en /cefalometria/analisis y aparecen en el selector del trazador.
 */
import { useState, useEffect, useCallback } from "react";
import { Loader2, X, Wrench, Plus, Trash2, Save } from "lucide-react";
import { api } from "@/shared/lib/api";

type Landmark = { code: string; label: string };
type Tipo = "angulo3" | "lineas" | "distancia" | "perpendicular";
type Medida = { code: string; label: string; tipo: Tipo; puntos: string[]; norma?: number | null; sd?: number | null };
type Custom = { id: number; slug: string; nombre: string; landmarks: Landmark[]; medidas: Medida[] };

const TIPOS: { tipo: Tipo; label: string; n: number; ayuda: string }[] = [
  { tipo: "angulo3", label: "Ángulo (3 puntos)", n: 3, ayuda: "Vértice · lado 1 · lado 2" },
  { tipo: "lineas", label: "Ángulo entre 2 rectas (4 puntos)", n: 4, ayuda: "Recta A: p1·p2 · Recta B: p3·p4" },
  { tipo: "distancia", label: "Distancia (2 puntos, mm)", n: 2, ayuda: "Requiere calibración" },
  { tipo: "perpendicular", label: "Distancia punto→recta (3 puntos, mm)", n: 3, ayuda: "Punto · recta: p1·p2" },
];
const nDe = (t: Tipo) => TIPOS.find((x) => x.tipo === t)!.n;

export function ConstructorAnalisis({ onCerrar, onCambio }: { onCerrar?: () => void; onCambio?: () => void }) {
  const [existentes, setExistentes] = useState<Custom[]>([]);
  const [nombre, setNombre] = useState("");
  const [landmarks, setLandmarks] = useState<Landmark[]>([{ code: "", label: "" }]);
  const [medidas, setMedidas] = useState<Medida[]>([]);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(() => { api.get<Custom[]>("/cefalometria/analisis").then(setExistentes).catch(() => setExistentes([])); }, []);
  useEffect(() => { cargar(); }, [cargar]);

  const codes = landmarks.map((l) => l.code.trim()).filter(Boolean);
  const setLm = (i: number, k: keyof Landmark, v: string) => setLandmarks((p) => p.map((l, j) => (j === i ? { ...l, [k]: v } : l)));
  const setMed = (i: number, patch: Partial<Medida>) => setMedidas((p) => p.map((m, j) => (j === i ? { ...m, ...patch } : m)));

  const guardar = async () => {
    setError(null);
    if (!nombre.trim()) return setError("Ponle un nombre al análisis");
    if (codes.length < 2) return setError("Define al menos 2 puntos con código");
    if (medidas.length === 0) return setError("Añade al menos una medida");
    for (const m of medidas) {
      if (!m.code.trim() || !m.label.trim()) return setError("Cada medida necesita código y nombre");
      if (m.puntos.filter(Boolean).length !== nDe(m.tipo)) return setError(`«${m.label || m.code}» necesita ${nDe(m.tipo)} puntos`);
    }
    setGuardando(true);
    try {
      await api.post("/cefalometria/analisis", {
        nombre: nombre.trim(),
        landmarks: landmarks.filter((l) => l.code.trim()).map((l) => ({ code: l.code.trim(), label: l.label.trim() || l.code.trim() })),
        medidas: medidas.map((m) => ({ ...m, code: m.code.trim(), label: m.label.trim(), puntos: m.puntos.filter(Boolean) })),
      });
      setNombre(""); setLandmarks([{ code: "", label: "" }]); setMedidas([]);
      cargar(); onCambio?.();
    } catch (e) {
      setError(e instanceof Error ? e.message.slice(0, 160) : "No se pudo guardar");
    } finally { setGuardando(false); }
  };

  const borrar = async (id: number) => { if (confirm("¿Eliminar este análisis?")) { await api.del(`/cefalometria/analisis/${id}`); cargar(); onCambio?.(); } };

  return (
    <div className="flex flex-col h-full min-h-0 bg-white">
      <div className="flex items-center justify-between px-3 py-2 bg-[#1500A0] text-white shrink-0">
        <b className="text-[13px] uppercase tracking-wide flex items-center gap-2"><Wrench className="w-4 h-4" /> Análisis a medida</b>
        {onCerrar && <button type="button" onClick={onCerrar} className="text-white/80 hover:text-white cursor-pointer"><X className="w-4 h-4" /></button>}
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto p-3 flex flex-col gap-4">
        {existentes.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {existentes.map((c) => (
              <span key={c.id} className="inline-flex items-center gap-1 text-xs bg-white rounded-sm px-2 py-1">
                {c.nombre} <span className="text-slate-400">({c.medidas.length})</span>
                <button type="button" onClick={() => borrar(c.id)} className="text-slate-400 hover:text-[#C026D3] cursor-pointer"><Trash2 className="w-3 h-3" /></button>
              </span>
            ))}
          </div>
        )}

        <div>
          <label className="text-xs font-semibold text-slate-500">Nombre del análisis</label>
          <input value={nombre} onChange={(e) => setNombre(e.target.value)} placeholder="p. ej. Mi Steiner reducido"
            className="w-full text-sm border border-slate-300 rounded-sm px-2 py-1.5 mt-1" />
        </div>

        {/* Puntos */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs font-semibold text-slate-500">Puntos (landmarks)</span>
            <button type="button" onClick={() => setLandmarks((p) => [...p, { code: "", label: "" }])} className="text-xs text-[#013b82] flex items-center gap-0.5 cursor-pointer"><Plus className="w-3 h-3" /> punto</button>
          </div>
          <div className="flex flex-col gap-1">
            {landmarks.map((l, i) => (
              <div key={i} className="flex items-center gap-1.5">
                <input value={l.code} onChange={(e) => setLm(i, "code", e.target.value)} placeholder="Código" maxLength={6} className="w-20 text-xs border border-slate-300 rounded-sm px-1.5 py-1" />
                <input value={l.label} onChange={(e) => setLm(i, "label", e.target.value)} placeholder="Nombre del punto" className="flex-1 text-xs border border-slate-300 rounded-sm px-1.5 py-1" />
                {landmarks.length > 1 && <button type="button" onClick={() => setLandmarks((p) => p.filter((_, j) => j !== i))} className="text-slate-400 hover:text-[#C026D3] cursor-pointer"><Trash2 className="w-3.5 h-3.5" /></button>}
              </div>
            ))}
          </div>
        </div>

        {/* Medidas */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs font-semibold text-slate-500">Medidas (fórmulas)</span>
            <button type="button" onClick={() => setMedidas((p) => [...p, { code: "", label: "", tipo: "angulo3", puntos: [] }])} className="text-xs text-[#013b82] flex items-center gap-0.5 cursor-pointer"><Plus className="w-3 h-3" /> medida</button>
          </div>
          <div className="flex flex-col gap-2">
            {medidas.map((m, i) => (
              <div key={i} className="border border-slate-200 rounded-sm p-2 flex flex-col gap-1.5">
                <div className="flex items-center gap-1.5">
                  <input value={m.code} onChange={(e) => setMed(i, { code: e.target.value })} placeholder="Cód." maxLength={12} className="w-16 text-xs border border-slate-300 rounded-sm px-1.5 py-1" />
                  <input value={m.label} onChange={(e) => setMed(i, { label: e.target.value })} placeholder="Nombre de la medida" className="flex-1 text-xs border border-slate-300 rounded-sm px-1.5 py-1" />
                  <button type="button" onClick={() => setMedidas((p) => p.filter((_, j) => j !== i))} className="text-slate-400 hover:text-[#C026D3] cursor-pointer"><Trash2 className="w-3.5 h-3.5" /></button>
                </div>
                <select value={m.tipo} onChange={(e) => setMed(i, { tipo: e.target.value as Tipo, puntos: [] })} className="text-xs border border-slate-300 rounded-sm px-1.5 py-1 cursor-pointer">
                  {TIPOS.map((t) => <option key={t.tipo} value={t.tipo}>{t.label}</option>)}
                </select>
                <div className="text-[10px] text-slate-400">{TIPOS.find((t) => t.tipo === m.tipo)!.ayuda}</div>
                <div className="flex flex-wrap gap-1">
                  {Array.from({ length: nDe(m.tipo) }).map((_, k) => (
                    <select key={k} value={m.puntos[k] ?? ""} onChange={(e) => { const pts = [...m.puntos]; pts[k] = e.target.value; setMed(i, { puntos: pts }); }}
                      className="text-xs border border-slate-300 rounded-sm px-1 py-1 cursor-pointer">
                      <option value="">P{k + 1}</option>
                      {codes.map((c) => <option key={c} value={c}>{c}</option>)}
                    </select>
                  ))}
                  <input type="number" value={m.norma ?? ""} onChange={(e) => setMed(i, { norma: e.target.value === "" ? null : Number(e.target.value) })} placeholder="Norma" className="w-16 text-xs border border-slate-300 rounded-sm px-1.5 py-1" />
                  <input type="number" value={m.sd ?? ""} onChange={(e) => setMed(i, { sd: e.target.value === "" ? null : Number(e.target.value) })} placeholder="±SD" className="w-14 text-xs border border-slate-300 rounded-sm px-1.5 py-1" />
                </div>
              </div>
            ))}
          </div>
        </div>

        {error && <div className="text-xs text-[#A21CAF] bg-[#FFFFFF] rounded-sm px-3 py-2">{error}</div>}
      </div>

      <div className="p-2 border-t border-slate-100">
        <button type="button" onClick={guardar} disabled={guardando}
          className="w-full text-sm bg-[#013b82] text-white rounded-sm px-3 py-2 flex items-center justify-center gap-1.5 cursor-pointer disabled:opacity-50">
          {guardando ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} Guardar análisis
        </button>
      </div>
    </div>
  );
}
