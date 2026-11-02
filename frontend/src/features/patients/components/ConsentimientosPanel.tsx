"use client";
/**
 * Consentimientos informados COEM del paciente — dentro del emergente Documentos.
 * Generar (rellena el PDF COEM oficial con clínica/doctor/paciente/fecha) → firma digital
 * en pantalla (lienzo) → PDF firmado. Backend: /consentimientos/*.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, X, FileSignature, Plus, Eye, Trash2, Eraser, CheckCircle2, Clock } from "lucide-react";
import { API_BASE } from "@/shared/lib/api";
import { Modal, ModalBody, ModalFooter, ModalButton } from "@/shared/components";
import { patientService } from "../services/patientService";
import type { Consentimiento, ConsentPlantilla } from "../types/patient";

type Doctor = { id: number; nombre: string; es_doctor?: boolean };

export function ConsentimientosPanel({ patientId }: { patientId: number }) {
  const [plantillas, setPlantillas] = useState<ConsentPlantilla[]>([]);
  const [lista, setLista] = useState<Consentimiento[]>([]);
  const [doctores, setDoctores] = useState<Doctor[]>([]);
  const [plantilla, setPlantilla] = useState("");
  const [doctorId, setDoctorId] = useState<number | "">("");
  const [busy, setBusy] = useState(false);
  const [firmando, setFirmando] = useState<Consentimiento | null>(null);
  const [msg, setMsg] = useState<{ t: string; err?: boolean }>({ t: "" });
  const flash = (t: string, err = false) => { setMsg({ t, err }); setTimeout(() => setMsg({ t: "" }), 3000); };

  const cargar = useCallback(() => { patientService.consentListar(patientId).then(setLista).catch(() => setLista([])); }, [patientId]);
  useEffect(() => {
    patientService.consentPlantillas().then((d) => { setPlantillas(d.plantillas); setPlantilla(d.plantillas[0]?.key ?? ""); }).catch(() => {});
    patientService.presupuestos(patientId).then((p) => setDoctores((p.colaboradores ?? []).filter((c) => c.es_doctor !== false))).catch(() => {});
    cargar();
  }, [patientId, cargar]);

  async function generar() {
    if (!plantilla) return;
    setBusy(true);
    try { await patientService.consentGenerar({ paciente_id: patientId, plantilla, colaborador_id: doctorId === "" ? null : Number(doctorId) }); flash("Consentimiento generado ✓"); cargar(); }
    catch { flash("No se pudo generar", true); }
    finally { setBusy(false); }
  }
  async function borrar(c: Consentimiento) {
    if (!confirm(`¿Borrar el consentimiento «${c.tipo}»?`)) return;
    try { await patientService.consentBorrar(c.id); cargar(); } catch { flash("No se pudo borrar", true); }
  }
  const verPdf = (c: Consentimiento) => c.archivo_url && window.open(`${API_BASE}${c.archivo_url}`, "_blank");

  const fmt = (iso: string | null) => { if (!iso) return "—"; const d = new Date(iso); return `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}/${d.getFullYear()}`; };

  return (
    <div className="flex flex-col gap-3">
      {msg.t && <div className="fixed top-14 right-6 z-[60] px-4 py-2.5 rounded-sm font-semibold text-[12px] shadow-lg" style={{ background: msg.err ? "#C026D3" : "#2DD9C3", color: msg.err ? "#fff" : "#1500A0" }}>{msg.t}</div>}

      {/* Generar */}
      <div className="flex items-end gap-2 flex-wrap border border-[#e5e7eb] rounded-sm p-3 bg-[#FFFFFF]">
        <label className="flex flex-col gap-1 text-[11px] font-semibold text-[#065AED]">Consentimiento
          <select value={plantilla} onChange={(e) => setPlantilla(e.target.value)} className="font-normal text-[12px] text-[#333] border border-[#e5e7eb] rounded-sm px-2 py-1.5 outline-none focus:border-[#1ca0d1] min-w-[190px]">
            {plantillas.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-[11px] font-semibold text-[#065AED]">Doctor (opcional)
          <select value={doctorId} onChange={(e) => setDoctorId(e.target.value === "" ? "" : Number(e.target.value))} className="font-normal text-[12px] text-[#333] border border-[#e5e7eb] rounded-sm px-2 py-1.5 outline-none focus:border-[#1ca0d1] min-w-[170px]">
            <option value="">— sin doctor —</option>
            {doctores.map((d) => <option key={d.id} value={d.id}>{d.nombre}</option>)}
          </select>
        </label>
        <button onClick={generar} disabled={busy || !plantilla} className="flex items-center gap-1.5 h-[34px] px-4 text-[12px] font-semibold uppercase tracking-wide rounded-sm text-white bg-[#1500A0] hover:bg-[#0d0072] disabled:opacity-50">
          {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />} Generar
        </button>
      </div>

      {/* Lista de consentimientos del paciente */}
      <div className="border border-[#e5e7eb] rounded-sm bg-white overflow-hidden">
        <table className="w-full text-[12px]">
          <thead>
            <tr className="bg-[#FFFFFF] text-[10px] font-bold text-[#7f8c8d] uppercase">
              <th className="px-3 py-2 text-left w-24">Fecha</th>
              <th className="px-3 py-2 text-left">Consentimiento</th>
              <th className="px-3 py-2 text-left w-28">Estado</th>
              <th className="px-3 py-2 text-right w-40">Acciones</th>
            </tr>
          </thead>
          <tbody>
            {lista.map((c) => (
              <tr key={c.id} className="border-t border-[#f0f2f5] hover:bg-[#E6EDFF]">
                <td className="px-3 py-2 text-[#1500A0] whitespace-nowrap">{fmt(c.fecha)}</td>
                <td className="px-3 py-2 font-semibold text-[#333]"><FileSignature className="w-3.5 h-3.5 inline mr-1.5 text-[#1ca0d1]" />{c.tipo}</td>
                <td className="px-3 py-2">
                  {c.estado === "firmado"
                    ? <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-[#0F8C7D]"><CheckCircle2 className="w-3.5 h-3.5" /> Firmado</span>
                    : <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-[#7C3AED]"><Clock className="w-3.5 h-3.5" /> Pendiente</span>}
                </td>
                <td className="px-3 py-2 text-right whitespace-nowrap">
                  <button onClick={() => verPdf(c)} title="Ver PDF" className="text-[#1ca0d1] hover:text-[#065AED] px-1.5"><Eye className="w-4 h-4" /></button>
                  {c.estado !== "firmado" && <button onClick={() => setFirmando(c)} title="Firmar" className="text-[#1500A0] hover:text-[#0d0072] px-1.5"><FileSignature className="w-4 h-4" /></button>}
                  <button onClick={() => borrar(c)} title="Borrar" className="text-slate-400 hover:text-[#C026D3] px-1.5"><Trash2 className="w-4 h-4" /></button>
                </td>
              </tr>
            ))}
            {lista.length === 0 && <tr><td colSpan={4} className="px-3 py-5 text-center text-[12px] text-slate-400 italic">Sin consentimientos. Genera uno arriba.</td></tr>}
          </tbody>
        </table>
      </div>

      {firmando && <FirmaModal consent={firmando} onClose={() => setFirmando(null)} onFirmado={() => { setFirmando(null); flash("Consentimiento firmado ✓"); cargar(); }} onError={() => flash("No se pudo firmar", true)} />}
    </div>
  );
}

// ── Lienzo de firma (ratón / dedo) ──
function FirmaModal({ consent, onClose, onFirmado, onError }: { consent: Consentimiento; onClose: () => void; onFirmado: () => void; onError: () => void }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const dibujando = useRef(false);
  const [hayTrazo, setHayTrazo] = useState(false);
  const [guardando, setGuardando] = useState(false);

  useEffect(() => {
    const c = ref.current; if (!c) return;
    const ctx = c.getContext("2d"); if (!ctx) return;
    ctx.strokeStyle = "#0a1a5a"; ctx.lineWidth = 2.5; ctx.lineCap = "round"; ctx.lineJoin = "round";
  }, []);

  const pos = (e: React.PointerEvent) => { const r = ref.current!.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; };
  const down = (e: React.PointerEvent) => { dibujando.current = true; const ctx = ref.current!.getContext("2d")!; const { x, y } = pos(e); ctx.beginPath(); ctx.moveTo(x, y); ref.current!.setPointerCapture(e.pointerId); };
  const move = (e: React.PointerEvent) => { if (!dibujando.current) return; const ctx = ref.current!.getContext("2d")!; const { x, y } = pos(e); ctx.lineTo(x, y); ctx.stroke(); setHayTrazo(true); };
  const up = () => { dibujando.current = false; };
  const limpiar = () => { const c = ref.current!; c.getContext("2d")!.clearRect(0, 0, c.width, c.height); setHayTrazo(false); };

  async function guardar() {
    if (!hayTrazo) { onError(); return; }
    setGuardando(true);
    try { await patientService.consentFirmar(consent.id, ref.current!.toDataURL("image/png")); onFirmado(); }
    catch { onError(); } finally { setGuardando(false); }
  }

  return (
    <Modal
      title={`Firmar · ${consent.tipo}`}
      size="md"
      onClose={onClose}
      closeOnBackdrop={false}
      zIndex={60}
      className="!max-w-[520px]"
    >
      <ModalBody>
        <div className="flex flex-col gap-3">
          <p className="text-[12px] text-[#7f8c8d]">Firma del paciente en el recuadro (ratón o dedo):</p>
          <canvas ref={ref} width={472} height={170} onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerLeave={up}
            className="w-full h-[170px] border-2 border-dashed border-[#BFE4F7] rounded-sm bg-white touch-none cursor-crosshair" />
        </div>
      </ModalBody>
      <ModalFooter>
        <button type="button" onClick={limpiar}
          className="mr-auto flex items-center gap-1.5 text-[12px] text-[#7f8c8d] hover:text-[#C026D3] cursor-pointer">
          <Eraser className="w-3.5 h-3.5" /> Limpiar
        </button>
        <ModalButton variant="magenta" icon={X} onClick={onClose}>Cancelar</ModalButton>
        <ModalButton variant="primary" disabled={!hayTrazo || guardando} onClick={guardar}>
          {guardando ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileSignature className="w-4 h-4" strokeWidth={2.5} />} Guardar firma
        </ModalButton>
      </ModalFooter>
    </Modal>
  );
}
