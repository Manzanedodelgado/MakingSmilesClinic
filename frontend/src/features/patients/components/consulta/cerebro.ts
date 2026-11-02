/**
 * El cerebro del flujo vivo — enruta lo que se dice a la incógnita correcta.
 * Versión heurística (sin LLM): lee piezas FDI y términos del diccionario del gabinete
 * (ver docs/DICCIONARIO-GABINETE.md) y decide a qué incógnita ancla la evidencia, cuánto
 * sube su confianza, si propone un tratamiento o si abre una incógnita nueva.
 * Cuando haya clave LLM (integración NVIDIA/OpenRouter), esto se sustituye por una llamada
 * al modelo que devuelva la misma Decision — el resto del sistema no cambia.
 */
import type { Incognita } from "./incognitas";

// Spec de una incógnita nueva (sin id): el que la aplica la envuelve con nuevaIncognita().
// Mismo formato que devuelve el cerebro LLM del backend → aplicación unificada.
export type NuevaSpec = Partial<Incognita> & { pregunta: string };

// Piezas FDI (adulto 1x-4x, temporal 5x-8x).
const FDI = /\b([1-4][1-8]|[5-8][1-5])\b/g;

// Términos coloquiales → familia de tratamiento del catálogo (resumen del diccionario).
const TRAT: { re: RegExp; nombre: string }[] = [
  { re: /endodon|matar.*nervio|quitar.*nervio|conducto/i, nombre: "ENDODONCIA" },
  { re: /reendodon|retratamiento/i, nombre: "REENDODONCIA" },
  { re: /empast|obtura/i, nombre: "OBTURACIÓN" },
  { re: /reconstru|perno|poste/i, nombre: "RECONSTRUCCION" },
  { re: /incrustac|inlay|onlay/i, nombre: "INCRUSTACION" },
  { re: /carilla|l[aá]min/i, nombre: "CARILLA" },
  { re: /funda|corona|capuch/i, nombre: "CORONA" },
  { re: /limpieza profunda|curetaj|raspad|alisad/i, nombre: "LIMPIEZA PROFUNDA" },
  { re: /limpieza|sarro|tartr|profilax/i, nombre: "LIMPIEZA O TARTRECTOMIA" },
  { re: /extra|sacar|exodon|quitar.*(muela|diente)/i, nombre: "EXODONCIA" },
  { re: /cordal|muela del juicio/i, nombre: "EXODONCIA CORDAL" },
  { re: /implante|tornillo/i, nombre: "IMPLANTE" },
  { re: /blanque/i, nombre: "BLANQUEAMIENTO" },
  { re: /f[eé]rula|descarga|bruxism|apriet/i, nombre: "FÉRULA DE DESCARGA" },
  { re: /sellad/i, nombre: "SELLADOR UNITARIO" },
];

const SINTOMA = /(dolor|duele|molest|sensib|fr[ií]o|calor|dulce|sangr|hinch|flem[oó]n|punzad|lat[ei]|palpit|sensac)/i;
const PRECAUCION = /(al[eé]rgic|alergia|sintrom|anticoagul|diab[eé]tic|embaraz|marcapas|warfarin|hipertens)/i;

export interface Decision {
  pieza: string | null;        // pieza detectada (para enfocar la boca)
  targetId: string | null;     // incógnita a la que se ancla la evidencia
  deltaConf: number;           // cuánto sube su confianza
  propuesta?: { texto: string; precio: number | null };
  nueva: NuevaSpec | null;     // incógnita que nace de la frase (sin id)
  explica: string;             // por qué (etiqueta en el flujo)
}

const casa = (nombre: string, txt: string) =>
  new RegExp(nombre.split(" ")[0].replace(/[^\wÁÉÍÓÚÑ]/gi, ""), "i").test(txt);

export function analizar(texto: string, incognitas: Incognita[], piezaActiva: string | null): Decision {
  const abiertas = incognitas.filter((i) => i.estado === "abierta");
  const pieza = ([...texto.matchAll(FDI)].map((m) => m[0])[0]) ?? piezaActiva ?? null;
  const trat = TRAT.find((t) => t.re.test(texto));

  // 1) Precaución (alergia/medicación crítica) → nueva alerta, confianza alta.
  if (PRECAUCION.test(texto)) {
    return {
      pieza, targetId: null, deltaConf: 0,
      nueva: { pregunta: `Precaución: ${texto}`, hipotesis: "Detectada en la consulta", confianza: 90, origen: "alerta", evidencias: [texto] },
      explica: "precaución médica",
    };
  }

  // 2) Pieza con incógnita abierta → ancla ahí (y propone tratamiento si se nombra).
  if (pieza) {
    const hit = abiertas.find((i) => i.pieza === pieza);
    if (hit) return { pieza, targetId: hit.id, deltaConf: 20, propuesta: trat ? { texto: trat.nombre, precio: null } : undefined, nueva: null, explica: `pieza ${pieza}` };
  }

  // 3) Tratamiento nombrado → casa con incógnita abierta, o abre una con propuesta.
  if (trat) {
    const hit = abiertas.find((i) => casa(trat.nombre, i.pregunta) || (i.propuesta && casa(trat.nombre, i.propuesta.texto)));
    if (hit) return { pieza, targetId: hit.id, deltaConf: 25, propuesta: hit.propuesta ?? { texto: trat.nombre, precio: null }, nueva: null, explica: `plan ${trat.nombre}` };
    return {
      pieza, targetId: null, deltaConf: 0,
      nueva: { pregunta: `¿${trat.nombre}${pieza ? ` · ${pieza}` : ""}?`, pieza, confianza: 55, hipotesis: "Propuesto en la consulta", propuesta: { texto: trat.nombre, precio: null }, origen: "escucha", evidencias: [texto] },
      explica: `propone ${trat.nombre}`,
    };
  }

  // 4) Síntoma → sube el motivo; si hay pieza, abre la incógnita de su causa.
  if (SINTOMA.test(texto)) {
    const motivo = abiertas.find((i) => i.origen === "motivo");
    if (pieza && !abiertas.some((i) => i.pieza === pieza)) {
      return { pieza, targetId: motivo?.id ?? null, deltaConf: 15, nueva: { pregunta: `¿Causa del dolor en ${pieza}?`, pieza, confianza: 30, hipotesis: "Síntoma referido", necesita: "Explorar / Rx", origen: "escucha", evidencias: [texto] }, explica: `síntoma · ${pieza}` };
    }
    return { pieza, targetId: motivo?.id ?? null, deltaConf: 20, nueva: null, explica: "síntoma → motivo" };
  }

  // 5) Por defecto → la incógnita activa, o el motivo.
  const fallback = abiertas.find((i) => i.origen === "motivo") ?? abiertas[0];
  return { pieza, targetId: fallback?.id ?? null, deltaConf: 10, nueva: null, explica: "contexto" };
}
