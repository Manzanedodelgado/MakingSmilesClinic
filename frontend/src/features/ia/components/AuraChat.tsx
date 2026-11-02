"use client";
/**
 * Chat flotante con Aura (SuperUser). Se abre desde el icono de la app al pie del rail
 * lateral — solo visible/clicable si el usuario tiene el permiso `superuser`.
 *
 * NO es un overlay de pantalla completa: flota en la esquina y deja trabajar en el resto
 * de la web. Minimizar NO desmonta el componente (`hidden`, no un `&&` condicional) — así
 * el hilo de conversación (`historial`) se conserva mientras está minimizado. El contador
 * de mensajes sin leer vive en el layout padre (icono de origen), no aquí.
 *
 * Aura es de SOLO LECTURA (ver `application/services/aura_agente.py`): consulta métricas,
 * auditoría y usuarios reales del centro. No cambia nada por su cuenta.
 */
import { useEffect, useRef, useState } from "react";
import { Minus, Loader2, ShieldCheck, Send } from "lucide-react";
import { api } from "@/shared/lib/api";
import { errMsg } from "@/shared/lib/errores";

type Turno = { role: "user" | "assistant"; content: string };
type ChatResp = { ok: boolean; respuesta: string; herramientasUsadas?: string[]; historial: Turno[] };


export function AuraChat({ minimizado, onMinimizar, onRespuesta }: {
  minimizado: boolean;
  onMinimizar: () => void;
  onRespuesta: () => void;   // avisa al layout de una respuesta nueva (para el contador)
}) {
  const [historial, setHistorial] = useState<Turno[]>([]);
  const [texto, setTexto] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const finRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!minimizado) finRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [historial, enviando, minimizado]);

  // Al deshabilitar el input mientras se envía, el navegador le quita el foco y no lo
  // devuelve solo — sin esto, tras cada mensaje hay que volver a pinchar con el ratón.
  useEffect(() => {
    if (!enviando && !minimizado) inputRef.current?.focus();
  }, [enviando, minimizado]);

  const enviar = async () => {
    const msg = texto.trim();
    if (!msg || enviando) return;
    setTexto(""); setError(null);
    setHistorial((h) => [...h, { role: "user", content: msg }]);
    setEnviando(true);
    try {
      const res = await api.post<ChatResp>("/agentes/aura/chat", { texto: msg, historial });
      if (!res.ok) { setError(res.respuesta); setHistorial((h) => h.slice(0, -1)); return; }
      setHistorial((h) => [...h, { role: "assistant", content: res.respuesta }]);
      onRespuesta();
    } catch (e) {
      setError(errMsg(e));
      setHistorial((h) => h.slice(0, -1));
    } finally { setEnviando(false); }
  };

  return (
    <div
      className={`fixed z-[100] bottom-4 right-4 sm:bottom-6 sm:right-6 bg-white rounded-lg shadow-2xl w-[360px] max-w-[calc(100vw-2rem)] flex flex-col overflow-hidden transition-all ${
        minimizado ? "hidden" : ""
      }`}
      style={{ height: "min(70vh, 560px)" }}
    >
      <div className="flex items-center justify-between px-4 py-3 bg-[#1500A0] shrink-0">
        <span className="flex items-center gap-2 text-white">
          <ShieldCheck className="w-4 h-4" />
          <b className="text-[13px] uppercase tracking-wide">Aura · SuperUser</b>
        </span>
        <button onClick={onMinimizar} title="Minimizar" className="text-white/80 hover:text-white cursor-pointer">
          <Minus className="w-4 h-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-2 bg-[#FFFFFF]">
        {historial.length === 0 && (
          <p className="text-[11.5px] text-slate-400 text-center mt-6">
            Pregúntale a Aura por métricas del centro, el registro de auditoría o quién
            tiene acceso. Es de solo lectura: no cambia nada por su cuenta.
          </p>
        )}
        {historial.map((t, i) => (
          <div key={i} className={`max-w-[85%] rounded-lg px-3 py-2 text-[12.5px] leading-snug whitespace-pre-wrap ${
            t.role === "user" ? "self-end bg-[#1500A0] text-white" : "self-start bg-white border border-[#e5e7eb] text-slate-700"
          }`}>
            {t.content}
          </div>
        ))}
        {enviando && (
          <div className="self-start bg-white border border-[#e5e7eb] rounded-lg px-3 py-2">
            <Loader2 className="w-3.5 h-3.5 animate-spin text-[#1ca0d1]" />
          </div>
        )}
        {error && (
          <div className="self-start bg-[#FFFFFF] border border-[#F0C4F7] text-[#A21CAF] rounded-lg px-3 py-2 text-[11.5px]">
            {error}
          </div>
        )}
        <div ref={finRef} />
      </div>

      <div className="flex items-center gap-2 p-2.5 border-t border-[#e5e7eb] shrink-0">
        <input
          ref={inputRef}
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); enviar(); } }}
          placeholder="Escribe a Aura…"
          disabled={enviando}
          className="flex-1 px-3 py-2 text-[12.5px] border border-[#e5e7eb] rounded-md focus:outline-none focus:ring-1 focus:ring-[#1500A0]"
        />
        <button onClick={enviar} disabled={enviando || !texto.trim()}
                className="w-9 h-9 shrink-0 rounded-md bg-[#1500A0] text-white flex items-center justify-center disabled:opacity-40 hover:brightness-110">
          <Send className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
