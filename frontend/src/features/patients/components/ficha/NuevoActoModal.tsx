"use client";
/** «Nuevo acto clínico» como emergente (estilo GesdenOne): el formulario de siempre dentro del Modal compartido. */
import { useCallback, useRef } from "react";
import { X } from "lucide-react";
import { Modal, ModalBody, ModalButton } from "@/shared/components";
import { AltaActo } from "../AltaActo";

export function NuevoActoModal({ patientId, onClose, onSaved }: {
  patientId: number; onClose: () => void; onSaved: () => void;
}) {
  const sucio = useRef(false);
  const onSucio = useCallback((v: boolean) => { sucio.current = v; }, []);
  // La X y «Cerrar» no deben tirar en silencio un acto a medio escribir; «Cancelar» sí descarta, a propósito.
  const cerrar = useCallback(() => {
    if (sucio.current && !window.confirm("Hay un acto sin guardar. ¿Cerrar y descartarlo?")) return;
    onClose();
  }, [onClose]);

  return (
    <Modal title="Nuevo acto clínico" size="lg" closeOnBackdrop={false} onClose={cerrar}
      footer={<ModalButton variant="magenta" icon={X} onClick={cerrar}>Cerrar</ModalButton>}>
      <ModalBody>
        <AltaActo patientId={patientId} variante="emergente" onSucio={onSucio} onCancelar={onClose}
          onSaved={() => { onSaved(); onClose(); }} />
      </ModalBody>
    </Modal>
  );
}
