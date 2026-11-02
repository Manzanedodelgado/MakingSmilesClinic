/**
 * Conversión de datos de la BBDD nueva → PiezaMarcada[] para OdontogramaOverlay.
 * Reusa el parser/colores exactos del .37 (odontogramaUtils): misma representación visual.
 */
import type { PiezaMarcada } from "./OdontogramaOverlay";
import type { Hallazgo } from "../../types/patient";
import { parseTratamientoPresupuesto, piezasImplicitas, SVG_COLOR } from "./odontogramaUtils";

// Color por ESTADO de hallazgo (idéntico al de O2/Odontograma.tsx).
export const ESTADO_COLOR: Record<string, string> = {
  SANO: "#20BEAB", CARIES: "#7C3AED", "OBTURACIÓN": "#00B0FF", AUSENTE: "#D500F9",
  CORONA: "#E9C22E", "CORONA-IMPLANTE": "#E9C22E", IMPLANTE: "#1DE9B6", ENDODONCIA: "#424242",
  ORTODONCIA: "#9aa0a6", EXODONCIA: "#D500F9", "PRÓTESIS": "#F8BBD0",
  LIMPIEZA: "#00BCD4", RASPADO: "#E01B84", CURETAJE: "#E01B84", PERNO: "#7C3AED", QUISTECTOMIA: "#C026D3",
  "PRÓTESIS REMOVIBLE": "#F8BBD0", INJERTO: "#A21CAF", GINGIVECTOMIA: "#9C27B0", "ALARGAMIENTO CORONARIO": "#C026D3",
  "RETENEDOR REMOVIBLE": "#81D4FA", "RETENEDOR FIJO": "#3c4043", "ORTODONCIA INVISIBLE": "#42A5F5",
};

export interface ItemTratamiento {
  pieza: string | null;
  tratamiento: string; // descripción/nombre del catálogo
}

// FDI válido: permanente (cuadrantes 1-4, posiciones 1-8) o de leche (cuadrantes 5-8, posiciones 1-5).
const ES_FDI = (p: string) => /^([1-4][1-8]|[5-8][1-5])$/.test(p);

// Fecha (Date o "dd/mm/yyyy") → epoch ms (0 si no parsea). Único helper de fecha del módulo.
const _fechaT = (f?: string | null) => {
  if (!f) return 0;
  return new Date(f).getTime() || new Date(f.split("/").reverse().join("-")).getTime() || 0;
};

/** Una línea (presupuesto) o acto (ficha) → sus piezas marcadas con su tratamiento y color. */
export function itemsToPiezas(items: ItemTratamiento[], opts?: { gris?: boolean; isInicial?: boolean }): PiezaMarcada[] {
  const out: PiezaMarcada[] = [];
  for (const it of items) {
    if (!it.tratamiento) continue;
    const { key, caras } = parseTratamientoPresupuesto(it.tratamiento);
    const color = opts?.gris ? "#9aa0a6" : SVG_COLOR[key] || "#3388FF";
    let piezas = (it.pieza || "").split(/[\s,.;/]+/).map((p) => p.trim()).filter(ES_FDI);
    if (piezas.length === 0) piezas = piezasImplicitas(key, it.tratamiento);
    for (const p of piezas) {
      out.push({ pieza: p, tratamiento: key, caras, color, isInicial: opts?.isInicial });
    }
  }
  return out;
}

// Reglas de exclusión por pieza (qué tratamiento borra a cuáles). Coherente con la .37.
export const TRATAMIENTOS_EXCLUYENTES: Record<string, string[]> = {
  sano: ["*"], exodoncia: ["*"], ausente: ["*"], ausencia: ["*"], protesis: ["*"],
  "protesis removible": ["*"], "protesis-removible": ["*"],
  implante: ["caries", "obturacion", "endodoncia", "sano"],
  corona: ["caries", "obturacion", "sano"],
  "corona-implante": ["caries", "obturacion", "corona", "sano"],
  obturacion: ["caries", "sano"],
  "retenedor fijo": ["ortodoncia", "ortodoncia invisible", "alineadores", "bracket"],
  "retenedor removible": ["ortodoncia", "ortodoncia invisible", "alineadores", "bracket"],
};
const ARCADA_SUP = new Set(["18","17","16","15","14","13","12","11","21","22","23","24","25","26","27","28"]);
const ARCADA_INF = new Set(["48","47","46","45","44","43","42","41","31","32","33","34","35","36","37","38"]);

/** Aplica las reglas de exclusión/prioridad a una lista YA ordenada (más reciente al final). */
export function resolverExclusiones(ordenadas: PiezaMarcada[]): PiezaMarcada[] {
  let result: PiezaMarcada[] = [];
  for (const n of ordenadas) {
    const exc = TRATAMIENTOS_EXCLUYENTES[n.tratamiento] || [];
    const eraseAll = exc.includes("*");
    if (exc.length > 0) result = result.filter((prev) => prev.pieza !== n.pieza || (!eraseAll && !exc.includes(prev.tratamiento)));
    result.push(n);
  }
  // Excluyentes absolutos: borran TODO de la pieza (incluso lo posterior).
  const absolutos = new Set(["protesis", "protesis removible", "protesis-removible", "exodoncia", "ausente", "ausencia", "sano"]);
  const conAbsoluto = new Map<string, string>();
  for (const r of result) if (absolutos.has(r.tratamiento)) conAbsoluto.set(r.pieza, r.tratamiento);
  if (conAbsoluto.size > 0) result = result.filter((r) => !conAbsoluto.has(r.pieza) || r.tratamiento === conAbsoluto.get(r.pieza));
  // Retenedor en una arcada → borra la ortodoncia de TODA esa arcada.
  const ORTO = new Set(["ortodoncia", "bracket", "ortodoncia invisible", "alineadores"]);
  const RET = new Set(["retenedor fijo", "retenedor removible"]);
  let borrarSup = false, borrarInf = false;
  for (const r of result) if (RET.has(r.tratamiento)) { if (ARCADA_SUP.has(r.pieza)) borrarSup = true; if (ARCADA_INF.has(r.pieza)) borrarInf = true; }
  if (borrarSup || borrarInf) result = result.filter((r) => {
    if (!ORTO.has(r.tratamiento)) return true;
    if (borrarSup && ARCADA_SUP.has(r.pieza)) return false;
    if (borrarInf && ARCADA_INF.has(r.pieza)) return false;
    return true;
  });
  return result;
}

/** Actos/realizados (con fecha) → piezas marcadas, ordenados por fecha y con exclusiones aplicadas,
 *  para que el odontograma muestre el ESTADO REAL actual (p.ej. una exodoncia borra el empaste anterior). */
export function actosAPiezas(items: { pieza: string | null; tratamiento: string; fecha?: string | null }[]): PiezaMarcada[] {
  const ord = [...items].sort((a, b) => _fechaT(a.fecha) - _fechaT(b.fecha));
  return resolverExclusiones(itemsToPiezas(ord.map((r) => ({ pieza: r.pieza, tratamiento: r.tratamiento }))));
}

export interface EstadoEstructural { missing: boolean; implante: boolean; corona: boolean; puente: boolean; }

/** Estados ESTRUCTURALES por pieza, derivados del render activo de O1 (para el periodontograma):
 *  exodoncia/ausencia→ausente, implante/corona-implante→implante, corona→corona, prótesis(fija/puente)→puente. */
export function estadosEstructurales(piezas: PiezaMarcada[]): Record<string, EstadoEstructural> {
  const out: Record<string, EstadoEstructural> = {};
  const get = (p: string) => (out[p] ??= { missing: false, implante: false, corona: false, puente: false });
  for (const pz of piezas) {
    const t = pz.tratamiento;
    if (t === "exodoncia" || t === "ausencia" || t === "ausente") get(pz.pieza).missing = true;
    else if (t === "implante" || t === "corona-implante") get(pz.pieza).implante = true;
    else if (t === "corona") get(pz.pieza).corona = true;
    else if (t === "protesis") get(pz.pieza).puente = true;
  }
  return out;
}

/** Odontograma clínico ACTIVO = el render de O2 (Tratamientos previos): hallazgos (INICIAL por
 *  defecto) + realizados, combinados en orden de fecha y resueltos con las MISMAS prioridades/
 *  exclusiones (resolverExclusiones). Fuente única que comparten O1 (ficha) y O2. */
export function construirOdontogramaClinico(
  hallazgos: Hallazgo[],
  realizados: { piezas: string | null; tratamiento: string; fecha?: string | null }[],
  opts?: { soloInicial?: boolean },
): PiezaMarcada[] {
  const fil = opts?.soloInicial ? hallazgos.filter((h) => h.tipoRegistro === "INICIAL") : hallazgos;
  // Hallazgos ordenados por fecha ("—" primero; orden de inserción como desempate) — igual que O2.
  const sorted = fil.map((h, i) => ({ h, i })).sort((a, b) => {
    const fa = a.h.fecha, fb = b.h.fecha;
    if (fa === "—" && fb !== "—") return -1;
    if (fb === "—" && fa !== "—") return 1;
    if (fa === "—" && fb === "—") return b.i - a.i;
    const ta = _fechaT(fa), tb = _fechaT(fb);
    if (ta !== tb) return ta - tb;
    return b.i - a.i;
  }).map((x) => x.h);
  const hPiezas: PiezaMarcada[] = sorted
    .filter((h) => h.pieza)
    .map((h) => ({
      pieza: h.pieza, tratamiento: h.estado.toLowerCase().replace("ó", "o"),
      caras: h.cara && h.cara !== "-" ? h.cara : undefined,
      color: ESTADO_COLOR[h.estado] || "#000",
      isPlanificado: h.tipoRegistro === "PRESUPUESTADO", isInicial: false,
    }));
  const reaOrden = [...realizados].sort((a, b) => _fechaT(a.fecha) - _fechaT(b.fecha));
  const rPiezas = itemsToPiezas(reaOrden.map((r) => ({ pieza: r.piezas, tratamiento: r.tratamiento })));
  // Hallazgos primero, realizados después → mismas prioridades/exclusiones que O2.
  return resolverExclusiones([...hPiezas, ...rPiezas]);
}
