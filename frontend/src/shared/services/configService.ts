import { api } from "@/shared/lib/api";

/** Formato nativo de react-grid-layout: una entrada por caja. */
export type FichaLayoutItem = { i: string; x: number; y: number; w: number; h: number };

/** Capa de acceso al /config genérico, para la clave ficha_layout (sistema "pacientes"). */
export const configService = {
  /** null si el centro aún no ha guardado nunca una disposición (primer uso). */
  fichaLayout: async (): Promise<FichaLayoutItem[] | null> => {
    const r = await api.get<{ valores: Record<string, unknown> }>("/config?sistema=pacientes");
    const v = r.valores?.ficha_layout;
    return Array.isArray(v) ? (v as FichaLayoutItem[]) : null;
  },
  guardarFichaLayout: (layout: FichaLayoutItem[]) =>
    api.put<{ id: number }>("/config", { clave: "ficha_layout", valor: layout, sistema: "pacientes" }),
};
