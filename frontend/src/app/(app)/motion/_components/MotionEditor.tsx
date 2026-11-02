"use client";
import { Eye, Save, Zap } from "lucide-react";
/**
 * Motion › Editor — edita la regla de un disparador del catálogo: nombre, cuerpo y
 * previsualización de candidatos REALES (preview del backend: no envía ni registra nada).
 * Guardar NO enciende la regla; el ON/OFF vive en Reglas.
 */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/shared/lib/api";
import { ClinicalButton, ClinicalCard, INPUT, LABEL, SECTION_SUB, SELECT, SectionHeader, TEXTAREA } from "@/shared/components";
import { errMsg, type ReglasResponse } from "./types";

interface PreviewItem { clave: string; telefono: string; mensaje: string }
interface PreviewResponse { resultado: Record<string, PreviewItem[]> }

export function MotionEditor({ reglas, onGuardado }: { reglas: ReglasResponse | null; onGuardado: () => void }) {
  const [disparador, setDisparador] = useState("");
  const [nombre, setNombre] = useState("");
  const [cuerpo, setCuerpo] = useState("");
  const [preview, setPreview] = useState<PreviewItem[] | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [msg, setMsg] = useState<{ t: string; e?: boolean }>({ t: "" });
  const flash = (t: string, e = false) => { setMsg({ t, e }); setTimeout(() => setMsg({ t: "" }), 3500); };

  const regla = useMemo(
    () => reglas?.data.find((r) => r.disparador === disparador) ?? null,
    [reglas, disparador],
  );

  // Al elegir disparador, carga su regla actual en el formulario.
  useEffect(() => {
    if (!regla) return;
    setNombre(regla.nombre);
    setCuerpo(regla.cuerpo);
    setPreview(null);
  }, [regla]);

  if (!reglas) return <div className="text-[12px] text-slate-400 italic py-10 text-center">Cargando…</div>;

  async function guardar() {
    if (!disparador || !nombre.trim() || !cuerpo.trim()) { flash("Elige disparador y rellena nombre y mensaje", true); return; }
    setOcupado(true);
    try {
      await api.put(`/motion/reglas/${disparador}/plantilla`, { nombre: nombre.trim(), cuerpo });
      flash("Regla guardada ✓");
      onGuardado();
    } catch (e) { flash(errMsg(e), true); }
    finally { setOcupado(false); }
  }

  async function verCandidatos() {
    if (!disparador) return;
    setOcupado(true);
    try {
      const r = await api.post<PreviewResponse>("/motion/preview", { disparador });
      setPreview(r.resultado[disparador] ?? []);
    } catch (e) { flash(errMsg(e), true); }
    finally { setOcupado(false); }
  }

  return (
    <div className="max-w-3xl space-y-3">
      {msg.t && <div className={`fixed top-14 right-6 z-50 px-4 py-2.5 rounded-sm text-[12px] font-semibold shadow-lg ${msg.e ? "bg-[#C026D3] text-white" : "bg-[#2DD9C3] text-[#1500A0]"}`}>{msg.t}</div>}

      <ClinicalCard>
        <SectionHeader title="Disparador" icon={Zap} />
        <p className={SECTION_SUB}>Cada regla corresponde a un disparador del motor. El canal es WhatsApp.</p>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className={LABEL}>Disparador</label>
            <select value={disparador} onChange={(e) => setDisparador(e.target.value)} className={SELECT}>
              <option value="">— Elegir disparador —</option>
              {reglas.data.map((r) => (
                <option key={r.disparador} value={r.disparador}>{r.nombre} ({r.disparador})</option>
              ))}
            </select>
          </div>
          <div>
            <label className={LABEL}>Nombre de la regla</label>
            <input value={nombre} onChange={(e) => setNombre(e.target.value)} className={INPUT}
              placeholder="Ej: Recordatorio 24h antes de cita" disabled={!disparador} />
          </div>
        </div>
        {regla && <p className="text-[11px] text-[#7f8c8d] mt-2">{regla.descripcion} · Estado: <span className={regla.activo ? "text-[#2DD9C3] font-semibold" : "text-[#7f8c8d]"}>{regla.activo ? "ACTIVA" : "apagada"}</span></p>}
      </ClinicalCard>

      <ClinicalCard>
        <SectionHeader title="Mensaje" icon={Save}
          action={<div className="flex items-center gap-2">
            <ClinicalButton variant="secondary" icon={Eye} onClick={verCandidatos} disabled={ocupado || !disparador}
              title="Muestra a quién se enviaría AHORA. No envía nada.">Ver candidatos</ClinicalButton>
            <ClinicalButton variant="save" icon={Save} onClick={guardar} disabled={ocupado || !disparador}>Guardar</ClinicalButton>
          </div>} />
        <textarea value={cuerpo} onChange={(e) => setCuerpo(e.target.value)} rows={6} className={TEXTAREA}
          disabled={!disparador} placeholder="Hola {{nombre}}, le recordamos su cita del {{fecha}} a las {{hora}} en {{clinica}}…" />
        <p className="text-[10px] text-[#7f8c8d] mt-1">
          Variables: <code className="font-mono text-[#1500A0]">{"{{nombre}} {{fecha}} {{hora}} {{clinica}}"}</code>
        </p>
      </ClinicalCard>

      {preview !== null && (
        <ClinicalCard>
          <SectionHeader title={`Candidatos ahora mismo (${preview.length})`} icon={Eye} />
          <p className={SECTION_SUB}>Vista previa real del motor: a quién tocaría enviarle este mensaje en este momento. <b>No se ha enviado nada.</b></p>
          {preview.length === 0 ? (
            <p className="text-[12px] text-slate-400 italic">Ahora mismo no hay ningún candidato para este disparador.</p>
          ) : (
            <div className="space-y-1.5 max-h-72 overflow-y-auto">
              {preview.slice(0, 20).map((p) => (
                <div key={p.clave} className="bg-[#FFFFFF] border border-[#e5e7eb] rounded-sm px-2.5 py-1.5">
                  <div className="text-[10px] font-mono text-[#7f8c8d]">{p.clave} · {p.telefono}</div>
                  <div className="text-[11px] text-[#333] whitespace-pre-wrap">{p.mensaje}</div>
                </div>
              ))}
              {preview.length > 20 && <p className="text-[10px] text-[#7f8c8d]">… y {preview.length - 20} más</p>}
            </div>
          )}
        </ClinicalCard>
      )}
    </div>
  );
}
