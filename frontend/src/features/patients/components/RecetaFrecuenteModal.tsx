"use client";
import { useState, useCallback } from "react";
import { Loader2, X, AlertCircle } from "lucide-react";
import { Modal, ModalBody, ModalButton, MODAL_INPUT } from "@/shared/components";
import { patientService } from "../services/patientService";
import { ListaMedicamentos, useMedicamentos, type MedicamentoReceta } from "./EditorMedicamentos";

interface RecetaFrecuenteModalProps {
  patientId: number;
  plantillaInicial?: { id: number; nombre: string; medicamentos: MedicamentoReceta[] };
  onClose: () => void;
  onSuccess?: () => void;
}

export function RecetaFrecuenteModal({ patientId, plantillaInicial, onClose, onSuccess }: RecetaFrecuenteModalProps) {
  const [nombre, setNombre] = useState(plantillaInicial?.nombre || "");
  const { medicamentos, add: handleAddMedicamento, remove: handleRemoveMedicamento,
    change: handleChangeMedicamento, normalizados } = useMedicamentos(plantillaInicial?.medicamentos);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleGuardar = useCallback(async () => {
    const meds = normalizados();

    if (!nombre.trim()) {
      setError("El nombre de la plantilla es requerido");
      return;
    }

    if (meds.length === 0) {
      setError("Añade al menos un medicamento");
      return;
    }

    setGuardando(true);
    setError(null);

    try {
      if (plantillaInicial) {
        await patientService.actualizarRecetaFrecuente(patientId, plantillaInicial.id, nombre.trim(), meds);
      } else {
        await patientService.crearRecetaFrecuente(patientId, nombre.trim(), meds);
      }
      setGuardando(false);
      onSuccess?.();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al guardar plantilla");
      setGuardando(false);
    }
  }, [patientId, nombre, normalizados, plantillaInicial, onSuccess, onClose]);

  return (
    <Modal
      title={`${plantillaInicial ? "Editar" : "Nueva"} Plantilla de Receta`}
      subtitle="Crea una receta reutilizable"
      onClose={onClose}
      size="lg"
      closeOnBackdrop={false}
      footer={
        <>
          <ModalButton variant="magenta" icon={X} onClick={onClose} disabled={guardando}>Cancelar</ModalButton>
          <ModalButton
            variant="primary"
            onClick={handleGuardar}
            disabled={guardando || !nombre.trim() || medicamentos.filter((m) => m.medicamento.trim()).length === 0}
          >
            {guardando && <Loader2 className="w-4 h-4 animate-spin" />}
            {guardando ? "Guardando..." : "Guardar Plantilla"}
          </ModalButton>
        </>
      }
    >
      <ModalBody className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-[#374151] mb-2">Nombre de la plantilla *</label>
          <input
            type="text"
            value={nombre}
            onChange={(e) => setNombre(e.target.value)}
            placeholder="Ej: Dolor postexodoncia, Infección dental..."
            className={MODAL_INPUT}
          />
        </div>

        <ListaMedicamentos medicamentos={medicamentos} onChange={handleChangeMedicamento}
          onRemove={handleRemoveMedicamento} onAdd={handleAddMedicamento} quitar="icono" />

        {error && (
          <div className="bg-[#FFFFFF] border border-[#C026D3] rounded-lg p-4 flex gap-3">
            <AlertCircle className="w-5 h-5 text-[#C026D3] flex-shrink-0" />
            <p className="text-sm text-[#8B1A96]">{error}</p>
          </div>
        )}
      </ModalBody>
    </Modal>
  );
}
