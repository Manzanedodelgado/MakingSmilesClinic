"use client";
/**
 * EscuchaActiva — presentación MODAL del flujo de escucha. Toda la lógica vive en <Escucha/>
 * (fuente única); esto solo es el envoltorio emergente. Se mantiene el nombre por compatibilidad
 * con las llamadas existentes (ficha del paciente, etc.).
 */
import { Escucha } from "./Escucha";

export function EscuchaActiva({
  patientId,
  onClose,
  onTratamientosExtractos
}: {
  patientId: number;
  onClose: () => void;
  onTratamientosExtractos?: (tratamientos: Array<{ texto: string; pieza?: string }>) => void;
}) {
  return (
    <Escucha
      patientId={patientId}
      variant="modal"
      onClose={onClose}
      onTratamientosExtractos={onTratamientosExtractos}
    />
  );
}
