// Tipos del módulo Motion — espejo de /motion/reglas (backend motion_router).
export interface Regla {
  disparador: string;
  nombre: string;
  grupo: string;            // citas | pacientes | recaptacion | clinico | economico
  descripcion: string;
  solo_consentidos: boolean;
  activo: boolean;
  plantilla_id: number | null;
  cuerpo: string;
  tipo: string;             // texto | encuesta | lista
  enviados: number;
  ultimo_envio: string | null;
}

export interface ReglasResponse {
  maestro: boolean;
  whatsapp_activo: boolean;
  data: Regla[];
}

export const GRUPOS: [string, string][] = [
  ["", "Todos los grupos"],
  ["citas", "Citas"],
  ["pacientes", "Pacientes"],
  ["recaptacion", "Recaptación"],
  ["clinico", "Clínico"],
  ["economico", "Económico"],
];

export { errMsg } from "@/shared/lib/errores";
