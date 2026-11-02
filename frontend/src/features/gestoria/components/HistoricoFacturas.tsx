"use client";
import { FileText, Search } from "lucide-react";
/* Gestoría › Facturación › Histórico — buscador del ARCHIVO documental de facturas (libros
   2019-2024 + PDFs). Consulta pura sobre la tabla aislada facturas_historico: ningún total de
   Gestoría sale de aquí (los números contables de años cerrados no cambian). */
import React, { useEffect, useState } from "react";

import { eur, gestoriaService, fecha as fmtFecha } from "../services/gestoriaService";
import type { FacturaHistorica } from "../types/gestoria";

const Th = ({ children, r }: { children?: React.ReactNode; r?: boolean }) => <th className={`py-1.5 px-3 font-semibold ${r ? "text-right" : "text-left"}`}>{children}</th>;
const Td = ({ children, r }: { children?: React.ReactNode; r?: boolean }) => <td className={`py-1.5 px-3 text-slate-600 ${r ? "text-right" : ""}`}>{children}</td>;

export function HistoricoFacturas() {
  const [q, setQ] = useState("");
  const [anio, setAnio] = useState<number | undefined>(undefined);
  const [anios, setAnios] = useState<number[]>([]);
  const [rows, setRows] = useState<FacturaHistorica[]>([]);
  const [total, setTotal] = useState(0);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => {
      gestoriaService.historico(q || undefined, anio).then((r) => { setRows(r.data); setTotal(r.total); setAnios(r.anios); });
    }, 250);
    return () => clearTimeout(t);
  }, [q, anio]);

  const abrirPdf = async (id: number) => {
    setMsg(null);
    try { await gestoriaService.abrirHistoricoPdf(id); }
    catch (e) { setMsg(e instanceof Error ? e.message : "No se pudo abrir el PDF"); }
  };

  return (
    <div className="flex-1 overflow-y-auto p-4 bg-white flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <div className="relative flex-1 max-w-md">
          <Search className="w-3.5 h-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-[#7f8c8d]" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Proveedor, NIF, nº de factura o detalle…"
            className="w-full border border-[#e5e7eb] rounded-sm pl-7 pr-2 py-1.5 text-[11px] outline-none focus:border-[#1ca0d1]" />
        </div>
        <select value={anio ?? ""} onChange={(e) => setAnio(e.target.value ? Number(e.target.value) : undefined)}
          className="border border-[#e5e7eb] rounded-sm px-2 py-1.5 text-[11px]">
          <option value="">Todos los años</option>
          {anios.map((a) => <option key={a} value={a}>{a}</option>)}
        </select>
        <span className="text-[12px] text-[#7f8c8d] ml-auto"><b className="text-[#1500A0]">{total}</b> resultados{total === 300 ? " (máx.)" : ""}</span>
      </div>
      {msg && <div className="text-[11px] text-[#6D28D9] bg-[#FFFFFF] border border-[#C4B5FD] rounded-sm px-2 py-1">{msg}</div>}
      <div className="border border-[#e5e7eb] rounded-sm overflow-x-auto">
        <table className="w-full text-[11px]">
          <thead className="bg-[#FFFFFF] text-[#1500A0]">
            <tr><Th>Fecha</Th><Th>Nº factura</Th><Th>Proveedor</Th><Th>NIF</Th><Th>Área</Th><Th r>Base</Th><Th r>IVA</Th><Th r>Ret. IRPF</Th><Th r>Total</Th><Th>Pago</Th><Th>Abonada</Th><Th r>PDF</Th></tr>
          </thead>
          <tbody>
            {rows.length === 0 ? <tr><td colSpan={12} className="text-center py-8 text-gray-400 italic">Sin resultados en el archivo histórico</td></tr>
              : rows.map((f) => (
                <tr key={f.id} className="border-b border-[#f0f3f7] even:bg-[#FFFFFF] hover:bg-[#E6EDFF]">
                  <Td>{f.fecha ? fmtFecha(f.fecha) : f.mes ? `${String(f.mes).padStart(2, "0")}/${f.anio}` : f.anio}</Td>
                  <Td><b className="text-[#065AED]">{f.numFactura ?? "—"}</b></Td>
                  <Td>{f.proveedor ?? "—"}</Td>
                  <Td>{f.nif ?? "—"}</Td>
                  <Td>{f.areaGasto ?? "—"}</Td>
                  <Td r>{f.base != null ? eur(f.base) : "—"}</Td>
                  <Td r>{f.iva != null ? eur(f.iva) : "—"}</Td>
                  <Td r>{f.retencion != null ? eur(f.retencion) : "—"}</Td>
                  <Td r>{f.total != null ? <b className="text-[#1500A0]">{eur(f.total)}</b> : "—"}</Td>
                  <Td>{f.formaPago ?? "—"}</Td>
                  <Td>{f.abonada ?? "—"}</Td>
                  <td className="py-1.5 px-3 text-right">
                    {f.tienePdf
                      ? <button onClick={() => abrirPdf(f.id)} title="Abrir PDF" className="text-[#065AED] hover:text-[#1ca0d1]"><FileText className="w-3.5 h-3.5 inline" /></button>
                      : <span className="text-gray-300">—</span>}
                  </td>
                </tr>))}
          </tbody>
        </table>
      </div>
      <p className="text-[10px] text-[#7f8c8d]">Archivo documental de los libros de facturas 2019-2024. Solo consulta: no altera ni suma en ningún número de Gestoría.</p>
    </div>
  );
}
