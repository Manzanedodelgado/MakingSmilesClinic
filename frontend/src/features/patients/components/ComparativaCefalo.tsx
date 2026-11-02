"use client";
/**
 * COMPARATIVA CEFALOMÉTRICA LONGITUDINAL — evolución del tratamiento.
 *
 * Muestra los trazados del mismo análisis del paciente por fecha (columnas) y el cambio
 * (final − inicial) de cada medida. Se apoya en /pacientes/{id}/cefalometria/comparar.
 */
import { useState, useEffect, useCallback } from "react";
import { Loader2, X, TrendingUp } from "lucide-react";
import { api } from "@/shared/lib/api";

type Medida = { valor: number | null; label: string; unidad: string };
type Punto = { imagen_id: number; fecha: string; mediciones: Record<string, Medida> };
type Delta = { label: string; unidad: string; inicial: number; final: number; cambio: number };
type Comparativa = { analisis: string; serie: Punto[]; delta: Record<string, Delta> };

export function ComparativaCefalo({ patientId, onCerrar }: { patientId: number; onCerrar?: () => void }) {
  const [analisis, setAnalisis] = useState("steiner");
  const [data, setData] = useState<Comparativa | null>(null);
  const [loading, setLoading] = useState(false);

  const cargar = useCallback(async () => {
    setLoading(true);
    try { setData(await api.get<Comparativa>(`/pacientes/${patientId}/cefalometria/comparar?analisis=${analisis}`)); }
    catch { setData(null); }
    finally { setLoading(false); }
  }, [patientId, analisis]);
  useEffect(() => { void cargar(); }, [cargar]);

  // Filas = unión de códigos de medida en toda la serie (orden del primer trazado)
  const codigos = data ? Array.from(new Set(data.serie.flatMap((p) => Object.keys(p.mediciones)))) : [];

  return (
    <div className="flex flex-col h-full min-h-0 bg-white">
      <div className="flex items-center justify-between px-3 py-2 bg-[#1500A0] text-white shrink-0">
        <b className="text-[13px] uppercase tracking-wide flex items-center gap-2"><TrendingUp className="w-4 h-4" /> Evolución cefalométrica</b>
        <div className="flex items-center gap-2">
          <select value={analisis} onChange={(e) => setAnalisis(e.target.value)}
            className="text-xs bg-white/15 text-white rounded-sm px-1.5 py-1 cursor-pointer border border-white/20">
            <option value="steiner" className="text-slate-800">Steiner</option>
            <option value="ricketts" className="text-slate-800">Ricketts</option>
          </select>
          {onCerrar && <button type="button" onClick={onCerrar} className="text-white/80 hover:text-white cursor-pointer"><X className="w-4 h-4" /></button>}
        </div>
      </div>

      <div className="flex-1 min-h-0 overflow-auto p-3">
        {loading ? (
          <div className="h-32 grid place-items-center text-slate-400"><Loader2 className="w-5 h-5 animate-spin" /></div>
        ) : !data || data.serie.length < 2 ? (
          <div className="h-32 grid place-items-center text-slate-400 text-sm text-center px-6">
            Se necesitan al menos 2 trazados de {analisis === "steiner" ? "Steiner" : "Ricketts"} (en RX de distintas fechas) para comparar la evolución.
          </div>
        ) : (
          <table className="w-full text-xs border-collapse">
            <thead>
              <tr className="text-slate-400">
                <th className="text-left font-semibold py-1 pr-2">Medida</th>
                {data.serie.map((p) => (
                  <th key={p.imagen_id} className="text-right font-semibold py-1 px-2 whitespace-nowrap">{p.fecha}</th>
                ))}
                <th className="text-right font-semibold py-1 pl-2">Cambio</th>
              </tr>
            </thead>
            <tbody>
              {codigos.map((code) => {
                const ref = data.serie.find((p) => p.mediciones[code])?.mediciones[code];
                const d = data.delta[code];
                return (
                  <tr key={code} className="border-t border-slate-100">
                    <td className="py-1.5 pr-2 text-slate-600">{ref?.label ?? code}</td>
                    {data.serie.map((p) => (
                      <td key={p.imagen_id} className="py-1.5 px-2 text-right font-medium text-[#013b82]">
                        {p.mediciones[code]?.valor ?? "—"}{p.mediciones[code]?.unidad ?? ""}
                      </td>
                    ))}
                    <td className={`py-1.5 pl-2 text-right font-semibold ${d ? (d.cambio > 0 ? "text-[#20BEAB]" : d.cambio < 0 ? "text-[#C026D3]" : "text-slate-400") : "text-slate-300"}`}>
                      {d ? `${d.cambio > 0 ? "+" : ""}${d.cambio}${d.unidad}` : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
