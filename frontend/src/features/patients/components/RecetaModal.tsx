"use client";
import { useState, useCallback } from "react";
import { Loader2, X, AlertCircle, FileText, Plus } from "lucide-react";
import { Button, Modal, ModalBody, ModalButton, MODAL_INPUT } from "@/shared/components";
import { API_BASE } from "@/shared/lib/api";
import { patientService } from "../services/patientService";
import { RecetaFrecuenteSelector } from "./RecetaFrecuenteSelector";
import { RecetaFrecuenteModal } from "./RecetaFrecuenteModal";
import { ListaMedicamentos, useMedicamentos, type MedicamentoReceta } from "./EditorMedicamentos";

interface RecetaModalProps {
  patientId: number;
  citaId?: number;
  onClose: () => void;
  onSuccess?: () => void;
}

export function RecetaModal({ patientId, citaId, onClose, onSuccess }: RecetaModalProps) {
  const { medicamentos, setMedicamentos, add: handleAddMedicamento, remove: handleRemoveMedicamento,
    change: handleChangeMedicamento, normalizados } = useMedicamentos();
  const [diagnostico, setDiagnostico] = useState("");
  const [instrucciones, setInstrucciones] = useState("");
  const [urgencia, setUrgencia] = useState(false);
  const [desabastecimiento, setDesabastecimiento] = useState(false);
  const [motivoSustitucion, setMotivoSustitucion] = useState("");
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [crearPlantilla, setCrearPlantilla] = useState(false);
  const [recetaCreadaId, setRecetaCreadaId] = useState<number | null>(null);

  const handleGuardar = useCallback(async () => {
    const meds = normalizados();

    if (meds.length === 0) {
      setError("Añade al menos un medicamento");
      return;
    }

    setGuardando(true);
    setError(null);

    try {
      const res = await patientService.guardarReceta(patientId, meds, {
        diagnostico: diagnostico || undefined,
        instrucciones: instrucciones || undefined,
        urgencia,
        desabastecimiento,
        motivo_sustitucion: motivoSustitucion || undefined,
      });
      setRecetaCreadaId(res.receta_id);
      onSuccess?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al guardar receta");
    } finally {
      setGuardando(false);
    }
  }, [patientId, normalizados, diagnostico, instrucciones, urgencia, desabastecimiento, motivoSustitucion, onSuccess]);

  const handleCargarPlantilla = (medicamentos: MedicamentoReceta[]) => {
    setMedicamentos(medicamentos);
  };

  return (
    <>
      <Modal
        title="Generar Receta"
        subtitle="Medicación prescrita en la consulta"
        onClose={onClose}
        size="lg"
        closeOnBackdrop={false}
        footer={
          recetaCreadaId ? undefined : (
            <>
              <ModalButton variant="magenta" icon={X} onClick={onClose} disabled={guardando}>Cancelar</ModalButton>
              <ModalButton
                variant="primary"
                onClick={handleGuardar}
                disabled={guardando || medicamentos.filter((m) => m.medicamento.trim()).length === 0}
              >
                {guardando && <Loader2 className="w-4 h-4 animate-spin" />}
                {guardando ? "Guardando..." : "Guardar Receta"}
              </ModalButton>
            </>
          )
        }
      >
        {recetaCreadaId ? (
          <ModalBody className="space-y-4 text-center">
            <div className="mx-auto w-14 h-14 rounded-full bg-[#FFFFFF] flex items-center justify-center">
              <FileText className="w-7 h-7 text-[#0F8C7D]" />
            </div>
            <p className="text-[15px] font-semibold text-[#1500A0]">Receta creada y archivada</p>
            <div className="flex gap-3 justify-center pt-2">
              <a href={`${API_BASE}/pacientes/${patientId}/recetas/${recetaCreadaId}/pdf`} target="_blank" rel="noreferrer">
                <Button className="flex items-center gap-2"><FileText className="w-4 h-4" /> Ver PDF</Button>
              </a>
              <ModalButton variant="magenta" icon={X} onClick={onClose}>Cerrar</ModalButton>
            </div>
          </ModalBody>
        ) : (
        <ModalBody className="space-y-4">
          {/* Diagnóstico */}
          <div>
            <label className="block text-sm font-medium text-[#374151] mb-2">
              Diagnóstico (opcional)
            </label>
            <textarea
              value={diagnostico}
              onChange={(e) => setDiagnostico(e.target.value)}
              placeholder="Diagnóstico o motivo de la prescripción"
              className={`${MODAL_INPUT} resize-y`}
              rows={2}
            />
          </div>

          {/* Medicamentos */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-[#1500A0]">Medicamentos</h3>
              <button
                type="button"
                onClick={() => setCrearPlantilla(true)}
                className="text-xs text-[#21A2E5] hover:text-[#073D8D] font-medium flex items-center gap-1"
              >
                <Plus className="w-3 h-3" /> Guardar como plantilla
              </button>
            </div>
            <RecetaFrecuenteSelector patientId={patientId} onSelect={handleCargarPlantilla} />
            <ListaMedicamentos medicamentos={medicamentos} onChange={handleChangeMedicamento}
              onRemove={handleRemoveMedicamento} onAdd={handleAddMedicamento} quitar="texto" />
          </div>

          {/* Instrucciones al paciente */}
          <div>
            <label className="block text-sm font-medium text-[#374151] mb-2">
              Instrucciones al paciente (opcional)
            </label>
            <textarea
              value={instrucciones}
              onChange={(e) => setInstrucciones(e.target.value)}
              placeholder="Indicaciones para el paciente"
              className={`${MODAL_INPUT} resize-y`}
              rows={2}
            />
          </div>

          {/* Información al farmacéutico */}
          <div className="grid grid-cols-2 gap-3">
            <label className="flex items-center gap-2 text-sm text-[#374151]">
              <input type="checkbox" checked={urgencia} onChange={(e) => setUrgencia(e.target.checked)} />
              Urgencia
            </label>
            <label className="flex items-center gap-2 text-sm text-[#374151]">
              <input type="checkbox" checked={desabastecimiento} onChange={(e) => setDesabastecimiento(e.target.checked)} />
              Desabastecimiento
            </label>
          </div>
          <div>
            <label className="block text-sm font-medium text-[#374151] mb-2">
              Motivo de la sustitución (opcional)
            </label>
            <input
              type="text"
              value={motivoSustitucion}
              onChange={(e) => setMotivoSustitucion(e.target.value)}
              placeholder="Información al farmacéutico, si procede"
              className={MODAL_INPUT}
            />
          </div>

          {error && (
            <div className="bg-[#FFFFFF] border border-[#C026D3] rounded-lg p-4 flex gap-3">
              <AlertCircle className="w-5 h-5 text-[#C026D3] flex-shrink-0" />
              <p className="text-sm text-[#8B1A96]">{error}</p>
            </div>
          )}
        </ModalBody>
        )}
      </Modal>

      {crearPlantilla && (
        <RecetaFrecuenteModal
          patientId={patientId}
          onClose={() => setCrearPlantilla(false)}
          onSuccess={() => setCrearPlantilla(false)}
        />
      )}
    </>
  );
}
