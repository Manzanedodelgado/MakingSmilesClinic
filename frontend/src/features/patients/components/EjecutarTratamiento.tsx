"use client";
/**
 * EjecutarTratamiento — Camino 1: ejecutar un tratamiento ya diagnosticado/presupuestado.
 * Modal ligero que muestra tratamientos previstos, valida consentimiento, y permite registrar
 * la ejecución con observaciones. Tras éxito, encadena 3 preguntas (Receta/Presupuesto/Recomendaciones).
 */
import { useState, useCallback, useEffect } from "react";
import { Loader2, X, AlertCircle, CheckCircle } from "lucide-react";
import { Modal, ModalBody, ModalButton, MODAL_INPUT } from "@/shared/components";
import { iconoTratamiento } from "@/shared/lib/iconoTratamiento";
import { patientService } from "../services/patientService";
import { useMe } from "@/shared/hooks/useMe";

interface PrevistoLinea {
  id?: number;
  tratamiento_id: number;
  tratamiento: string;
  pieza: string | null;
  zona_boca: string | null;
  cantidad: number;
  precio_unitario: number;
  presupuesto_id?: number;
  presupuesto_num?: string | number;
}

interface EjecutarTratamientoProps {
  patientId: number;
  citaId?: number;
  onClose: () => void;
  onSuccess?: () => void;
}

export function EjecutarTratamiento({ patientId, citaId, onClose, onSuccess }: EjecutarTratamientoProps) {
  const [previstos, setPrevistos] = useState<PrevistoLinea[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [observaciones, setObservaciones] = useState("");
  const [ejecutando, setEjecutando] = useState(false);
  const [lineasSeleccionadas, setLineasSeleccionadas] = useState<Set<number>>(new Set());
  const { colaborador_id } = useMe();

  // Cargar tratamientos previstos
  useEffect(() => {
    const cargar = async () => {
      try {
        setLoading(true);
        const res = await patientService.previstos(patientId);
        // Aplanar el array de presupuestos → líneas
        const lineas: PrevistoLinea[] = [];
        res.presupuestos?.forEach((pg) => {
          pg.previstos?.forEach((item) => {
            lineas.push({
              id: item.linea_id,
              tratamiento_id: item.tratamiento_id || 0,
              tratamiento: item.tratamiento,
              pieza: item.pieza,
              zona_boca: item.zona_boca,
              cantidad: 1,
              precio_unitario: item.importe || 0,
              presupuesto_id: pg.id,
              presupuesto_num: pg.num || 0,
            });
          });
        });
        setPrevistos(lineas);
        // Seleccionar todas por defecto
        setLineasSeleccionadas(new Set(lineas.map((_, i) => i)));
      } catch (e) {
        setError(e instanceof Error ? e.message : "Error al cargar tratamientos previstos");
      } finally {
        setLoading(false);
      }
    };
    cargar();
  }, [patientId]);

  const handleEjecutar = useCallback(async () => {
    if (!colaborador_id) {
      setError("Debes estar autenticado como doctor/colaborador");
      return;
    }

    const lineasAEjecutar = Array.from(lineasSeleccionadas).map((idx) => previstos[idx]);
    if (lineasAEjecutar.length === 0) {
      setError("Selecciona al menos un tratamiento para ejecutar");
      return;
    }

    setEjecutando(true);
    setError(null);

    try {
      // Llamar al endpoint de realizar-en-cita
      const result = await patientService.realizarEnCita(
        patientId,
        lineasAEjecutar.map((ln) => ({
          tratamiento_id: ln.tratamiento_id,
          pieza: ln.pieza,
          precio: ln.precio_unitario * ln.cantidad,
          cantidad: ln.cantidad,
        })),
        colaborador_id
      );

      setEjecutando(false);
      onSuccess?.();
      onClose();
    } catch (e: any) {
      // Manejar error 422 de consentimiento
      if (e.response?.status === 422 && e.response?.data?.detail?.error === "consentimiento_requerido") {
        setError(`Consentimiento requerido: ${e.response.data.detail.consentimiento_tipo || "desconocido"}`);
      } else {
        setError(e instanceof Error ? e.message : "Error al ejecutar tratamiento");
      }
      setEjecutando(false);
    }
  }, [patientId, colaborador_id, previstos, lineasSeleccionadas, onSuccess, onClose]);

  if (loading) {
    return (
      <Modal title="Ejecutar Tratamiento" onClose={onClose} size="lg" closeOnBackdrop={false}>
        <ModalBody className="flex flex-col items-center gap-4 py-8">
          <Loader2 className="w-8 h-8 animate-spin text-[#21A2E5]" />
          <p className="text-[#5F7690]">Cargando tratamientos previstos...</p>
        </ModalBody>
      </Modal>
    );
  }

  return (
    <Modal
      title="Ejecutar Tratamiento"
      subtitle="Registra el tratamiento realizado (Camino 1)"
      onClose={onClose}
      size="lg"
      closeOnBackdrop={false}
      footer={
        <>
          <ModalButton variant="magenta" icon={X} onClick={onClose} disabled={ejecutando || previstos.length === 0}>Cancelar</ModalButton>
          <ModalButton variant="primary" onClick={handleEjecutar} disabled={ejecutando || lineasSeleccionadas.size === 0}>
            {ejecutando && <Loader2 className="w-4 h-4 animate-spin" />}
            {ejecutando ? "Registrando..." : `Registrar ${lineasSeleccionadas.size} realizado(s)`}
          </ModalButton>
        </>
      }
    >
      <ModalBody className="space-y-6">
          {/* Alert: cita confirmada */}
          <div className="bg-white border border-yellow-200 rounded-lg p-4 flex gap-3">
            <AlertCircle className="w-5 h-5 text-yellow-700 flex-shrink-0 mt-0.5" />
            <div className="text-sm text-yellow-800">
              <p className="font-medium">Recuerda: Verifica que la cita esté confirmada</p>
              <p className="text-yellow-700 mt-1">El paciente debe haber confirmado su asistencia</p>
            </div>
          </div>

          {/* Tratamientos previstos */}
          <div>
            <h3 className="text-sm font-semibold text-[#1500A0] mb-3">
              Tratamientos Previstos ({lineasSeleccionadas.size} seleccionados)
            </h3>
            {previstos.length === 0 ? (
              <div className="bg-[#FFFFFF] border border-[#BFE4F7] rounded-lg p-4 text-sm text-[#073D8D]">
                No hay tratamientos previstos para este paciente en esta cita.
              </div>
            ) : (
              <div className="border border-[#BFE4F7] rounded-lg overflow-hidden">
                <div className="bg-[#21A2E5] px-4 py-2.5 text-sm font-semibold text-white grid gap-4" style={{ gridTemplateColumns: "1fr 60px 60px 80px" }}>
                  <div>Tratamiento</div>
                  <div className="text-center">Pieza</div>
                  <div className="text-right">Cant.</div>
                  <div className="text-right">Precio</div>
                </div>
                <div className="divide-y">
                  {previstos.map((ln, idx) => (
                    <label key={idx} className="px-4 py-3 text-sm grid gap-4 items-center hover:bg-[#E6EDFF] cursor-pointer transition" style={{ gridTemplateColumns: "1fr 60px 60px 80px" }}>
                      <div className="flex items-center gap-3">
                        <input
                          type="checkbox"
                          checked={lineasSeleccionadas.has(idx)}
                          onChange={(e) => {
                            const nueva = new Set(lineasSeleccionadas);
                            if (e.target.checked) {
                              nueva.add(idx);
                            } else {
                              nueva.delete(idx);
                            }
                            setLineasSeleccionadas(nueva);
                          }}
                          className="w-4 h-4 rounded border-[#BFE4F7] text-[#21A2E5] cursor-pointer"
                        />
                        <span className="w-6 h-6 rounded-md bg-white border border-gray-200 flex items-center justify-center shrink-0">
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img src={iconoTratamiento(ln.tratamiento)} alt="" className="w-4 h-4" />
                        </span>
                        <span className="font-medium text-[12.5px] text-[#1500A0] truncate">{ln.tratamiento}</span>
                      </div>
                      <div className="text-center text-[#5F7690]">{ln.pieza || "—"}</div>
                      <div className="text-right text-[#5F7690]">{ln.cantidad}</div>
                      <div className="text-right font-semibold text-[#21A2E5]">
                        {(ln.precio_unitario * ln.cantidad).toLocaleString("es-ES", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}€
                      </div>
                    </label>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Observaciones */}
          <div>
            <label className="block text-sm font-medium text-[#374151] mb-2">
              Observaciones (opcional)
            </label>
            <textarea
              value={observaciones}
              onChange={(e) => setObservaciones(e.target.value)}
              placeholder="Notas sobre cómo se realizó el tratamiento, incidencias, etc."
              className={`${MODAL_INPUT} resize-y`}
              rows={4}
            />
          </div>

          {/* Error */}
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
