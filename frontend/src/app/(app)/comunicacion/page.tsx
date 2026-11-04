"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Send } from "lucide-react";
import { api } from "@/shared/lib/api";
import { type Conv, type Msg } from "@/features/comunicacion/chatComun";
import { errMsg, hora } from "@/features/comunicacion/chatComun";

export default function ComunicacionPage() {
  const router = useRouter();
  const [convs, setConvs] = useState<Conv[]>([]);
  const [activa, setActiva] = useState<Conv | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [texto, setTexto] = useState("");
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    api.get<{ data: Conv[] }>("/comunicacion/conversaciones").then((r) => {
      setConvs(r.data);
      setCargando(false);
    }).catch(() => setCargando(false));
  }, []);

  useEffect(() => {
    if (!activa) return;
    api.get<{ data: Msg[] }>(`/comunicacion/conversaciones/${activa.id}/mensajes`).then((r) => setMsgs(r.data)).catch(() => setMsgs([]));
    api.get(`/comunicacion/contexto/${encodeURIComponent(activa.telefono)}`).catch(() => {});
  }, [activa]);

  const enviar = async () => {
    if (!activa || !texto.trim()) return;
    try {
      await api.post(`/comunicacion/conversaciones/${activa.id}/mensajes`, { texto: texto.trim() });
      setTexto("");
      api.get<{ data: Msg[] }>(`/comunicacion/conversaciones/${activa.id}/mensajes`).then((r) => setMsgs(r.data)).catch(() => {});
    } catch (e) {
      alert(errMsg(e));
    }
  };

  if (cargando) {
    return (
      <div className="flex h-screen items-center justify-center text-[#7f8c8d]">
        Cargando conversaciones...
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Lista de conversaciones */}
      <div className="flex-1 overflow-y-auto">
        {convs.length === 0 ? (
          <div className="p-4 text-center text-[#7f8c8d]">No hay conversaciones</div>
        ) : (
          convs.map((c) => (
            <button
              key={c.id}
              onClick={() => setActiva(c)}
              className={`w-full text-left p-3 border-b ${
                activa?.id === c.id ? "bg-gray-100" : "hover:bg-gray-50"
              }`}
            >
              <span className="font-medium">{c.nombre}</span>
              <span className="text-xs text-gray-500"> - {c.telefono}</span>
              {c.ultimoMensaje && (
                <div className="text-sm text-gray-600 truncate max-w-xs">{c.ultimoMensaje}</div>
              )}
              <span className="text-xs text-gray-400"> {hora(c.ultimoMensajeAt)}</span>
            </button>
          ))
        )}
      </div>

      {/* Chat */}
      {activa ? (
        <>
          <div className="flex-1 overflow-y-auto p-3">
            {msgs.length === 0 ? (
              <div className="text-center text-[#7f8c8d]">Sin mensajes</div>
            ) : (
              msgs.map((m) => (
                <div key={m.id} className={`mb-2 ${m.direccion === "saliente" ? "justify-end" : "justify-start"} flex`}>
                  <div className={`max-w-[80%] p-2 rounded ${
                    m.direccion === "saliente" ? "bg-blue-100" : "bg-gray-100"
                  }`}>
                    {m.cuerpo}
                    <div className="text-xs text-gray-500 text-right">{hora(m.enviadoAt)}</div>
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Input */}
          <div className="p-3 border-t">
            <div className="flex gap-2">
              <input
                value={texto}
                onChange={(e) => setTexto(e.target.value)}
                placeholder="Escribe un mensaje..."
                className="flex-1 p-2 border rounded"
                onKeyDown={(e) => e.key === "Enter" && enviar()}
              />
              <button
                onClick={enviar}
                disabled={!texto.trim()}
                className="px-3 py-2 bg-blue-500 text-white rounded disabled:opacity-50"
              >
                <Send className="h-4 w-4" />
              </button>
            </div>
          </div>
        </>
      ) : (
        <div className="flex-1 flex items-center justify-center text-[#7f8c8d]">
          {cargando ? "Cargando..." : "Selecciona una conversación"}
        </div>
      )}
    </div>
  );
}