/**
 * Justificante de asistencia: lo genera el backend y se abre para imprimir.
 */
import { api } from "@/shared/lib/api";

export async function imprimirJustificante(citaId: number): Promise<void> {
  try {
    // Backend devuelve PDF binario
    const blob = await api.get<Blob>(`/agenda/citas/${citaId}/justificante`);
    const url = URL.createObjectURL(blob);
    const win = window.open(url, "_blank");
    if (!win) {
      throw new Error("Popup bloqueado: permite ventanas emergentes para imprimir");
    }
    // Liberar URL cuando la ventana cargue
    win.onload = () => URL.revokeObjectURL(url);
  } catch (error) {
    console.error("Error generando justificante:", error);
    throw new Error(`No se pudo generar el justificante: ${error instanceof Error ? error.message : "Error desconocido"}`);
  }
}
