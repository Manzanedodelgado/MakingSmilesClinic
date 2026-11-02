"use client";
/**
 * VISOR DICOM — navegación de cortes de una serie del PACS (Orthanc).
 *
 * Lista las series DICOM del paciente y permite recorrer los cortes (slider, prev/next y rueda del
 * ratón) sobre los renders que Orthanc ya expone. Cada corte se sirve por el proxy scopeado del
 * backend (guard anti-IDOR). No hace reconstrucción MPR/3D (eso requiere un motor de volumen).
 */
import { useState, useEffect, useCallback, useRef } from "react";
import { Loader2, ChevronLeft, ChevronRight, X, Layers, ScanSearch } from "lucide-react";
import { api, API_BASE } from "@/shared/lib/api";

type Serie = { series_id: string; modalidad: string; descripcion: string; fecha: string | null; instancias: string[] };

export function VisorDicom({ patientId, onCerrar }: { patientId: number; onCerrar?: () => void }) {
  const [series, setSeries] = useState<Serie[]>([]);
  const [sel, setSel] = useState(0);          // serie seleccionada
  const [idx, setIdx] = useState(0);          // corte actual
  const [loading, setLoading] = useState(false);
  const contRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setLoading(true);
    api.get<Serie[]>(`/pacientes/${patientId}/dicom/series`)
      .then((s) => { setSeries(s); setSel(0); setIdx(0); })
      .catch(() => setSeries([]))
      .finally(() => setLoading(false));
  }, [patientId]);

  const serie = series[sel];
  const total = serie?.instancias.length ?? 0;

  const mover = useCallback((delta: number) => {
    setIdx((i) => Math.max(0, Math.min(total - 1, i + delta)));
  }, [total]);

  // Rueda del ratón sobre el lienzo = cambiar de corte
  const onWheel = (e: React.WheelEvent) => { e.preventDefault(); mover(e.deltaY > 0 ? 1 : -1); };

  // Precarga del corte siguiente/anterior para fluidez
  useEffect(() => {
    if (!serie) return;
    [idx + 1, idx - 1].forEach((j) => {
      if (j >= 0 && j < total) { const im = new Image(); im.src = `${API_BASE}/pacientes/${patientId}/dicom/slice/${serie.instancias[j]}`; }
    });
  }, [idx, serie, total, patientId]);

  return (
    <div className="flex flex-col h-full min-h-0 bg-white">
      <div className="flex items-center justify-between px-3 py-2 bg-[#1500A0] text-white shrink-0">
        <b className="text-[13px] uppercase tracking-wide flex items-center gap-2"><Layers className="w-4 h-4" /> Visor DICOM · PACS</b>
        <div className="flex items-center gap-2">
          {series.length > 1 && (
            <select value={sel} onChange={(e) => { setSel(Number(e.target.value)); setIdx(0); }}
              className="text-xs bg-white/15 text-white rounded-sm px-1.5 py-1 cursor-pointer border border-white/20 max-w-[240px]">
              {series.map((s, i) => <option key={s.series_id} value={i} className="text-slate-800">{s.descripcion} · {s.modalidad}{s.fecha ? ` · ${s.fecha}` : ""}</option>)}
            </select>
          )}
          {onCerrar && <button type="button" onClick={onCerrar} className="text-white/80 hover:text-white cursor-pointer"><X className="w-4 h-4" /></button>}
        </div>
      </div>

      {loading ? (
        <div className="flex-1 grid place-items-center text-slate-400"><Loader2 className="w-6 h-6 animate-spin" /></div>
      ) : !serie ? (
        <div className="flex-1 grid place-items-center text-slate-400 text-sm">
          <div className="flex flex-col items-center gap-1"><ScanSearch className="w-7 h-7" />Sin estudios DICOM en el PACS para este paciente.</div>
        </div>
      ) : (
        <div className="flex-1 min-h-0 flex flex-col">
          <div className="px-3 py-1.5 text-xs text-slate-500 border-b border-slate-100 flex items-center justify-between">
            <span>{serie.descripcion} · {serie.modalidad}{serie.fecha ? ` · ${serie.fecha}` : ""}</span>
            <span className="font-semibold text-[#013b82]">Corte {idx + 1} / {total}</span>
          </div>
          <div ref={contRef} onWheel={onWheel} className="flex-1 min-h-0 bg-black grid place-items-center relative select-none">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img key={serie.instancias[idx]} src={`${API_BASE}/pacientes/${patientId}/dicom/slice/${serie.instancias[idx]}`}
              alt={`Corte ${idx + 1}`} className="max-w-full max-h-full object-contain" draggable={false} />
            <button type="button" onClick={() => mover(-1)} disabled={idx === 0}
              className="absolute left-2 top-1/2 -translate-y-1/2 bg-white/10 hover:bg-white/20 text-white rounded-full p-2 cursor-pointer disabled:opacity-30"><ChevronLeft className="w-5 h-5" /></button>
            <button type="button" onClick={() => mover(1)} disabled={idx >= total - 1}
              className="absolute right-2 top-1/2 -translate-y-1/2 bg-white/10 hover:bg-white/20 text-white rounded-full p-2 cursor-pointer disabled:opacity-30"><ChevronRight className="w-5 h-5" /></button>
          </div>
          <div className="px-3 py-2 border-t border-slate-100">
            <input type="range" min={0} max={Math.max(0, total - 1)} value={idx}
              onChange={(e) => setIdx(Number(e.target.value))} className="w-full cursor-pointer accent-[#1ca0d1]" />
            <div className="text-center text-[11px] text-slate-400 mt-0.5">Desplázate con la rueda del ratón o arrastra el control</div>
          </div>
        </div>
      )}
    </div>
  );
}
