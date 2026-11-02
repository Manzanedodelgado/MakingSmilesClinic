/** Datos derivados de los actos clínicos para los paneles de la ficha. Funciones puras, sin red. */
import type { ActoClinico, AlertaMedica } from "../../types/patient";

export type Visita = { fecha: string | null; doctor: string; tratamientos: string[] };

const dia = (f: string | null): string | null => (f ? f.slice(0, 10) : null);

/** Un acto cuya fecha viene con hora y otro sin ella cuentan como el mismo día. Más reciente primero; sin fecha, al final. */
export function agruparVisitas(actos: ActoClinico[]): Visita[] {
  const porDia = new Map<string | null, { doctores: string[]; tratamientos: string[] }>();
  for (const a of actos) {
    const k = dia(a.fecha);
    const g = porDia.get(k) ?? { doctores: [], tratamientos: [] };
    if (a.doctor && !g.doctores.includes(a.doctor)) g.doctores.push(a.doctor);
    g.tratamientos.push(a.tratamiento);
    porDia.set(k, g);
  }
  return [...porDia.entries()]
    .map(([fecha, g]) => ({ fecha, doctor: g.doctores.join(", "), tratamientos: g.tratamientos }))
    .sort((a, b) => (a.fecha === b.fecha ? 0 : a.fecha === null ? 1 : b.fecha === null ? -1 : a.fecha < b.fecha ? 1 : -1));
}

// AltaActo.componerNota guarda la nota como "S: … · O: … · Dx: … · Plan: …" en las observaciones del acto.
const MOTIVO = /(?:^| · )S: ([\s\S]*?)(?= · (?:O|Dx|Plan): |$)/;

/** «Lo que cuenta el paciente» del acto más reciente que lo tenga; a igual fecha, el de id mayor. */
export function extraerMotivo(actos: ActoClinico[]): string | null {
  const recientesPrimero = [...actos].sort((a, b) => {
    const fa = dia(a.fecha) ?? "";
    const fb = dia(b.fecha) ?? "";
    return fa === fb ? b.id - a.id : fa < fb ? 1 : -1;
  });
  for (const a of recientesPrimero) {
    const texto = a.observaciones?.match(MOTIVO)?.[1].trim();
    if (texto) return texto;
  }
  return null;
}

/** "2026-03-01" o "2026-03-01T10:00:00" → "01/03/2026". No pasa por Date: así no hay desfases de huso horario. */
export function fechaCorta(f: string | null): string {
  if (!f) return "Sin fecha";
  const [y, m, d] = f.slice(0, 10).split("-");
  return `${d}/${m}/${y}`;
}

const RANGO_SEVERIDAD: Record<string, number> = { GRAVE: 0, MODERADA: 1, LEVE: 2 };

/** Las `max` alertas más importantes: por gravedad y, a igual gravedad, la más reciente. Incluye las ya resueltas (histórico). */
export function alertasImportantes(alertas: AlertaMedica[], max = 5): AlertaMedica[] {
  const rango = (a: AlertaMedica) => RANGO_SEVERIDAD[(a.severidad ?? "").toUpperCase()] ?? 3;
  return [...alertas]
    .sort((a, b) => rango(a) - rango(b) || (b.fecha ?? "").localeCompare(a.fecha ?? ""))
    .slice(0, max);
}

/** Las `max` citas más recientes hasta `hoy` (YYYY-MM-DD), de más nueva a más antigua. No incluye citas futuras. */
export function ultimasCitas<T extends { fecha: string; hora: string }>(citas: T[], hoy: string, max = 5): T[] {
  return citas
    .filter((c) => c.fecha.slice(0, 10) <= hoy)
    .sort((a, b) => b.fecha.localeCompare(a.fecha) || b.hora.localeCompare(a.hora))
    .slice(0, max);
}
