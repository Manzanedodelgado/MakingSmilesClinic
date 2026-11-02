"use client";
/**
 * Tab PERIODONTOGRAMA — funciona como "Tratamientos Previos" pero de periodoncia:
 * ver el historial de estudios perio hechos, cargar cualquiera, y registrar nuevos.
 * El chart es solo lectura al ver; editable al crear un estudio nuevo. Solo BBDD nueva.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, Plus, Save } from "lucide-react";
import { patientService } from "../../services/patientService";
import type { PeriodontogramaData, PerioSitio, PerioEstudio, OdontogramaData } from "../../types/patient";
import { blankTeeth, PerioChart, type Pt, type Td } from "./PerioChart";
import { construirOdontogramaClinico, estadosEstructurales, type EstadoEstructural } from "../odontograma/odontogramaData";

// Aplica los estados ESTRUCTURALES de O1 (ausente/implante/corona/puente) sobre el chart perio.
function aplicarEstructural(teeth: Record<number, Td>, estr: Record<string, EstadoEstructural>): Record<number, Td> {
  const out: Record<number, Td> = { ...teeth };
  for (const [fdi, e] of Object.entries(estr)) {
    const n = Number(fdi);
    if (out[n]) out[n] = { ...out[n], missing: out[n].missing || e.missing, implante: e.implante, corona: e.corona, puente: e.puente };
  }
  return out;
}

const toPt = (s: PerioSitio): Pt => ({ ps: s.ps, rec: s.rec, ss: s.ss, ip: s.ip });
const tri = (a: PerioSitio[]): [Pt, Pt, Pt] => [toPt(a[0] ?? {} as PerioSitio), toPt(a[1] ?? {} as PerioSitio), toPt(a[2] ?? {} as PerioSitio)];

function buildTeeth(data: PeriodontogramaData): Record<number, Td> {
  const teeth = blankTeeth();
  for (const [fdi, pz] of Object.entries(data.piezas)) {
    const n = Number(fdi);
    if (!teeth[n]) continue;
    teeth[n] = { ...teeth[n], v: tri(pz.v || []), p: tri(pz.p || []), mob: (Math.min(3, pz.mob || 0) as 0 | 1 | 2 | 3) };
  }
  return teeth;
}

// Chart (Td) → payload del POST (un objeto por pieza FDI).
function teethToPayload(teeth: Record<number, Td>): Record<string, { v: PerioSitio[]; p: PerioSitio[]; mob: number }> {
  const piezas: Record<string, { v: PerioSitio[]; p: PerioSitio[]; mob: number }> = {};
  for (const [n, t] of Object.entries(teeth)) piezas[n] = { v: t.v, p: t.p, mob: t.mob };
  return piezas;
}

const fmtFecha = (s: string | null) => (s ? new Date(s).toLocaleDateString("es-ES", { day: "2-digit", month: "short", year: "numeric" }) : "Sin fecha");

function Metric({ label, value, alert, teal }: { label: string; value: string; alert?: boolean; teal?: boolean }) {
  return (
    <div className={`flex items-center gap-2 px-3.5 py-1 rounded-md border ${alert ? (teal ? "bg-[#FFFFFF] border-[#DDD6FE]" : "bg-[#FFFFFF] border-[#F0C4F7]") : "bg-[#FFFFFF] border-[#c7d8ff]"}`}>
      <span className="text-[8px] font-bold uppercase tracking-[0.12em] text-[#1500A0] opacity-70">{label}</span>
      <span className={`text-[16px] font-extrabold leading-none ${alert ? (teal ? "text-[#1ca0d1]" : "text-[#1500A0]") : "text-[#065AED]"}`}>{value}</span>
    </div>
  );
}

export function Periodontograma({ patientId }: { patientId: number }) {
  const [data, setData] = useState<PeriodontogramaData | null>(null);
  const [estudios, setEstudios] = useState<PerioEstudio[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [editTeeth, setEditTeeth] = useState<Record<number, Td>>(() => blankTeeth());
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");
  const [edad, setEdad] = useState<number | null>(null);   // dentición infantil/mixta por edad
  const [odo, setOdo] = useState<OdontogramaData | null>(null);   // O1: para derivar ausente/implante/corona/puente
  const flash = (t: string) => { setMsg(t); setTimeout(() => setMsg(""), 2500); };

  useEffect(() => {
    let alive = true;
    patientService.cabecera(patientId).then((c) => { if (alive) setEdad(c.edad); }).catch(() => {});
    patientService.odontograma(patientId).then((d) => { if (alive) setOdo(d); }).catch(() => {});
    return () => { alive = false; };
  }, [patientId]);

  const cargar = useCallback(async (exploracionId?: number) => {
    setLoading(true); setError(null);
    try {
      const [d, h] = await Promise.all([
        patientService.periodontograma(patientId, exploracionId),
        patientService.periodontogramaEstudios(patientId),
      ]);
      setData(d); setEstudios(h.estudios || []);
    } catch (e) { setError(e instanceof Error ? e.message : "No se pudo cargar el periodontograma"); }
    finally { setLoading(false); }
  }, [patientId]);
  useEffect(() => { cargar(); }, [cargar]);

  // Estados estructurales (ausente/implante/corona/puente) derivados del render activo de O1.
  const estructural = useMemo(
    () => estadosEstructurales(construirOdontogramaClinico(odo?.teeth ?? [], odo?.realizados ?? [], { soloInicial: true })),
    [odo],
  );
  const teeth = useMemo(() => aplicarEstructural(data ? buildTeeth(data) : blankTeeth(), estructural), [data, estructural]);

  const onCell = (n: number, face: "v" | "p", i: number, field: "ps" | "rec" | "ss" | "ip", value: number | boolean) =>
    setEditTeeth((prev) => {
      const t = prev[n]; const arr = [...t[face]] as [Pt, Pt, Pt];
      arr[i] = { ...arr[i], [field]: value } as Pt;
      return { ...prev, [n]: { ...t, [face]: arr } };
    });
  const onMob = (n: number, value: number) =>
    setEditTeeth((prev) => ({ ...prev, [n]: { ...prev[n], mob: (value % 4) as 0 | 1 | 2 | 3 } }));

  const nuevoEstudio = () => { setEditTeeth(aplicarEstructural(blankTeeth(), estructural)); setEditing(true); };
  const guardar = async () => {
    setSaving(true);
    try {
      const r = await patientService.guardarPeriodontograma(patientId, teethToPayload(editTeeth));
      setEditing(false); flash("Estudio guardado ✓");
      await cargar(r.exploracion_id);
    } catch { flash("Error al guardar"); }
    finally { setSaving(false); }
  };

  if (loading && !data) return <div className="flex-1 flex items-center justify-center"><Loader2 className="w-5 h-5 animate-spin text-[#1500A0]" /></div>;
  if (error) return <p className="text-[12px] text-[#C026D3] p-4">{error}</p>;

  const vacio = !data || Object.keys(data.piezas).length === 0;

  return (
    <div className="flex flex-col h-full overflow-hidden bg-[#FFFFFF]">
      {msg && <div className="fixed top-14 right-6 z-[60] px-4 py-2.5 rounded-sm text-[12px] font-semibold shadow-lg bg-[#2DD9C3] text-[#1500A0]">{msg}</div>}

      {/* Cabecera: título + selector de estudios + métricas + acciones */}
      <div className="flex items-center justify-between flex-wrap gap-2 px-5 py-2.5 bg-white border-b border-[#dce5f2] shrink-0">
        <div className="flex items-center gap-4">
          <div>
            <div className="text-[11px] font-extrabold text-[#065AED] uppercase tracking-[0.14em]">Periodontograma</div>
            <div className="text-[9px] text-slate-400 mt-0.5">{editing ? "Nuevo estudio — sin guardar" : fmtFecha(data?.fecha ?? null)}</div>
          </div>
          {!editing && estudios.length > 0 && (
            <select value={data?.exploracion_id ?? ""} onChange={(e) => cargar(Number(e.target.value))}
              className="border border-[#dce5f2] rounded-sm px-2 py-1 text-[12px] text-[#065AED] outline-none focus:border-[#1ca0d1] cursor-pointer">
              {estudios.map((es, i) => (
                <option key={es.exploracion_id} value={es.exploracion_id}>
                  Estudio {estudios.length - i}{es.fecha ? ` · ${fmtFecha(es.fecha)}` : ""} · BOP {es.bop}% · Bolsas≥4: {es.bolsas4}
                </option>
              ))}
            </select>
          )}
        </div>
        <div className="flex items-center gap-2">
          {!editing && data && !vacio && (
            <>
              <Metric label="BOP" value={`${data.bop}%`} alert={data.bop > 20} />
              <Metric label="Bolsas ≥4" value={String(data.bolsas4)} alert={data.bolsas4 > 0} teal />
            </>
          )}
          {editing ? (
            <>
              <button onClick={() => setEditing(false)} className="px-3 py-1.5 text-[12px] border border-[#e5e7eb] text-[#7f8c8d] rounded-sm hover:bg-[#E6EDFF] cursor-pointer">Cancelar</button>
              <button onClick={guardar} disabled={saving} className="flex items-center gap-1.5 px-4 py-1.5 text-[12px] font-semibold uppercase tracking-wider text-[#1500A0] rounded-sm bg-[#2DD9C3] hover:bg-[#20BEAB] border border-[#1AA897] disabled:opacity-50 cursor-pointer"><Save className="w-3.5 h-3.5" /> {saving ? "Guardando…" : "Guardar"}</button>
            </>
          ) : (
            <button onClick={nuevoEstudio} className="flex items-center gap-1 px-3 py-1.5 text-[12px] font-semibold uppercase tracking-wider bg-white text-[#1500A0] border border-[#9ca3af] rounded-sm hover:bg-[#E6EDFF] cursor-pointer"><Plus className="w-3.5 h-3.5" /> Nuevo estudio</button>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-auto p-4">
        {editing ? (
          <>
            <p className="text-[11px] text-[#1ca0d1] mb-2">Rellena bolsa, recesión, sangrado (clic), placa (clic) y movilidad (clic en M). Al guardar se registra como nuevo estudio con la fecha de hoy.</p>
            <PerioChart teeth={editTeeth} editable onCell={onCell} onMob={onMob} edad={edad} />
          </>
        ) : vacio ? (
          <div className="flex flex-col items-center gap-3 text-slate-400 py-12">
            <p className="text-[12px] italic">Sin estudios periodontales registrados para este paciente.</p>
            <button onClick={nuevoEstudio} className="flex items-center gap-1 px-3 py-1.5 text-[12px] font-semibold uppercase text-[#1500A0] border border-[#9ca3af] rounded-sm hover:bg-[#E6EDFF] cursor-pointer"><Plus className="w-3.5 h-3.5" /> Nuevo estudio</button>
          </div>
        ) : (
          <PerioChart teeth={teeth} edad={edad} />
        )}
      </div>
    </div>
  );
}
