"use client";
import { FileText } from "lucide-react";
/**
 * Piezas comunes del chat de WhatsApp: tipos del backend (`comunicacion_router`), agrupación por
 * fecha, media en línea y plantillas. Las usan la bandeja de /comunicacion y el área WhatsApp de Inicio.
 */
import { API_BASE } from "@/shared/lib/api";

export type Conv = {
  id: number; telefono: string; nombre: string; pacienteId: number | null;
  estado: string; tags: string | null; noLeidos: number;
  ultimoMensaje: string | null; ultimoMensajeAt: string | null;
  ultimaDireccion: "entrante" | "saliente" | null; fijada: boolean; urgente: boolean;
  iaPausada?: boolean; iaPausadaHasta?: string | null;
  archivada?: boolean;
};
export type Msg = {
  id: number; direccion: "entrante" | "saliente" | "nota"; cuerpo: string; estado: string;
  generadoPorIa: boolean; enviadoAt: string | null; fijado?: boolean;
  mediaUrl?: string | null; mediaTipo?: string | null; mediaNombre?: string | null;
  eliminado?: boolean; editado?: boolean;
};
// Textos que el backend guarda como cuerpo cuando se adjunta un archivo SIN caption
// (comunicacion_service.py, _MEDIA_DESC) — se ocultan en el hilo porque el adjunto ya se ve.
export const MEDIA_PLACEHOLDERS = new Set(["[imagen]", "[vídeo]", "[audio]", "[documento]", "[archivo]"]);
// Plantillas rápidas (texto plano; el operador las edita antes de enviar).
export const PLANTILLAS = [
  { label: "Saludo", texto: "¡Hola! Le escribimos desde la clínica. ¿En qué podemos ayudarle?" },
  { label: "Confirmar cita", texto: "Le recordamos su próxima cita. ¿Puede confirmarnos su asistencia, por favor?" },
  { label: "Recordatorio", texto: "Le recordamos que tiene una cita pendiente con nosotros. Quedamos a su disposición." },
  { label: "En espera", texto: "Gracias por su mensaje. Lo revisamos y le respondemos enseguida." },
  { label: "Horario", texto: "Nuestro horario de atención es de lunes a viernes, mañana y tarde. ¿Le viene bien algún día?" },
  { label: "Despedida", texto: "¡Gracias por contactar con nosotros! Que tenga un buen día. 😊" },
];

export { errMsg } from "@/shared/lib/errores";
export const hora = (iso: string | null) =>
  iso ? new Date(iso).toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" }) : "";
export function etiquetaFecha(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  const a = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const hoy = new Date(); const h0 = new Date(hoy.getFullYear(), hoy.getMonth(), hoy.getDate());
  const diff = Math.round((h0.getTime() - a.getTime()) / 86400000);
  if (diff === 0) return "Hoy";
  if (diff === 1) return "Ayer";
  return d.toLocaleDateString("es-ES", { day: "2-digit", month: "long", ...(a.getFullYear() !== h0.getFullYear() ? { year: "numeric" } : {}) });
}
export function agruparPorFecha(msgs: Msg[]): { fecha: string; items: Msg[] }[] {
  const out: { fecha: string; items: Msg[] }[] = [];
  for (const m of msgs) {
    const f = etiquetaFecha(m.enviadoAt);
    const last = out[out.length - 1];
    if (last && last.fecha === f) last.items.push(m);
    else out.push({ fecha: f, items: [m] });
  }
  return out;
}
export const mediaSrc = (u: string) => (u.startsWith("http") || u.startsWith("data:") ? u : `${API_BASE}${u}`);
export function MediaView({ m }: { m: Msg }) {
  if (!m.mediaUrl) return null;
  const url = mediaSrc(m.mediaUrl);
  const t = (m.mediaTipo || "").toLowerCase();
  if (t.includes("image")) return <a href={url} target="_blank" rel="noreferrer">{/* eslint-disable-next-line @next/next/no-img-element */}<img src={url} alt="" className="max-h-[240px] rounded-sm mb-1 object-contain" /></a>;
  if (t.includes("audio")) return <audio controls src={url} className="max-w-[240px] h-8 mb-1" />;
  if (t.includes("video")) return <video controls src={url} className="max-h-[200px] rounded-sm mb-1" />;
  return <a href={url} target="_blank" rel="noreferrer" className="flex items-center gap-2 bg-[#FFFFFF] border border-[#e5e7eb] rounded-sm p-2 mb-1 hover:bg-[#E6EDFF] transition-colors"><FileText className="h-4 w-4 text-[#3388FF] shrink-0" /><span className="text-[11px] text-[#1500A0] font-semibold truncate">{m.mediaNombre || "Documento"}</span></a>;
}

