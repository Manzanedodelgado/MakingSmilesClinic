/**
 * Generación, impresión y envío de presupuesto.
 * Llama a endpoints backend que devuelven PDF.
 */
import { api } from "@/shared/lib/api";

export async function imprimirPresupuesto(pacienteId: number, presupuestoId: number, _opciones?: unknown): Promise<void> {
  try {
    const blob = await api.get<Blob>(`/pacientes/${pacienteId}/presupuestos/${presupuestoId}/pdf`);
    const url = URL.createObjectURL(blob);
    const win = window.open(url, "_blank");
    if (!win) {
      throw new Error("Popup bloqueado: permite ventanas emergentes para imprimir");
    }
    win.onload = () => URL.revokeObjectURL(url);
  } catch (error) {
    console.error("Error generando presupuesto:", error);
    throw new Error(`No se pudo generar el presupuesto: ${error instanceof Error ? error.message : "Error desconocido"}`);
  }
}

export async function enviarPresupuestoWhatsApp(pacienteId: number, presupuestoId: number, telefono?: string): Promise<void> {
  try {
    await api.post(`/pacientes/${pacienteId}/presupuestos/${presupuestoId}/enviar-whatsapp`, { telefono });
  } catch (error) {
    console.error("Error enviando presupuesto por WhatsApp:", error);
    throw new Error(`No se pudo enviar el presupuesto: ${error instanceof Error ? error.message : "Error desconocido"}`);
  }
}

/**
 * Normaliza piezas/zonas de una línea de presupuesto a array de strings.
 * Ej: pieza="16,17", zona="vestibular" -> ["16 vestibular", "17 vestibular"]
 */
export function piezasDeLinea(pieza: string | null, zona: string | null): string[] {
  if (!pieza) return [];
  const piezas = pieza.split(",").map((p) => p.trim()).filter(Boolean);
  const sufijo = zona ? ` ${zona}` : "";
  return piezas.map((p) => `${p}${sufijo}`);
}
