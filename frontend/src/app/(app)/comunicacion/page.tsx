"use client";
/**
 * WHATSAPP — inbox de 3 paneles (conversaciones · chat · contexto del paciente).
 * Nivel .37: filtros + orden por no-leídas, acciones de estado, agrupación por fecha,
 * burbuja de IA, media en línea y plantillas rápidas. Tiempo real por SSE (poll lento de respaldo).
 * Datos reales del backend `comunicacion_router`. Estética MakingSmiles.
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
  tratamientosRealizados?: { id: number; fecha: string | null; tratamiento: string; piezas: string | null }[];
  pagos?: { id: number; fecha: string; importe: number; formaPago: string | null }[];
};
type Estado = { evolution: boolean; conectado: boolean; estado: string | null; error?: string };

const FILTROS = ["No leídas", "Urgentes", "Todas", "Archivadas"] as const;
type Filtro = (typeof FILTROS)[number];
const ESTADO_DOT: Record<string, string> = { abierta: "bg-[#3388FF]", pendiente: "bg-[#7C3AED]", resuelta: "bg-[#20BEAB]" };
// Selección curada de emojis frecuentes en mensajería con pacientes — sin librería externa.
const EMOJIS = [
  "😊", "😀", "🙂", "😉", "😍", "🥰", "😘", "😅", "😢", "😭", "😮", "🙏",
  "👍", "👌", "👏", "🙌", "🎉", "❤️", "💙", "🦷", "😴", "🤒", "🤕", "🤔",
  "📅", "⏰", "✅", "❌", "📌", "📞", "💬", "😁",
];
// Conversación urgente = tag 'urgencia' y aún no resuelta.
// Iniciales para el avatar (estética .37): 2 primeras palabras.
const iniciales = (nombre: string) => (nombre || "?").trim().split(/\s+/).slice(0, 2).map((p) => p[0]?.toUpperCase() || "").join("") || "?";

type PacienteHit = { id: number; num_historia: string | null; nombre: string; apellidos: string; nif: string | null; telefono: string | null };

// Modal: iniciar una conversación nueva (buscar paciente o teléfono manual) → envía el 1er mensaje.
function NuevaConvModal({ onClose, onCreated, initialTel }: { onClose: () => void; onCreated: (telefono: string) => void; initialTel?: string | null }) {
  const [modo, setModo] = useState<"paciente" | "manual">(initialTel ? "manual" : "paciente");
  const [busq, setBusq] = useState("");
  const [res, setRes] = useState<PacienteHit[]>([]);
  const [sel, setSel] = useState<PacienteHit | null>(null);
  const [tel, setTel] = useState(initialTel ?? "");
  const [txt, setTxt] = useState("");
  const [enviando, setEnviando] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    if (modo !== "paciente" || busq.trim().length < 2) { setRes([]); return; }
    timer.current = setTimeout(() => {
      api.get<{ pacientes: PacienteHit[] }>(`/pacientes/buscar?q=${encodeURIComponent(busq.trim())}`)
        .then((r) => setRes(r.pacientes)).catch(() => setRes([]));
    }, 250);
    return () => { if (timer.current) clearTimeout(timer.current); };
  }, [busq, modo]);

  const telDest = modo === "paciente" ? (sel?.telefono || "") : tel.trim();
  const enviar = async () => {
    if (!telDest || !txt.trim() || enviando) return;
    setEnviando(true);
    try { await api.post("/comunicacion/whatsapp/enviar", { telefono: telDest, texto: txt.trim() }); onCreated(telDest); }
    catch (e) { alert(errMsg(e)); } finally { setEnviando(false); }
  };

  return (
    <Modal
      title={<span className="flex items-center gap-2"><MessageCircle className="w-4 h-4" />Nueva conversación</span>}
      onClose={onClose}
      size="sm"
      zIndex={70}
      closeOnBackdrop={false}
      footer={
        <>
          <ModalButton variant="magenta" icon={X} onClick={onClose}>Cancelar</ModalButton>
          <ModalButton variant="primary" icon={Send} onClick={enviar} disabled={enviando || !telDest || !txt.trim()}>Enviar</ModalButton>
        </>
      }
    >
      <ModalTabs
        tabs={[{ id: "paciente", label: "Paciente" }, { id: "manual", label: "Número manual" }]}
        activeTab={modo}
        onChange={(id) => setModo(id as "paciente" | "manual")}
      />
      <ModalBody>
        <div className="space-y-3">
          {modo === "paciente" ? (
            <div className="relative">
              <Search className="absolute left-2.5 top-2.5 w-3.5 h-3.5 text-[#7892b8]" />
              <input value={busq} onChange={(e) => { setBusq(e.target.value); setSel(null); }} placeholder="Nombre, apellidos, NumPac o teléfono…"
                className={`${MODAL_INPUT} pl-8`} />
              {!sel && res.length > 0 && (
                <div className="mt-1 max-h-52 overflow-y-auto border border-[#BFE4F7] rounded divide-y divide-[#F0F5FC]">
                  {res.map((p) => (
                    <button key={p.id} onClick={() => { setSel(p); setBusq(`${p.nombre} ${p.apellidos}`.trim()); }}
                      disabled={!p.telefono} title={p.telefono ? "" : "Sin teléfono"}
                      className="w-full text-left px-2.5 py-1.5 hover:bg-[#E6EDFF] disabled:opacity-50">
                      <div className="text-[12px] font-medium text-[#065AED]">{p.nombre} {p.apellidos} <span className="text-[10px] text-[#9bb0d0]">Hª {p.num_historia || "—"}</span></div>
                      <div className="text-[11px] text-[#7892b8]">{p.telefono || "sin teléfono"}</div>
                    </button>
                  ))}
                </div>
              )}
              {sel && <div className="mt-1 flex items-center gap-1.5 text-[12px] text-[#0F8C7D]"><CheckCircle2 className="w-4 h-4" /> {sel.nombre} {sel.apellidos} · {sel.telefono}</div>}
            </div>
          ) : (
            <input value={tel} onChange={(e) => setTel(e.target.value)} placeholder="Ej: 34600000000" className={MODAL_INPUT} />
          )}

          <textarea value={txt} onChange={(e) => setTxt(e.target.value)} rows={3} placeholder="Mensaje inicial…"
            className={`${MODAL_INPUT} resize-none`} />
        </div>
      </ModalBody>
    </Modal>
  );
}

export default function ComunicacionPage() {
  const [convs, setConvs] = useState<Conv[]>([]);
  const [convsLoaded, setConvsLoaded] = useState(false);
  const [activa, setActiva] = useState<Conv | null>(null);
  const [vista, setVista] = useState<"lista" | "chat" | "info">("lista");
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [ctx, setCtx] = useState<Ctx | null>(null);
  const [texto, setTexto] = useState("");
  const [q, setQ] = useState("");
  const [filtro, setFiltro] = useState<Filtro>("Todas");
  const [showTpl, setShowTpl] = useState(false);
  const [estado, setEstado] = useState<Estado | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [nuevaOpen, setNuevaOpen] = useState(false);
  const [prefillTel, setPrefillTel] = useState<string | null>(null);
  const [telParam, setTelParam] = useState<string | null>(null);
  const [importando, setImportando] = useState(false);
  const deepLinkRef = useRef(false);
  const [archivo, setArchivo] = useState<File | null>(null);
  const [modoNota, setModoNota] = useState(false);
  const [showEmoji, setShowEmoji] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const insertarEmoji = (emoji: string) => {
    const el = textareaRef.current;
    if (!el) { setTexto((t) => t + emoji); setShowEmoji(false); return; }
    const inicio = el.selectionStart ?? texto.length;
    const fin = el.selectionEnd ?? texto.length;
    const nuevo = texto.slice(0, inicio) + emoji + texto.slice(fin);
    setTexto(nuevo);
    setShowEmoji(false);
    requestAnimationFrame(() => { el.focus(); el.selectionStart = el.selectionEnd = inicio + emoji.length; });
  };
  const [buscarChat, setBuscarChat] = useState("");
  const [buscarChatOpen, setBuscarChatOpen] = useState(false);
  const [iaGlobal, setIaGlobal] = useState<{ pausada: boolean; hasta: string | null; iaActiva: boolean }>({ pausada: false, hasta: null, iaActiva: false });
  const [ahora, setAhora] = useState(0);
  const finRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const router = useRouter();
  const searchParams = useSearchParams();
  // Vista previa local del adjunto (solo imágenes); se revoca al cambiar/limpiar.
  const archivoPrev = useMemo(() => (archivo && archivo.type.startsWith("image/") ? URL.createObjectURL(archivo) : null), [archivo]);
  useEffect(() => () => { if (archivoPrev) URL.revokeObjectURL(archivoPrev); }, [archivoPrev]);
  // Igual, pero para reproducir la nota de voz grabada/adjuntada antes de enviarla.
  const archivoAudioPrev = useMemo(() => (archivo && archivo.type.startsWith("audio/") ? URL.createObjectURL(archivo) : null), [archivo]);
  useEffect(() => () => { if (archivoAudioPrev) URL.revokeObjectURL(archivoAudioPrev); }, [archivoAudioPrev]);

  // ── Grabar nota de voz (MediaRecorder) — al parar, queda como `archivo` normal:
  // se previsualiza/escucha y se envía por el MISMO flujo que un audio adjuntado. ──
  const [grabando, setGrabando] = useState(false);
  const [grabSegundos, setGrabSegundos] = useState(0);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const grabTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pararStream = () => { streamRef.current?.getTracks().forEach((t) => t.stop()); streamRef.current = null; };
  const iniciarGrabacion = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const mime = ["audio/webm", "audio/ogg"].find((m) => MediaRecorder.isTypeSupported(m)) || "";
      const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      const chunks: Blob[] = [];
      rec.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };
      rec.onstop = () => {
        const tipo = rec.mimeType || "audio/webm";
        const ext = tipo.includes("ogg") ? "ogg" : "webm";
        setArchivo(new File([new Blob(chunks, { type: tipo })], `nota-de-voz-${Date.now()}.${ext}`, { type: tipo }));
        pararStream();
      };
      rec.start();
      recorderRef.current = rec;
      setGrabando(true); setGrabSegundos(0);
      grabTimerRef.current = setInterval(() => setGrabSegundos((s) => s + 1), 1000);
    } catch {
      alert("No se pudo acceder al micrófono. Revisa los permisos del navegador para este sitio.");
    }
  };
  const detenerGrabacion = () => {
    recorderRef.current?.stop();
    recorderRef.current = null;
    if (grabTimerRef.current) { clearInterval(grabTimerRef.current); grabTimerRef.current = null; }
    setGrabando(false);
  };
  useEffect(() => () => { pararStream(); if (grabTimerRef.current) clearInterval(grabTimerRef.current); }, []);
  const fmtGrab = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

  // Deep-link desde la agenda: /comunicacion?tel=XXX abre (o inicia) la conversación de ese número.
  // useSearchParams (reactivo) y no window.location leído una vez: si /comunicacion ya estaba
  // montada en esta pestaña, un router.push con un ?tel= nuevo no remonta el componente y un
  // efecto de deps [] no volvería a leerlo (mismo fallo que el ?fecha=/&cita= de Agenda).
  useEffect(() => {
    const p = searchParams.get("tel");
    if (p) { deepLinkRef.current = false; setTelParam(p); }
  }, [searchParams]);
  useEffect(() => {
    if (!telParam || deepLinkRef.current || !convsLoaded) return;
    deepLinkRef.current = true;
    const n9 = telParam.replace(/\D/g, "").slice(-9);
    const c = convs.find((x) => x.telefono.replace(/\D/g, "").slice(-9) === n9);
    if (c) setActiva(c);
    else { setPrefillTel(telParam); setNuevaOpen(true); }   // sin conversación previa → iniciar una nueva
  }, [telParam, convsLoaded, convs]);

  // Tras enviar el 1er mensaje a un número, recargamos y abrimos esa conversación (match por últimos 9 dígitos).
  const onCreated = async (telDest: string) => {
    setNuevaOpen(false);
    try {
      const r = await api.get<{ data: Conv[] }>("/comunicacion/conversaciones");
      setConvs(r.data);
      const n9 = telDest.replace(/\D/g, "").slice(-9);
      const c = r.data.find((x) => x.telefono.replace(/\D/g, "").slice(-9) === n9);
      if (c) setActiva(c);
    } catch { /* noop */ }
  };

  const cargarConvs = useCallback(() => {
    const qs = filtro === "Archivadas" ? "?archivadas=true" : "";
    api.get<{ data: Conv[] }>(`/comunicacion/conversaciones${qs}`).then((r) => { setConvs(r.data); setConvsLoaded(true); }).catch(() => {});
  }, [filtro]);
  // Refrescar = repinta la vista AL INSTANTE con lo que ya hay en BD (no depende de Evolution)
  // + de paso trae el historial nuevo de WhatsApp (antes era un botón aparte "Importar
  // historial"). Si Evolution no responde, el refresco de la vista igualmente ha ocurrido —
  // solo el aviso de "mensajes nuevos" queda pendiente, en silencio.
  const refrescar = async () => {
    if (importando) return;
    setImportando(true);
    cargarConvs(); cargarEstado();
    try {
      const r = await api.post<{ conversaciones: number; mensajes_importados: number; chats_procesados: number }>(
        "/comunicacion/whatsapp/importar-historial", {});
      if (r.mensajes_importados > 0) {
        cargarConvs();
        alert(`Historial importado: ${r.conversaciones} conversaciones · ${r.mensajes_importados} mensajes nuevos (${r.chats_procesados} chats).`);
      }
    } catch { /* la vista ya se refrescó; traer historial nuevo es un extra, no crítico */ }
    finally { setImportando(false); }
  };
  const cargarEstado = useCallback(() => {
    api.get<Estado>("/comunicacion/whatsapp/estado").then(setEstado).catch(() => setEstado(null));
  }, []);
  const cargarIaGlobal = useCallback(() => {
    api.get<{ pausada: boolean; hasta: string | null; iaActiva: boolean }>("/comunicacion/ia/estado").then(setIaGlobal).catch(() => {});
  }, []);
  const setPacienteIa = async (acepta: boolean) => {
    if (!activa) return;
    try {
      await api.post(`/comunicacion/contexto/${encodeURIComponent(activa.telefono)}/ia`, { acepta });
      setCtx((c) => (c && c.paciente ? { ...c, paciente: { ...c.paciente, aceptaBots: acepta } } : c));
    } catch (e) { alert(errMsg(e)); }
  };
  const pausarIaGlobal = async () => {
    try { const r = await api.post<{ pausada: boolean; hasta: string | null }>("/comunicacion/ia/pausar", { minutos: 20 }); setIaGlobal((p) => ({ ...p, ...r })); }
    catch (e) { alert(errMsg(e)); }
  };
  const reanudarIaGlobal = async () => {
    try { const r = await api.post<{ pausada: boolean; hasta: string | null }>("/comunicacion/ia/reanudar", {}); setIaGlobal((p) => ({ ...p, ...r })); }
    catch (e) { alert(errMsg(e)); }
  };
  const reloadMsgs = useCallback((id: number) => {
    api.get<{ data: Msg[] }>(`/comunicacion/conversaciones/${id}/mensajes`).then((r) => setMsgs(r.data)).catch(() => {});
  }, []);

  // Ref a la conversación abierta: la lee el handler SSE sin re-suscribir el stream.
  const activaRef = useRef<Conv | null>(null);
  useEffect(() => { activaRef.current = activa; }, [activa]);
  useEffect(() => { if (activa) setVista("chat"); }, [activa]);

  // Borrador sin enviar por conversación — solo en memoria del componente, se pierde al
  // recargar la página (R4: nada persistente fuera de la BD). Antes `texto` era un único
  // estado global: al escribir a un paciente y cambiar a otro sin enviar, el texto se
  // quedaba puesto para CUALQUIER paciente. Cada conversación guarda el suyo y solo el
  // suyo; al volver a por ella se restaura, al resto no les afecta.
  const drafts = useRef<Record<number, string>>({});
  const textoRef = useRef(texto);
  useEffect(() => { textoRef.current = texto; }, [texto]);

  useEffect(() => { cargarConvs(); cargarEstado(); cargarIaGlobal(); }, [cargarConvs, cargarEstado, cargarIaGlobal]);
  // Reloj para la cuenta atrás de la pausa global (refresca cada 15 s; caduca sola).
  useEffect(() => { setAhora(Date.now()); const t = setInterval(() => setAhora(Date.now()), 15000); return () => clearInterval(t); }, []);

  // Tiempo real: SSE empuja los cambios al instante; un poll lento (30 s) reconcilia por si cae.
  useEffect(() => {
    const es = new EventSource(`${API_BASE}/comunicacion/stream`, { withCredentials: true });
    es.onmessage = (e) => {
      let ev: { convId?: number; tipo?: string } = {};
      try { ev = JSON.parse(e.data); } catch { /* heartbeat */ }
      // El stream trae tambien cita.*/estudio.*/etc: no son de la bandeja de WhatsApp.
      if (ev.tipo && ["cita.", "estudio.", "presupuesto.", "factura."].some((p) => ev.tipo!.startsWith(p))) return;
      const a = activaRef.current;
      if (a && (!ev.convId || ev.convId === a.id)) {
        reloadMsgs(a.id);
        if (ev.tipo === "mensaje") {
          // Mensaje nuevo en la conversación QUE YA TIENES ABIERTA: marcarla leída ahora mismo.
          // Sin esto, el contador de no-leídas sube sin parar mientras la estás mirando en
          // directo — solo se marcaba leída al ABRIRLA, no en cada mensaje que llega después.
          api.post(`/comunicacion/conversaciones/${a.id}/leida`, {}).then(cargarConvs).catch(cargarConvs);
          return;
        }
      }
      cargarConvs();
    };
    const reconc = setInterval(() => {
      const a = activaRef.current;
      if (a) {
        reloadMsgs(a.id);
        api.post(`/comunicacion/conversaciones/${a.id}/leida`, {}).then(cargarConvs).catch(cargarConvs);
        return;
      }
      cargarConvs();
    }, 30000);
    return () => { es.close(); clearInterval(reconc); };
  }, [cargarConvs, reloadMsgs]);

  useEffect(() => {
    if (!activa) return;
    setTexto(drafts.current[activa.id] ?? "");   // borrador de ESTE paciente, o vacío
    setBuscarChat(""); setBuscarChatOpen(false); setModoNota(false);   // no arrastrar búsqueda/modo-nota de la conv anterior
    reloadMsgs(activa.id);
    api.post(`/comunicacion/conversaciones/${activa.id}/leida`, {}).catch(() => {});
    api.get<Ctx>(`/comunicacion/contexto/${encodeURIComponent(activa.telefono)}`).then(setCtx).catch(() => setCtx(null));
    return () => { drafts.current[activa.id] = textoRef.current; };   // al salir, guarda lo sin enviar SOLO para él
  }, [activa, reloadMsgs]);

  useEffect(() => { finRef.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs]);

  const enviar = async () => {
    if (!activa || enviando || (!texto.trim() && !archivo)) return;
    if (modoNota) {
      if (!texto.trim()) return;
      setEnviando(true);
      const cuerpo = texto.trim(); const convId = activa.id;
      try {
        const m = await api.post<Msg>(`/comunicacion/conversaciones/${convId}/notas`, { texto: cuerpo });
        setTexto(""); delete drafts.current[convId];
        if (activaRef.current?.id === convId) setMsgs((prev) => [...prev, m]);
      } catch (e) { alert(errMsg(e)); }
      finally { setEnviando(false); }
      return;
    }
    setEnviando(true);
    const cuerpo = texto.trim(); const adj = archivo; const convId = activa.id;
    setTexto(""); setShowTpl(false); setArchivo(null); delete drafts.current[convId];
    // El mensaje se pinta YA, sin esperar a que WhatsApp confirme. Antes no aparecía nada
    // hasta que volvía la ida y vuelta completa (backend → Evolution → recarga del hilo
    // entero) y eran varios segundos mirando una pantalla que no reaccionaba. Id negativo
    // para distinguir el provisional del real y poder retirarlo si el envío falla.
    const idProvisional = -Date.now();
    if (!adj) {
      setMsgs((prev) => [...prev, {
        id: idProvisional, direccion: "saliente", cuerpo, estado: "enviando",
        generadoPorIa: false, enviadoAt: new Date().toISOString(),
      } as Msg]);
    }
    try {
      if (adj) {
        await api.upload(`/comunicacion/conversaciones/${convId}/media`, adj, cuerpo ? { caption: cuerpo } : undefined);
      } else {
        await api.post(`/comunicacion/conversaciones/${convId}/mensajes`, { texto: cuerpo });
      }
      // Reconciliación con el hilo real; si ya cambiaste de conversación, no se pisa.
      api.get<{ data: Msg[] }>(`/comunicacion/conversaciones/${convId}/mensajes`)
        .then((r) => { if (activaRef.current?.id === convId) setMsgs(r.data); })
        .catch(() => {});
    } catch (e) {
      setMsgs((prev) => prev.filter((m) => m.id !== idProvisional));   // no dejar un fantasma
      alert(errMsg(e)); setArchivo(adj);
      drafts.current[convId] = cuerpo;
      if (activaRef.current?.id === convId) setTexto(cuerpo);   // solo lo repone si sigues en esa conversación
    } finally { setEnviando(false); }
  };

  const cambiarEstadoConv = async (e: string) => {
    if (!activa) return;
    try {
      await api.patch(`/comunicacion/conversaciones/${activa.id}/estado`, { estado: e });
      setActiva({ ...activa, estado: e }); cargarConvs();
    } catch (err) { alert(errMsg(err)); }
  };

  // Pausar / reanudar la IA SOLO para la conversación activa (un humano toma el control).
  const toggleIa = async () => {
    if (!activa) return;
    try {
      if (activa.iaPausada) { await api.post(`/comunicacion/conversaciones/${activa.id}/ia/reanudar`, {}); setActiva({ ...activa, iaPausada: false }); }
      else { await api.post(`/comunicacion/conversaciones/${activa.id}/ia/pausar`, { minutos: 60 }); setActiva({ ...activa, iaPausada: true }); }
      cargarConvs();
    } catch (err) { alert(errMsg(err)); }
  };

  const togglePin = async (m: Msg) => {
    if (!activa) return;
    try {
      if (m.fijado) await api.post(`/comunicacion/conversaciones/${activa.id}/desfijar`, {});
      else await api.post(`/comunicacion/conversaciones/${activa.id}/mensajes/${m.id}/fijar`, {});
      api.get<{ data: Msg[] }>(`/comunicacion/conversaciones/${activa.id}/mensajes`).then((r) => setMsgs(r.data)).catch(() => {});
    } catch (e) { alert(errMsg(e)); }
  };

  // ── Menú ⋮ por conversación (lista): no leída / fijar / archivar ──
  const [menuAbierto, setMenuAbierto] = useState<number | null>(null);
  const marcarNoLeidaConv = async (c: Conv) => {
    setMenuAbierto(null);
    try { await api.post(`/comunicacion/conversaciones/${c.id}/no-leida`, {}); cargarConvs(); }
    catch (e) { alert(errMsg(e)); }
  };
  const toggleFijarConv = async (c: Conv) => {
    setMenuAbierto(null);
    try {
      if (c.fijada) await api.post(`/comunicacion/conversaciones/${c.id}/desfijar-conv`, {});
      else await api.post(`/comunicacion/conversaciones/${c.id}/fijar-conv`, {});
      if (activa?.id === c.id) setActiva({ ...activa, fijada: !c.fijada });
      cargarConvs();
    } catch (e) { alert(errMsg(e)); }
  };
  // En la pestaña "Archivadas" la acción es la inversa (desarchivar); en el resto, archivar.
  const enArchivadas = filtro === "Archivadas";
  const archivarConv = async (c: Conv) => {
    setMenuAbierto(null);
    if (!enArchivadas && !confirm(`¿Archivar la conversación con ${c.nombre}? Deja de verse en la bandeja (recuperable, no se borran los mensajes).`)) return;
    try {
      await api.post(`/comunicacion/conversaciones/${c.id}/${enArchivadas ? "desarchivar" : "archivar"}`, {});
      if (activa?.id === c.id) setActiva(null);
      cargarConvs();
    } catch (e) { alert(errMsg(e)); }
  };
  const toggleUrgenteConv = async (c: Conv) => {
    setMenuAbierto(null);
    try {
      await api.post(`/comunicacion/conversaciones/${c.id}/${c.urgente ? "no-urgente" : "urgente"}`, {});
      if (activa?.id === c.id) setActiva({ ...activa, urgente: !c.urgente });
      cargarConvs();
    } catch (e) { alert(errMsg(e)); }
  };

  // ── Selección múltiple + acciones en bloque (reutiliza los endpoints de uno-en-uno) ──
  const [seleccionActiva, setSeleccionActiva] = useState(false);
  const [seleccionados, setSeleccionados] = useState<Set<number>>(new Set());
  const toggleSeleccion = (id: number) => setSeleccionados((prev) => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });
  const salirSeleccion = () => { setSeleccionActiva(false); setSeleccionados(new Set()); };
  const bulkMarcarLeidas = async () => {
    const ids = [...seleccionados];
    await Promise.all(ids.map((id) => api.post(`/comunicacion/conversaciones/${id}/leida`, {}).catch(() => {})));
    salirSeleccion(); cargarConvs();
  };
  const bulkArchivar = async () => {
    const ids = [...seleccionados];
    if (!enArchivadas && !confirm(`¿${enArchivadas ? "Desarchivar" : "Archivar"} ${ids.length} conversación${ids.length === 1 ? "" : "es"}?`)) return;
    const accion = enArchivadas ? "desarchivar" : "archivar";
    await Promise.all(ids.map((id) => api.post(`/comunicacion/conversaciones/${id}/${accion}`, {}).catch(() => {})));
    if (activa && seleccionados.has(activa.id)) setActiva(null);
    salirSeleccion(); cargarConvs();
  };

  // Editar/borrar un mensaje NUESTRO — el backend solo lo permite mientras el paciente aún
  // no lo ha leído (Evolution deja "editar/borrar para ambos" de verdad en esa ventana).
  const [editando, setEditando] = useState<{ id: number; texto: string } | null>(null);
  const [editSaving, setEditSaving] = useState(false);
  const puedeEditar = (m: Msg) => m.direccion === "saliente" && !m.eliminado && m.estado !== "leido";
  const guardarEdicion = async () => {
    if (!activa || !editando || !editando.texto.trim()) return;
    setEditSaving(true);
    try {
      await api.patch(`/comunicacion/conversaciones/${activa.id}/mensajes/${editando.id}`, { texto: editando.texto.trim() });
      setEditando(null);
      api.get<{ data: Msg[] }>(`/comunicacion/conversaciones/${activa.id}/mensajes`).then((r) => setMsgs(r.data)).catch(() => {});
    } catch (e) { alert(errMsg(e)); } finally { setEditSaving(false); }
  };
  const borrarMsg = async (m: Msg) => {
    if (!activa || !confirm("¿Borrar este mensaje para ambos? No se puede deshacer.")) return;
    try {
      await api.del(`/comunicacion/conversaciones/${activa.id}/mensajes/${m.id}`);
      api.get<{ data: Msg[] }>(`/comunicacion/conversaciones/${activa.id}/mensajes`).then((r) => setMsgs(r.data)).catch(() => {});
    } catch (e) { alert(errMsg(e)); }
  };

  const filtradas = useMemo(() => {
    const s = q.trim().toLowerCase();
    let arr = convs;
    if (filtro === "No leídas") arr = arr.filter((c) => c.noLeidos > 0);
    else if (filtro === "Urgentes") arr = arr.filter(esUrgente);
    if (s) arr = arr.filter((c) => (c.nombre || "").toLowerCase().includes(s) || (c.telefono || "").includes(s) || (c.ultimoMensaje || "").toLowerCase().includes(s));
    return [...arr].sort((a, b) =>
      (b.fijada ? 1 : 0) - (a.fijada ? 1 : 0) ||
      (esUrgente(b) ? 1 : 0) - (esUrgente(a) ? 1 : 0) ||
      new Date(b.ultimoMensajeAt || 0).getTime() - new Date(a.ultimoMensajeAt || 0).getTime());
  }, [convs, q, filtro]);
  const urgentes = useMemo(() => convs.filter(esUrgente).length, [convs]);
  const totalNoLeidos = useMemo(() => convs.reduce((s, c) => s + (c.noLeidos || 0), 0), [convs]);
  const contadorFiltro = (f: Filtro): number | null =>
    f === "No leídas" ? totalNoLeidos : f === "Urgentes" ? urgentes : null;

  // Buscador dentro del hilo abierto: los mensajes ya están todos cargados en `msgs`
  // (listar_mensajes trae la conversación entera), así que es puro filtro de cliente.
  const msgsFiltrados = useMemo(() => {
    const q = buscarChat.trim().toLowerCase();
    return q ? msgs.filter((m) => (m.cuerpo || "").toLowerCase().includes(q)) : msgs;
  }, [msgs, buscarChat]);
  const grupos = useMemo(() => agruparPorFecha(msgsFiltrados), [msgsFiltrados]);
  const fijado = useMemo(() => msgs.find((m) => m.fijado) || null, [msgs]);
  // Pausa global temporal de la IA: minutos restantes y si sigue activa (caduca sola).
  const iaPausaMin = iaGlobal.pausada && iaGlobal.hasta ? Math.max(0, Math.ceil((new Date(iaGlobal.hasta).getTime() - ahora) / 60000)) : 0;
  const iaEnPausa = iaGlobal.pausada && iaPausaMin > 0;

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Barra superior: el título "WhatsApp" lo pinta la barra común del layout; aquí solo el contenido. */}
      <div className="flex flex-1 min-h-0">
        {/* ── Lista de conversaciones ── */}
        <aside className={`${vista === "lista" ? "flex" : "hidden"} lg:flex w-full lg:w-[340px] shrink-0 border-r border-[#e5e7eb] flex-col min-h-0 bg-white`}>
          <div className="p-2 border-b border-[#e5e7eb] space-y-2">
            {urgentes > 0 && (
              <div className="bg-[#FFFFFF] border border-[#E9A8F5] text-[#A21CAF] text-[11px] font-semibold px-2 py-1.5 rounded-sm flex items-center gap-1.5 animate-pulse">
                <AlertTriangle className="h-3.5 w-3.5 shrink-0" /> {urgentes} conversación{urgentes > 1 ? "es" : ""} urgente{urgentes > 1 ? "s" : ""}
              </div>
            )}
            <div className="flex items-center gap-2">
              <div className="flex-1 flex items-center gap-2 px-2 py-1.5 bg-white border border-[#e5e7eb] rounded-sm focus-within:border-[#1ca0d1]">
                <Search className="h-4 w-4 text-[#7f8c8d] shrink-0" />
                <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar conversación…" className="bg-transparent text-[16px] lg:text-[12px] text-[#333] outline-none w-full" />
                {q && (
                  <button onClick={() => setQ("")} title="Borrar búsqueda" className="shrink-0 text-[#7f8c8d] hover:text-[#C026D3]">
                    <X className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
              <button onClick={() => (seleccionActiva ? salirSeleccion() : setSeleccionActiva(true))} title={seleccionActiva ? "Salir de selección" : "Seleccionar varias"}
                className={`p-2 rounded-sm shrink-0 ${seleccionActiva ? "bg-[#1500A0] text-white" : "text-[#7f8c8d] hover:bg-[#E6EDFF] border border-[#e5e7eb]"}`}><CheckSquare className="h-4 w-4" /></button>
              <button onClick={() => setNuevaOpen(true)} title="Nueva conversación" className="p-2 rounded-sm text-white shrink-0 bg-[#2DD9C3] hover:bg-[#2DD9C3]/90"><Plus className="h-4 w-4" /></button>
            </div>
            {seleccionActiva ? (
              <div className="flex items-center gap-2 bg-[#FFFFFF] border border-[#e5e7eb] rounded-sm px-2 py-1.5">
                <span className="text-[11px] text-[#333] font-medium flex-1">{seleccionados.size} seleccionada{seleccionados.size === 1 ? "" : "s"}</span>
                <button onClick={bulkMarcarLeidas} disabled={!seleccionados.size} title="Marcar como leídas" className="p-1.5 rounded-sm text-[#1ca0d1] hover:bg-white disabled:opacity-30 disabled:cursor-not-allowed"><MailOpen className="h-4 w-4" /></button>
                <button onClick={bulkArchivar} disabled={!seleccionados.size} title={enArchivadas ? "Desarchivar" : "Archivar"} className="p-1.5 rounded-sm text-[#C026D3] hover:bg-white disabled:opacity-30 disabled:cursor-not-allowed">
                  {enArchivadas ? <ArchiveRestore className="h-4 w-4" /> : <Archive className="h-4 w-4" />}
                </button>
                <button onClick={salirSeleccion} title="Cancelar" className="p-1.5 rounded-sm text-[#7f8c8d] hover:bg-white"><X className="h-4 w-4" /></button>
              </div>
            ) : (
            <div className="flex gap-1 overflow-x-auto lg:flex-wrap [&>*]:shrink-0">
              {FILTROS.map((f) => {
                const n = contadorFiltro(f);
                return (
                  <button key={f} onClick={() => setFiltro(f)}
                    className={`flex items-center gap-1 text-[12px] lg:text-[11px] px-2.5 lg:px-2 py-1 lg:py-0.5 rounded-sm border ${filtro === f ? "bg-[#1500A0] text-white border-[#1500A0]" : "bg-white text-[#7f8c8d] border-[#e5e7eb] hover:border-[#1ca0d1]"}`}>
                    {f}
                    {!!n && (
                      <span className={`inline-flex items-center justify-center min-w-[16px] h-[16px] px-1 rounded-full text-[9px] font-bold leading-none ${
                        filtro === f ? "bg-white text-[#1500A0]" : f === "Urgentes" ? "bg-[#C026D3] text-white" : "bg-[#1ca0d1] text-white"
                      }`}>{n}</span>
                    )}
                  </button>
                );
              })}
            </div>
            )}
          </div>
          <div className="flex-1 overflow-y-auto relative">
            {menuAbierto !== null && <div className="fixed inset-0 z-10" onClick={() => setMenuAbierto(null)} />}
            {filtradas.length === 0 && <div className="p-4 text-center text-[12px] text-[#7892b8]">Sin conversaciones</div>}
            {filtradas.map((c, idx) => {
              const esMio = c.ultimaDireccion === "saliente";
              const clasePreview = esMio ? "text-[#7f8c8d]" : c.noLeidos > 0 ? "text-[#000] font-medium" : "text-[#111]";
              return (
              <div key={c.id} className="group relative">
                <button onClick={() => { if (seleccionActiva) toggleSeleccion(c.id); else { setActiva(c); setVista("chat"); } }}
                  className={`w-full text-left pl-3 pr-10 lg:pr-8 py-3 lg:py-2.5 border-b border-[#e5e7eb] transition-colors outline-none focus:outline-none focus-visible:ring-2 focus-visible:ring-[#1500A0] focus-visible:ring-inset ${esUrgente(c) ? "border-l-2 border-l-[#C026D3]" : ""} ${
                    activa?.id === c.id
                      ? (esUrgente(c) ? "bg-[#FFFFFF]" : idx % 2 === 1 ? "bg-[#FFFFFF]" : "bg-white")
                      : esUrgente(c) ? "bg-[#FFFFFF] hover:bg-[#E6EDFF]" : idx % 2 === 1 ? "bg-[#FFFFFF] hover:bg-[#E6EDFF]" : "bg-white hover:bg-[#E6EDFF]"
                  }`}>
                  <div className="flex gap-2.5 items-start">
                    {seleccionActiva && (
                      <span className={`mt-1.5 shrink-0 h-4 w-4 rounded-sm border flex items-center justify-center ${seleccionados.has(c.id) ? "bg-[#1500A0] border-[#1500A0]" : "border-[#cbd5e1] bg-white"}`}>
                        {seleccionados.has(c.id) && <Check className="h-3 w-3 text-white" />}
                      </span>
                    )}
                    <div className="relative shrink-0">
                      <div className={`${esUrgente(c) ? "bg-[#ff1493]" : "bg-[#1500A0]"} text-white text-[10px] font-semibold w-9 h-9 rounded-full flex items-center justify-center ${activa?.id === c.id ? "ring-2 ring-[#ff1493] ring-offset-1" : ""}`}>{iniciales(c.nombre)}</div>
                      <span className={`absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2 border-white ${ESTADO_DOT[c.estado] || "bg-[#cbd5e1]"}`} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-1">
                        <span className="flex items-center gap-1 min-w-0">
                          {c.fijada && <Pin className="h-3 w-3 text-[#1ca0d1] shrink-0" />}
                          <span className="text-[14px] lg:text-[12px] font-semibold text-[#1500A0] truncate">{c.nombre}</span>
                          {esUrgente(c) && <AlertTriangle className="h-3 w-3 text-[#A21CAF] shrink-0" />}
                        </span>
                        <span className="text-[10px] text-[#7f8c8d] shrink-0">{hora(c.ultimoMensajeAt)}</span>
                      </div>
                      <div className="flex items-center gap-1.5 mt-0.5">
                        <p className={`text-[13px] lg:text-[11px] truncate flex-1 min-w-0 ${clasePreview}`}>{c.ultimoMensaje || c.telefono}</p>
                        {c.noLeidos > 0 && <span className="shrink-0 text-[10px] font-semibold text-white bg-[#3388FF] rounded-sm px-1.5 leading-[16px]">{c.noLeidos}</span>}
                      </div>
                    </div>
                  </div>
                </button>
                {!seleccionActiva && (
                <>
                <button onClick={(e) => { e.stopPropagation(); setMenuAbierto(menuAbierto === c.id ? null : c.id); }}
                  title="Más acciones"
                  className={`absolute top-2 right-1 p-2 lg:p-1 rounded-sm text-[#7f8c8d] hover:bg-black/10 lg:opacity-0 lg:group-hover:opacity-100 focus:opacity-100 ${menuAbierto === c.id ? "opacity-100 bg-black/10" : ""}`}>
                  <MoreVertical className="h-3.5 w-3.5" />
                </button>
                {menuAbierto === c.id && (
                  <div className="absolute right-1.5 top-8 z-20 w-52 bg-white border border-[#e5e7eb] rounded-sm shadow-lg py-1 text-[13px] lg:text-[11px]">
                    <button onClick={() => marcarNoLeidaConv(c)} className="w-full text-left px-3 py-2.5 lg:py-1.5 hover:bg-[#E6EDFF] flex items-center gap-2 text-[#333]">
                      <MailOpen className="h-3.5 w-3.5" /> Marcar como no leída
                    </button>
                    <button onClick={() => toggleFijarConv(c)} className="w-full text-left px-3 py-2.5 lg:py-1.5 hover:bg-[#E6EDFF] flex items-center gap-2 text-[#333]">
                      <Pin className="h-3.5 w-3.5" /> {c.fijada ? "Desfijar" : "Fijar"}
                    </button>
                    <button onClick={() => toggleUrgenteConv(c)} className="w-full text-left px-3 py-2.5 lg:py-1.5 hover:bg-[#E6EDFF] flex items-center gap-2 text-[#A21CAF]">
                      <AlertTriangle className="h-3.5 w-3.5" /> {c.urgente ? "Quitar urgente" : "Marcar como urgente"}
                    </button>
                    <button onClick={() => archivarConv(c)} className="w-full text-left px-3 py-2.5 lg:py-1.5 hover:bg-[#E6EDFF] flex items-center gap-2 text-[#C026D3]">
                      {enArchivadas ? <ArchiveRestore className="h-3.5 w-3.5" /> : <Archive className="h-3.5 w-3.5" />} {enArchivadas ? "Desarchivar" : "Archivar"}
                    </button>
                  </div>
                )}
                </>
                )}
              </div>
              );
            })}
          </div>
        </aside>

        {/* ── Chat + panel de información: UNA sola cabecera que cubre ambos ── */}
        <div className={`${vista === "lista" ? "hidden" : "flex"} lg:flex flex-1 flex-col min-h-0 min-w-0`}>
          {activa && (
            <div className="px-3 lg:px-4 py-2 lg:py-2.5 bg-[#BBBCBC] border-b border-black/10 shrink-0 flex flex-wrap lg:flex-nowrap items-center justify-between gap-x-2 gap-y-1.5">
              <div className="flex items-center gap-3 min-w-0">
                <button onClick={() => setVista(vista === "info" ? "chat" : "lista")} className="lg:hidden p-2 -ml-2 text-[#1500A0] hover:bg-black/10 rounded-sm shrink-0">
                  <ChevronLeft className="h-5 w-5" />
                </button>
                <div className={`${esUrgente(activa) ? "bg-[#ff1493]" : "bg-[#1500A0]"} text-white text-[11px] font-semibold w-9 h-9 rounded-full flex items-center justify-center shrink-0`}>{iniciales(activa.nombre)}</div>
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="text-[12px] font-semibold text-[#1500A0] truncate">{activa.nombre}</span>
                    {esUrgente(activa) && <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-[#A21CAF] bg-[#FFFFFF] px-1.5 py-0.5 rounded-sm shrink-0"><AlertTriangle className="h-3 w-3" />URGENTE</span>}
                  </div>
                  <div className="text-[11px] text-black/50">{activa.telefono}</div>
                </div>
              </div>
              <div className="flex items-center gap-2 w-full lg:w-auto lg:shrink-0 overflow-x-auto lg:overflow-visible whitespace-nowrap [&>*]:shrink-0">
                <button onClick={() => setVista(vista === "info" ? "chat" : "info")} title={vista === "info" ? "Volver al chat" : "Ver info del paciente"} className="lg:hidden p-2 rounded-sm border border-[#1500A0]/40 bg-white text-[#1500A0] hover:bg-[#E6EDFF]">
                  <User className="h-4 w-4" />
                </button>
                <button onClick={() => setBuscarChatOpen((v) => !v)} title="Buscar en esta conversación"
                  className={`p-1.5 rounded-sm border border-[#1500A0]/40 ${buscarChatOpen ? "bg-[#1500A0] text-white" : "bg-white text-[#1500A0] hover:bg-[#E6EDFF]"}`}><Search className="h-3.5 w-3.5" /></button>
                <button onClick={toggleIa} disabled={!iaGlobal.iaActiva}
                  title={!iaGlobal.iaActiva ? "La IA está desactivada en Config › IA's" : activa.iaPausada ? "Reanudar IA" : "Pausar IA (1 h) — tomar el control"}
                  className={`flex items-center gap-1 text-[11px] px-2 py-1 rounded border ${!iaGlobal.iaActiva ? "text-black/30 bg-white/40 border-black/10 cursor-not-allowed" : activa.iaPausada ? "bg-[#1ca0d1]/15 text-[#1ca0d1] border-[#1500A0]/40" : "bg-white text-[#1500A0] border-[#1500A0]/40 hover:bg-[#E6EDFF]"}`}>
                  {activa.iaPausada ? <><Play className="h-3.5 w-3.5" /> Reanudar IA</> : <><Pause className="h-3.5 w-3.5" /> Pausar IA</>}
                </button>
                <select value={activa.estado} onChange={(e) => cambiarEstadoConv(e.target.value)} title="Estado de la conversación"
                  className="text-[11px] border border-[#1500A0]/40 rounded px-2 py-1 outline-none focus:border-[#1500A0] bg-white text-[#1500A0]">
                  <option value="abierta">Abierta</option>
                  <option value="pendiente">Pendiente</option>
                  <option value="resuelta">Resuelta</option>
                </select>
                {ctx?.encontrado && ctx.paciente && (
                  <>
                    <button onClick={() => router.push(`/pacientes/${ctx.paciente!.id}/ficha`)}
                      className="text-[11px] px-2 py-1 rounded border border-[#1500A0]/40 bg-white text-[#1500A0] hover:bg-[#E6EDFF] shrink-0 ml-1 pl-2 border-l border-black/20">Abrir ficha</button>
                    <button onClick={() => setPacienteIa(!ctx.paciente?.aceptaBots)}
                      title={ctx.paciente?.aceptaBots ? "El paciente acepta IA — clic para marcar que NO quiere" : "El paciente NO quiere IA — clic para permitirla"}
                      className={`flex items-center gap-1 text-[11px] px-2 py-1 rounded border shrink-0 ${ctx.paciente?.aceptaBots ? "bg-[#2DD9C3] text-white border-[#2DD9C3] hover:bg-[#2DD9C3]/90" : "bg-white text-[#1500A0] border-[#1500A0]/40 hover:bg-[#E6EDFF]"}`}>
                      <Bot className="h-3.5 w-3.5" /> IA: {ctx.paciente?.aceptaBots ? "Sí" : "No"}
                    </button>
                    <span className="text-[11px] text-black/50 pl-2 ml-1 border-l border-black/20 shrink-0">Hª {ctx.paciente.numHistoria || "—"}</span>
                  </>
                )}
              </div>
            </div>
          )}
          <div className="flex flex-1 min-h-0 min-w-0">
        <section className={`${vista === "chat" ? "flex" : "hidden"} lg:flex flex-1 min-w-0 flex-col min-h-0`} style={{ background: "#FFFFFF" }}>
          {!activa ? (
            <div className="flex-1 flex flex-col items-center justify-center text-[#9bb0d0]">
              <MessageCircle className="h-10 w-10 mb-2" />
              <span className="text-[13px]">Elige una conversación</span>
            </div>
          ) : (
            <>
              {activa.iaPausada && (
                <div className="px-4 py-1.5 bg-[#1ca0d1]/10 border-b border-[#1ca0d1]/20 text-[11px] text-[#0a3a5e] flex items-center gap-1.5 shrink-0">
                  <Pause className="h-3.5 w-3.5 text-[#1ca0d1]" /> IA pausada — las respuestas automáticas están desactivadas en esta conversación.
                </div>
              )}
              {buscarChatOpen && (
                <div className="px-4 py-1.5 bg-[#BBBCBC] border-b border-black/10 shrink-0 flex items-center gap-2">
                  <Search className="h-3.5 w-3.5 text-black/50 shrink-0" />
                  <input autoFocus value={buscarChat} onChange={(e) => setBuscarChat(e.target.value)}
                    placeholder="Buscar en esta conversación…"
                    className="flex-1 text-[16px] lg:text-[12px] outline-none bg-transparent text-[#333] placeholder:text-black/40" />
                  {buscarChat.trim() && <span className="text-[10px] text-black/50 shrink-0">{msgsFiltrados.length} resultado{msgsFiltrados.length === 1 ? "" : "s"}</span>}
                  <button onClick={() => { setBuscarChatOpen(false); setBuscarChat(""); }} title="Cerrar búsqueda" className="shrink-0 text-black/50 hover:text-[#C026D3]"><X className="h-3.5 w-3.5" /></button>
                </div>
              )}
              {fijado && (
                <div className="px-4 py-1.5 bg-[#FFFFFF] border-b border-[#C4B5FD] text-[11px] text-[#5B21B6] flex items-center gap-1.5 shrink-0">
                  <Pin className="h-3.5 w-3.5 shrink-0" /><span className="truncate flex-1">{fijado.cuerpo || "[multimedia]"}</span>
                  <button onClick={() => togglePin(fijado)} title="Desfijar" className="shrink-0 hover:text-[#C026D3]"><X className="h-3.5 w-3.5" /></button>
                </div>
              )}
              <div className="flex-1 overflow-y-auto overscroll-contain px-3 sm:px-4 py-3 space-y-1 bg-[#FFFFFF]">
                {grupos.map((g) => (
                  <div key={g.fecha}>
                    <div className="flex items-center gap-3 my-3">
                      <div className="flex-1 h-px bg-[#FFFFFF]" />
                      <span className="text-[10px] font-semibold text-[#7f8c8d] bg-[#FFFFFF] px-3 uppercase">{g.fecha}</span>
                      <div className="flex-1 h-px bg-[#FFFFFF]" />
                    </div>
                    {g.items.map((m) => {
                      if (m.direccion === "nota") {
                        return (
                          <div key={m.id} className="flex justify-center mb-2">
                            <div className="max-w-[85%] px-3 py-1.5 rounded-sm text-[11.5px] leading-relaxed bg-[#FFFFFF] border border-[#DDD6FE] text-[#5B21B6]">
                              <div className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide mb-0.5"><StickyNote className="h-3 w-3" /> Nota interna</div>
                              <div className="whitespace-pre-wrap break-words">{m.cuerpo}</div>
                              <div className="text-[9px] text-[#6D28D9] text-right mt-0.5">{hora(m.enviadoAt)}</div>
                            </div>
                          </div>
                        );
                      }
                      const bot = m.generadoPorIa;
                      const out = m.direccion === "saliente";
                      const enEdicion = editando?.id === m.id;
                      return (
                        <div key={m.id} className={`flex mb-2 ${out ? "justify-end" : "justify-start"}`}>
                          <div tabIndex={0} className={`group relative outline-none max-w-[88%] sm:max-w-[72%] px-3 py-1.5 rounded-lg text-[14px] sm:text-[12px] leading-relaxed shadow-sm bg-white text-[#333] border border-[#1500A0]/40 ${bot || !out ? "rounded-bl-none" : "rounded-br-none"}`}>
                            {bot && <div className="flex items-center gap-1 text-[10px] text-[#1ca0d1] font-semibold mb-0.5"><Bot className="h-3 w-3" /> Asistente IA</div>}
                            {m.eliminado ? (
                              <div className="italic text-[#7f8c8d] flex items-center gap-1"><Trash2 className="h-3 w-3" /> Mensaje eliminado</div>
                            ) : enEdicion ? (
                              <div className="flex flex-col gap-1 min-w-[220px]">
                                <textarea autoFocus value={editando.texto} onChange={(e) => setEditando({ id: m.id, texto: e.target.value })}
                                  rows={2} className="text-[12px] border border-[#1ca0d1] rounded-sm px-1.5 py-1 outline-none resize-none bg-white" />
                                <div className="flex items-center justify-end gap-1">
                                  <button onClick={() => setEditando(null)} title="Cancelar" className="p-1 rounded-sm text-[#7f8c8d] hover:bg-[#E6EDFF]"><X className="h-3.5 w-3.5" /></button>
                                  <button onClick={guardarEdicion} disabled={editSaving || !editando.texto.trim()} title="Guardar"
                                    className="p-1 rounded-sm text-white bg-[#1ca0d1] hover:brightness-110 disabled:opacity-50"><Check className="h-3.5 w-3.5" /></button>
                                </div>
                              </div>
                            ) : (
                              <>
                                <MediaView m={m} />
                                {/* Placeholder genérico ("[documento]"…) del backend cuando se adjunta SIN texto —
                                    ya se ve el adjunto arriba, así que sobra repetirlo como si fuera un mensaje real. */}
                                {m.cuerpo && !(m.mediaUrl && MEDIA_PLACEHOLDERS.has(m.cuerpo)) && <div className="whitespace-pre-wrap break-words">{m.cuerpo}</div>}
                              </>
                            )}
                            <div className="flex items-center justify-end gap-1 mt-0.5 text-[9px] text-[#7f8c8d]">
                              {m.fijado && <Pin className="h-2.5 w-2.5 text-[#1ca0d1]" />}
                              {m.editado && !m.eliminado && <span className="italic">editado</span>}
                              <span>{hora(m.enviadoAt)}</span>
                              {out && (m.estado === "leido" ? <CheckCheck className="h-3 w-3 text-[#3388FF]" /> : m.estado === "entregado" ? <CheckCheck className="h-3 w-3" /> : m.estado === "error" ? <span className="text-[#C026D3]">!</span> : <Check className="h-3 w-3" />)}
                            </div>
                            {!m.eliminado && !enEdicion && (
                              <div className="absolute -top-2 -right-2 flex items-center gap-0.5 opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 transition-opacity">
                                {puedeEditar(m) && (
                                  <>
                                    <button onClick={() => setEditando({ id: m.id, texto: m.cuerpo })} title="Editar (solo antes de leído)"
                                      className="bg-white border border-[#e5e7eb] rounded-sm p-1 shadow-sm text-[#7f8c8d] hover:text-[#1ca0d1]"><Pencil className="h-3 w-3" /></button>
                                    <button onClick={() => borrarMsg(m)} title="Borrar para ambos (solo antes de leído)"
                                      className="bg-white border border-[#e5e7eb] rounded-sm p-1 shadow-sm text-[#7f8c8d] hover:text-[#C026D3]"><Trash2 className="h-3 w-3" /></button>
                                  </>
                                )}
                                <button onClick={() => togglePin(m)} title={m.fijado ? "Desfijar" : "Fijar mensaje"}
                                  className="bg-white border border-[#e5e7eb] rounded-sm p-1 shadow-sm">
                                  <Pin className={`h-3 w-3 ${m.fijado ? "text-[#1ca0d1]" : "text-[#7f8c8d]"}`} />
                                </button>
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ))}
                <div ref={finRef} />
              </div>
              <div className="relative p-2 sm:p-3 pb-[max(0.5rem,env(safe-area-inset-bottom))] bg-white border-t border-[#e5e7eb] shrink-0 flex flex-col gap-2">
                {showTpl && (
                  <div className="absolute bottom-full left-3 mb-1 w-72 bg-white border border-[#e5e7eb] rounded-sm shadow-lg overflow-hidden z-10">
                    <div className="text-[10px] uppercase tracking-wide text-[#7f8c8d] px-3 py-1.5 border-b border-[#e5e7eb]">Plantillas rápidas</div>
                    {PLANTILLAS.map((t) => (
                      <button key={t.label} onClick={() => { setTexto((x) => (x ? x + " " : "") + t.texto); setShowTpl(false); }}
                        className="w-full text-left px-3 py-1.5 hover:bg-[#E6EDFF] border-b border-[#e5e7eb] last:border-0">
                        <div className="text-[12px] font-medium text-[#1500A0]">{t.label}</div>
                        <div className="text-[11px] text-[#7f8c8d] truncate">{t.texto}</div>
                      </button>
                    ))}
                  </div>
                )}
                {showEmoji && (
                  <>
                    <div className="fixed inset-0 z-[9]" onClick={() => setShowEmoji(false)} />
                    <div className="absolute bottom-full left-3 mb-1 w-64 bg-white border border-[#e5e7eb] rounded-sm shadow-lg p-2 z-10">
                      <div className="grid grid-cols-8 gap-1">
                        {EMOJIS.map((e) => (
                          <button key={e} onClick={() => insertarEmoji(e)} title={e}
                            className="text-[18px] leading-none p-1 rounded-sm hover:bg-[#E6EDFF]">{e}</button>
                        ))}
                      </div>
                    </div>
                  </>
                )}
                {archivo && (
                  <div className="flex items-center gap-2 bg-[#FFFFFF] border border-[#e5e7eb] rounded-sm px-2 py-1.5 text-[12px]">
                    {archivoPrev
                      ? <img src={archivoPrev} alt="" className="h-10 w-10 object-cover rounded-sm" />
                      : archivoAudioPrev
                        ? <audio controls src={archivoAudioPrev} className="h-8 flex-1 min-w-0" />
                        : <FileText className="h-5 w-5 text-[#1ca0d1] shrink-0" />}
                    {!archivoAudioPrev && <span className="truncate flex-1 text-[#333]">{archivo.name}</span>}
                    <span className="text-[11px] text-[#7f8c8d] shrink-0">{Math.max(1, Math.round(archivo.size / 1024))} KB</span>
                    <button onClick={() => setArchivo(null)} title="Quitar adjunto" className="shrink-0 text-[#7f8c8d] hover:text-[#C026D3]"><X className="h-4 w-4" /></button>
                  </div>
                )}
                <div className="flex flex-wrap sm:flex-nowrap items-end gap-1 sm:gap-2">
                  {grabando ? (
                    <div className="flex-1 flex items-center gap-2 px-3 py-2 bg-[#FFFFFF] border border-[#E9A8F5] rounded-sm">
                      <span className="h-2.5 w-2.5 rounded-full bg-[#C026D3] animate-pulse shrink-0" />
                      <span className="text-[12px] text-[#A21CAF] font-medium">Grabando… {fmtGrab(grabSegundos)}</span>
                      <div className="flex-1" />
                      <button onClick={detenerGrabacion} title="Parar y escuchar antes de enviar" className="p-1.5 rounded-sm bg-[#C026D3] text-white hover:brightness-110 shrink-0"><Square className="h-3.5 w-3.5" /></button>
                    </div>
                  ) : (
                    <>
                      <div className="flex items-center gap-1 sm:gap-2 w-full sm:w-auto shrink-0">
                      <button onClick={() => setShowTpl((v) => !v)} disabled={modoNota} title="Plantillas" className={`p-2.5 sm:p-2 rounded-sm shrink-0 disabled:opacity-30 disabled:cursor-not-allowed ${showTpl ? "bg-[#FFFFFF] text-[#1ca0d1]" : "text-[#7f8c8d] hover:bg-[#E6EDFF]"}`}><Zap className="h-4 w-4" /></button>
                      <input ref={fileRef} type="file" hidden accept="image/*,video/*,audio/*,application/pdf,.pdf,.doc,.docx,.xls,.xlsx"
                        onChange={(e) => { const f = e.target.files?.[0]; if (f) setArchivo(f); e.currentTarget.value = ""; }} />
                      <button onClick={() => fileRef.current?.click()} disabled={modoNota} title="Adjuntar archivo" className="p-2.5 sm:p-2 rounded-sm shrink-0 text-[#7f8c8d] hover:bg-[#E6EDFF] disabled:opacity-30 disabled:cursor-not-allowed"><Paperclip className="h-4 w-4" /></button>
                      <button onClick={iniciarGrabacion} disabled={!!archivo || modoNota} title="Grabar nota de voz" className="p-2.5 sm:p-2 rounded-sm shrink-0 text-[#7f8c8d] hover:bg-[#E6EDFF] disabled:opacity-30 disabled:cursor-not-allowed"><Mic className="h-4 w-4" /></button>
                      <button onClick={() => setModoNota((v) => !v)} title="Nota interna (no se envía al paciente)" className={`p-2.5 sm:p-2 rounded-sm shrink-0 ${modoNota ? "bg-[#FFFFFF] text-[#6D28D9]" : "text-[#7f8c8d] hover:bg-[#E6EDFF]"}`}><StickyNote className="h-4 w-4" /></button>
                      <button onClick={() => setShowEmoji((v) => !v)} disabled={modoNota} title="Insertar emoji" className={`p-2.5 sm:p-2 rounded-sm shrink-0 disabled:opacity-30 disabled:cursor-not-allowed ${showEmoji ? "bg-[#FFFFFF] text-[#1ca0d1]" : "text-[#7f8c8d] hover:bg-[#E6EDFF]"}`}><Smile className="h-4 w-4" /></button>
                      </div>
                      <textarea ref={textareaRef} value={texto} onChange={(e) => setTexto(e.target.value)}
                        onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); enviar(); } }}
                        rows={1} placeholder={modoNota ? "Nota interna — el paciente NO la ve…" : archivo ? "Añade un comentario (opcional)…" : "Escribe un mensaje…"}
                        className={`flex-1 min-w-0 resize-none text-[16px] sm:text-[12px] px-3 py-2 border rounded-sm outline-none focus:ring-1 max-h-28 ${modoNota ? "text-[#5B21B6] bg-[#FFFFFF] border-[#DDD6FE] focus:border-[#7C3AED] focus:ring-[#7C3AED]/20" : "text-[#333] bg-white border-[#e5e7eb] focus:border-[#1ca0d1] focus:ring-[#1ca0d1]/20"}`} />
                      <button onClick={enviar} disabled={enviando || (!texto.trim() && !archivo)}
                        className={`p-2.5 sm:p-2 rounded-sm shrink-0 transition-colors text-white ${(enviando || (!texto.trim() && !archivo)) ? "cursor-not-allowed opacity-50 " : ""}${modoNota ? "bg-[#7C3AED] hover:bg-[#7C3AED]/90" : "bg-[#2DD9C3] hover:bg-[#2DD9C3]/90"}`}><Send className="h-4 w-4" /></button>
                    </>
                  )}
                </div>
              </div>
            </>
          )}
        </section>

        {/* ── Contexto del paciente ── */}
        <aside className={`${vista === "info" ? "flex" : "hidden"} lg:flex w-full lg:w-[320px] shrink-0 border-l border-black/10 bg-[#D1D3D4] overflow-y-auto flex-col`}>
          {!activa ? null : !ctx?.encontrado ? (
            <div className="p-4 text-[12px] text-black/40">Sin ficha asociada a este número.</div>
          ) : (
            <div className="p-3 space-y-3">
              {ctx.ultimaCita && (
                <button onClick={() => router.push(`/agenda?fecha=${ctx.ultimaCita!.fecha}&cita=${ctx.ultimaCita!.id}`)}
                  className="w-full text-left rounded-lg border border-[#1500A0]/40 bg-white p-2 hover:bg-[#E6EDFF]">
                  <div className="flex items-center gap-1 text-[11px] text-[#065AED] font-medium"><Calendar className="h-3.5 w-3.5" /> Última cita</div>
                  <div className="text-[12px] text-[#333] mt-1">{ctx.ultimaCita.fecha} {ctx.ultimaCita.hora || ""}</div>
                  {ctx.ultimaCita.tratamiento && <div className="text-[11px] text-black/50 mt-0.5 truncate">{ctx.ultimaCita.tratamiento}</div>}
                </button>
              )}
              {ctx.proximaCita && (
                <button onClick={() => router.push(`/agenda?fecha=${ctx.proximaCita!.fecha}&cita=${ctx.proximaCita!.id}`)}
                  className="w-full text-left rounded-lg border border-[#1500A0]/40 bg-white p-2 hover:bg-[#E6EDFF]">
                  <div className="flex items-center gap-1 text-[11px] text-[#065AED] font-medium"><Calendar className="h-3.5 w-3.5" /> Próxima cita</div>
                  <div className="text-[12px] text-[#333] mt-1">{ctx.proximaCita.fecha} {ctx.proximaCita.hora || ""}
                    {ctx.proximaCita.confirmada ? <span className="ml-1 text-[#20BEAB]">✓ confirmada</span> : <span className="ml-1 text-[#7C3AED]">sin confirmar</span>}</div>
                  {ctx.proximaCita.tratamiento && <div className="text-[11px] text-black/50 mt-0.5 truncate">{ctx.proximaCita.tratamiento}</div>}
                </button>
              )}
              {!!ctx.tratamientosRealizados?.length && (
                <div>
                  <div className="text-[11px] text-[#065AED] font-medium mb-1">Últimas entradas médicas</div>
                  <div className="border border-[#1500A0]/40 bg-white rounded-lg overflow-hidden">
                    {ctx.tratamientosRealizados.map((t) => (
                      <button key={t.id} onClick={() => router.push(`/pacientes/${ctx.paciente!.id}/ficha`)}
                        className="w-full text-left px-2 py-1.5 border-b border-black/10 last:border-0 hover:bg-[#E6EDFF]">
                        <div className="text-[10px] text-black/50">{t.fecha || "—"}</div>
                        <div className="text-[11.5px] text-[#333] truncate">{t.tratamiento || "—"}{t.piezas ? <span className="text-black/50"> · pieza {t.piezas}</span> : ""}</div>
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {!!ctx.pagos?.length && (
                <div>
                  <div className="text-[11px] text-[#065AED] font-medium mb-1">Últimos movimientos económicos</div>
                  <div className="border border-[#1500A0]/40 bg-white rounded-lg overflow-hidden">
                    {ctx.pagos.map((p) => (
                      <button key={p.id} onClick={() => router.push(`/pacientes/${ctx.paciente!.id}/plan-econ`)}
                        className="w-full text-left px-2 py-1.5 border-b border-black/10 last:border-0 hover:bg-[#E6EDFF] flex items-center justify-between gap-2">
                        <div className="min-w-0">
                          <div className="text-[10px] text-black/50">{p.fecha}</div>
                          <div className="text-[11px] text-[#333] truncate">{p.formaPago || "—"}</div>
                        </div>
                        <div className="text-[12px] font-semibold text-[#065AED] shrink-0">{p.importe.toFixed(2)} €</div>
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {!!ctx.alertas?.length && (
                <div>
                  <div className="text-[11px] text-[#065AED] font-medium mb-1">Alertas</div>
                  {ctx.alertas.map((a, i) => (
                    <div key={i} className="flex items-start gap-1 text-[12px] text-[#5B21B6] bg-[#FFFFFF] rounded px-2 py-1 mb-1">
                      <AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0" />{a.texto}</div>
                  ))}
                </div>
              )}
            </div>
          )}
        </aside>
          </div>
        </div>
      </div>

      {nuevaOpen && <NuevaConvModal onClose={() => { setNuevaOpen(false); setPrefillTel(null); }} onCreated={onCreated} initialTel={prefillTel} />}
    </div>
  );
}
