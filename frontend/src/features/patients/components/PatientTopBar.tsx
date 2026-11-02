"use client";
/**
 * Barra superior PERSISTENTE del área Pacientes — réplica EXACTA del .37 (PatientLayout):
 * Nº Historial (texto rosa) · nombre · ALERTAS (rosa) · Edad · Teléfono · Tarifa · buscador · NUEVO.
 * Celdas en gris cuando no hay paciente. Dos líneas de acento debajo (#00e5ff + #1500A0).
 */
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { X, ChevronDown, Plus, Search, Calendar, AlertTriangle, Phone } from "lucide-react";
import { api } from "@/shared/lib/api";
import { patientService } from "../services/patientService";
import { patientSession } from "../store/patientSession";
import { NuevoPacienteModal } from "./NuevoPacienteModal";
import type { PacienteBusqueda, PacienteCabecera } from "../types/patient";

type CitaHoy = { id: number; hora: string | null; paciente_id: number | null; nombre: string; apellidos: string; num_historia: string | null; tipo_nombre: string | null };
const pad = (n: number) => String(n).padStart(2, "0");
const hoyYMD = () => { const d = new Date(); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`; };

// Tarifa(s) en formato corto para la cabecera: varias palabras → iniciales (SEGURIDAD SOCIAL→SS),
// una palabra → 3 primeras letras (Privada→PRI). Mantiene el nombre completo en el tooltip.
const abreviarTarifa = (full: string | null): string => {
  if (!full) return "—";
  return full.split("/").map((s) => {
    const w = s.trim().split(/\s+/).filter(Boolean);
    return w.length > 1 ? w.map((p) => p[0]).join("").toUpperCase() : (w[0] || "").slice(0, 3).toUpperCase();
  }).join("/");
};

export function PatientTopBar({ cab, onClose }: { cab: PacienteCabecera | null; onClose: () => void }) {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [res, setRes] = useState<PacienteBusqueda[]>([]);
  const [total, setTotal] = useState(0);          // cuántos hay de verdad, no cuántos caben
  const [cargandoMas, setCargandoMas] = useState(false);
  const [open, setOpen] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Desplegable de la agenda de hoy.
  const [agendaOpen, setAgendaOpen] = useState(false);
  const [agendaCitas, setAgendaCitas] = useState<CitaHoy[]>([]);
  const [loadingAg, setLoadingAg] = useState(false);
  const [nuevoOpen, setNuevoOpen] = useState(false);   // alta de paciente (dispara puente Romexis)

  const toggleAgenda = async () => {
    if (agendaOpen) { setAgendaOpen(false); return; }
    setOpen(false); setAgendaOpen(true); setLoadingAg(true);
    try {
      const r = await api.get<{ citas: CitaHoy[] }>(`/agenda/citas?fecha=${hoyYMD()}&incluir_anuladas=false`);
      setAgendaCitas((r.citas ?? []).filter((c) => c.paciente_id).sort((a, b) => (a.hora ?? "").localeCompare(b.hora ?? "")));
    } catch { setAgendaCitas([]); }
    finally { setLoadingAg(false); }
  };

  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    if (q.trim().length < 2) { setRes([]); setTotal(0); setOpen(false); return; }
    timer.current = setTimeout(async () => {
      try {
        const r = await patientService.buscar(q.trim());
        setRes(r.pacientes); setTotal(r.total ?? r.pacientes.length); setOpen(true);
      } catch { setRes([]); setTotal(0); }
    }, 250);
    return () => { if (timer.current) clearTimeout(timer.current); };
  }, [q]);

  // Cargar otro paciente pasa por el guard (si el actual tiene cambios sin guardar, pregunta).
  // "Ver los N" pide el resto sin cambiar la búsqueda: el desplegable enseña un tramo por
  // manejabilidad, pero el usuario siempre puede llegar a todos.
  const verTodos = async () => {
    setCargandoMas(true);
    try {
      const r = await patientService.buscar(q.trim(), 200);
      setRes(r.pacientes); setTotal(r.total ?? r.pacientes.length);
    } finally { setCargandoMas(false); }
  };

  const abrir = (id: number) => {
    setQ(""); setRes([]); setTotal(0); setOpen(false); setAgendaOpen(false);
    patientSession.requestClose(() => { patientSession.open(id, null); router.push(`/pacientes/${id}/ficha`); });
  };
  const alertas = cab?.alertas_activas ?? 0;

  return (
    <>
      <div className="flex-shrink-0 flex items-stretch h-[34.2px] border-b border-[#e5e7eb] uppercase text-[12px] text-[#333333] relative z-30">
        {/* Nº Historial */}
        <div className="w-24 flex-shrink-0 px-2 py-1 text-center flex flex-col items-center justify-center border-r border-white bg-[#1500A0]">
          {cab ? (
            <span className="font-semibold text-[16px] tracking-tighter leading-none text-[#FF66B2]" style={{ textShadow: "0 0 6px rgba(255,102,178,0.35)" }}>
              {(cab.num_historia ?? "").slice(-4)}
            </span>
          ) : (
            <span className="font-semibold text-[11px] uppercase tracking-tighter leading-tight text-[#FF007F]">Nº Historial</span>
          )}
        </div>
        {/* Nombre */}
        <div className="flex-[2] min-w-[320px] px-2 flex flex-col justify-center bg-white border-r border-[#e5e7eb]">
          {cab ? (
            <div className="flex items-baseline gap-2 min-w-0">
              <span className="text-[14px] font-semibold leading-tight text-[#1500A0] truncate">{cab.apellidos}, {cab.nombre}</span>
              {cab.nif && <span className="text-[12px] text-slate-500 shrink-0 normal-case">{cab.nif}</span>}
            </div>
          ) : (
            <span className="text-slate-400 italic">Ningún paciente seleccionado</span>
          )}
        </div>
        {/* Alertas: parpadea si hay datos críticos del paciente; al pasar el ratón, emergente con la lista */}
        <div className={`relative group w-32 flex-shrink-0 px-2 py-1 flex flex-col items-center justify-center text-center border-r border-[#e5e7eb] ${cab ? "bg-white" : "bg-white"}`}>
          <span className={`font-semibold text-[14px] leading-tight text-[#FF007F] ${alertas > 0 ? "alertas-text-pulse" : ""}`}>ALERTAS</span>
          {!!cab && (cab.alertas_lista?.length ?? 0) > 0 && (
            <div className="absolute top-full left-1/2 -translate-x-1/2 mt-1 hidden group-hover:block z-[100] w-72 bg-white border border-[#ffc8ec] rounded-lg shadow-[0_10px_40px_rgba(0,0,0,0.18)] p-2 normal-case text-left">
              <div className="text-[10px] font-bold text-[#FF007F] uppercase tracking-widest mb-1 px-1">Alertas del paciente</div>
              <ul className="flex flex-col">
                {cab.alertas_lista.map((a, i) => (
                  <li key={i} className="flex items-start gap-1.5 text-[12px] text-[#374151] px-1 py-1 border-b border-[#fff0fb] last:border-0">
                    <AlertTriangle className="w-3.5 h-3.5 text-[#FF007F] mt-0.5 shrink-0" /><span>{a}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
        {/* Edad */}
        <div className={`w-28 flex-shrink-0 px-2 py-1 flex flex-col items-center justify-center border-r border-[#e5e7eb] text-center ${cab ? "bg-white" : "bg-white"}`}>
          {cab ? <span className="text-[13px] text-[#1500A0]">{cab.edad != null ? `${cab.edad} AÑOS` : "-- AÑOS"}</span>
            : <span className="text-[12px] uppercase tracking-tighter text-[#7f8c8d]">Edad</span>}
        </div>
        {/* Teléfono */}
        <div className={`w-32 flex-shrink-0 px-2 py-1 flex flex-col items-center justify-center border-r border-[#e5e7eb] text-center ${cab ? "bg-white" : "bg-white"}`}>
          {cab ? <span className="text-[13px] text-[#1500A0]">{cab.telefono_movil || "--- -- -- --"}</span>
            : <span className="text-[12px] uppercase tracking-tighter text-[#7f8c8d]">Teléfono</span>}
        </div>
        {/* Tarifa */}
        <div className={`w-20 flex-shrink-0 px-2 py-1 flex flex-col items-center justify-center border-r border-[#e5e7eb] text-center ${cab ? "bg-white" : "bg-white"}`}>
          {cab ? <span title={cab.tarifa ?? undefined} className="text-[13px] font-semibold text-[#1500A0] uppercase tracking-tighter truncate max-w-full">{abreviarTarifa(cab.tarifa)}</span>
            : <span className="text-[12px] uppercase tracking-tighter text-[#7f8c8d]">Tarifa</span>}
        </div>
        {/* Buscador + Nuevo */}
        <div className="flex-1 min-w-[280px] px-2 py-1 flex items-center gap-2 bg-white border-r border-[#e5e7eb] relative">
          <div className="relative flex-1">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar por NumPac, nombre, apellidos, teléfono…"
              className="w-full pl-8 pr-8 py-1.5 bg-[#FFFFFF] border border-transparent rounded-[4px] text-[12px] focus:ring-1 focus:ring-[#3388FF] focus:border-[#3388FF] outline-none normal-case" />
            {q && (
              <button type="button" onClick={() => { setQ(""); setOpen(false); }}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-[#C026D3]">
                <X className="w-3.5 h-3.5" />
              </button>
            )}
            {open && (
              <div className="absolute right-0 top-full mt-1 w-[420px] max-h-[450px] overflow-hidden flex flex-col bg-white shadow-[0_10px_40px_rgba(0,0,0,0.18)] border border-[#e5e7eb] rounded-lg z-[100] normal-case">
                <div className="flex items-center justify-between px-4 py-2.5 border-b bg-white/80">
                  <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-widest">
                    Resultados ({total > res.length ? `${res.length} de ${total}` : res.length})
                  </span>
                  <button onClick={() => setOpen(false)} className="p-1.5 hover:bg-slate-200 rounded-full"><X className="w-3.5 h-3.5 text-slate-500" /></button>
                </div>
                <div className="overflow-y-auto">
                  {res.length === 0 && <p className="p-6 text-center text-[12px] text-slate-400 italic">Sin resultados</p>}
                  {res.map((p) => (
                    <button key={p.id} onClick={() => abrir(p.id)} className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-[#E6EDFF] border-b border-gray-50 last:border-0 text-left">
                      <div className="flex flex-col min-w-0">
                        <span className="text-[13px] text-[#1500A0] truncate">{p.apellidos}, {p.nombre}</span>
                        <div className="flex items-center gap-2 mt-0.5">
                          <span className="text-[10px] font-semibold text-[#1ca0d1] bg-[#FFFFFF] px-1.5 py-0.5 rounded-[3px] border border-[#ffc8ec]">{p.num_historia ?? "—"}</span>
                          <span className="text-[10px] text-slate-400 truncate">{p.nif || "Sin NIF"}</span>
                          {p.telefono && <span className="flex items-center gap-1 text-[10px] text-slate-500 shrink-0"><Phone className="w-3 h-3 text-[#1ca0d1]" />{p.telefono}</span>}
                        </div>
                      </div>
                    </button>
                  ))}
                  {total > res.length && (
                    <button onClick={verTodos} disabled={cargandoMas}
                            className="w-full px-4 py-2.5 text-[12px] font-semibold text-[#1ca0d1] hover:bg-[#E6EDFF] border-t border-gray-100">
                      {cargandoMas ? "Cargando…"
                        : `Ver los ${total} — hay ${total - res.length} más que no caben aquí`}
                    </button>
                  )}
                  {total > 200 && res.length >= 200 && (
                    <p className="px-4 py-2 text-[11px] text-[#7C3AED] italic border-t border-gray-100">
                      Hay {total} coincidencias; se muestran 200. Añade un apellido o el nº de historia.
                    </p>
                  )}
                </div>
              </div>
            )}
            {/* Flecha: pacientes en la agenda de hoy */}
            <button onClick={toggleAgenda} title="Pacientes con cita hoy"
              className="absolute right-1.5 top-1/2 -translate-y-1/2 flex items-center justify-center w-6 h-6 rounded-[4px] text-[#1500A0] hover:bg-[#e6edff]">
              <ChevronDown className={`w-4 h-4 transition-transform ${agendaOpen ? "rotate-180" : ""}`} />
            </button>
          </div>
          {agendaOpen && (
            <>
              <div className="fixed inset-0 z-[90]" onClick={() => setAgendaOpen(false)} />
              <div className="absolute right-2 top-full mt-1 w-[360px] max-h-[450px] overflow-hidden flex flex-col bg-white shadow-[0_10px_40px_rgba(0,0,0,0.18)] border border-[#e5e7eb] rounded-lg z-[100] normal-case">
                <div className="flex items-center justify-between px-4 py-2.5 border-b bg-white/80">
                  <span className="flex items-center gap-1.5 text-[11px] font-semibold text-slate-500 uppercase tracking-widest"><Calendar className="w-3.5 h-3.5" /> Citas de hoy ({agendaCitas.length})</span>
                  <button onClick={() => setAgendaOpen(false)} className="p-1.5 hover:bg-slate-200 rounded-full"><X className="w-3.5 h-3.5 text-slate-500" /></button>
                </div>
                <div className="overflow-y-auto">
                  {loadingAg && <p className="p-6 text-center text-[12px] text-slate-400 italic">Cargando…</p>}
                  {!loadingAg && agendaCitas.length === 0 && <p className="p-6 text-center text-[12px] text-slate-400 italic">Sin citas hoy</p>}
                  {agendaCitas.map((c) => (
                    <button key={c.id} onClick={() => abrir(c.paciente_id!)} className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-[#E6EDFF] border-b border-gray-50 last:border-0 text-left">
                      <span className="text-[13px] font-bold text-[#1500A0] w-12 shrink-0">{c.hora || "--:--"}</span>
                      <div className="flex flex-col min-w-0">
                        <span className="text-[13px] text-[#1500A0] truncate">{c.apellidos}, {c.nombre}</span>
                        <div className="flex items-center gap-2 mt-0.5">
                          <span className="text-[10px] font-semibold text-[#1ca0d1] bg-[#FFFFFF] px-1.5 py-0.5 rounded-[3px] border border-[#ffc8ec]">{c.num_historia ?? "—"}</span>
                          {c.tipo_nombre && <span className="text-[10px] text-slate-400 truncate">{c.tipo_nombre}</span>}
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            </>
          )}
          <button onClick={() => setNuevoOpen(true)} title="Nuevo paciente (se crea también en Romexis)"
            className="flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-semibold text-white bg-[#3388FF] hover:bg-[#1500A0] rounded-[4px] uppercase tracking-tight whitespace-nowrap transition-colors">
            <Plus className="w-3.5 h-3.5" /> Nuevo
          </button>
        </div>
        {/* Cerrar paciente */}
        <button onClick={onClose} title="Cerrar paciente"
          className="flex-shrink-0 flex items-center justify-center px-2 h-full text-slate-400 hover:text-[#1500A0] hover:bg-[#E6EDFF] transition-colors border-r border-[#e5e7eb]">
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
      <div className="h-[2px] bg-[#00e5ff] flex-shrink-0" />
      <div className="h-[2px] bg-[#1500A0] flex-shrink-0" />
      {nuevoOpen && (
        <NuevoPacienteModal onCerrar={() => setNuevoOpen(false)}
          onCreado={(id) => { setNuevoOpen(false); router.push(`/pacientes/${id}/ficha`); }} />
      )}
    </>
  );
}
