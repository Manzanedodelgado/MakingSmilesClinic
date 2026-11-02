"use client";
/**
 * Formulario de cita (crear / editar / anular). Vivía dentro de la página de Agenda; se comparte
 * con Inicio para que el paciente de agenda reciba su próxima cita sin salir de allí.
 * `ref_` = GET /agenda/referencias (catálogos del centro y de la agenda).
 */
import { useEffect, useState } from "react";
import { X, Ban, CalendarClock, Save } from "lucide-react";
import { api } from "@/shared/lib/api";

export type Cita = {
  id: number; fecha: string; hora: string; duracion_min: number;
  gabinete_id: number | null; colaborador_id: number | null;
  estado_id: number | null; estado_nombre: string | null; estado_color: string;
  tipo_cita_id: number | null; tipo_nombre: string | null;
  paciente_id: number | null; nombre: string; apellidos: string; num_historia: string | null; telefono: string | null;
  notas: string | null; confirmada: boolean;
};
export type Ref = {
  agendas: { id: number; nombre: string; color?: string | null }[];
  gabinetes: { id: number; nombre: string }[];
  estados: { id: number; codigo: string; nombre: string; color: string }[];
  tipos_cita: { id: number; nombre: string; color?: string | null }[];
  colaboradores: { id: number; nombre: string; color?: string | null }[];
  horario: { dias?: { abierto: boolean; t1a: string; t1b: string; t2a: string; t2b: string }[]; intervalo?: number | null; vistaDefecto?: string | null };
  duraciones?: { colaborador_id: number; tipo_cita_id: number; duracion_min: number }[];
  festivos: string[];
  bloqueos?: { fecha_inicio: string; fecha_fin: string; motivo?: string | null; colaborador_id?: number | null; gabinete_id?: number | null }[];
  horarios?: { colaborador_id: number; gabinete_id: number | null; dia_semana: number; hora_inicio: string; hora_fin: string }[];
};
export type Draft = Partial<Cita> & { id?: number };
export type Pac = { id: number; nombre: string; apellidos: string; num_historia: string | null; telefono: string | null };

export function CitaModal({ draft, ref_, agendaId, onClose, onSaved, flash }: {
  draft: Draft; ref_: Ref; agendaId: number | null; onClose: () => void; onSaved: (t: string) => void; flash: (t: string, e?: boolean) => void;
}) {
  const [d, setD] = useState<Draft>(draft);
  // Estilos GesdenOne (réplica exacta captura "Crear una cita").
  const L = "gesden-label";
  const I = "gesden-input";
  // estados_cita.id es global, no por centro — se resuelve por código, nunca "el primero de la lista".
  const planificadaId = ref_.estados.find((e) => e.codigo === "planificada")?.id ?? ref_.estados[0]?.id ?? null;
  const s = (k: keyof Draft, v: unknown) => setD((p) => ({ ...p, [k]: v }));
  const esEdicion = !!d.id;
  const [buscar, setBuscar] = useState("");
  const [res, setRes] = useState<Pac[]>([]);
  useEffect(() => {
    if (buscar.trim().length < 2) { setRes([]); return; }
    const t = setTimeout(async () => {
      try { const r = await api.get<{ pacientes: Pac[] }>(`/agenda/pacientes/buscar?q=${encodeURIComponent(buscar.trim())}`); setRes(r.pacientes); } catch { setRes([]); }
    }, 250);
    return () => clearTimeout(t);
  }, [buscar]);
  const elegir = (p: Pac) => { setD((x) => ({ ...x, paciente_id: p.id, nombre: p.nombre, apellidos: p.apellidos, telefono: p.telefono || x.telefono, num_historia: p.num_historia })); setBuscar(""); setRes([]); };
  const manual = (k: keyof Draft, v: string) => setD((p) => ({ ...p, [k]: v, paciente_id: null }));

  // Duración por defecto del doctor para este tipo de cita (Config→Colaboradores→"Tiempos por tipo
  // de cita"). Solo en cita nueva: al elegir/cambiar doctor+tipo, sugiere su duración configurada.
  useEffect(() => {
    if (esEdicion || !d.colaborador_id || !d.tipo_cita_id) return;
    const m = ref_.duraciones?.find((x) => x.colaborador_id === d.colaborador_id && x.tipo_cita_id === d.tipo_cita_id);
    if (m) s("duracion_min", m.duracion_min);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [d.colaborador_id, d.tipo_cita_id]);

  // Plan de próxima cita que dejó el doctor (para recepción): se muestra y permite usar su duración.
  const [plan, setPlan] = useState<{ items: { tratamiento: string }[]; minutos: number } | null>(null);
  useEffect(() => {
    if (!d.paciente_id) { setPlan(null); return; }
    api.get<{ plan: { items: { tratamiento: string }[]; minutos: number } | null }>(`/pacientes/${d.paciente_id}/plan-proxima`)
      .then((r) => setPlan(r.plan)).catch(() => setPlan(null));
  }, [d.paciente_id]);

  async function guardar() {
    const body = {
      fecha: d.fecha, hora: d.hora, duracion_min: d.duracion_min ?? 30, agenda_id: agendaId,
      gabinete_id: d.gabinete_id ?? null, colaborador_id: d.colaborador_id ?? null,
      estado_id: d.estado_id ?? null, tipo_cita_id: d.tipo_cita_id ?? null,
      paciente_id: d.paciente_id ?? null, nombre: d.nombre ?? null, apellidos: d.apellidos ?? null,
      telefono_movil: d.telefono ?? null, num_historia: d.num_historia ?? null, notas: d.notas ?? null,
    };
    try {
      if (esEdicion) await api.put(`/agenda/citas/${d.id}`, body);
      else await api.post("/agenda/citas", body);
      // Si el paciente tenía un plan del doctor, esta cita lo consume → marcarlo agendado.
      if (!esEdicion && d.paciente_id && plan && (plan.items?.length ?? 0) > 0) {
        try { await api.post(`/pacientes/${d.paciente_id}/plan-proxima/agendar`, {}); } catch { /* no bloquea la cita */ }
      }
      onSaved(esEdicion ? "Cita guardada ✓" : "Cita creada ✓");
    } catch (e) { flash(e instanceof Error ? e.message.replace(/.*→\s*\d+\s*/, "") : "Error", true); }
  }
  async function anular() {
    if (!d.id) return;
    try { await api.put(`/agenda/citas/${d.id}/anular`, {}); onSaved("Cita anulada ✓"); }
    catch (e) { flash(e instanceof Error ? e.message : "Error", true); }
  }

  return (
    <div className="fixed inset-0 z-50 overflow-hidden">
      <div className="absolute inset-0" style={{ background: "rgba(1,30,66,.25)" }} onClick={onClose} />
      <div onClick={(e) => e.stopPropagation()} className="absolute left-0 top-0 bottom-0 w-[320px] bg-[#FFFFFF] shadow-2xl overflow-y-auto p-2">
        <div className="bg-white rounded-md shadow-sm p-4">
          <div className="flex items-center justify-between mb-3">
            <b className="text-[17px] font-bold" style={{ color: "#21A2E5" }}>{esEdicion ? "Editar cita" : "Crear una cita"}</b>
            <button onClick={onClose} className="w-7 h-7 rounded-full grid place-items-center bg-[#FFFFFF] text-[#21A2E5] hover:bg-[#21A2E5] hover:text-white transition-colors cursor-pointer" title="Cerrar" aria-label="Cerrar">
              <X className="w-4 h-4" strokeWidth={2.5} />
            </button>
          </div>
          <div className="grid grid-cols-2 gap-x-3 gap-y-2">
            <div><label className={L}>Nombre</label><input value={d.nombre || ""} onChange={(e) => manual("nombre", e.target.value)} className={I} /></div>
            <div><label className={L}>Apellidos</label><input value={d.apellidos || ""} onChange={(e) => manual("apellidos", e.target.value)} className={I} /></div>
            <div><label className={L}>Correo electrónico</label><input value="" onChange={() => {}} className={I} /></div>
            <div><label className={L}>Teléfono</label><input value={d.telefono || ""} onChange={(e) => s("telefono", e.target.value)} className={I} /></div>
            <div className="col-span-2"><label className={L}>Fecha</label><input type="date" value={d.fecha || ""} onChange={(e) => s("fecha", e.target.value)} className={I} /></div>
            <div><label className={L}>Hora</label>
              <div className="flex items-center gap-1">
                <input value={(d.hora || "11:00").split(":")[0]} onChange={(e) => s("hora", `${e.target.value.padStart(2, "0")}:${(d.hora || "11:00").split(":")[1] || "00"}`)} className={I} style={{ width: 56 }} />
                <span className="text-slate-500">:</span>
                <input value={(d.hora || "11:00").split(":")[1] || "00"} onChange={(e) => s("hora", `${(d.hora || "11:00").split(":")[0]}:${e.target.value.padStart(2, "0")}`)} className={I} style={{ width: 56 }} />
              </div>
            </div>
            <div><label className={L}>Duración</label>
            <select value={d.duracion_min ?? 30} onChange={(e) => s("duracion_min", Number(e.target.value))} className={I}>
              {(() => { const base = [15, 30, 45, 60, 75, 90, 105, 120]; const cur = d.duracion_min ?? 30; const ops = base.includes(cur) ? base : [...base, cur].sort((a, b) => a - b); return ops.map((m) => <option key={m} value={m}>{m}</option>); })()}
            </select>
            </div>
            <div className="col-span-2"><label className={L}>Motivo de la visita</label>
            <select value={d.tipo_cita_id ?? ""} onChange={(e) => s("tipo_cita_id", e.target.value ? Number(e.target.value) : null)} className={I}>
              <option value="">-- Seleccione uno --</option>
              {ref_.tipos_cita.map((t) => <option key={t.id} value={t.id}>{t.nombre}</option>)}
            </select>
            </div>
            <div className="col-span-2"><label className={L}>Observaciones</label><textarea rows={3} value={d.notas || ""} onChange={(e) => s("notas", e.target.value)} className={`${I} resize-none`} /></div>
            {/* Campos propios (gabinete/doctor/estado/paciente) */}
            <div><label className={L}>Gabinete</label>
            <select value={d.gabinete_id ?? ""} onChange={(e) => s("gabinete_id", e.target.value ? Number(e.target.value) : null)} className={I}>
              <option value="">—</option>
              {ref_.gabinetes.map((g) => <option key={g.id} value={g.id}>{g.nombre}</option>)}
            </select>
            </div>
            <div><label className={L}>Doctor</label>
            <select value={d.colaborador_id ?? ""} onChange={(e) => s("colaborador_id", e.target.value ? Number(e.target.value) : null)} className={I}>
              <option value="">Sin doctor</option>
              {ref_.colaboradores.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}
            </select>
            </div>
            <input type="hidden" value={d.estado_id ?? planificadaId ?? ""} readOnly />
            <div className="col-span-2 relative">
              <label className={L}>Buscar paciente {d.paciente_id ? "· ficha vinculada" : "· o escribe arriba (sin ficha)"}</label>
              <input value={buscar} onChange={(e) => setBuscar(e.target.value)} placeholder="Nombre, apellidos o nº historia…" className={I} />
            {res.length > 0 && (
              <div className="absolute z-20 left-0 right-0 top-full mt-0.5 bg-white border border-slate-200 rounded-sm shadow-lg max-h-56 overflow-auto">
                {res.map((p) => (
                  <button key={p.id} onClick={() => elegir(p)} className="w-full text-left px-3 py-1.5 text-[12px] hover:bg-[#E6EDFF] focus:outline-none focus:ring-2 focus:ring-cyan-500/30">
                    <b className="text-slate-900">{p.nombre} {p.apellidos}</b>
                    <span className="text-slate-500 ml-2 text-slate-500">{p.num_historia ? `#${p.num_historia}` : ""} {p.telefono || ""}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
          {plan && (plan.items?.length ?? 0) > 0 && (
            <div className="col-span-2 bg-[#FFFFFF] border border-[#DDD6FE] rounded-sm px-3 py-2 text-[12px] flex items-center justify-between gap-x-3">
              <CalendarClock className="w-4 h-4 text-[#7C3AED] shrink-0" />
              <span className="text-slate-700 font-semibold truncate">{plan.items.map((i) => i.tratamiento).join(", ")} · ~{plan.minutos} min</span>
              <button type="button" onClick={() => s("duracion_min", plan.minutos)}
                className="shrink-0 px-2 py-0.5 rounded-sm text-[10px] font-bold uppercase bg-[#7C3AED] hover:bg-[#6D28D9] text-white">Usar {plan.minutos} min</button>
            </div>
          )}
          </div>
          <div className="flex items-center gap-2 mt-4">
            <button onClick={guardar} type="submit" className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-full px-4 py-2 text-[13px] font-semibold bg-[#2DD9C3] text-[#1500A0] hover:bg-[#20BEAB] transition-colors">
              <span>✓</span><span>Aceptar</span>
            </button>
            <button onClick={esEdicion ? anular : onClose} type="button" className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-full px-4 py-2 text-[13px] font-semibold bg-[#C026D3] text-white hover:bg-[#A21CAF] transition-colors">
              <span>✕</span><span>{esEdicion ? "Anular" : "Cancelar"}</span>
            </button>
          </div>
          {esEdicion && (
            <button onClick={onClose} type="button" className="w-full mt-2 text-[12px] text-slate-500 hover:text-slate-800">Cerrar sin guardar</button>
          )}
        </div>
      </div>
    </div>
  );
}

