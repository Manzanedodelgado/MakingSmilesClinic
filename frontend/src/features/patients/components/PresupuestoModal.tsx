"use client";
import { useState, useCallback } from "react";
import { Loader2, X, AlertCircle, Plus } from "lucide-react";
import { Modal, ModalBody, ModalButton, MODAL_INPUT } from "@/shared/components";
import { patientService } from "../services/patientService";

interface LineaPresupuesto {
  tratamiento: string;
  pieza?: string;
  precio: number;
}

interface PresupuestoModalProps {
  patientId: number;
  citaId?: number;
  onClose: () => void;
  onSuccess?: () => void;
  lineasIniciales?: Array<{ tratamiento: string; pieza?: string; precio?: number; tratamiento_id?: number | null }>;
}

export function PresupuestoModal({
  patientId,
  citaId,
  onClose,
  onSuccess,
  lineasIniciales
}: PresupuestoModalProps) {
  const [titulo, setTitulo] = useState("Presupuesto (Consulta)");
  const iniciales = lineasIniciales && lineasIniciales.length > 0
    ? lineasIniciales.map(l => ({ tratamiento: l.tratamiento, pieza: l.pieza || "", precio: l.precio || 0 }))
    : [{ tratamiento: "", pieza: "", precio: 0 }];
  const [lineas, setLineas] = useState<LineaPresupuesto[]>(iniciales);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleAddLinea = () => {
    setLineas([...lineas, { tratamiento: "", pieza: "", precio: 0 }]);
  };

  const handleRemoveLinea = (index: number) => {
    setLineas(lineas.filter((_, i) => i !== index));
  };

  const handleChangeLinea = (index: number, field: keyof LineaPresupuesto, value: unknown) => {
    const updated = [...lineas];
    updated[index][field] = value as never;
    setLineas(updated);
  };

  const total = lineas.reduce((sum, l) => sum + (l.precio || 0), 0);

  const handleGuardar = useCallback(async () => {
    const lineasValidas = lineas.filter((l) => l.tratamiento.trim() && l.precio > 0);
    if (lineasValidas.length === 0) {
      setError("Añade al menos un tratamiento con precio");
      return;
    }

    setGuardando(true);
    setError(null);

    try {
      // Convertir a formato esperado por el endpoint
      const body = {
        titulo: titulo || "Presupuesto (Consulta)",
        lineas: lineasValidas.map((l) => ({
          tratamiento_id: 0,
          tratamiento: l.tratamiento,
          pieza: l.pieza || null,
          precio: l.precio,
          cantidad: 1,
        })),
      };

      await patientService.crearPresupuesto(patientId, body);
      onSuccess?.();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al guardar presupuesto");
    } finally {
      setGuardando(false);
    }
  }, [patientId, titulo, lineas, onSuccess, onClose]);

  return (
    <Modal
      title="Crear Presupuesto"
      subtitle="Tratamientos adicionales o cambios de plan"
      onClose={onClose}
      size="lg"
      closeOnBackdrop={false}
      footer={
        <>
          <ModalButton variant="magenta" icon={X} onClick={onClose} disabled={guardando}>Cancelar</ModalButton>
          <ModalButton
            variant="primary"
            onClick={handleGuardar}
            disabled={guardando || lineas.filter((l) => l.tratamiento.trim() && l.precio > 0).length === 0}
          >
            {guardando && <Loader2 className="w-4 h-4 animate-spin" />}
            {guardando ? "Guardando..." : "Crear Presupuesto"}
          </ModalButton>
        </>
      }
    >
      <ModalBody className="space-y-4">
          {/* Título */}
          <div>
            <label className="block text-sm font-medium text-[#374151] mb-2">
              Título del presupuesto
            </label>
            <input
              type="text"
              value={titulo}
              onChange={(e) => setTitulo(e.target.value)}
              placeholder="Ej: Presupuesto implante superior"
              className={MODAL_INPUT}
            />
          </div>

          {/* Líneas */}
          <div>
            <h3 className="text-sm font-semibold text-[#1500A0] mb-3">Líneas de tratamiento</h3>
            <div className="space-y-2">
              {lineas.map((linea, idx) => (
                <div key={idx} className="flex gap-2 items-end">
                  <input
                    type="text"
                    value={linea.tratamiento}
                    onChange={(e) => handleChangeLinea(idx, "tratamiento", e.target.value)}
                    placeholder="Tratamiento"
                    className={`${MODAL_INPUT} flex-1`}
                  />
                  <input
                    type="text"
                    value={linea.pieza || ""}
                    onChange={(e) => handleChangeLinea(idx, "pieza", e.target.value)}
                    placeholder="Pieza (opt)"
                    className={`${MODAL_INPUT} w-24`}
                  />
                  <input
                    type="number"
                    value={linea.precio || ""}
                    onChange={(e) => handleChangeLinea(idx, "precio", parseFloat(e.target.value) || 0)}
                    placeholder="Precio €"
                    className={`${MODAL_INPUT} w-24`}
                  />
                  {lineas.length > 1 && (
                    <button
                      onClick={() => handleRemoveLinea(idx)}
                      className="px-2 py-2 text-[#5F7690] hover:text-[#C026D3] transition"
                    >
                      ✕
                    </button>
                  )}
                </div>
              ))}
            </div>
            <button
              onClick={handleAddLinea}
              className="mt-2 text-sm text-[#21A2E5] hover:text-[#073D8D] font-medium inline-flex items-center gap-1"
            >
              <Plus className="w-4 h-4" /> Añadir línea
            </button>
          </div>

          {/* Total */}
          <div className="bg-[#FFFFFF] border border-[#BFE4F7] rounded-lg p-3 flex items-center justify-between">
            <span className="text-sm font-medium text-[#073D8D]">Total:</span>
            <span className="text-lg font-bold text-[#21A2E5]">
              {total.toLocaleString("es-ES", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}€
            </span>
          </div>

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
