"use client";
/**
 * Tab CASCABEL — portado del .37 (views/pacientes/tabs/Cascabel.tsx), 100% sobre la BBDD nueva.
 * Score de adherencia + historial de citas se calculan de `citas` (estado 5=asistió, 6=no-show).
 * Recordatorios/Consentimientos/Seguimiento van vacíos (sus tablas aún no tienen datos) y se
 * muestran honestamente como "sin registros". Paleta corporativa (teal/cian/navy, sin rojo/verde).
 */
import { useState, useEffect, useCallback } from "react";
import { Loader2, RefreshCw, AlertTriangle, CalendarClock } from "lucide-react";
import { patientService } from "../services/patientService";
import type { CascabelData, CitaCascabel } from "../types/patient";

const scoreColor = (s: number) => (s >= 80 ? "#2DD9C3" : s >= 50 ? "#1ca0d1" : "#1500A0");
const scoreLabel = (s: number) => (s >= 80 ? "Alta adherencia" : s >= 50 ? "Adherencia media" : "Baja adherencia");

// Color del punto del timeline según estado (sin rojo/verde puros).
const estadoDot: Record<string, string> = {
  Finalizada: "#2DD9C3", Fallada: "#C026D3", Anulada: "#c8d2dc", Cancelada: "#c8d2dc",
  Confirmada: "#1ca0d1", Planificada: "#1500A0",
};

function ScoreBadge({ score }: { score: number | null }) {
  if (score === null) return <span className="text-[12px] text-slate-400">Sin datos de asistencia</span>;
  const color = scoreColor(score);
  return (
    <div className="flex items-center gap-3">
      <div className="relative w-16 h-16 rounded-full flex items-center justify-center"
        style={{ background: `conic-gradient(${color} ${score * 3.6}deg, rgba(0,0,0,0.08) 0deg)` }}>
        <div className="w-11 h-11 rounded-full bg-white flex items-center justify-center">
          <span className="text-[13px] font-semibold" style={{ color }}>{score}%</span>
        </div>
      </div>
      <div>
        <p className="text-[12px] font-semibold" style={{ color }}>{scoreLabel(score)}</p>
        <p className="text-[11px] text-slate-400">Asistencia a citas</p>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="text-[11px] uppercase tracking-wider mb-2 pb-1 border-b text-[#1500A0]" style={{ borderColor: "rgba(1,59,130,0.15)" }}>
        {title}
      </h3>
      {children}
    </section>
  );
}

function Timeline({ citas }: { citas: CitaCascabel[] }) {
  if (citas.length === 0) return <p className="text-[12px] text-slate-400 italic py-2">Sin citas registradas</p>;
  const fmt = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString("es-ES") : "—");
  return (
    <div className="flex flex-col">
      {citas.map((c, i) => (
        <div key={c.id} className="flex items-start gap-3 group">
          <div className="flex flex-col items-center">
            <span className="w-2.5 h-2.5 rounded-full mt-1.5 shrink-0" style={{ background: estadoDot[c.estado] || "#9aa0a6" }} />
            {i < citas.length - 1 && <span className="w-px flex-1 min-h-[18px] bg-[#FFFFFF]" />}
          </div>
          <div className="flex-1 pb-2.5">
            <div className="flex items-center gap-2 text-[12px]">
              <span className="text-[#1500A0] font-semibold">{fmt(c.fecha)}</span>
              {c.hora && <span className="text-slate-400">{c.hora}</span>}
              <span className="text-slate-600">· {c.estado}</span>
            </div>
            {c.texto && <p className="text-[11px] text-slate-400 truncate">{c.texto}</p>}
          </div>
        </div>
      ))}
    </div>
  );
}

export function Cascabel({ patientId }: { patientId: number }) {
  const [data, setData] = useState<CascabelData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError(false);
    try { setData(await patientService.cascabel(patientId)); }
    catch { setError(true); setData(null); }
    finally { setLoading(false); }
  }, [patientId]);

  useEffect(() => { load(); }, [load]);

  if (loading && !data) {
    return <div className="flex-1 flex items-center justify-center"><Loader2 className="w-5 h-5 animate-spin text-[#1500A0]" /></div>;
  }
  if (error || !data) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-2 text-slate-400">
        <AlertTriangle className="w-6 h-6" />
        <p className="text-[12px]">Error cargando adherencia</p>
        <button type="button" onClick={load} className="text-[12px] underline text-[#1ca0d1] cursor-pointer">Reintentar</button>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto bg-white">
      <div className="max-w-3xl mx-auto px-6 py-5 flex flex-col gap-6">
        {/* Header: score + stats */}
        <div className="flex items-center justify-between px-5 py-4 rounded-sm border" style={{ borderColor: "rgba(1,59,130,0.20)", background: "rgba(1,59,130,0.04)" }}>
          <div className="flex items-center gap-6">
            <ScoreBadge score={data.scorePorcentaje} />
            <div className="flex gap-6">
              <div className="text-center">
                <p className="text-[15px] text-[#2DD9C3] font-semibold leading-none">{data.citasAsistidas}</p>
                <p className="text-[11px] text-slate-400 mt-1">Asistidas</p>
              </div>
              <div className="text-center">
                <p className="text-[15px] text-[#C026D3] font-semibold leading-none">{data.citasNoShow}</p>
                <p className="text-[11px] text-slate-400 mt-1">No asistidas</p>
              </div>
              <div className="text-center">
                <p className="text-[15px] text-slate-500 font-semibold leading-none">{data.citasTotal}</p>
                <p className="text-[11px] text-slate-400 mt-1">Con resultado</p>
              </div>
            </div>
          </div>
          <button type="button" onClick={load} className="p-2 text-slate-400 hover:text-slate-600 transition-colors cursor-pointer">
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>

        {/* Consentimientos (sin datos en BBDD) */}
        <Section title="Consentimientos">
          <p className="text-[12px] text-slate-400 italic py-2">Sin consentimientos registrados</p>
        </Section>

        {/* Seguimiento clínico (sin datos en BBDD) */}
        <Section title="Seguimiento clínico">
          <p className="text-[12px] text-slate-400 italic py-2">Sin seguimientos activos</p>
        </Section>

        {/* Historial de citas (datos reales) */}
        <Section title={`Historial de citas (últimas ${data.citas.length})`}>
          {data.citas.length === 0 ? (
            <div className="flex items-center gap-2 text-[12px] text-slate-400 py-2">
              <CalendarClock className="w-4 h-4" /> Sin citas registradas
            </div>
          ) : <Timeline citas={data.citas} />}
        </Section>
      </div>
    </div>
  );
}
