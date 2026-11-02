"use client";
/**
 * PostConsultaDocumentos — B5: secuencia común de 3 preguntas al final de la consulta (Caminos 1, 2, 3).
 * Encadena modales: ¿Receta? → ¿Presupuesto? → ¿Recomendaciones?
 * Reutiliza componentes existentes (Escucha para receta) y nuevos (RecomendacionesModal).
 */
import { useState } from "react";
import { X, AlertCircle, CheckCircle } from "lucide-react";
import { Modal, ModalBody, ModalButton } from "@/shared/components";
import { RecomendacionesModal } from "./RecomendacionesModal";
import { RecetaModal } from "./RecetaModal";
import { PresupuestoModal } from "./PresupuestoModal";

type Paso = "receta" | "presupuesto" | "recomendaciones" | "fin";

interface PostConsultaDocumentosProps {
  patientId: number;
  citaId?: number;
  onClose: () => void;
  tratamientosExtractos?: Array<{ texto: string; pieza?: string; tratamiento_id?: number | null; precio?: number }>;
}

export function PostConsultaDocumentos({
  patientId,
  citaId,
  onClose,
  tratamientosExtractos
}: PostConsultaDocumentosProps) {
  const [paso, setPaso] = useState<Paso>("receta");
  const [respuestas, setRespuestas] = useState<Record<Paso, boolean>>({
    receta: false,
    presupuesto: false,
    recomendaciones: false,
    fin: false,
  });

  const handleSi = (key: Paso) => {
    setRespuestas((prev) => ({ ...prev, [key]: true }));
    siguiente();
  };

  const handleNo = () => {
    siguiente();
  };

  const siguiente = () => {
    if (paso === "receta") setPaso("presupuesto");
    else if (paso === "presupuesto") setPaso("recomendaciones");
    else if (paso === "recomendaciones") setPaso("fin");
    else onClose();
  };

  // Durante cada paso, se abre el modal correspondiente
  if (paso === "receta" && respuestas.receta) {
    return <RecetaModal patientId={patientId} citaId={citaId} onClose={siguiente} onSuccess={siguiente} />;
  }

  if (paso === "presupuesto" && respuestas.presupuesto) {
    const lineas = tratamientosExtractos?.map((t) => ({
      tratamiento: t.texto,
      pieza: t.pieza,
      precio: t.precio || 0,
      tratamiento_id: t.tratamiento_id
    }));
    return (
      <PresupuestoModal
        patientId={patientId}
        citaId={citaId}
        onClose={siguiente}
        onSuccess={siguiente}
        lineasIniciales={lineas}
      />
    );
  }

  if (paso === "recomendaciones" && respuestas.recomendaciones) {
    return <RecomendacionesModal patientId={patientId} citaId={citaId} onClose={siguiente} onSuccess={siguiente} />;
  }

  // Pantalla de pregunta simple
  const preguntas: Record<Paso, { titulo: string; descripcion: string }> = {
    receta: {
      titulo: "¿Deseas generar una receta?",
      descripcion: "Crea una receta médica para medicación prescrita",
    },
    presupuesto: {
      titulo: "¿Deseas crear un nuevo presupuesto?",
      descripcion: "Presupuesto para tratamientos no previos o cambios de plan",
    },
    recomendaciones: {
      titulo: "¿Deseas añadir recomendaciones?",
      descripcion: "Selecciona recomendaciones de cuidado post-tratamiento",
    },
    fin: {
      titulo: "✅ Consulta finalizada",
      descripcion: "Todos los documentos han sido guardados correctamente",
    },
  };

  const preg = preguntas[paso];

  if (paso === "fin") {
    return (
      <Modal title={preg.titulo} onClose={onClose} size="sm" closeOnBackdrop={false}>
        <ModalBody className="text-center">
          <div className="mx-auto w-12 h-12 rounded-full bg-[#FFFFFF] flex items-center justify-center mb-4">
            <CheckCircle className="w-7 h-7 text-[#0F8C7D]" />
          </div>
          <p className="text-[#5F7690] mb-6">{preg.descripcion}</p>
          <ModalButton variant="magenta" icon={X} onClick={onClose} className="w-full">Cerrar</ModalButton>
        </ModalBody>
      </Modal>
    );
  }

  return (
    <Modal
      title={preg.titulo}
      subtitle={preg.descripcion}
      onClose={onClose}
      size="sm"
      closeOnBackdrop={false}
      footer={
        <>
          <ModalButton variant="outline" onClick={handleNo} className="flex-1">No, siguiente</ModalButton>
          <ModalButton variant="primary" onClick={() => handleSi(paso)} className="flex-1">Sí, abrir</ModalButton>
        </>
      }
    >
      {/* Indicador de progreso */}
      <div className="bg-[#FFFFFF] px-5 py-3 flex gap-2 border-b border-[#BFE4F7]">
        {(["receta", "presupuesto", "recomendaciones"] as const).map((p) => (
          <div
            key={p}
            className={`flex-1 h-2 rounded transition ${
              p === paso
                ? "bg-[#21A2E5]"
                : respuestas[p]
                  ? "bg-[#20BEAB]"
                  : "bg-[#cbd5e1]"
            }`}
          />
        ))}
      </div>

      <ModalBody className="space-y-4">
        <div className="bg-[#FFFFFF] border border-[#BFE4F7] rounded-lg p-4 flex gap-3">
          <AlertCircle className="w-5 h-5 text-[#073D8D] flex-shrink-0 mt-0.5" />
          <p className="text-sm text-[#073D8D]">
            {paso === "receta" && "¿Necesitas prescribir medicación?"}
            {paso === "presupuesto" && "¿Hay tratamientos adicionales o cambios de plan?"}
            {paso === "recomendaciones" && "¿Deseas añadir recomendaciones de cuidado?"}
          </p>
        </div>
      </ModalBody>
    </Modal>
  );
}
