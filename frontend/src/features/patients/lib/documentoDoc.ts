/**
 * Generación de documentos clínicos (PDF) — consents, informes, etc.
 * Llama a endpoint backend que devuelve PDF binario; convierte a base64 string.
 *
 * El backend rellena LA MISMA plantilla que el centro tiene configurada en
 * Config › Admin (con su firma y su sello), así que el documento sale igual que
 * cuando lo generaba el navegador. Si se necesita el render pixel-perfect del
 * navegador, se le puede pasar el `html` ya renderizado (ver docBase.ts).
 */
import { api } from "@/shared/lib/api";

export async function generarDocumentoPdf(
  pacienteId: number,
  tipo: string,
  datos: Record<string, string> = {},
  html?: string,
): Promise<string> {
  try {
    // Backend espera: POST /pacientes/:id/documentos/generar { tipo, datos }
    const blob = await api.post<Blob>(`/pacientes/${pacienteId}/documentos/generar`, { tipo, datos, html });
    // Convertir Blob a base64
    return new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onloadend = () => {
        const result = reader.result as string;
        // reader.result incluye "data:application/pdf;base64,..." -> quitar prefix
        const base64 = result.split(",")[1] || result;
        resolve(base64);
      };
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  } catch (error) {
    console.error("Error generando documento:", error);
    throw new Error(`No se pudo generar el documento: ${error instanceof Error ? error.message : "Error desconocido"}`);
  }
}
