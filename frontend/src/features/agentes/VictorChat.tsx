"use client";
/**
 * Chat flotante con Victor (agente del equipo), disponible en toda la web.
 *
 * Se abre con un botón en la esquina y se puede dejar abierto o minimizado mientras se
 * trabaja en el resto de la web: va montado en el layout común, así que no se desmonta al
 * cambiar de pantalla. La conversación, las acciones pendientes y si estaba abierto o
 * minimizado se guardan en sessionStorage (dura lo que la sesión del navegador), por
 * usuario: otra persona que entre en el mismo navegador no ve la conversación anterior.
 *
 * Victor contesta a través de su operador de Jarvis (POST /agentes/victor/chat, exige
 * citas.ver). Nunca cambia nada solo: lo que toca datos vuelve en `accionesPendientes` y
 * aquí se confirma con su endpoint (bloquear agenda exige citas.editar).
 */
import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { Bot, Minus, Loader2, Send, Trash2, Check } from "lucide-react";
import { api } from "@/shared/lib/api";
import { errMsg } from "@/shared/lib/errores";
import { useMe } from "@/shared/hooks/useMe";
import { usePermisos } from "@/shared/hooks/usePermisos";

type Turno = { role: "user" | "assistant"; content: string };
type Accion = {
  accion: string;
  args: Record<string, unknown>;
  resumen?: string;
  citasAfectadas?: number;
  estado?: "pendiente" | "hecha" | "error";
  detalle?: string;
};
type ChatResp = { ok: boolean; respuesta: string; historial?: Turno[]; accionesPendientes?: Accion[] };
type Estado = { abierto: boolean; minimizado: boolean; historial: Turno[]; acciones: Accion[]; sinLeer: number };

const VACIO: Estado = { abierto: false, minimizado: false, historial: [], acciones: [], sinLeer: 0 };

function leer(clave: string): Estado {
  try {
    const raw = sessionStorage.getItem(clave);
    return raw ? { ...VACIO, ...JSON.parse(raw) } : VACIO;
  } catch {
    return VACIO;
  }
}

export function VictorChat() {
  const { usuario_id } = useMe();
  // En móvil el botón flotante taparía el «enviar» del compositor de WhatsApp.
  const enWhatsApp = usePathname()?.startsWith("/comunicacion") ?? false;
  const { has, loading } = usePermisos();
  const clave = usuario_id ? `victor-chat:${usuario_id}` : null;

  const [estado, setEstado] = useState<Estado>(VACIO);
  const [cargado, setCargado] = useState(false);
  const [texto, setTexto] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const finRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Recupera la conversación de esta sesión (solo cuando ya se sabe quién es el usuario).
  useEffect(() => {
    if (!clave) return;
    setEstado(leer(clave));
    setCargado(true);
  }, [clave]);

  useEffect(() => {
    if (!clave || !cargado) return;
    try { sessionStorage.setItem(clave, JSON.stringify(estado)); } catch { /* sin almacenamiento: sigue en memoria */ }
  }, [clave, cargado, estado]);

  const visible = estado.abierto && !estado.minimizado;
  useEffect(() => {
    if (visible) finRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [estado.historial, estado.acciones, enviando, visible]);
  useEffect(() => {
    if (!enviando && visible) inputRef.current?.focus();
  }, [enviando, visible]);

  if (loading || !clave || !has("citas.ver")) return null;

  const abrir = () => setEstado((e) => ({ ...e, abierto: true, minimizado: false, sinLeer: 0 }));
  const minimizar = () => setEstado((e) => ({ ...e, minimizado: true }));
  const nueva = () => { setEstado((e) => ({ ...e, historial: [], acciones: [], sinLeer: 0 })); setError(null); };

  const enviar = async () => {
    const msg = texto.trim();
    if (!msg || enviando) return;
    const previo = estado.historial;
    setTexto(""); setError(null);
    setEstado((e) => ({ ...e, historial: [...e.historial, { role: "user", content: msg }] }));
    setEnviando(true);
    try {
      const res = await api.post<ChatResp>("/agentes/victor/chat", { texto: msg, historial: previo });
      if (!res.ok) {
        setError(res.respuesta);
        setEstado((e) => ({ ...e, historial: previo }));
        return;
      }
      const nuevas = (res.accionesPendientes ?? []).map((a) => ({ ...a, estado: "pendiente" as const }));
      setEstado((e) => ({
        ...e,
        historial: [...e.historial, { role: "assistant", content: res.respuesta }],
        acciones: [...e.acciones, ...nuevas],
        sinLeer: e.minimizado || !e.abierto ? e.sinLeer + 1 : 0,
      }));
    } catch (err) {
      setError(errMsg(err));
      setEstado((e) => ({ ...e, historial: previo }));
    } finally {
      setEnviando(false);
    }
  };

  const confirmar = async (i: number) => {
    const a = estado.acciones[i];
    if (!a || a.accion !== "bloquear_agenda") return;
    try {
      await api.post("/agentes/victor/agenda/bloquear", { ...a.args, confirmar: true });
      setEstado((e) => ({ ...e, acciones: e.acciones.map((x, j) => (j === i ? { ...x, estado: "hecha" } : x)) }));
    } catch (err) {
      setEstado((e) => ({ ...e, acciones: e.acciones.map((x, j) => (j === i ? { ...x, estado: "error", detalle: errMsg(err) } : x)) }));
    }
  };

  const descartar = (i: number) =>
    setEstado((e) => ({ ...e, acciones: e.acciones.filter((_, j) => j !== i) }));

  return (
    <>
      {!visible && (
        <button
          onClick={abrir}
          title="Hablar con Victor"
          className={`fixed z-[100] bottom-4 right-4 sm:bottom-6 sm:right-6 w-12 h-12 rounded-full bg-[#1500A0] text-white shadow-lg flex items-center justify-center hover:brightness-110 cursor-pointer ${enWhatsApp ? "max-lg:hidden" : ""}`}
        >
          <Bot className="w-5 h-5" />
          {estado.sinLeer > 0 && (
            <span className="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 rounded-full bg-[#C026D3] text-white text-[10px] flex items-center justify-center">
              {estado.sinLeer}
            </span>
          )}
        </button>
      )}

      <div
        className={`fixed z-[100] bottom-4 right-4 sm:bottom-6 sm:right-6 bg-white rounded-lg shadow-2xl w-[360px] max-w-[calc(100vw-2rem)] flex flex-col overflow-hidden ${visible ? "" : "hidden"}`}
        style={{ height: "min(70vh, 560px)" }}
      >
        <div className="flex items-center justify-between px-4 py-3 bg-[#1500A0] shrink-0">
          <span className="flex items-center gap-2 text-white text-[13px]">
            <Bot className="w-4 h-4" /> Victor
          </span>
          <span className="flex items-center gap-3">
            <button onClick={nueva} title="Nueva conversación" className="text-white/70 hover:text-white cursor-pointer">
              <Trash2 className="w-3.5 h-3.5" />
            </button>
            <button onClick={minimizar} title="Minimizar" className="text-white/80 hover:text-white cursor-pointer">
              <Minus className="w-4 h-4" />
            </button>
          </span>
        </div>

        <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-2 bg-[#FFFFFF]">
          {estado.historial.length === 0 && (
            <p className="text-[11.5px] text-slate-400 text-center mt-6">
              Pregúntale a Victor por la agenda, el resumen del día o pídele que prepare un
              bloqueo. Lo que cambie datos te lo propone y lo confirmas tú.
            </p>
          )}
          {estado.historial.map((t, i) => (
            <div key={i} className={`max-w-[85%] rounded-lg px-3 py-2 text-[12.5px] leading-snug whitespace-pre-wrap ${
              t.role === "user" ? "self-end bg-[#1500A0] text-white" : "self-start bg-white border border-[#e5e7eb] text-slate-700"
            }`}>
              {t.content}
            </div>
          ))}
          {estado.acciones.map((a, i) => (
            <div key={`a${i}`} className="self-stretch rounded-lg border border-[#c7d2fe] bg-[#FFFFFF] px-3 py-2 text-[12px] text-slate-700">
              <p>{a.resumen || a.accion}</p>
              {typeof a.citasAfectadas === "number" && <p className="text-[11px] text-slate-500">Citas afectadas: {a.citasAfectadas}</p>}
              {a.estado === "pendiente" && (
                <div className="flex gap-2 mt-1.5">
                  <button onClick={() => confirmar(i)} className="flex items-center gap-1 px-2 py-1 rounded bg-[#1500A0] text-white text-[11px] cursor-pointer hover:brightness-110">
                    <Check className="w-3 h-3" /> Confirmar
                  </button>
                  <button onClick={() => descartar(i)} className="px-2 py-1 rounded border border-[#c7d2fe] text-[11px] text-slate-600 cursor-pointer hover:bg-white">
                    Descartar
                  </button>
                </div>
              )}
              {a.estado === "hecha" && <p className="text-[11px] text-[#0F8C7D] mt-1">Hecho.</p>}
              {a.estado === "error" && <p className="text-[11px] text-[#A21CAF] mt-1">{a.detalle || "No se pudo hacer."}</p>}
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
            placeholder="Escribe a Victor…"
            disabled={enviando}
            className="flex-1 px-3 py-2 text-[12.5px] border border-[#e5e7eb] rounded-md focus:outline-none focus:ring-1 focus:ring-[#1500A0]"
          />
          <button onClick={enviar} disabled={enviando || !texto.trim()}
                  className="w-9 h-9 shrink-0 rounded-md bg-[#1500A0] text-white flex items-center justify-center disabled:opacity-40 hover:brightness-110 cursor-pointer">
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </>
  );
}
