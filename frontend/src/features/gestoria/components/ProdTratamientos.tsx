"use client";
import { useEffect, useState } from "react";
import { gestoriaService, eur, fecha as fmtFecha } from "../services/gestoriaService";
import { Buscador, coincide } from "./Buscador";
import { AreaTabs } from "@/shared/components";
import { MESES } from "../constants";
import type { ActoRealizado } from "../types/gestoria";

const Y = new Date().getFullYear();

export function ProdTratamientos({ tabs, activeTab, onChange }: { tabs: { id: string; label: string }[]; activeTab: string; onChange: (id: string) => void }) {
  const [anyo, setAnyo] = useState<number | "">(Y);  // "" = todos los años; marca la CARGA (rango al backend)
  const [doctor, setDoctor] = useState("");     // resto de filtros: en cliente sobre lo cargado
  const [mes, setMes] = useState("");
  const [dia, setDia] = useState("");
  const [tratamiento, setTratamiento] = useState("");
  const [paciente, setPaciente] = useState("");
  const [busca, setBusca] = useState("");       // buscador general (todas las columnas)
  const [rows, setRows] = useState<ActoRealizado[]>([]);
  const [anios, setAnios] = useState<number[]>([Y, Y - 1, Y - 2]);  // años reales con datos (del backend)
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const req = anyo === ""
      ? gestoriaService.tratamientos()                                  // sin rango → todos los años
      : gestoriaService.tratamientos(`${anyo}-01-01`, `${anyo}-12-31`);
    req.then((r) => { setRows(r.data); if (r.anios?.length) setAnios(r.anios); }).finally(() => setLoading(false));
  }, [anyo]);

  const doctores = [...new Set(rows.map((r) => r.doctor).filter(Boolean))].sort();
  const mostrados = rows.filter((t) => {
    const f = t.fecha || "";
    return (!doctor || t.doctor === doctor)
      && (!mes || f.slice(5, 7) === mes)
      && (!dia || f.slice(8, 10) === dia)
      && (!tratamiento || (t.tratamiento || "").toLowerCase().includes(tratamiento.toLowerCase()))
      && (!paciente || (t.paciente || "").toLowerCase().includes(paciente.toLowerCase()))
      && coincide(busca, t.fecha, t.tratamiento, t.piezas, t.doctor, t.paciente);
  });
  const suma = mostrados.reduce((s, t) => s + (t.importe || 0), 0);

  // Guardar el dto. realizado / si aplica al doctor (optimista: actualiza la fila en local).
  const [guardando, setGuardando] = useState<number | null>(null);
  const patchRow = (id: number, patch: Partial<ActoRealizado>) =>
    setRows((rs) => rs.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  const guardarDto = async (id: number, data: { descuento?: number; descuento_aplica_doctor?: boolean; coste_laboratorio?: number }) => {
    setGuardando(id);
    try {
      const r = await gestoriaService.actualizarTratamiento(id, data);
      patchRow(id, { descuento: r.descuento, descuentoAplicaDoctor: r.descuentoAplicaDoctor,
                     costeLaboratorio: r.costeLaboratorio });
    } finally { setGuardando(null); }
  };

  return (
    <>
      <AreaTabs tabs={tabs} activeTab={activeTab} onChange={onChange} className="pt-2" right={
        <>
          <span className="shrink-0 text-[12px] text-[#7f8c8d]"><b className="text-[#1500A0]">{mostrados.length}</b> acto{mostrados.length === 1 ? "" : "s"} {anyo === "" ? "(todos)" : anyo} · <b className="text-[#1500A0]">{eur(suma)}</b></span>
          <Buscador value={busca} onChange={setBusca} />
          <select value={doctor} onChange={(e) => setDoctor(e.target.value)} className="border border-[#e5e7eb] rounded-sm px-2 py-1 text-[11px]">
            <option value="">Todos los doctores</option>
            {doctores.map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
          <select value={anyo} onChange={(e) => setAnyo(e.target.value === "" ? "" : Number(e.target.value))} className="border border-[#e5e7eb] rounded-sm px-2 py-1 text-[11px]">
            <option value="">Todos los años</option>
            {anios.map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
          <select value={mes} onChange={(e) => setMes(e.target.value)} className="border border-[#e5e7eb] rounded-sm px-2 py-1 text-[11px]">
            <option value="">Todos los meses</option>
            {MESES.map((m, i) => <option key={m} value={String(i + 1).padStart(2, "0")}>{m}</option>)}
          </select>
          <select value={dia} onChange={(e) => setDia(e.target.value)} className="border border-[#e5e7eb] rounded-sm px-2 py-1 text-[11px]">
            <option value="">Todos los días</option>
            {Array.from({ length: 31 }, (_, i) => String(i + 1).padStart(2, "0")).map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
          <input value={tratamiento} onChange={(e) => setTratamiento(e.target.value)} placeholder="Tratamiento…"
            className="border border-[#e5e7eb] rounded-sm px-2 py-1 text-[11px] w-36" />
          <input value={paciente} onChange={(e) => setPaciente(e.target.value)} placeholder="Paciente…"
            className="border border-[#e5e7eb] rounded-sm px-2 py-1 text-[11px] w-32" />
        </>
      } />
      <div className="flex-1 min-h-0 overflow-auto border border-[#e5e7eb] rounded-sm m-4 mt-3">
        <table className="w-full text-[12px]">
          <thead className="sticky top-0 bg-[#1500A0] text-white text-[11px] uppercase tracking-wider">
            <tr><th className="py-1.5 px-3 text-left">Fecha</th><th className="py-1.5 px-3 text-left">Tratamiento</th>
              <th className="py-1.5 px-3 text-left">Pieza</th><th className="py-1.5 px-3 text-left">Doctor</th>
              <th className="py-1.5 px-3 text-left">Paciente</th><th className="py-1.5 px-3 text-right">Importe</th>
              <th className="py-1.5 px-3 text-right">Coste lab.</th>
              <th className="py-1.5 px-3 text-right">Dto. realizado</th><th className="py-1.5 px-3 text-center">Aplica dto. al doctor</th>
              <th className="py-1.5 px-3 text-center">Fact.</th></tr>
          </thead>
          <tbody>
            {loading ? <tr><td colSpan={10} className="text-center py-6 text-gray-400">Cargando…</td></tr>
              : mostrados.length === 0 ? <tr><td colSpan={10} className="text-center py-6 text-gray-400 italic">Sin actos en este filtro.</td></tr>
              : mostrados.map((t) => (
                <tr key={t.id} className="border-b border-[#f0f3f7] even:bg-[#FFFFFF] hover:bg-[#E6EDFF]">
                  <td className="py-1.5 px-3 text-slate-600">{fmtFecha(t.fecha)}</td>
                  <td className="py-1.5 px-3 text-slate-700">{t.tratamiento}</td>
                  <td className="py-1.5 px-3 text-slate-500">{t.piezas ?? "—"}</td>
                  <td className="py-1.5 px-3 text-slate-600">{t.doctor}</td>
                  <td className="py-1.5 px-3 text-slate-600">{t.paciente}</td>
                  <td className="py-1.5 px-3 text-right text-[#065AED]">{eur(t.importe)}</td>
                  {/* Coste de laboratorio de ESTE acto. Vacío = sin informar (≠ 0 €). */}
                  <td className="py-1.5 px-3 text-right">
                    <input type="number" min={0} step="0.01" placeholder="—"
                      defaultValue={t.costeLaboratorio ?? ""} disabled={guardando === t.id}
                      onBlur={(e) => {
                        const txt = e.target.value.trim();
                        if (txt === "") return;                       // vacío = no informado: no se toca
                        const v = Math.max(0, Number(txt) || 0);
                        if (v !== t.costeLaboratorio) guardarDto(t.id, { coste_laboratorio: v });
                      }}
                      title="Coste de laboratorio de este acto"
                      className="w-20 border border-[#e5e7eb] rounded-sm px-1 py-0.5 text-[11px] text-right outline-none focus:border-[#1ca0d1] disabled:opacity-50" />
                  </td>
                  <td className="py-1.5 px-3 text-right">
                    <input type="number" min={0} step="0.01" defaultValue={t.descuento || 0} disabled={guardando === t.id}
                      onBlur={(e) => { const v = Math.max(0, Number(e.target.value) || 0); if (v !== (t.descuento || 0)) guardarDto(t.id, { descuento: v }); }}
                      className="w-20 border border-[#e5e7eb] rounded-sm px-1 py-0.5 text-[11px] text-right outline-none focus:border-[#1ca0d1] disabled:opacity-50" />
                  </td>
                  <td className="py-1.5 px-3 text-center">
                    <input type="checkbox" checked={t.descuentoAplicaDoctor} disabled={guardando === t.id}
                      onChange={(e) => guardarDto(t.id, { descuento_aplica_doctor: e.target.checked })}
                      title="Si se marca, el descuento resta en la liquidación del doctor" className="accent-[#1ca0d1] w-3.5 h-3.5 cursor-pointer" />
                  </td>
                  <td className="py-1.5 px-3 text-center text-[11px]">{t.facturado ? "✓" : "—"}</td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
