"use client";
/**
 * Emergente de cambios sin guardar al cerrar / cambiar de paciente.
 * Tres botones: Cancelar (cancela el cierre, por defecto/marcado) · No guardar · Guardar.
 * Se renderiza global (en el shell de la app) y lo gobierna patientSession.closing.
 */
import { useEffect, useRef, useState } from "react";
import { X, Check } from "lucide-react";
import { Modal, ModalBody, ModalButton, PILL_MAGENTA } from "@/shared/components";
import { usePatientSession, patientSession } from "../store/patientSession";

export function PatientCloseGuard() {
  const { closing } = usePatientSession();
  const [saving, setSaving] = useState(false);
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => { if (closing) cancelRef.current?.focus(); }, [closing]);
  if (!closing) return null;

  const resolver = (a: "cancel" | "discard" | "save") => {
    if (a === "save") { setSaving(true); patientSession.resolveClose("save").finally(() => setSaving(false)); }
    else patientSession.resolveClose(a);
  };

  return (
    <Modal
      title="Cambios sin guardar"
      onClose={() => resolver("cancel")}
      size="sm"
      zIndex={200}
      closeOnBackdrop={false}
      footer={
        <>
          <button
            ref={cancelRef}
            type="button"
            onClick={() => resolver("cancel")}
            className={`${PILL_MAGENTA} ${""}`}
          >
            <X className="w-4 h-4" strokeWidth={2.5} />
            Cancelar
          </button>
          <ModalButton variant="outline" onClick={() => resolver("discard")} disabled={saving}>
            No guardar
          </ModalButton>
          <ModalButton variant="primary" icon={Check} onClick={() => resolver("save")} disabled={saving}>
            {saving ? "Guardando…" : "Guardar"}
          </ModalButton>
        </>
      }
    >
      <ModalBody>
        <p className="text-[13px] text-[#374151]">Hay <b>cambios pendientes de guardar</b> en la ficha del paciente. ¿Qué quieres hacer?</p>
      </ModalBody>
    </Modal>
  );
}
