"use client";
/**
 * Chat con el Gestor IA, a pantalla completa dentro de Gestoría (como Alex en Pacientes y
 * Victor en el equipo). El Gestor es de SOLO LECTURA: contesta sobre el banco (Debe/Haber),
 * las facturas y los pagos de pacientes (informe contable), pero no cambia nada; los cambios se hacen
 * en las pestañas de Gestoría. La conversación se guarda en sessionStorage, por usuario.
 *
 * Responde a través de POST /agentes/gestor/chat (exige gestoria.ver).
 */
import { useEffect, useRef, useState } from "react";
import { Bot, Loader2, Send, Trash2 } from "lucide-react";
import { api } from "@/shared/lib/api";
import { errMsg } from "@/shared/lib/errores";
import { useMe } from "@/shared/hooks/useMe";

type Turno = { role: "user" | "assistant"; content: string };
type ChatResp = { ok: boolean; respuesta: string; historial?: Turno[]; herramientasUsadas?: string[] };

// Desglose de lo que se le puede pedir: cada bloque es una parte del informe contable (se actualiza solo).
const DESGLOSE: { titulo: string; detalle: string; preguntas: string[] }[] = [
  { titulo: "Debe", detalle: "Lo que sale del banco, por mes y año.",
    preguntas: ["¿Cuánto salió del banco cada mes este año?"] },
  { titulo: "Haber", detalle: "Lo que entra en el banco, por mes y año.",
    preguntas: ["¿Cuánto entró en el banco cada mes este año?"] },
  { titulo: "Facturas", detalle: "Totales por mes, año, forma de pago y estado.",
    preguntas: ["¿Cuánto facturamos de proveedores este año por forma de pago?"] },
  { titulo: "Pagos de pacientes", detalle: "Totales por mes, año y forma de pago.",
    preguntas: ["¿Cuánto cobramos de pacientes cada mes este año por forma de pago?"] },
];

function leer(clave: string): Turno[] {
  try {
    const raw = sessionStorage.getItem(clave);
    return raw ? (JSON.parse(raw) as Turno[]) : [];
  } catch {
    return [];
  }
}

export function GestorChat() {
  const { usuario_id } = useMe();
  const clave = usuario_id ? `gestor-chat:${usuario_id}` : null;
  const [historial, setHistorial] = useState<Turno[]>([]);
  const [cargado, setCargado] = useState(false);
  const [texto, setTexto] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const finRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!clave) return;
    setHistorial(leer(clave));
    setCargado(true);
  }, [clave]);

  useEffect(() => {
    if (!clave || !cargado) return;
    try { sessionStorage.setItem(clave, JSON.stringify(historial)); } catch { /* sin almacenamiento: sigue en memoria */ }
  }, [clave, cargado, historial]);

  useEffect(() => { finRef.current?.scrollIntoView({ behavior: "smooth" }); }, [historial, enviando]);
  useEffect(() => { if (!enviando) inputRef.current?.focus(); }, [enviando]);

  const enviar = async (msg: string) => {
    msg = msg.trim();
    if (!msg || enviando) return;
    const previo = historial;
    setTexto(""); setError(null);
    setHistorial([...previo, { role: "user", content: msg }]);
    setEnviando(true);
    try {
      const res = await api.post<ChatResp>("/agentes/gestor/chat", { texto: msg, historial: previo });
      if (!res.ok) {
        setError(res.respuesta);
        setHistorial(previo);
        return;
      }
      setHistorial([...previo, { role: "user", content: msg }, { role: "assistant", content: res.respuesta }]);
    } catch (err) {
      setError(errMsg(err));
      setHistorial(previo);
    } finally {
      setEnviando(false);
    }
  };

  return (
    <div className="flex flex-col flex-1 min-h-0 bg-white">
      <div className="flex items-center justify-between px-5 py-3 border-b border-[#e5e7eb] shrink-0">
        <span className="flex items-center gap-2 text-[14px] text-slate-700">
          <span className="w-8 h-8 rounded-full bg-[#2DD9C3] text-white flex items-center justify-center"><Bot className="w-4 h-4" /></span>
          <span>
            <span className="block font-medium leading-tight">Gestor IA</span>
            <span className="block text-[11.5px] text-slate-400 leading-tight">Informe contable: Debe, Haber, facturas y pagos de pacientes. Solo consulta.</span>
          </span>
        </span>
        <button
          onClick={() => { setHistorial([]); setError(null); }}
          disabled={historial.length === 0}
          title="Nueva conversación"
          className="flex items-center gap-1.5 text-[12px] text-slate-500 hover:text-slate-700 disabled:opacity-40 cursor-pointer"
        >
          <Trash2 className="w-3.5 h-3.5" /> Nueva conversación
        </button>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto px-5 py-4 bg-[#FFFFFF]">
        <div className="max-w-3xl mx-auto flex flex-col gap-2.5">
          {historial.length === 0 && (
            <div className="mt-6">
              <div className="self-start max-w-[85%] bg-white border border-[#e5e7eb] rounded-lg px-3.5 py-3 text-[13px] leading-snug text-slate-700">
                <p><b>Hola, soy el Gestor IA.</b> Consulto el informe contable de la clínica, que se actualiza solo.
                  No cambio nada: solo te cuento lo que hay. Esto es lo que puedes pedirme:</p>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-3">
                {DESGLOSE.map((d) => (
                  <div key={d.titulo} className="bg-white border border-[#e5e7eb] rounded-lg px-3.5 py-3">
                    <p className="text-[13px] font-medium text-slate-700">{d.titulo}</p>
                    <p className="text-[12px] text-slate-400 mb-2">{d.detalle}</p>
                    {d.preguntas.map((q) => (
                      <button key={q} onClick={() => enviar(q)}
                              className="text-left px-2.5 py-1.5 rounded-full border border-[#d1d5db] text-[12px] text-slate-600 hover:border-[#2DD9C3] hover:text-slate-800 cursor-pointer">
                        {q}
                      </button>
                    ))}
                  </div>
                ))}
              </div>
              <p className="text-[12px] text-slate-400 mt-3">También puedes escribir lo tuyo: un mes, un año, una forma de pago…</p>
            </div>
          )}
          {historial.map((t, i) => (
            <div key={i} className={`max-w-[85%] rounded-lg px-3.5 py-2.5 text-[13px] leading-snug whitespace-pre-wrap ${
              t.role === "user" ? "self-end bg-[#013b82] text-white" : "self-start bg-white border border-[#e5e7eb] text-slate-700"
            }`}>
              {t.content}
            </div>
          ))}
          {enviando && (
            <div className="self-start bg-white border border-[#e5e7eb] rounded-lg px-3.5 py-2.5">
              <Loader2 className="w-4 h-4 animate-spin text-[#2DD9C3]" />
            </div>
          )}
          {error && (
            <div className="self-start bg-[#FFFFFF] border border-[#F0C4F7] text-[#A21CAF] rounded-lg px-3.5 py-2.5 text-[12px]">
              {error}
            </div>
          )}
          <div ref={finRef} />
        </div>
      </div>

      <div className="px-5 py-3 border-t border-[#e5e7eb] shrink-0">
        <div className="max-w-3xl mx-auto flex items-end gap-2">
          <textarea
            ref={inputRef}
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); enviar(texto); } }}
            placeholder="Escribe al Gestor IA…"
            rows={1}
            disabled={enviando}
            className="flex-1 resize-none px-3 py-2 text-[13px] border border-[#e5e7eb] rounded-md focus:outline-none focus:ring-1 focus:ring-[#2DD9C3]"
          />
          <button
            onClick={() => enviar(texto)}
            disabled={enviando || !texto.trim()}
            className="w-10 h-10 shrink-0 rounded-md bg-[#013b82] text-white flex items-center justify-center disabled:opacity-40 hover:brightness-110 cursor-pointer"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
