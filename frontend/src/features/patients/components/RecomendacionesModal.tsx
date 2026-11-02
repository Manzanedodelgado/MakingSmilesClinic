"use client";
/**
 * RecomendacionesModal — B4: checklist de recomendaciones al paciente (fin de consulta).
 * Patrón visual igual a Anamnesis.tsx. Permite seleccionar items por sección, generar
 * texto, e imprimir/enviar por WhatsApp.
 */
import { useState, useEffect, useCallback } from "react";
import { Loader2, X, AlertCircle, Printer, MessageCircle } from "lucide-react";
import { Modal, ModalBody, ModalButton } from "@/shared/components";
import { patientService } from "../services/patientService";

interface Seccion {
  clave: string;
  titulo: string;
  icono: string;
  color: string;
  items: string[];
}

interface RecomendacionesModalProps {
  patientId: number;
  citaId?: number;
  onClose: () => void;
  onSuccess?: () => void;
}

export function RecomendacionesModal({ patientId, citaId, onClose, onSuccess }: RecomendacionesModalProps) {
  const [secciones, setSecciones] = useState<Seccion[]>([]);
  const [seleccionados, setSeleccionados] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [guardado, setGuardado] = useState(false);
  const [recomendacionId, setRecomendacionId] = useState<number | null>(null);

  // Cargar catálogo
  useEffect(() => {
    const cargar = async () => {
      try {
        setLoading(true);
        const res = await patientService.recomendacionesCatalogo();
        setSecciones(res.secciones || []);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Error al cargar recomendaciones");
      } finally {
        setLoading(false);
      }
    };
    cargar();
  }, []);

  const toggleItem = (item: string) => {
    const nueva = new Set(seleccionados);
    if (nueva.has(item)) {
      nueva.delete(item);
    } else {
      nueva.add(item);
    }
    setSeleccionados(nueva);
  };

  const handleGuardar = useCallback(async () => {
    if (seleccionados.size === 0) {
      setError("Selecciona al menos una recomendación");
      return;
    }

    setGuardando(true);
    setError(null);

    try {
      const result = await patientService.guardarRecomendaciones(
        patientId,
        Array.from(seleccionados),
        citaId
      );
      setGuardado(true);
      setRecomendacionId(result.recomendacion_id);
      onSuccess?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al guardar recomendaciones");
    } finally {
      setGuardando(false);
    }
  }, [patientId, citaId, seleccionados, onSuccess]);

  const handleImprimir = () => {
    if (!recomendacionId) return;
    // Abre PDF de recomendaciones (genera en backend vía endpoint futuro)
    window.open(`/api/pacientes/${patientId}/recomendaciones/${recomendacionId}/pdf`, '_blank');
  };

  const handleWhatsApp = async () => {
    if (!recomendacionId) return;
    // Envía por WhatsApp vía endpoint existente
    try {
      const res = await patientService.guardarRecomendaciones(patientId, Array.from(seleccionados), citaId);
      if (res.texto_generado) {
        // Buscar teléfono del paciente (guardado en caché o fetched de /cabecera)
        const cab = await patientService.cabecera(patientId);
        if (cab.telefono_movil) {
          await fetch('/api/comunicacion/whatsapp/enviar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              telefono: cab.telefono_movil,
              texto: `Recomendaciones de tu consulta:\n\n${res.texto_generado}`,
            }),
          });
          setError(null);
        } else {
          setError("El paciente no tiene teléfono registrado");
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al enviar por WhatsApp");
    }
  };

  if (loading) {
    return (
      <Modal title="Recomendaciones" onClose={onClose} size="lg" closeOnBackdrop={false}>
        <ModalBody className="flex flex-col items-center gap-4 py-8">
          <Loader2 className="w-8 h-8 animate-spin text-[#21A2E5]" />
          <p className="text-[#5F7690]">Cargando recomendaciones...</p>
        </ModalBody>
      </Modal>
    );
  }

  return (
    <Modal
      title="Recomendaciones"
      subtitle="Selecciona las recomendaciones para el paciente"
      onClose={onClose}
      size="lg"
      closeOnBackdrop={false}
      footer={
        !guardado ? (
          <>
            <ModalButton variant="magenta" icon={X} onClick={onClose} disabled={guardando}>Cancelar</ModalButton>
            <ModalButton variant="primary" onClick={handleGuardar} disabled={guardando || seleccionados.size === 0}>
              {guardando && <Loader2 className="w-4 h-4 animate-spin" />}
              {guardando ? "Guardando..." : "Guardar Recomendaciones"}
            </ModalButton>
          </>
        ) : (
          <>
            <ModalButton variant="magenta" icon={X} onClick={onClose}>Cerrar</ModalButton>
            <ModalButton variant="outline" icon={Printer} onClick={handleImprimir} disabled={!recomendacionId}>
              Imprimir
            </ModalButton>
            <ModalButton variant="primary" icon={MessageCircle} onClick={handleWhatsApp} disabled={!recomendacionId}>
              Enviar WhatsApp
            </ModalButton>
          </>
        )
      }
    >
      <ModalBody className="space-y-6">
          {error && (
            <div className="bg-[#FFFFFF] border border-[#C026D3] rounded-lg p-4 flex gap-3">
              <AlertCircle className="w-5 h-5 text-[#C026D3] flex-shrink-0 mt-0.5" />
              <p className="text-sm text-[#8B1A96]">{error}</p>
            </div>
          )}

          {/* Secciones de recomendaciones */}
          {secciones.map((seccion) => (
            <div key={seccion.clave} className="border border-[#BFE4F7] rounded-lg overflow-hidden">
              <div
                className="px-4 py-2 font-semibold text-white flex items-center gap-2"
                style={{ backgroundColor: seccion.color }}
              >
                <span className="w-[18px] h-[18px] rounded-full border border-white/80 grid place-items-center shrink-0 text-[11px] leading-none">{seccion.icono}</span>
                <span className="text-[13px]">{seccion.titulo}</span>
              </div>
              <div className="p-4 space-y-3">
                {seccion.items.map((item) => (
                  <label key={item} className="flex items-start gap-3 cursor-pointer hover:bg-[#E6EDFF] p-2 rounded transition">
                    <input
                      type="checkbox"
                      checked={seleccionados.has(item)}
                      onChange={() => toggleItem(item)}
                      className="w-4 h-4 rounded border-[#BFE4F7] text-[#21A2E5] mt-1 cursor-pointer"
                    />
                    <span className="text-sm text-[#374151] flex-1">{item}</span>
                  </label>
                ))}
              </div>
            </div>
          ))}

          {seleccionados.size > 0 && (
            <div className="bg-[#FFFFFF] border border-[#BFE4F7] rounded-lg p-4">
              <p className="text-sm text-[#073D8D]">
                <strong>{seleccionados.size}</strong> recomendación{seleccionados.size !== 1 ? "es" : ""} seleccionada{seleccionados.size !== 1 ? "s" : ""}
              </p>
            </div>
          )}

      </ModalBody>
    </Modal>
  );
}
