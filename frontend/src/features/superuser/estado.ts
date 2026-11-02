// Vocabulario común de SuperUser → Aura / Centinela: colores y textos de estado.
// Mismos puntos que el resto de la app: teal = bien, violeta = atención, magenta = error.
export const DOT: Record<string, string> = { ok: "bg-[#20BEAB]", warn: "bg-[#7C3AED]", error: "bg-[#C026D3]", off: "bg-slate-300" };
export const ESTADO_TXT: Record<string, string> = { ok: "OK", warn: "Atención", error: "Error", off: "Inactiva" };

export type Chequeo = { clave: string; label: string; estado: string; detalle: string };
export type Integr = { tipo: string; label: string; estado: string };
export type Salud = { nivel: string; sistema: Chequeo[]; integraciones: Integr[]; comprobado: string };

export type Aviso = {
  cuando: string | null; nivel: string | null; enviados: string[];
  fallando: { sistema: string | null; estado: string; detalle: string }[];
};
export type EspejoCentinela = {
  ok: boolean; nivel_actual: string; ultima_revision: string | null; origen: string | null; avisos: Aviso[];
};

// El peor de varios estados (error > warn > ok); "off" solo si todos están apagados.
export function peorEstado(estados: string[]): string {
  if (estados.includes("error")) return "error";
  if (estados.includes("warn")) return "warn";
  if (estados.includes("ok")) return "ok";
  return "off";
}
