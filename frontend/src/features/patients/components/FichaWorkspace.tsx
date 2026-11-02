"use client";
/**
 * FICHA — workspace del paciente. Muestra Actos clínicos + odontograma; desde los iconos
 * bajo el odontograma (en FichaActos) se abren en EMERGENTE Tratamientos Previos,
 * Periodontograma y Multimedia. Ya no hay barra de pestañas lateral.
 */
import { FichaActos } from "./FichaActos";

export function FichaWorkspace({ patientId }: { patientId: number }) {
  return (
    <div className="flex h-full min-h-0">
      <div className="flex-1 min-w-0 overflow-hidden"><FichaActos patientId={patientId} /></div>
    </div>
  );
}
