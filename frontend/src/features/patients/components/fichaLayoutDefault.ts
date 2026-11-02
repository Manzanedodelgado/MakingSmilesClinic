import type { FichaLayoutItem } from "@/shared/services/configService";

/** Los identificadores de caja — fuente única, ningún otro archivo los redeclara. «Nuevo acto» ya no es una caja: es un emergente. */
export const FICHA_LAYOUT_IDS = ["paciente", "alertas", "medicacion", "citas", "historial", "odontograma", "multimedia"] as const;
export type FichaBoxId = typeof FICHA_LAYOUT_IDS[number];

/** Columna 1: paciente, alertas, historia farmacológica y últimas citas · columna 2: historial · columna 3: odontograma\n * y, debajo de las dos últimas, multimedia. Rejilla de 12 columnas y 21 filas (el odontograma necesita 9 para verse entero).\n * Los layouts guardados con las 4 cajas antiguas dejan de ser válidos y caen aquí. */
export const FICHA_LAYOUT_DEFAULT: FichaLayoutItem[] = [
  { i: "paciente", x: 0, y: 0, w: 2, h: 6 },
  { i: "alertas", x: 0, y: 6, w: 2, h: 5 },
  { i: "medicacion", x: 0, y: 11, w: 2, h: 5 },
  { i: "citas", x: 0, y: 16, w: 2, h: 5 },
  { i: "historial", x: 2, y: 0, w: 5, h: 9 },
  { i: "odontograma", x: 7, y: 0, w: 5, h: 9 },
  { i: "multimedia", x: 2, y: 9, w: 10, h: 12 },
];

const GRID_COLS = 12;
const MAX_FILAS = 60; // tope defensivo: una caja no puede ser absurdamente alta

/** Entero finito — descarta strings, null, NaN, decimales, Infinity. */
function esEnteroValido(v: unknown): v is number {
  return typeof v === "number" && Number.isInteger(v) && Number.isFinite(v);
}

/** Una caja concreta cabe en la rejilla de 12 columnas y tiene tamaño positivo y acotado.
 * Sin esto, un layout guardado con datos corruptos (strings, negativos, nulls, fuera de
 * rango) puede colgar a react-grid-layout (compactación en bucle) o dejar cajas invisibles
 * — congelando la ficha para TODA la clínica, no solo para quien lo guardó. */
function esCajaValida(it: unknown): it is FichaLayoutItem {
  if (typeof it !== "object" || it === null) return false;
  const { x, y, w, h } = it as Record<string, unknown>;
  if (![x, y, w, h].every(esEnteroValido)) return false;
  const [xi, yi, wi, hi] = [x, y, w, h] as number[];
  return xi >= 0 && yi >= 0 && wi >= 1 && wi <= GRID_COLS && xi + wi <= GRID_COLS && hi >= 1 && hi <= MAX_FILAS;
}

/** Exactamente los ids de FICHA_LAYOUT_IDS, ni de más ni de menos, y cada caja con x/y/w/h válidos
 * y dentro de rango — guarda de un layout corrupto o de una edición manual en BD antes de
 * dárselo a react-grid-layout. */
export function esLayoutValido(layout: unknown): layout is FichaLayoutItem[] {
  if (!Array.isArray(layout) || layout.length !== FICHA_LAYOUT_IDS.length) return false;
  if (!layout.every(esCajaValida)) return false;
  const ids = new Set(layout.map((it) => (it as { i?: unknown })?.i));
  return FICHA_LAYOUT_IDS.every((id) => ids.has(id));
}
