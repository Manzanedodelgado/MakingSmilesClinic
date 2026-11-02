/**
 * Motor de incógnitas — el corazón de "La Consulta Viva".
 * No es un formulario SOAP: es un mapa de PREGUNTAS CLÍNICAS abiertas sobre el paciente,
 * cada una con su hipótesis y su % de confianza. La consulta consiste en CERRARLAS.
 * Aquí derivamos las incógnitas iniciales desde los datos REALES del paciente (sin IA todavía);
 * ESCUCHA/copiloto las moverán después.
 */
import type { AlertasData, Presupuestos, OdontogramaData } from "../../types/patient";

export type EstadoIncognita = "abierta" | "resuelta" | "descartada";
export type OrigenIncognita = "motivo" | "alerta" | "presupuesto" | "odontograma" | "escucha";

export interface Incognita {
  id: string;
  pregunta: string;          // "¿Por qué duele el 46?"
  pieza: string | null;      // ancla FDI (si aplica)
  hipotesis: string;         // mejor sospecha actual
  confianza: number;         // 0..100
  necesita: string;          // qué falta para cerrarla
  evidencias: string[];      // lo que se ha dicho/visto/medido y la mueve
  propuesta: { texto: string; precio: number | null } | null;
  estado: EstadoIncognita;
  origen: OrigenIncognita;
}

let _seq = 0;
export const nuevaIncognita = (p: Partial<Incognita> & { pregunta: string }): Incognita => ({
  id: `inc-${++_seq}`,
  pieza: null, hipotesis: "—", confianza: 0, necesita: "", evidencias: [],
  propuesta: null, estado: "abierta", origen: "escucha",
  ...p,
});

const REALIZADA = (e: string | null) => (e ?? "").toUpperCase() === "REALIZADA";

export function derivarIncognitas(d: {
  alertas?: AlertasData | null;
  presupuestos?: Presupuestos | null;
  odontograma?: OdontogramaData | null;
}): Incognita[] {
  const out: Incognita[] = [];

  // 1) El motivo — siempre abierta, a 0. La cierra la conversación.
  out.push(nuevaIncognita({
    pregunta: "¿Motivo de la visita de hoy?",
    necesita: "Escuchar al paciente", origen: "motivo",
  }));

  // 2) Alertas médicas activas → precauciones (hechos conocidos, confianza alta).
  for (const a of d.alertas?.alertas ?? []) {
    if (!a.activo) continue;
    out.push(nuevaIncognita({
      pregunta: `Precaución: ${a.texto}`,
      hipotesis: "Alerta médica activa — tenerla en cuenta en el plan",
      confianza: 100, origen: "alerta",
    }));
  }

  // 3) Líneas de presupuesto aceptado / en curso, pendientes → ¿se hace hoy?
  const pend = (d.presupuestos?.presupuestos ?? [])
    .filter((p) => p.estado === "Aceptado" || p.estado === "En curso")
    .flatMap((p) => p.lineas)
    .filter((l) => !REALIZADA(l.estado))
    .slice(0, 6);
  for (const l of pend) {
    out.push(nuevaIncognita({
      pregunta: `¿Se realiza hoy ${l.tratamiento}${l.pieza ? ` · ${l.pieza}` : ""}?`,
      pieza: l.pieza, hipotesis: "Pendiente de presupuesto aceptado",
      confianza: 50, necesita: "Decisión del doctor",
      propuesta: { texto: l.tratamiento, precio: l.precio }, origen: "presupuesto",
    }));
  }

  // 4) Caries inicial en el odontograma → ¿tratar?
  const caries = (d.odontograma?.teeth ?? [])
    .filter((h) => h.tipoRegistro === "INICIAL" && /CARIES/i.test(h.estado))
    .slice(0, 6);
  for (const h of caries) {
    out.push(nuevaIncognita({
      pregunta: `¿Tratar caries en ${h.pieza}?`, pieza: h.pieza,
      hipotesis: "Hallazgo en odontograma", confianza: 40,
      necesita: "Confirmar con exploración / Rx", origen: "odontograma",
    }));
  }

  return out;
}
