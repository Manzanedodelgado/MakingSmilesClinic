"use client";

/**
 * VISOR DICOM 3D DENCT — Visualizador CBCT / panorámico con planeamiento de implantes.
 *
 * Componente que integra la librería dental-cbct-viewer (DenCT) para visualizar
 * estudios de tomografía computarizada dental (CBCT) en 3D, con reconstrucción
 * panorámica OPG, cortes MPR y planeamiento de implantes guiados.
 *
 * Funciona únicamente en el cliente (use client) y requiere que la página host
 * esté servida con los headers COOP/COEP necesarios para SharedArrayBuffer:
 *
 *   Cross-Origin-Opener-Policy: same-origin
 *   Cross-Origin-Embedder-Policy: require-corp
 *
 * La librería DenCT ejecuta todo el procesamiento, renderizado y exportaciones
 * (PDF, STL, PNG) completamente en el navegador del paciente; no se suben
 * datos a ningún servidor.
 */
import { useEffect, useRef, useState } from "react";
import { useCallback } from "react";
import DicomViewer, { type DicomViewerHandle } from "dental-cbct-viewer";
import "dental-cbct-viewer/style.css";

type Dicom3DViewerProps = {
  /** ID de estudio Orthanc o similar. Si se provee, se carga el study automáticamente. */
  orthancStudyId?: string;
  /** Número de historia del paciente. Se usa para identificación y callbacks. */
  numHistoria?: string;
  /** ID interno del paciente (opcional). */
  pacienteId?: number;
  /** Función llamada cuando cambia el plan de implantes. */
  onPlanChange?: (plan: any) => void;
  /** Función llamada cuando cambian los implantes. */
  onImplantsChange?: (implants: any[]) => void;
  /** Si es true, oculta el banner interno de DenCT (el componente dueña el consentimiento). */
  embedded?: boolean;
  /** Altura mínima del contenedor (default: 80vh). */
  height?: string;
};

/**
 * Visualizador 3D CBCT con DenCT.
 *
 * Renderiza el viewer con tamaño por defecto 80vh. Puedes cargar un study
 * pasándole el orthancStudyId (obtenido al consultar /api/pacientes/{id}/dicom/series).
 *
 * El componente usa una ref para acceder al API de DenCT:
 * - ref.current?.loadStudy(files) — carga un study desde archivos DICOM
 * - ref.current?.loadSample() — carga un sample anonimizado para pruebas
 * - ref.current?.exportPdf() — exporta plan a PDF
 * - ref.current?.exportGuideStl() — exporta guía quirúrgica a STL
 *
 * Nota: El componente es "use client" porque toca el DOM (canvas, Web Workers)
 * al montar. Asegúrate de que la página que lo contiene tiene los headers
 * COOP/COEP configurados.
 */
export function Dicom3DViewer({
  orthancStudyId,
  numHistoria,
  pacienteId,
  onPlanChange,
  onImplantsChange,
  embedded = false,
  height = "80vh",
}: Dicom3DViewerProps) {
  const viewerRef = useRef<DicomViewerHandle>(null);
  const [loaded, setLoaded] = useState(false);

  // Cargar sample automáticamente si no hay orthancStudyId (para pruebas)
  useEffect(() => {
    if (viewerRef.current) {
      if (orthancStudyId) {
        // Cuando tengamos el studyId real, cargaremos el study completo
        // viewerRef.current?.loadStudy(...)
        console.log("📦 Cargando study CBCT:", orthancStudyId);
      } else {
        viewerRef.current?.loadSample();
        console.log("📦 Cargando sample de DenCT...");
      }
    }
  }, [orthancStudyId]);

  // Sincronizar callbacks con el padre
  useEffect(() => {
    if (!viewerRef.current) return;

    const handlePlanChange = (plan: any) => {
      console.log("🦷 DenCT plan change:", plan);
      if (onPlanChange) onPlanChange(plan);
      // Guardar en localStorage si hay numHistoria
      if (numHistoria) {
        try {
          localStorage.setItem(`denct-plan-${numHistoria}`, JSON.stringify(plan));
        } catch (e) {
          console.warn("No se pudo guardar plan en localStorage", e);
        }
      }
    };

    const handleImplantsChange = (implants: any[]) => {
      console.log("🦷 DenCT implants change:", implants.length, "implantes");
      if (onImplantsChange) onImplantsChange(implants);
    };

    // Los eventos vienen como props configuradas en el componente DicomViewer
    // Los suscriptores se configuran inline abajo
  }, [viewerRef, numHistoria, onPlanChange, onImplantsChange]);

  return (
    <div
      style={{
        height,
        border: "2px solid #007bff",
        borderRadius: "8px",
        background: "#FFFFFF",
        overflow: "hidden",
        margin: "10px 0",
      }}
    >
      <div
        style={{
          padding: "10px",
          background: "#007bff",
          color: "white",
          borderRadius: "6px 6px 0 0",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          fontWeight: "500",
        }}
      >
        <span>
          {numHistoria
            ? `👁️ Visualización CBCT - Paciente ${numHistoria}`
            : "👁️ Visualizador CBCT DenCT"}
        </span>
        {embedded ? null : (
          <button
            style={{
              background: "rgba(255,255,255,0.2)",
              border: "none",
              color: "white",
              padding: "4px 8px",
              borderRadius: "4px",
              fontSize: "12px",
              cursor: "pointer",
            }}
            onClick={() => viewerRef.current?.exportPdf()}
            title="Exportar plan a PDF"
          >
            PDF
          </button>
        )}
      </div>

      <div style={{ padding: "10px" }}>
        <DicomViewer
          ref={viewerRef}
          patientId={numHistoria || "making-smiles"}
          initialLayout="1+3"
          embedded={embedded}
          lang="es"
          onPlanChange={(plan) => {
            console.log("🦷 DenCT plan event:", plan);
            if (onPlanChange) onPlanChange(plan);
          }}
          onImplantsChange={(implants: any[]) => {
            console.log("🦷 DenCT implants event:", implants.length, "implantes");
            if (onImplantsChange) onImplantsChange(implants);
          }}
        />
      </div>
    </div>
  );
}