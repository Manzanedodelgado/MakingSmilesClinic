"use client";
/**
 * WHATSAPP — inbox de 3 paneles. UI completa con filtros, IA, plantillas.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Check, X, MoreVertical, CheckSquare, ChevronLeft, MessageCircle, Send, Search, RefreshCw, Wifi, WifiOff, AlertTriangle, User, Calendar, CheckCheck, Zap, FileText, Bot, Plus, CheckCircle2, Pause, Play, Pin, Paperclip, Pencil, Trash2, MailOpen, Archive, Mic, Square, StickyNote, ArchiveRestore, Smile } from "lucide-react";
import { api, API_BASE } from "@/shared/lib/api";
import { Modal, ModalBody, ModalButton, ModalTabs, MODAL_INPUT } from "@/shared/components";
import { esUrgente } from "@/shared/lib/comunicacion";
import {
  type Conv, type Msg, MEDIA_PLACEHOLDERS, PLANTILLAS, errMsg, hora, agruparPorFecha, MediaView,
} from "@/features/comunicacion/chatComun";

type Ctx = {
  encontrado: boolean;
  paciente?: { id: number; numHistoria: string | null; nombre: string; apellidos: string; telefonoMovil: string | null; aceptaBots?: boolean };
  alertas?: { texto: string; severidad: string | null }[];
  proximaCita?: { id: number; fecha: string; hora: string | null; confirmada: boolean; tratamiento: string } | null;
  ultimaCita?: { id: number; fecha: string; hora: string | null; tratamiento: string } | null;
};
type Estado = { evolution: boolean; conectado: boolean; estado: string | null; error?: string };

const FILTROS = ["No leídas", "Urgentes", "Todas", "Archivadas"] as const;
type Filtro = (typeof FILTROS)[number];
const ESTADO_DOT: Record<string, string> = { abierta: "bg-[#3388FF]", pendiente: "bg-[#7C3AED]", resuelta: "bg-[#20BEAB]" };
const EMOJIS = ["😊","😀","🙂","😉","😍","🥰","😘","😅","😢","😭","😮","🙏","👍","👌","👏","🙌","🎉","❤️","💙","🦷","😴","🤒","🤕","🤔","📅","⏰","✅","❌","📌","📞","💬","😁"];
const iniciales = (nombre: string) => (nombre || "?").trim().split(/\s+/).slice(0, 2).map((p) => p[0]?.toUpperCase() || "").join("") || "?";
type PacienteHit = { id: number; num_historia: string | null; nombre: string; apellidos: string; nif: string | null; telefono: string | null };

export default function ComunicacionClient() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [convs, setConvs] = useState<Conv[]>([]);
  const [activa, setActiva] = useState<Conv | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [texto, setTexto] = useState("");
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    api.get<{ data: Conv[] }>("/comunicacion/conversaciones").then((r) => {
      setConvs(r.data); setCargando(false);
    }).catch(() => setCargando(false));
  }, []);

  useEffect(() => {
    const tel = searchParams.get("tel");
    if (tel) {
      const n9 = tel.replace(/\D/g, "").slice(-9);
      const c = convs.find(x => x.telefono.replace(/\D/g, "").slice(-9) === n9);
      if (c) setActiva(c);
    }
  }, [searchParams, convs]);

  useEffect(() => {
    if (!activa) return;
    api.get<{ data: Msg[] }>(`/comunicacion/conversaciones/${activa.id}/mensajes`).then((r) => setMsgs(r.data)).catch(() => setMsgs([]));
  }, [activa]);

  const enviar = async () => {
    if (!activa || !texto.trim()) return;
    try {
      await api.post(`/comunicacion/conversaciones/${activa.id}/mensajes`, { texto: texto.trim() });
      setTexto("");
      api.get<{ data: Msg[] }>(`/comunicacion/conversaciones/${activa.id}/mensajes`).then((r) => setMsgs(r.data)).catch(() => {});
    } catch (e) { alert(errMsg(e)); }
  };

  if (cargando) return <div className="flex h-screen items-center justify-center text-[#7f8c8d]">Cargando conversaciones...</div>;

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto">
        {convs.length === 0 ? (
          <div className="p-4 text-center text-[#7f8c8d]">No hay conversaciones</div>
        ) : (
          convs.map((c) => (
            <button key={c.id} onClick={() => setActiva(c)} className={`w-full text-left p-3 border-b ${activa?.id === c.id ? "bg-gray-100" : "hover:bg-gray-50"}`}>
              <span className="font-medium">{c.nombre}</span>
              <span className="text-xs text-gray-500"> - {c.telefono}</span>
              {c.ultimoMensaje && <div className="text-sm text-gray-600 max-w-xs truncate">{c.ultimoMensaje}</div>}
              <span className="text-xs text-gray-400"> {hora(c.ultimoMensajeAt)}</span>
            </button>
          ))
        )}
      </div>
      {activa && (
        <>
          <div className="flex-1 overflow-y-auto p-3">
            {msgs.length === 0 ? (
              <div className="text-center text-[#7f8c8d]">Sin mensajes</div>
            ) : (
              msgs.map((m) => (
                <div key={m.id} className={`mb-2 ${m.direccion === "saliente" ? "justify-end" : "justify-start"} flex`}>
                  <div className={`max-w-[80%] p-2 rounded ${m.direccion === "saliente" ? "bg-blue-100" : "bg-gray-100"}`}>
                    {m.cuerpo}
                    <div className="text-xs text-gray-500 text-right">{hora(m.enviadoAt)}</div>
                  </div>
                </div>
              ))
            )}
          </div>
          <div className="p-3 border-t">
            <div className="flex gap-2">
              <input value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="Escribe un mensaje..." className="flex-1 p-2 border rounded" onKeyDown={(e) => e.key === "Enter" && enviar()} />
              <button onClick={enviar} disabled={!texto.trim()} className="px-3 py-2 bg-blue-500 text-white rounded disabled:opacity-50"><Send className="h-4 w-4" /></button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
