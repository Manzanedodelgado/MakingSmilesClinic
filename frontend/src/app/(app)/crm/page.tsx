"use client";
/**
 * CRM de la empresa. Dos motores, sobre datos reales:
 *  · Reactivación — pacientes activos que no vuelven desde hace X meses, ordenados por valor.
 *  · Pipeline — embudo de presupuestos: conversión + presupuestos COLGADOS (presentados sin cerrar)
 *    a perseguir, ordenados por importe. Teléfono directo a WhatsApp; clic al NumPac abre la ficha.
 */
import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, X, Contact, MessageCircle } from "lucide-react";
import { api } from "@/shared/lib/api";

type Inactivo = { id: number; numPac: string | null; paciente: string; telefono: string | null; ultimaVisita: string | null; gastado: number; mesesInactivo: number };
type Colgado = { pacienteId: number; numPac: string | null; paciente: string; telefono: string | null; total: number; fecha: string | null; dias: number };
type Pipeline = { resumen: { pendientesN: number; pendientesEur: number; cerradosN: number; cerradosEur: number; perdidosN: number; conversion: number }; mostrados: number; colgados: Colgado[] };

const eur = (n: number) => new Intl.NumberFormat("es-ES", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n || 0);
const waLink = (tel: string) => `https://wa.me/34${tel.replace(/\D/g, "").replace(/^34/, "")}`;
const Wa = ({ tel }: { tel: string | null }) => tel
  ? <a href={waLink(tel)} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-[11px] font-semibold text-[#0a7d6e] hover:text-[#065f54]"><MessageCircle className="w-3.5 h-3.5" /> WhatsApp</a>
  : <span className="text-slate-300 text-[11px]">sin tel.</span>;

const TABS = [{ id: "reactivacion", label: "Reactivación" }, { id: "pipeline", label: "Pipeline de presupuestos" }];

export default function CrmPage() {
  const router = useRouter();
  const [tab, setTab] = useState("pipeline");
  const [busca, setBusca] = useState("");

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="flex items-center gap-1 px-4 pt-2 bg-white border-b border-[#eef2f7]">
        {TABS.map((t) => (
          <button key={t.id} onClick={() => { setTab(t.id); setBusca(""); }}
            className={`px-3 py-1.5 text-[12px] font-semibold rounded-t-sm ${tab === t.id ? "bg-[#1500A0] text-white" : "text-[#065AED] hover:bg-[#E6EDFF]"}`}>
            {t.label}
          </button>
        ))}
        <div className="relative ml-auto mb-1">
          <input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar paciente / NumPac / tel…"
            className="border border-[#e5e7eb] rounded-sm pl-2 pr-6 py-1 text-[11px] w-64" />
          {busca && (
            <button type="button" onClick={() => setBusca("")} className="absolute right-1.5 top-1/2 -translate-y-1/2 text-[#9ca3af] hover:text-[#C026D3]">
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto bg-white p-4">
        {tab === "reactivacion" ? <Reactivacion router={router} busca={busca} /> : <PipelineView router={router} busca={busca} />}
      </div>
    </div>
  );
}

function Reactivacion({ router, busca }: { router: ReturnType<typeof useRouter>; busca: string }) {
  const [meses, setMeses] = useState(12);
  const [rows, setRows] = useState<Inactivo[]>([]);
  const [total, setTotal] = useState(0);
  const [mostrados, setMostrados] = useState(0);
  const [cargando, setCargando] = useState(true);
  useEffect(() => {
    setCargando(true);
    api.get<{ total: number; mostrados: number; data: Inactivo[] }>(`/crm/inactivos?meses=${meses}`)
      .then((r) => { setRows(r.data); setTotal(r.total); setMostrados(r.mostrados); }).finally(() => setCargando(false));
  }, [meses]);
  const vis = rows.filter((p) => !busca || [p.paciente, p.numPac, p.telefono].some((x) => (x || "").toLowerCase().includes(busca.toLowerCase())));
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="text-[12px] text-[#7f8c8d]"><b className="text-[#1500A0]">{total}</b> pacientes sin volver desde hace <b>+{meses} meses</b> — ordenados por lo que gastaron
          {mostrados < total && <span className="text-[#6D28D9]"> · mostrando los {mostrados} de mayor valor</span>}</span>
        <select value={meses} onChange={(e) => setMeses(Number(e.target.value))} className="border border-[#e5e7eb] rounded-sm px-2 py-1 text-[11px]">
          {[6, 9, 12, 18, 24, 36].map((m) => <option key={m} value={m}>+{m} meses</option>)}
        </select>
      </div>
      {cargando ? <Cargando /> : (
        <Tabla head={["NumPac", "Paciente", "Teléfono", "Última visita", "Sin volver", "Gastó", ""]}>
          {vis.map((p) => (
            <tr key={p.id} className="border-b border-[#f0f3f7] even:bg-[#FFFFFF] hover:bg-[#E6EDFF]">
              <Num router={router} id={p.id} numPac={p.numPac} /><td className="py-1.5 px-3 text-slate-700">{p.paciente}</td>
              <td className="py-1.5 px-3 text-slate-600">{p.telefono ?? "—"}</td><td className="py-1.5 px-3 text-slate-600">{p.ultimaVisita ?? "—"}</td>
              <td className="py-1.5 px-3 text-right text-[#6D28D9] font-semibold tabular-nums">{p.mesesInactivo} m</td>
              <td className="py-1.5 px-3 text-right font-semibold text-[#1500A0] tabular-nums">{eur(p.gastado)}</td>
              <td className="py-1.5 px-3 text-right"><Wa tel={p.telefono} /></td>
            </tr>
          ))}
        </Tabla>
      )}
    </div>
  );
}

function PipelineView({ router, busca }: { router: ReturnType<typeof useRouter>; busca: string }) {
  const [d, setD] = useState<Pipeline | null>(null);
  const [maxDias, setMaxDias] = useState(365);
  const [cargando, setCargando] = useState(true);
  useEffect(() => { setCargando(true); api.get<Pipeline>("/crm/pipeline").then(setD).finally(() => setCargando(false)); }, []);
  if (cargando || !d) return <Cargando />;
  const r = d.resumen;
  const vis = d.colgados.filter((c) => c.dias <= maxDias && (!busca || [c.paciente, c.numPac, c.telefono].some((x) => (x || "").toLowerCase().includes(busca.toLowerCase()))));
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <span className="text-[12px] text-[#7f8c8d]">
          Conversión <b className="text-[#0a7d6e]">{r.conversion}%</b> · cerrados <b>{r.cerradosN}</b> ({eur(r.cerradosEur)}) ·
          <b className="text-[#6D28D9]"> {r.pendientesN} colgados</b> ({eur(r.pendientesEur)}) a perseguir
        </span>
        <select value={maxDias} onChange={(e) => setMaxDias(Number(e.target.value))} className="border border-[#e5e7eb] rounded-sm px-2 py-1 text-[11px]">
          {[90, 180, 365, 99999].map((dd) => <option key={dd} value={dd}>{dd === 99999 ? "cualquier antigüedad" : `≤ ${dd} días`}</option>)}
        </select>
      </div>
      <Tabla head={["NumPac", "Paciente", "Teléfono", "Presupuesto", "Importe", "Colgado", ""]}>
        {vis.map((c, i) => (
          <tr key={i} className="border-b border-[#f0f3f7] even:bg-[#FFFFFF] hover:bg-[#E6EDFF]">
            <Num router={router} id={c.pacienteId} numPac={c.numPac} /><td className="py-1.5 px-3 text-slate-700">{c.paciente}</td>
            <td className="py-1.5 px-3 text-slate-600">{c.telefono ?? "—"}</td><td className="py-1.5 px-3 text-slate-600">{c.fecha ?? "—"}</td>
            <td className="py-1.5 px-3 text-right font-semibold text-[#1500A0] tabular-nums">{eur(c.total)}</td>
            <td className={`py-1.5 px-3 text-right tabular-nums font-semibold ${c.dias > 365 ? "text-slate-400" : "text-[#6D28D9]"}`}>{c.dias} d</td>
            <td className="py-1.5 px-3 text-right"><Wa tel={c.telefono} /></td>
          </tr>
        ))}
      </Tabla>
    </div>
  );
}

const Cargando = () => <div className="flex items-center justify-center py-16"><Loader2 className="w-7 h-7 text-[#1ca0d1] animate-spin" /></div>;
function Tabla({ head, children }: { head: string[]; children: React.ReactNode }) {
  return (
    <div className="border border-[#e5e7eb] rounded-sm overflow-auto">
      <table className="w-full text-[12px]">
        <thead className="bg-[#1500A0] text-white text-[11px] uppercase tracking-wider sticky top-0">
          <tr>{head.map((h, i) => <th key={i} className={`py-1.5 px-3 ${i >= 4 && i < head.length - 1 ? "text-right" : "text-left"}`}>{h}</th>)}</tr>
        </thead>
        <tbody>{React.Children.count(children) === 0 ? <tr><td colSpan={head.length} className="text-center py-8 text-gray-400 italic">Sin resultados en este filtro.</td></tr> : children}</tbody>
      </table>
    </div>
  );
}
function Num({ router, id, numPac }: { router: ReturnType<typeof useRouter>; id: number; numPac: string | null }) {
  return <td className="py-1.5 px-3 font-semibold text-[#065AED] cursor-pointer" onClick={() => router.push(`/pacientes/${id}/ficha`)}>{numPac ?? "—"}</td>;
}
