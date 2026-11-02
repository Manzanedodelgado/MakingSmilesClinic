"use client";
/**
 * Tab ALERTAS — portado del .37 (views/pacientes/Alertas.tsx), 100% sobre la BBDD nueva.
 * Alertas médicas ← alertas_paciente · Medicación habitual ← medic_preescrita ·
 * Notas ← pacientes.notas. Lectura + alta + alternar activa + guardar notas, todo real
 * (GET/POST/PUT /pacientes/{id}/alertas|medicaciones, PUT /pacientes/{id}). Botones según
 * el estándar MakingSmiles: "Nuevo"=blanco/borde/azul, "Guardar"=teal/navy.
 */
import { useState, useEffect, useCallback } from "react";
import { Loader2, X, AlertTriangle, Plus, ToggleRight, ToggleLeft, FileText, Pill, Check } from "lucide-react";
import { ClinicalCard, SectionHeader, ClinicalButton, Modal, ModalBody, ModalFooter, ModalButton, MODAL_INPUT } from "@/shared/components";
import { patientService } from "../services/patientService";
import { useDirtyForm } from "../store/patientSession";
import type { AlertaMedica, MedicacionPaciente } from "../types/patient";

// Gravedad → estilo de badge (paleta corporativa: salmón/ámbar/cian, sin rojo/verde puros).
const sevStyle: Record<string, string> = {
  GRAVE: "bg-[#C026D3]/15 text-[#A21CAF] border border-[#C026D3]/40",
  ALTA: "bg-[#C026D3]/15 text-[#A21CAF] border border-[#C026D3]/40",
  MODERADA: "bg-[#7C3AED]/15 text-[#6D28D9] border border-[#7C3AED]/40",
  MEDIA: "bg-[#7C3AED]/15 text-[#6D28D9] border border-[#7C3AED]/40",
  LEVE: "bg-[#1ca0d1]/15 text-[#0d5e7a] border border-[#1ca0d1]/40",
  BAJA: "bg-[#1ca0d1]/15 text-[#0d5e7a] border border-[#1ca0d1]/40",
};
const sevLabel: Record<string, string> = { GRAVE: "ALTA", MODERADA: "MEDIA", LEVE: "BAJA" };
const SEV_OPTIONS = ["", "Leve", "Moderada", "Grave"];

const fmtFecha = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString("es-ES") : "—");
const fmtYear = (iso: string | null) => (iso ? String(new Date(iso).getFullYear()) : "—");

export function Alertas({ patientId }: { patientId: number }) {
  const [alertas, setAlertas] = useState<AlertaMedica[]>([]);
  const [medicacion, setMedicacion] = useState<MedicacionPaciente[]>([]);
  const [nota, setNota] = useState("");
  const [notaBase, setNotaBase] = useState("");   // nota guardada → para detectar cambios sin guardar
  const [loading, setLoading] = useState(false);
  const [savingNota, setSavingNota] = useState(false);
  const [msg, setMsg] = useState("");
  const [modal, setModal] = useState<null | "alerta" | "medic">(null);
  const flash = (t: string) => { setMsg(t); setTimeout(() => setMsg(""), 2500); };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const d = await patientService.alertas(patientId);
      setAlertas(Array.isArray(d.alertas) ? d.alertas : []);
      setMedicacion(Array.isArray(d.medicaciones) ? d.medicaciones : []);
      setNota(d.notas ?? ""); setNotaBase(d.notas ?? "");
    } catch {
      setAlertas([]); setMedicacion([]); setNota(""); setNotaBase("");
    } finally {
      setLoading(false);
    }
  }, [patientId]);

  useEffect(() => { load(); }, [load]);

  const toggle = async (a: AlertaMedica) => {
    setAlertas((prev) => prev.map((x) => (x.id === a.id ? { ...x, activo: !x.activo } : x)));
    try { await patientService.toggleAlerta(patientId, a.id, !a.activo); }
    catch { flash("Error al actualizar"); load(); }
  };

  const guardarNota = async () => {
    setSavingNota(true);
    try { await patientService.actualizar(patientId, { notas: nota }); setNotaBase(nota); flash("Nota guardada"); }
    catch { flash("Error al guardar la nota"); }
    finally { setSavingNota(false); }
  };

  // La nota editada y sin guardar cuenta como cambio pendiente para el guard de cierre.
  useDirtyForm("alerta-nota", nota !== notaBase, guardarNota);

  return (
    <div className="flex-1 overflow-y-auto p-4 bg-white">
      {msg && <div className="fixed top-14 right-6 z-50 px-4 py-2.5 rounded-sm text-[12px] font-semibold shadow-lg bg-[#2DD9C3] text-[#1500A0]">{msg}</div>}

      {/* Alertas Médicas */}
      <ClinicalCard className="mb-4">
        <SectionHeader
          title="Alertas Médicas"
          icon={AlertTriangle}
          action={<ClinicalButton variant="nuevo" icon={Plus} onClick={() => setModal("alerta")}>Nueva alerta</ClinicalButton>}
        />
        {loading ? (
          <div className="text-center py-8 text-[#7f8c8d] text-[12px] flex items-center justify-center gap-2"><Loader2 className="w-4 h-4 animate-spin" /> Cargando…</div>
        ) : alertas.length === 0 ? (
          <div className="text-center py-8 text-[#7f8c8d] text-[12px]">Sin alertas registradas</div>
        ) : (
          <div className="border border-[#e5e7eb] rounded-sm overflow-hidden">
            <table className="w-full text-[12px]">
              <thead>
                <tr className="bg-[#FFFFFF] text-[10px] font-bold text-[#7f8c8d] uppercase">
                  <th className="px-3 py-2 text-left w-24">Tipo</th>
                  <th className="px-3 py-2 text-left">Descripción</th>
                  <th className="px-3 py-2 text-center w-24">Gravedad</th>
                  <th className="px-3 py-2 text-left w-24">Fecha</th>
                  <th className="px-3 py-2 text-center w-16">Activa</th>
                </tr>
              </thead>
              <tbody>
                {alertas.map((a) => {
                  const sev = (a.severidad || "").toUpperCase();
                  return (
                    <tr key={a.id} className={`border-t border-[#f0f2f5] hover:bg-[#E6EDFF] ${a.activo ? "" : "opacity-50"}`}>
                      <td className="px-3 py-2 text-[#1500A0] font-semibold">ALERTA</td>
                      <td className="px-3 py-2 text-[#333]">{a.texto}</td>
                      <td className="px-3 py-2 text-center">
                        {sev ? (
                          <span className={`inline-block px-2 py-0.5 rounded-sm text-[10px] font-semibold ${sevStyle[sev] || "bg-white text-slate-500"}`}>
                            {sevLabel[sev] || a.severidad}
                          </span>
                        ) : <span className="text-[#c8d2dc]">—</span>}
                      </td>
                      <td className="px-3 py-2 text-[#7f8c8d]">{fmtFecha(a.fecha)}</td>
                      <td className="px-3 py-2 text-center">
                        <button onClick={() => toggle(a)} title={a.activo ? "Desactivar" : "Activar"} className="cursor-pointer">
                          {a.activo
                            ? <ToggleRight className="w-5 h-5 text-[#2DD9C3] mx-auto" />
                            : <ToggleLeft className="w-5 h-5 text-[#c8d2dc] mx-auto" />}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </ClinicalCard>

      <div className="flex gap-4">
        {/* Notas Médicas */}
        <ClinicalCard className="flex-1 flex flex-col">
          <SectionHeader title="Notas Médicas" icon={FileText} />
          <textarea value={nota} onChange={(e) => setNota(e.target.value)}
            className="w-full h-28 text-[12px] border border-[#e5e7eb] bg-white text-[#333] px-3 py-1.5 rounded-sm outline-none focus:border-[#1ca0d1] resize-none transition-all"
            placeholder="Notas clínicas adicionales…" />
          <div className="flex justify-end mt-2">
            <ClinicalButton variant="save" onClick={guardarNota} disabled={savingNota}>
              {savingNota ? "Guardando…" : "Guardar"}
            </ClinicalButton>
          </div>
        </ClinicalCard>

        {/* Medicación Habitual */}
        <ClinicalCard className="flex-1 flex flex-col">
          <SectionHeader
            title="Medicación Habitual"
            icon={Pill}
            action={<ClinicalButton variant="nuevo" icon={Plus} onClick={() => setModal("medic")}>Añadir</ClinicalButton>}
          />
          {loading ? (
            <div className="text-center py-8 text-[#7f8c8d] text-[12px]">Cargando…</div>
          ) : medicacion.length === 0 ? (
            <div className="text-center py-8 text-[#7f8c8d] text-[12px]">Sin medicaciones registradas</div>
          ) : (
            <div className="border border-[#e5e7eb] rounded-sm overflow-hidden">
              <table className="w-full text-[12px]">
                <thead>
                  <tr className="bg-[#FFFFFF] text-[10px] font-bold text-[#7f8c8d] uppercase">
                    <th className="px-3 py-2 text-left">Medicamento</th>
                    <th className="px-3 py-2 text-left w-20">Dosis</th>
                    <th className="px-3 py-2 text-left w-24">Frecuencia</th>
                    <th className="px-3 py-2 text-left w-16">Desde</th>
                  </tr>
                </thead>
                <tbody>
                  {medicacion.map((m) => (
                    <tr key={m.id} className={`border-t border-[#f0f2f5] hover:bg-[#E6EDFF] ${m.activo ? "" : "opacity-50"}`}>
                      <td className="px-3 py-2 text-[#1500A0] font-semibold">{m.farmaco}</td>
                      <td className="px-3 py-2 text-slate-600">{m.dosis || "—"}</td>
                      <td className="px-3 py-2 text-slate-600">{m.frecuencia || "—"}</td>
                      <td className="px-3 py-2 text-[#7f8c8d]">{fmtYear(m.desde)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </ClinicalCard>
      </div>

      {modal === "alerta" && <ModalAlerta patientId={patientId} onClose={() => setModal(null)} onSaved={() => { setModal(null); load(); }} />}
      {modal === "medic" && <ModalMedic patientId={patientId} onClose={() => setModal(null)} onSaved={() => { setModal(null); load(); }} />}
    </div>
  );
}

function ModalShell({
  title,
  onClose,
  body,
  footer,
}: {
  title: string;
  onClose: () => void;
  body: React.ReactNode;
  footer: React.ReactNode;
}) {
  return (
    <Modal title={title} onClose={onClose} size="sm" closeOnBackdrop={false}>
      <ModalBody>{body}</ModalBody>
      <ModalFooter>{footer}</ModalFooter>
    </Modal>
  );
}

function ModalAlerta({ patientId, onClose, onSaved }: { patientId: number; onClose: () => void; onSaved: () => void }) {
  const [texto, setTexto] = useState("");
  const [sev, setSev] = useState("");
  const [saving, setSaving] = useState(false);
  const guardar = async () => {
    if (!texto.trim()) return;
    setSaving(true);
    try { await patientService.crearAlerta(patientId, texto.trim(), sev || null); onSaved(); }
    finally { setSaving(false); }
  };
  return (
    <ModalShell
      title="Nueva alerta"
      onClose={onClose}
      body={
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <span className="text-[12px] text-[#1ca0d1] uppercase">Descripción</span>
            <input value={texto} onChange={(e) => setTexto(e.target.value)} autoFocus placeholder="Ej: Alergia a penicilina"
              className={MODAL_INPUT} />
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-[12px] text-[#1ca0d1] uppercase">Gravedad</span>
            <select value={sev} onChange={(e) => setSev(e.target.value)} className={MODAL_INPUT}>
              {SEV_OPTIONS.map((s) => <option key={s} value={s}>{s || "Sin especificar"}</option>)}
            </select>
          </div>
        </div>
      }
      footer={
        <>
          <ModalButton variant="magenta" icon={X} onClick={onClose}>Cancelar</ModalButton>
          <ModalButton variant="primary" icon={Check} onClick={guardar} disabled={saving || !texto.trim()}>
            {saving ? "Guardando…" : "Guardar"}
          </ModalButton>
        </>
      }
    />
  );
}

function ModalMedic({ patientId, onClose, onSaved }: { patientId: number; onClose: () => void; onSaved: () => void }) {
  const [farmaco, setFarmaco] = useState("");
  const [dosis, setDosis] = useState("");
  const [frecuencia, setFrecuencia] = useState("");
  const [saving, setSaving] = useState(false);
  const guardar = async () => {
    if (!farmaco.trim()) return;
    setSaving(true);
    try { await patientService.crearMedicacion(patientId, { farmaco: farmaco.trim(), dosis: dosis || null, frecuencia: frecuencia || null }); onSaved(); }
    finally { setSaving(false); }
  };
  return (
    <ModalShell
      title="Añadir medicación"
      onClose={onClose}
      body={
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <span className="text-[12px] text-[#1ca0d1] uppercase">Medicamento</span>
            <input value={farmaco} onChange={(e) => setFarmaco(e.target.value)} autoFocus placeholder="Ej: Ibuprofeno 600 mg"
              className={MODAL_INPUT} />
          </div>
          <div className="flex gap-2">
            <div className="flex flex-col gap-1 flex-1">
              <span className="text-[12px] text-[#1ca0d1] uppercase">Dosis</span>
              <input value={dosis} onChange={(e) => setDosis(e.target.value)} placeholder="500 mg" className={MODAL_INPUT} />
            </div>
            <div className="flex flex-col gap-1 flex-1">
              <span className="text-[12px] text-[#1ca0d1] uppercase">Frecuencia</span>
              <input value={frecuencia} onChange={(e) => setFrecuencia(e.target.value)} placeholder="cada 8h" className={MODAL_INPUT} />
            </div>
          </div>
        </div>
      }
      footer={
        <>
          <ModalButton variant="magenta" icon={X} onClick={onClose}>Cancelar</ModalButton>
          <ModalButton variant="primary" icon={Check} onClick={guardar} disabled={saving || !farmaco.trim()}>
            {saving ? "Guardando…" : "Guardar"}
          </ModalButton>
        </>
      }
    />
  );
}
