"use client";
import { FileText, Pill, Printer } from "lucide-react";
/** PLAN ECON. → DOCUMENTOS: generar documento (factura/recibo/justificante/historia) + recetas emitidas. */
import { useCallback, useEffect, useState } from "react";
import { ClinicalCard, SectionHeader } from "@/shared/components";
import { patientService } from "../services/patientService";
import type { RecetaEmitida } from "../types/patient";

const fecha = (s: string | null) => (s ? new Date(s).toLocaleDateString("es-ES") : "—");
const GENERABLES = ["Factura", "Recibo", "Justificante", "Historia clínica"];

export function PlanEconDocs({ patientId }: { patientId: number }) {
  const [recetas, setRecetas] = useState<RecetaEmitida[]>([]);
  const [loading, setLoading] = useState(true);

  const cargar = useCallback(async () => {
    setLoading(true);
    try { setRecetas((await patientService.recetas(patientId)).recetas); } catch { setRecetas([]); }
    finally { setLoading(false); }
  }, [patientId]);
  useEffect(() => { cargar(); }, [cargar]);

  return (
    <div className="p-4 space-y-3 overflow-y-auto">
      <ClinicalCard noPadding>
        <SectionHeader variant="dark" title="Generar documento" icon={FileText} />
        <div className="flex flex-wrap gap-2 p-3">
          {GENERABLES.map((g) => (
            <button key={g} title={`${g} (pendiente)`}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-sm text-[11px] font-semibold uppercase tracking-wide border border-[#e5e7eb] text-[#1500A0] hover:bg-[#E6EDFF]">
              <Printer className="w-3.5 h-3.5" /> {g}
            </button>
          ))}
        </div>
      </ClinicalCard>

      <ClinicalCard noPadding>
        <SectionHeader
          variant="dark" title="Recetas emitidas" icon={Pill}
          action={<span className="text-[10px] text-white/80 uppercase tracking-wide">{recetas.length} receta(s)</span>}
        />
        <table className="w-full text-[12px]">
          <thead>
            <tr className="bg-[#FFFFFF] text-[#1ca0d1] text-[10px] uppercase tracking-wide border-b border-[#e5e7eb]">
              <th className="text-left px-3 py-1.5 font-semibold">Fecha</th>
              <th className="text-left px-3 py-1.5 font-semibold">Medicamento</th>
              <th className="text-left px-3 py-1.5 font-semibold">Posología</th>
              <th className="text-left px-3 py-1.5 font-semibold">Doctor</th>
              <th className="text-left px-3 py-1.5 font-semibold">Nº Receta</th>
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={5} className="px-3 py-4 text-center text-slate-400 text-[12px]">Cargando recetas…</td></tr>}
            {!loading && recetas.map((r) => (
              <tr key={r.id} className="border-b border-[#f0f2f5] hover:bg-[#E6EDFF]">
                <td className="px-3 py-1.5 text-slate-600 whitespace-nowrap">{fecha(r.fecha)}</td>
                <td className="px-3 py-1.5 text-[#333333] font-medium">{r.medicamento}{r.n_lineas > 1 ? <span className="text-slate-400"> +{r.n_lineas - 1}</span> : null}</td>
                <td className="px-3 py-1.5 text-slate-500">{r.posologia || "—"}</td>
                <td className="px-3 py-1.5 text-slate-600">{r.doctor}</td>
                <td className="px-3 py-1.5 text-slate-500 font-mono text-[11px]">{r.num_receta || "—"}</td>
              </tr>
            ))}
            {!loading && recetas.length === 0 && (
              <tr><td colSpan={5} className="px-3 py-6 text-center text-[12px] text-slate-400 italic">Sin recetas emitidas</td></tr>
            )}
          </tbody>
        </table>
      </ClinicalCard>
    </div>
  );
}
