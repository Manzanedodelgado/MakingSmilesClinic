"use client";
/**
 * Motion › Reglas — interruptor maestro + tabla de disparadores con ON/OFF por regla
 * (formato .37: buscador + filtro y tabla con cabecera navy; sin tarjetas de KPIs).
 * El maestro escribe `agente.alex.automatizacion` (misma clave que Config › IA's › Alex).
 */
import { useState } from "react";
import { X, MessageSquare, Power, Search, ShieldCheck } from "lucide-react";
import { api } from "@/shared/lib/api";
import { GRUPOS, errMsg, type ReglasResponse } from "./types";

const GRUPO_LABEL: Record<string, string> = {
  citas: "Citas", pacientes: "Pacientes", recaptacion: "Recaptación",
  clinico: "Clínico", economico: "Económico",
};

// Interruptor canónico (mismo que CatalogoAgentes): píldora redonda navy/turquesa.
function Toggle({ on, disabled, onClick, title }: { on: boolean; disabled?: boolean; onClick: () => void; title?: string }) {
  return (
    <button onClick={onClick} disabled={disabled} title={title}
      className={`relative w-9 h-5 rounded-full transition-colors shrink-0 disabled:opacity-40 ${on ? "bg-[#2DD9C3]" : "bg-slate-300"}`}>
      <span className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-all ${on ? "left-[18px]" : "left-0.5"}`} />
    </button>
  );
}

export function MotionReglas({ reglas, onCambio }: { reglas: ReglasResponse | null; onCambio: () => void }) {
  const [search, setSearch] = useState("");
  const [grupo, setGrupo] = useState("");
  const [ocupado, setOcupado] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ t: string; e?: boolean }>({ t: "" });
  const flash = (t: string, e = false) => { setMsg({ t, e }); setTimeout(() => setMsg({ t: "" }), 3000); };

  if (!reglas) return <div className="text-[12px] text-slate-400 italic py-10 text-center">Cargando…</div>;

  const maestro = reglas.maestro;
  const activas = reglas.data.filter((r) => r.activo).length;

  async function toggleMaestro() {
    if (ocupado) return;
    setOcupado("maestro");
    try { await api.put("/motion/maestro", { activo: !maestro }); onCambio(); }
    catch (e) { flash(errMsg(e), true); }
    finally { setOcupado(null); }
  }

  async function toggleRegla(disparador: string, activo: boolean) {
    if (ocupado) return;
    setOcupado(disparador);
    try { await api.patch(`/motion/reglas/${disparador}`, { activo: !activo }); onCambio(); }
    catch (e) { flash(errMsg(e), true); }
    finally { setOcupado(null); }
  }

  const filtradas = reglas.data.filter((r) => {
    if (grupo && r.grupo !== grupo) return false;
    if (!search) return true;
    const q = search.toLowerCase();
    return r.nombre.toLowerCase().includes(q) || r.disparador.includes(q);
  });

  return (
    <div className="space-y-3 max-w-5xl">
      {msg.t && <div className={`fixed top-14 right-6 z-50 px-4 py-2.5 rounded-sm text-[12px] font-semibold shadow-lg ${msg.e ? "bg-[#C026D3] text-white" : "bg-[#2DD9C3] text-[#1500A0]"}`}>{msg.t}</div>}

      {/* Interruptor maestro — anula el envío de TODAS las automatizaciones (kill-switch) */}
      <div className={`flex items-center justify-between gap-3 px-3 py-2 rounded-sm border bg-white ${maestro ? "border-[#2DD9C3]" : "border-[#e5e7eb]"}`}>
        <div className="flex items-center gap-2.5">
          <Power className={`w-4 h-4 ${maestro ? "text-[#2DD9C3]" : "text-[#7f8c8d]"}`} />
          <div>
            <span className="text-[12px] font-semibold text-[#1500A0]">Envío de automatizaciones</span>
            <p className="text-[11px] text-[#7f8c8d]">
              {maestro
                ? "Encendido — las reglas activas envían mensajes reales a los pacientes."
                : "Apagado — ninguna automatización envía mensajes (las reglas se pueden preparar sin riesgo)."}
              {!reglas.whatsapp_activo && " · WhatsApp sin conectar (Config › IA's › Alex › Canales)."}
            </p>
          </div>
        </div>
        <Toggle on={maestro} disabled={ocupado === "maestro"} onClick={toggleMaestro}
          title={maestro ? "Apagar el envío de automatizaciones" : "Encender el envío de automatizaciones"} />
      </div>

      {/* Controles */}
      <div className="flex items-center gap-2 flex-wrap">
        <div className="relative flex-1 min-w-[220px]">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[#7f8c8d]" />
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Buscar automatización…"
            className="w-full pl-8 pr-7 py-1.5 border border-[#e5e7eb] rounded-sm text-[12px] text-[#333] bg-white focus:border-[#1ca0d1] focus:ring-1 focus:ring-[#1ca0d1]/20 outline-none" />
          {search && (
            <button type="button" onClick={() => setSearch("")} className="absolute right-2 top-1/2 -translate-y-1/2 text-[#7f8c8d] hover:text-[#C026D3]">
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
        <div className="flex border border-[#e5e7eb] rounded-sm overflow-hidden">
          {GRUPOS.map(([id, label]) => (
            <button key={id} onClick={() => setGrupo(id)}
              className={`px-2.5 py-1.5 text-[10px] font-semibold uppercase transition-colors ${grupo === id ? "bg-[#1500A0] text-white" : "bg-white text-[#1500A0] hover:bg-[#E6EDFF]"}`}>
              {id === "" ? `Todas (${reglas.data.length})` : label}
            </button>
          ))}
        </div>
        <span className="text-[10px] font-semibold uppercase text-[#2DD9C3] bg-[#FFFFFF] border border-[#2DD9C3]/40 rounded-sm px-2 py-1">{activas} activas</span>
      </div>

      {/* Tabla de reglas */}
      <div className="border border-[#e5e7eb] rounded-sm overflow-hidden bg-white">
        <div className="bg-[#1500A0] text-white grid grid-cols-[52px_1fr_170px_110px_80px_90px] px-3 py-2 text-[10px] font-semibold uppercase tracking-wider">
          <span>ON/OFF</span><span>Automatización</span><span>Disparador</span><span>Grupo</span>
          <span className="text-center">Enviados</span><span className="text-center">Último envío</span>
        </div>
        {filtradas.map((r, i) => (
          <div key={r.disparador}
            className={`grid grid-cols-[52px_1fr_170px_110px_80px_90px] px-3 py-2 items-center border-b border-[#e5e7eb] last:border-b-0 ${i % 2 ? "bg-[#FFFFFF]" : "bg-white"}`}>
            <Toggle on={r.activo} disabled={ocupado === r.disparador}
              title={r.activo ? "Apagar esta regla" : "Encender esta regla"}
              onClick={() => toggleRegla(r.disparador, r.activo)} />
            <div className="min-w-0 pr-2">
              <span className="text-[12px] font-semibold text-[#1500A0] truncate block">{r.nombre}</span>
              <span className="text-[10px] text-[#7f8c8d] truncate block">
                {r.descripcion}
                {r.solo_consentidos && (
                  <span className="inline-flex items-center gap-0.5 ml-1 text-[#1ca0d1]"><ShieldCheck className="w-2.5 h-2.5" />consentimiento</span>
                )}
              </span>
            </div>
            <span className="text-[11px] font-mono text-[#333] truncate">{r.disparador}</span>
            <span className="text-[11px] text-[#333] flex items-center gap-1">
              <MessageSquare className="w-3 h-3 text-[#2DD9C3] shrink-0" />{GRUPO_LABEL[r.grupo] ?? r.grupo}
            </span>
            <span className="text-[12px] font-semibold text-[#1500A0] text-center">{r.enviados}</span>
            <span className="text-[11px] text-[#7f8c8d] text-center">
              {r.ultimo_envio ? new Date(r.ultimo_envio).toLocaleDateString("es-ES") : "—"}
            </span>
          </div>
        ))}
        {filtradas.length === 0 && <div className="px-3 py-8 text-center text-[12px] text-slate-400 italic">Sin resultados</div>}
      </div>
    </div>
  );
}
