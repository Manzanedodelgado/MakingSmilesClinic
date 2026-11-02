"use client";
import { useCallback, useEffect, useState } from "react";
import { X, Calendar, RefreshCw, CheckCircle2 } from "lucide-react";
import { gestoriaService, eur } from "../services/gestoriaService";
import { Buscador, coincide } from "./Buscador";
import { AreaTabs, Modal, ModalBody, ModalButton } from "@/shared/components";
import type { DoctoresResp, DoctorLiquidacion } from "../types/gestoria";

const fmt = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
type ProdProps = { tabs: { id: string; label: string }[]; activeTab: string; onChange: (id: string) => void };

export function ProdDoctores({ tabs, activeTab, onChange }: ProdProps) {
  const now = new Date();
  const [desde, setDesde] = useState(fmt(new Date(now.getFullYear(), 0, 1)));
  const [hasta, setHasta] = useState(fmt(now));
  const [doctorId, setDoctorId] = useState("");
  const [busca, setBusca] = useState("");
  const [r, setR] = useState<DoctoresResp | null>(null);
  const [loading, setLoading] = useState(true);
  const [liq, setLiq] = useState<DoctorLiquidacion | null>(null);

  const cargar = useCallback(() => {
    setLoading(true);
    gestoriaService.doctores(desde, hasta).then(setR).finally(() => setLoading(false));
  }, [desde, hasta]);
  useEffect(() => { cargar(); }, [cargar]);

  const rango = (tipo: "mes" | "ant" | "anio") => {
    const n = new Date();
    if (tipo === "mes") { setDesde(fmt(new Date(n.getFullYear(), n.getMonth(), 1))); setHasta(fmt(n)); }
    else if (tipo === "ant") { setDesde(fmt(new Date(n.getFullYear(), n.getMonth() - 1, 1))); setHasta(fmt(new Date(n.getFullYear(), n.getMonth(), 0))); }
    else { setDesde(fmt(new Date(n.getFullYear(), 0, 1))); setHasta(fmt(n)); }
  };

  const rows = (r?.data ?? []).filter((d) => (!doctorId || String(d.doctorId) === doctorId) && coincide(busca, d.doctor));

  return (
    <>
      {/* Filtros integrados al final de la línea de pestañas (como Facturación) */}
      <AreaTabs tabs={tabs} activeTab={activeTab} onChange={onChange} className="pt-2" right={
        <>
          <div className="flex items-center bg-white border border-[#e5e7eb] rounded-sm text-[11px] font-semibold">
            <button onClick={() => rango("mes")} className="px-2.5 py-1 text-gray-600 hover:text-white hover:bg-[#1500A0]">Este mes</button>
            <button onClick={() => rango("ant")} className="px-2.5 py-1 text-gray-600 hover:text-white hover:bg-[#1500A0] border-l border-[#e5e7eb]">Mes ant.</button>
            <button onClick={() => rango("anio")} className="px-2.5 py-1 text-gray-600 hover:text-white hover:bg-[#1500A0] border-l border-[#e5e7eb]">Año</button>
          </div>
          <div className="flex items-center gap-1.5 bg-white border border-[#e5e7eb] rounded-sm px-2 py-1">
            <Calendar className="w-3.5 h-3.5 text-gray-400 shrink-0" />
            <input type="date" value={desde} onChange={(e) => setDesde(e.target.value)} className="text-[11px] font-semibold outline-none w-[112px]" />
            <span className="text-[10px] text-gray-400 uppercase">a</span>
            <input type="date" value={hasta} onChange={(e) => setHasta(e.target.value)} className="text-[11px] font-semibold outline-none w-[112px]" />
          </div>
          <select value={doctorId} onChange={(e) => setDoctorId(e.target.value)} className="bg-white border border-[#e5e7eb] rounded-sm px-2 py-1 text-[11px] font-semibold">
            <option value="">Todos los doctores</option>
            {(r?.data ?? []).map((d) => <option key={d.doctorId} value={String(d.doctorId)}>{d.doctor}</option>)}
          </select>
          <Buscador value={busca} onChange={setBusca} placeholder="Buscar doctor…" />
          <button onClick={cargar} className="p-1 border border-[#e5e7eb] bg-white rounded-sm text-gray-400 hover:text-[#1ca0d1]"><RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} /></button>
          <Kpi label="Bruta" value={eur(r?.prodBruta ?? 0)} />
          <Kpi label="Neta" value={eur(r?.prodNeta ?? 0)} accent />
        </>
      } />

      {/* Tabla liquidación */}
      <div className="flex-1 min-h-0 overflow-auto border border-[#e5e7eb] rounded-sm m-4 mt-3">
        <table className="w-full text-left border-collapse min-w-[1000px] text-[12px]">
          <thead className="sticky top-0 bg-[#1500A0] text-white z-10">
            <tr className="text-[11px] uppercase tracking-wider">
              <th className="py-1.5 px-3 border-r border-[#1a4b8c]">Doctor</th>
              <th className="py-1.5 px-3 text-right border-r border-[#1a4b8c]">Prod. Bruta</th>
              <th className="py-1.5 px-3 text-right border-r border-[#1a4b8c]">Ratio</th>
              <th className="py-1.5 px-3 text-right border-r border-[#1a4b8c]">Comisión Bruta</th>
              <th className="py-1.5 px-3 text-right border-r border-[#1a4b8c] text-[#8bc9f7]">Gasto Lab.</th>
              <th className="py-1.5 px-3 text-right border-r border-[#1a4b8c] text-[#8bc9f7]">Base Neta</th>
              <th className="py-1.5 px-3 text-right border-r border-[#1a4b8c]">IRPF</th>
              <th className="py-1.5 px-3 text-right border-r border-[#1a4b8c] bg-[#0b1b3d]">A Liquidar</th>
              <th className="py-1.5 px-3 text-center">Nómina</th>
            </tr>
          </thead>
          <tbody>
            {loading ? <tr><td colSpan={9} className="text-center py-6 text-gray-400">Cargando…</td></tr>
              : rows.length === 0 ? <tr><td colSpan={9} className="text-center py-8 text-gray-400 italic">No hay producción en el rango.</td></tr>
              : rows.map((row) => (
                <tr key={row.doctorId} className="border-b border-[#e5e7eb] even:bg-[#FFFFFF] hover:bg-[#E6EDFF]">
                  <td className="py-2 px-3 border-r border-[#e5e7eb]">
                    <div className="font-semibold text-[#1500A0]">{row.doctor}</div>
                    <div className="text-[11px] text-gray-500">{row.tratamientos} trabajos</div>
                  </td>
                  <td className="py-1.5 px-3 text-right border-r border-[#e5e7eb]">{eur(row.prodBruta)}</td>
                  <td className="py-1.5 px-3 text-right text-[#7C3AED] border-r border-[#e5e7eb]">{row.acuerdoPct}%</td>
                  <td className="py-1.5 px-3 text-right text-gray-500 border-r border-[#e5e7eb]">{eur(row.comisionBruta)}</td>
                  <td className="py-1.5 px-3 text-right border-r border-[#e5e7eb]">{row.deduceLaboratorio ? <span className="text-[#1500A0] font-semibold">{eur(row.gastosLabReales)}</span> : <span className="text-gray-400">0,00 €</span>}</td>
                  <td className="py-1.5 px-3 text-right font-semibold text-[#1500A0] bg-[#FFFFFF] border-r border-[#e5e7eb]">{eur(row.baseIrpf)}</td>
                  <td className="py-1.5 px-3 text-right text-[#C026D3] border-r border-[#e5e7eb]">-{eur(row.deduccionIrpf)} ({row.irpfPct}%)</td>
                  <td className="py-1.5 px-3 text-right font-semibold text-[#1500A0] bg-[#FFFFFF] border-r border-[#e5e7eb]">{eur(row.produccionNeta)}</td>
                  <td className="py-2 px-3 text-center">
                    <button onClick={() => setLiq(row)} className="bg-[#3388FF] hover:bg-[#20BEAB] px-3 py-1 text-white rounded-sm text-[11px] font-semibold uppercase">Autofactura</button>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      {liq && <AutofacturaModal liq={liq} desde={desde} hasta={hasta} onClose={() => setLiq(null)} onDone={() => { setLiq(null); cargar(); }} />}
    </>
  );
}

function AutofacturaModal({ liq, desde, hasta, onClose, onDone }: { liq: DoctorLiquidacion; desde: string; hasta: string; onClose: () => void; onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const emitir = async () => {
    if (liq.doctorId == null) { setErr("Doctor sin colaborador asociado"); return; }
    setBusy(true); setErr("");
    try { await gestoriaService.autofactura(liq.doctorId, desde, hasta); onDone(); }
    catch (e) { setErr(e instanceof Error ? e.message : "Error"); setBusy(false); }
  };
  return (
    <Modal
      title="Generar autofactura"
      onClose={onClose}
      size="md"
      closeOnBackdrop={false}
      footer={
        <>
          <ModalButton variant="magenta" icon={X} onClick={onClose}>Cancelar</ModalButton>
          <ModalButton variant="primary" onClick={emitir} disabled={busy}>
            {busy ? <><RefreshCw className="w-4 h-4 animate-spin" /> Procesando…</> : <><CheckCircle2 className="w-4 h-4" /> Emitir</>}
          </ModalButton>
        </>
      }
    >
      <ModalBody className="flex flex-col gap-3">
        <div className="text-center"><div className="text-[11px] text-[#5F7690] uppercase tracking-wider">Colaborador</div><div className="font-semibold text-[#1500A0]">{liq.doctor}</div></div>
        <div className="border border-[#BFE4F7] bg-white rounded-md overflow-hidden text-[12px]">
          <Fila k={`Comisión bruta (${liq.acuerdoPct}%)`} v={eur(liq.comisionBruta)} />
          <Fila k="Gastos laboratorio" v={`-${eur(liq.gastosLabReales)}`} rojo />
          <Fila k="Base imponible" v={eur(liq.baseIrpf)} bold />
          <Fila k={`Retención IRPF (${liq.irpfPct}%)`} v={`-${eur(liq.deduccionIrpf)}`} rojo />
          <div className="flex justify-between px-4 py-3 bg-[#FFFFFF] font-semibold text-[#0F8C7D]"><span className="uppercase tracking-wider text-[12px]">Total a liquidar</span><span>{eur(liq.produccionNeta)}</span></div>
        </div>
        {err && <div className="text-[11px] text-[#C026D3]">{err}</div>}
      </ModalBody>
    </Modal>
  );
}

const Kpi = ({ label, value, accent }: { label: string; value: string | number; accent?: boolean }) => (
  <div className={`flex items-center gap-2 border rounded-sm px-3 py-1 ${accent ? "bg-[#FFFFFF] border-[#c8d8e8]" : "bg-white border-[#e5e7eb]"}`}>
    <span className="text-[10px] uppercase font-semibold text-gray-400 tracking-wider">{label}:</span>
    <span className={`text-[12px] font-semibold ${accent ? "text-[#3388FF]" : "text-[#1500A0]"}`}>{value}</span>
  </div>
);
const Fila = ({ k, v, rojo, bold }: { k: string; v: string; rojo?: boolean; bold?: boolean }) => (
  <div className={`flex justify-between px-4 py-2.5 border-b border-[#e5e7eb] ${bold ? "bg-[#FFFFFF] font-semibold text-[#1500A0]" : ""}`}>
    <span className="uppercase tracking-wide text-gray-600 text-[11px] font-semibold">{k}</span>
    <span className={rojo ? "text-[#C026D3]" : ""}>{v}</span>
  </div>
);
