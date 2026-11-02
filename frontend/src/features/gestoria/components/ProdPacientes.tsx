"use client";
import { FileText, Receipt, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { gestoriaService, eur } from "../services/gestoriaService";
import { AreaTabs } from "@/shared/components";
import type { PacienteBusqueda, PatientTreatmentsResp } from "../types/gestoria";

export function ProdPacientes({ tabs, activeTab, onChange }: { tabs: { id: string; label: string }[]; activeTab: string; onChange: (id: string) => void }) {
  const [q, setQ] = useState("");
  const [sug, setSug] = useState<PacienteBusqueda[]>([]);
  const [pacId, setPacId] = useState<number | null>(null);
  const [data, setData] = useState<PatientTreatmentsResp | null>(null);
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [msg, setMsg] = useState<{ ok: boolean; txt: string } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (q.length < 2 || pacId) { setSug([]); return; }
    const t = setTimeout(() => gestoriaService.buscarPaciente(q).then((r) => setSug(r.pacientes)).catch(() => setSug([])), 250);
    return () => clearTimeout(t);
  }, [q, pacId]);

  const elegir = (p: PacienteBusqueda) => {
    setPacId(p.id); setQ(`${p.apellidos} ${p.nombre}`); setSug([]); setSel(new Set()); setMsg(null);
    gestoriaService.pacienteTtos(p.id).then(setData);
  };

  const rows = data?.data ?? [];
  const facturables = rows.filter((r) => !r.facturado);
  const totalSel = rows.filter((r) => sel.has(r.ident)).reduce((s, r) => s + r.neto, 0);

  const toggle = (id: string) => setSel((p) => { const n = new Set(p); if (n.has(id)) n.delete(id); else n.add(id); return n; });

  const facturar = async () => {
    if (!pacId || sel.size === 0) return;
    setBusy(true); setMsg(null);
    try {
      const r = await gestoriaService.facturarPaciente(pacId, [...sel].map(Number));
      setMsg({ ok: true, txt: `Factura ${r.numeroFactura} generada` });
      setSel(new Set());
      gestoriaService.pacienteTtos(pacId).then(setData);
    } catch (e) { setMsg({ ok: false, txt: e instanceof Error ? e.message : "Error" }); }
    setBusy(false);
  };

  return (
    <>
      <AreaTabs tabs={tabs} activeTab={activeTab} onChange={onChange} className="pt-2" right={
        <div className="relative w-72">
          <Search className="w-3.5 h-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-gray-400" />
          <input value={q} onChange={(e) => { setQ(e.target.value); setPacId(null); }} placeholder="Paciente: nombre, Nº hist., NIF…"
            className="w-full pl-7 pr-2 py-1 border border-[#e5e7eb] rounded-sm text-[12px]" />
          {sug.length > 0 && (
            <div className="absolute z-20 mt-1 w-full bg-white border border-[#e5e7eb] rounded-sm shadow-lg max-h-60 overflow-y-auto">
              {sug.map((p) => (
                <button key={p.id} onClick={() => elegir(p)} className="block w-full text-left px-3 py-1.5 text-[12px] hover:bg-[#E6EDFF]">
                  {p.apellidos} {p.nombre} <span className="text-gray-400">· {p.num_historia ?? p.id}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      } />
      <div className="flex-1 min-h-0 overflow-y-auto p-4 flex flex-col gap-3 bg-white">

      {msg && <div className={`text-[12px] font-semibold px-3 py-1.5 rounded-sm ${msg.ok ? "bg-[#2DD9C3]/15 text-[#065AED]" : "bg-[#FFFFFF] text-[#C026D3]"}`}>{msg.txt}</div>}

      {!pacId ? (
        <div className="flex-1 flex flex-col items-center justify-center text-gray-400 gap-2"><FileText className="w-10 h-10 text-slate-200" /><span className="text-[12px]">Busca un paciente para ver sus tratamientos.</span></div>
      ) : rows.length === 0 ? (
        <div className="text-center py-8 text-gray-400 italic text-[12px]">Sin tratamientos.</div>
      ) : (
        <div className="border border-[#e5e7eb] rounded-sm overflow-hidden">
          <table className="w-full text-[12px]">
            <thead className="bg-[#FFFFFF] border-b border-[#e5e7eb] text-[11px] uppercase text-[#7f8c8d]">
              <tr>
                <th className="w-8 px-2 py-2"><input type="checkbox" checked={facturables.length > 0 && facturables.every((r) => sel.has(r.ident))} onChange={(e) => setSel(e.target.checked ? new Set(facturables.map((r) => r.ident)) : new Set())} /></th>
                <th className="px-3 py-2 text-left font-bold">Fecha</th><th className="px-3 py-2 text-left font-bold">Tratamiento</th>
                <th className="px-3 py-2 text-left font-bold">Doctor</th><th className="px-3 py-2 text-right font-bold">Importe</th>
                <th className="px-3 py-2 text-right font-bold">Dto.</th><th className="px-3 py-2 text-right font-bold">Neto</th>
                <th className="px-3 py-2 text-center font-bold">Abonado</th><th className="px-3 py-2 text-center font-bold">Factura</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.ident} className={`border-b border-[#f0f2f5] ${row.facturado ? "opacity-60 bg-[#FFFFFF]" : sel.has(row.ident) ? "bg-white" : "even:bg-[#FFFFFF] hover:bg-[#E6EDFF] cursor-pointer"}`}
                  onClick={() => !row.facturado && toggle(row.ident)}>
                  <td className="px-2 py-2 text-center" onClick={(e) => e.stopPropagation()}><input type="checkbox" disabled={row.facturado} checked={sel.has(row.ident)} onChange={() => toggle(row.ident)} /></td>
                  <td className="px-3 py-2 text-[#7f8c8d]">{row.fecha ?? "—"}</td>
                  <td className="px-3 py-2 text-[#333]">{row.concepto}</td>
                  <td className="px-3 py-2 text-slate-500">{row.doctor}</td>
                  <td className={`px-3 py-2 text-right ${row.descuento ? "text-slate-400 line-through" : "font-bold text-[#065AED]"}`}>{eur(row.importe)}</td>
                  <td className="px-3 py-2 text-right text-[#7C3AED]">{row.descuento ? `−${eur(row.descuento)}` : "—"}</td>
                  <td className="px-3 py-2 text-right font-bold text-[#065AED]">{eur(row.neto)}</td>
                  <td className="px-3 py-2 text-center"><span className={`px-1.5 py-0.5 rounded-sm text-[10px] uppercase ${row.abonado ? "bg-[#2DD9C3]/20 text-[#065AED]" : "bg-[#FFFFFF] text-[#6D28D9]"}`}>{row.abonado ? "Sí" : "No"}</span></td>
                  <td className="px-3 py-2 text-center text-[11px] font-mono text-slate-500">{row.facturaNumero ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {sel.size > 0 && (
            <div className="flex items-center justify-between gap-3 px-3 py-2 border-t border-[#e5e7eb] bg-[#FFFFFF]">
              <span className="text-[12px] text-[#7f8c8d]"><b className="text-[#065AED]">{sel.size}</b> sel. · Total <b>{eur(totalSel)}</b> <span className="text-[10px]">(exento IVA)</span></span>
              <button onClick={facturar} disabled={busy} className="flex items-center gap-1.5 bg-[#065AED] hover:bg-[#0250a8] text-white font-bold text-[12px] px-4 py-1 rounded-sm uppercase disabled:opacity-50">
                <Receipt className="w-3.5 h-3.5" /> {busy ? "Generando…" : "Generar factura Verifactu"}
              </button>
            </div>
          )}
        </div>
      )}
      </div>
    </>
  );
}
