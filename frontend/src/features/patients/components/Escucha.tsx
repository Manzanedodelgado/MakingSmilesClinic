"use client";
/**
 * Escucha — ÚNICO componente del flujo de escucha activa: el doctor dicta/escribe la visita, la IA la
 * estructura y saca los 4 BORRADORES (Diagnóstico+Plan → Observaciones · presupuesto · medicación ·
 * mensaje de WhatsApp). La IA propone, el doctor valida y dispara cada uno. Nada se guarda solo.
 *
 * Dos presentaciones de lo MISMO:
 *  - variant="modal"  → ventana emergente (botón "Escucha").
 *  - variant="inline" → dentro del cockpit de la agenda (zona Evolución).
 *
 * Coherencia: el número de raíces de la endodoncia lo fija el backend por la posición FDI (determinista).
 */
import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, X, Check, Mic, Square, Sparkles, Stethoscope, Calculator, Pill, MessageCircle, Send, Trash2 } from "lucide-react";
import { api } from "@/shared/lib/api";
import { Modal, ModalBody, ModalButton } from "@/shared/components";
import { patientService, type EscuchaExtraido } from "../services/patientService";
import { errMsg } from "@/shared/lib/errores";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Any = any;
const eur = (n: number) => new Intl.NumberFormat("es-ES", { style: "currency", currency: "EUR" }).format(n || 0);


export interface EscuchaProps {
  patientId: number;
  telefono?: string | null;
  variant?: "modal" | "inline";
  /** Doctor de la cita. Si se pasa, se habilita la caja "Realizado en esta cita" (registra tratamientos
   *  hechos hoy en tratamientos_realizados con este doctor). Sin él, esa caja no aparece. */
  doctorId?: number | null;
  /** Si se pasa, el mensaje de WhatsApp se delega al padre (p.ej. el borrador del cockpit) y no se pinta aquí. */
  onMensaje?: (texto: string) => void;
  /** Aviso al padre tras guardar algo (para refrescar listas: actos, recetas…). */
  onGuardado?: () => void;
  /** Callback cuando se extraen tratamientos del LLM (para pasar al presupuesto) */
  onTratamientosExtractos?: (tratamientos: Array<{ texto: string; pieza?: string; tratamiento_id?: number | null; precio?: number }>) => void;
  onClose?: () => void;
}

export function Escucha({
  patientId,
  telefono,
  variant = "modal",
  doctorId,
  onMensaje,
  onGuardado,
  onTratamientosExtractos,
  onClose
}: EscuchaProps) {
  const router = useRouter();
  const [texto, setTexto] = useState("");
  const [grabando, setGrabando] = useState<null | "diag" | "realizado">(null);
  const [cargando, setCargando] = useState(false);
  const [res, setRes] = useState<EscuchaExtraido | null>(null);
  const [notaActoId, setNotaActoId] = useState<number | null>(null);
  const [guardando, setGuardando] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ k: string; ok: boolean; txt: string } | null>(null);
  // Caja "Realizado en esta cita": lo dictado se interpreta como tratamientos ya hechos → realizados.
  const [realizadoTexto, setRealizadoTexto] = useState("");
  const [realizados, setRealizados] = useState<EscuchaExtraido["presupuesto"]>([]);
  const [extrayendo, setExtrayendo] = useState(false);
  const recRef = useRef<Any>(null);
  const baseRef = useRef("");

  // ── Captura por voz (Web Speech API, es-ES) → escribe en la caja indicada ("diag" o "realizado") ──
  const dictar = (target: "diag" | "realizado") => {
    if (grabando) { recRef.current?.stop(); return; }
    const SR = (window as Any).SpeechRecognition || (window as Any).webkitSpeechRecognition;
    if (!SR) {
      setMsg({ k: target === "diag" ? "cap" : "realizado", ok: false, txt: "Este navegador no soporta dictado (usa Chrome/Edge) — o escribe abajo" });
      return;
    }
    const setter = target === "diag" ? setTexto : setRealizadoTexto;
    const actual = target === "diag" ? texto : realizadoTexto;
    const rec = new SR();
    rec.lang = "es-ES";
    rec.continuous = true;
    rec.interimResults = true;
    baseRef.current = actual ? actual.trim() + " " : "";

    rec.onstart = () => {
      setMsg({ k: target === "diag" ? "cap" : "realizado", ok: true, txt: "🎙️ Escuchando..." });
    };

    rec.onresult = (e: Any) => {
      let fin = "", interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript;
        if (e.results[i].isFinal) fin += t; else interim += t;
      }
      if (fin) {
        baseRef.current += fin + " ";
      }
      setter(baseRef.current + interim);
    };

    rec.onend = () => {
      setGrabando(null);
      setMsg({ k: target === "diag" ? "cap" : "realizado", ok: true, txt: "✅ Dictado completado" });
    };

    rec.onerror = (e: Any) => {
      console.error("❌ Error de dictado:", e.error);
      setGrabando(null);
      setMsg({ k: target === "diag" ? "cap" : "realizado", ok: false, txt: `Error: ${e.error}` });
    };

    recRef.current = rec;
    try {
      rec.start();
      setGrabando(target);
    } catch (err) {
      console.error("❌ Error al iniciar SpeechRecognition:", err);
      setMsg({ k: target === "diag" ? "cap" : "realizado", ok: false, txt: `Error al iniciar: ${err}` });
    }
  };

  // ── "Realizado en esta cita": misma extracción de líneas (con precio de tarifa) que el presupuesto,
  //    pero para registrarlas como REALIZADAS (tratamientos_realizados), no como propuesta. ──
  const extraerRealizados = async () => {
    if (!realizadoTexto.trim() || extrayendo) return;
    if (grabando) recRef.current?.stop();
    setExtrayendo(true); setMsg(null);
    try {
      const r = await patientService.consultaEscucha(patientId, realizadoTexto.trim());
      setRealizados(r.presupuesto || []);
      if (!(r.presupuesto || []).length) setMsg({ k: "realizado", ok: false, txt: "No se detectó ningún tratamiento" });
    } catch (e) { setMsg({ k: "realizado", ok: false, txt: errMsg(e) }); }
    finally { setExtrayendo(false); }
  };
  const updReal = (i: number, patch: Partial<EscuchaExtraido["presupuesto"][number]>) =>
    setRealizados((p) => p.map((l, j) => (j === i ? { ...l, ...patch } : l)));
  const delReal = (i: number) => setRealizados((p) => p.filter((_, j) => j !== i));

  const registrarRealizados = async () => {
    const lineas = realizados.filter((l) => l.tratamiento_id).map((l) => ({
      tratamiento_id: l.tratamiento_id as number, pieza: l.pieza, precio: l.precio, cantidad: l.cantidad || 1 }));
    if (!lineas.length) { setMsg({ k: "realizado", ok: false, txt: "Ninguna línea casó con el catálogo" }); return; }
    if (doctorId == null) { setMsg({ k: "realizado", ok: false, txt: "Falta el doctor de la cita" }); return; }
    setGuardando("realizado");
    try {
      // Ciclo real: presupuesto Entregado → Aceptado → Previsto → Realizado (con doctor e importe).
      const r = await patientService.realizarEnCita(patientId, lineas, doctorId);
      // Conciliación en pantalla: lo hecho sale del presupuesto PROPUESTO (mismo tratamiento+pieza).
      const clave = (tid: number | null, pz: string | null) => `${tid}|${(pz || "").replace(/\D/g, "")}`;
      const hechos = new Set(lineas.map((l) => clave(l.tratamiento_id, l.pieza)));
      setRes((prev) => (prev ? { ...prev, presupuesto: prev.presupuesto.filter((l) => !hechos.has(clave(l.tratamiento_id, l.pieza))) } : prev));
      setMsg({ k: "realizado", ok: true, txt: `${r.realizados} realizado(s) ✓ · presupuesto nº ${r.num} entregado→aceptado→realizado${r.anuladas_previas ? ` · cancelado en previos (${r.anuladas_previas})` : ""}` });
      setRealizados([]); setRealizadoTexto("");
      onGuardado?.();
    } catch (e) { setMsg({ k: "realizado", ok: false, txt: errMsg(e) }); }
    finally { setGuardando(null); }
  };

  // ── La IA estructura la visita en los 4 borradores ──
  const estructurar = async () => {
    if (!texto.trim() || cargando) return;
    if (grabando) recRef.current?.stop();
    setCargando(true); setMsg(null);
    try {
      const r = await patientService.consultaEscucha(patientId, texto.trim());
      setRes(r);
      // Pasar tratamientos extraídos al padre (para presupuesto modal)
      if (onTratamientosExtractos && r.presupuesto?.length > 0) {
        onTratamientosExtractos(r.presupuesto.map((l) => ({
          texto: l.tratamiento,
          pieza: l.pieza || undefined,
          tratamiento_id: l.tratamiento_id,
          precio: l.precio
        })));
      }
      if (r.mensaje?.trim() && onMensaje) onMensaje(r.mensaje.trim());   // delega el mensaje al padre (borrador del cockpit)
    } catch (e) { setMsg({ k: "cap", ok: false, txt: errMsg(e) }); }
    finally { setCargando(false); }
  };

  const setSoap = (k: keyof EscuchaExtraido["soap"], v: string) => setRes((r) => (r ? { ...r, soap: { ...r.soap, [k]: v } } : r));
  const updPresu = (i: number, patch: Partial<EscuchaExtraido["presupuesto"][number]>) =>
    setRes((r) => (r ? { ...r, presupuesto: r.presupuesto.map((l, j) => (j === i ? { ...l, ...patch } : l)) } : r));
  const delPresu = (i: number) => setRes((r) => (r ? { ...r, presupuesto: r.presupuesto.filter((_, j) => j !== i) } : r));
  const updRec = (i: number, patch: Partial<EscuchaExtraido["receta"][number]>) =>
    setRes((r) => (r ? { ...r, receta: r.receta.map((m, j) => (j === i ? { ...m, ...patch } : m)) } : r));
  const delRec = (i: number) => setRes((r) => (r ? { ...r, receta: r.receta.filter((_, j) => j !== i) } : r));
  const addRec = () => setRes((r) => (r ? { ...r, receta: [...r.receta, { medicamento: "", posologia: "", pauta: "", duracion: "", envases: undefined, unidades: undefined }] } : r));

  // ── Disparar cada borrador (aquí SÍ se guarda/envía, cuando el doctor lo confirma) ──
  const marcar = (k: string, ok: boolean, txt: string) => setMsg({ k, ok, txt });

  const guardarFicha = async () => {   // Diagnóstico + Plan → SOAP y Observaciones del acto (substituye lo que hubiera)
    if (!res) return;
    setGuardando("soap");
    const obs = [res.soap.analisis.trim() && `Diagnóstico: ${res.soap.analisis.trim()}`,
                 res.soap.plan.trim() && `Tratamiento: ${res.soap.plan.trim()}`].filter(Boolean).join("\n");
    let soapOk = false;
    try { await patientService.guardarSoap(patientId, res.soap); soapOk = true; } catch { /* SOAP requiere cita de hoy */ }
    try {
      if (obs) {
        if (notaActoId) await patientService.editarActo(patientId, notaActoId, { notas: obs });
        else { const r = await patientService.crearActo(patientId, { fecha: new Date().toISOString().slice(0, 10), notas: obs }); setNotaActoId(r.id); }
        onGuardado?.();
      }
      marcar("soap", true, obs ? (soapOk ? "Guardado ✓ · Diagnóstico y Plan en Observaciones del acto" : "Observaciones guardadas ✓ (SOAP requiere cita de hoy)") : "SOAP guardado ✓");
    } catch (e) { const m = e instanceof Error ? e.message : ""; marcar("soap", false, m.includes("doctor") ? "Falta el doctor para crear el acto" : "Error al guardar"); }
    finally { setGuardando(null); }
  };

  const crearPresupuesto = async () => {
    if (!res) return;
    const lineas = res.presupuesto.filter((l) => l.tratamiento_id).map((l) => ({
      tratamiento_id: l.tratamiento_id as number, pieza: l.pieza, precio: l.precio, cantidad: l.cantidad || 1 }));
    if (!lineas.length) { marcar("presu", false, "Ninguna línea casó con el catálogo"); return; }
    setGuardando("presu");
    try {
      const r = await patientService.crearPresupuesto(patientId, { titulo: "Presupuesto (Escucha)", lineas });
      marcar("presu", true, `Presupuesto nº ${r.num} creado ✓${r.anuladas_previas ? ` · cancelado en presupuestos anteriores lo repetido (${r.anuladas_previas})` : ""} — abriendo…`);
      router.push(`/pacientes/${patientId}/presupuestos?pre=${r.id}`);
    } catch (e) { marcar("presu", false, errMsg(e)); } finally { setGuardando(null); }
  };

  const generarReceta = async () => {
    if (!res) return;
    const meds = res.receta.filter((m) => m.medicamento.trim()).map((m) => ({ medicamento: m.medicamento.trim(), posologia: m.posologia?.trim(), pauta: m.pauta?.trim(), duracion: m.duracion?.trim(), envases: m.envases, unidades: m.unidades }));
    if (!meds.length) { marcar("receta", false, "Sin medicación"); return; }
    setGuardando("receta");
    try { await patientService.guardarReceta(patientId, meds, { diagnostico: res.soap.analisis }); marcar("receta", true, "Receta generada ✓"); onGuardado?.(); }
    catch (e) { marcar("receta", false, errMsg(e)); } finally { setGuardando(null); }
  };

  const enviarMensaje = async () => {
    if (!res) return;
    const tel = res.telefono || telefono;
    if (!tel) { marcar("mensaje", false, "El paciente no tiene teléfono"); return; }
    if (!res.mensaje.trim()) { marcar("mensaje", false, "Mensaje vacío"); return; }
    setGuardando("mensaje");
    try { await api.post("/comunicacion/whatsapp/enviar", { telefono: tel, texto: res.mensaje }); marcar("mensaje", true, "Enviado por WhatsApp ✓"); }
    catch (e) { marcar("mensaje", false, errMsg(e)); } finally { setGuardando(null); }
  };

  const M = (k: string) => (msg?.k === k ? <span className={`text-[11px] font-semibold ${msg.ok ? "text-[#0F8C7D]" : "text-[#C026D3]"}`}>{msg.txt}</span> : null);
  const inline = variant === "inline";

  const cuerpo = (
    <div className={inline ? "flex flex-col gap-2.5" : "p-4 space-y-3 bg-[#FFFFFF] overflow-y-auto flex-1"}>
      {/* Captura 1 — VALORACIÓN Y DIAGNÓSTICO (protocolo actual: SOAP + presupuesto propuesto + receta + mensaje) */}
      <div className={inline ? "" : "bg-white border border-[#e5e7eb] rounded-sm p-3"}>
        <div className="flex items-center gap-1.5 mb-1.5"><Stethoscope className="w-3.5 h-3.5 text-[#1ca0d1]" /><span className="text-[11px] font-semibold uppercase tracking-wide text-[#1500A0]">Valoración y diagnóstico</span></div>
        <div className="flex items-center gap-2 mb-2">
          <button onClick={() => dictar("diag")} className={`flex items-center gap-1.5 text-[12px] font-semibold px-3 py-1.5 rounded-sm ${grabando === "diag" ? "bg-[#C026D3] text-white animate-pulse" : "bg-[#2DD9C3] text-[#1500A0] hover:brightness-110"}`}>
            {grabando === "diag" ? <><Square className="w-3.5 h-3.5" /> Parar</> : <><Mic className="w-3.5 h-3.5" /> Dictar</>}
          </button>
          <span className="text-[11px] text-[#7f8c8d]">{grabando === "diag" ? "Escuchando…" : "Pulsa y habla, o escribe la visita."}</span>
          <button onClick={estructurar} disabled={cargando || !texto.trim()}
            className={`ml-auto flex items-center gap-1.5 text-[12px] font-semibold px-3 py-1.5 rounded-sm ${cargando || !texto.trim() ? "bg-[#FFFFFF] text-[#7f8c8d] cursor-not-allowed" : "bg-[#1500A0] text-white hover:brightness-110"}`}>
            {cargando ? <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Estructurando…</> : <><Sparkles className="w-3.5 h-3.5" /> Estructurar con IA</>}
          </button>
        </div>
        <textarea value={texto} onChange={(e) => setTexto(e.target.value)} rows={3}
          placeholder="Escribe o dicta la valoración de la visita… (la IA lo estructura en diagnóstico, plan, presupuesto propuesto, receta y mensaje)"
          className="w-full border border-[#e5e7eb] rounded-sm text-[12px] text-[#333] px-3 py-2 bg-white focus:border-[#1ca0d1] outline-none resize-none" />
        {M("cap")}
      </div>

      {/* Captura 2 — REALIZADO EN ESTA CITA (solo con doctor de cita): lo dictado = tratamientos hechos hoy → realizados con importe */}
      {doctorId != null && (
        <div className={inline ? "" : "bg-white border border-[#e5e7eb] rounded-sm p-3"}>
          <div className="flex items-center gap-1.5 mb-1.5"><Check className="w-3.5 h-3.5 text-[#2DD9C3]" /><span className="text-[11px] font-semibold uppercase tracking-wide text-[#1500A0]">Realizado en esta cita</span></div>
          <div className="flex items-center gap-2 mb-2">
            <button onClick={() => dictar("realizado")} className={`flex items-center gap-1.5 text-[12px] font-semibold px-3 py-1.5 rounded-sm ${grabando === "realizado" ? "bg-[#C026D3] text-white animate-pulse" : "bg-[#2DD9C3] text-[#1500A0] hover:brightness-110"}`}>
              {grabando === "realizado" ? <><Square className="w-3.5 h-3.5" /> Parar</> : <><Mic className="w-3.5 h-3.5" /> Dictar</>}
            </button>
            <span className="text-[11px] text-[#7f8c8d]">{grabando === "realizado" ? "Escuchando…" : "Lo que has hecho hoy → se registra como realizado."}</span>
            <button onClick={extraerRealizados} disabled={extrayendo || !realizadoTexto.trim()}
              className={`ml-auto flex items-center gap-1.5 text-[12px] font-semibold px-3 py-1.5 rounded-sm ${extrayendo || !realizadoTexto.trim() ? "bg-[#FFFFFF] text-[#7f8c8d] cursor-not-allowed" : "bg-[#1500A0] text-white hover:brightness-110"}`}>
              {extrayendo ? <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Extrayendo…</> : <><Sparkles className="w-3.5 h-3.5" /> Extraer tratamientos</>}
            </button>
          </div>
          <textarea value={realizadoTexto} onChange={(e) => setRealizadoTexto(e.target.value)} rows={2}
            placeholder="Escribe o dicta lo realizado hoy (p.ej. 'reconstrucción del 15, endodoncia del 46')…"
            className="w-full border border-[#e5e7eb] rounded-sm text-[12px] text-[#333] px-3 py-2 bg-white focus:border-[#1ca0d1] outline-none resize-none" />
          {realizados.length > 0 && (
            <>
              <div className="border border-[#e5e7eb] rounded-sm divide-y divide-[#f0f2f5] mt-2">
                {realizados.map((l, i) => (
                  <div key={i} className="flex items-center gap-1.5 px-2 py-1 text-[11px]">
                    <span className={`flex-1 min-w-0 truncate ${l.tratamiento_id ? "text-[#1500A0] font-medium" : "text-[#6D28D9]"}`} title={l.tratamiento}>{l.tratamiento}{!l.tratamiento_id && " (no encontrado)"}</span>
                    <input value={l.pieza ?? ""} onChange={(e) => updReal(i, { pieza: e.target.value || null })} placeholder="pza" className="w-10 border border-[#e5e7eb] rounded-sm px-1 py-0.5 text-[10px] text-center outline-none focus:border-[#1ca0d1]" />
                    <input type="number" min={0} step="0.01" value={l.precio} onChange={(e) => updReal(i, { precio: Number(e.target.value) || 0 })} className="w-16 border border-[#e5e7eb] rounded-sm px-1 py-0.5 text-[10px] text-right outline-none focus:border-[#1ca0d1]" title="Importe (€)" />
                    <button onClick={() => delReal(i)} title="Quitar" className="text-[#C026D3] hover:bg-[#E6EDFF] rounded-sm p-0.5 shrink-0"><Trash2 className="w-3 h-3" /></button>
                  </div>
                ))}
              </div>
              <div className="flex items-center gap-2 mt-2 pt-2 border-t border-[#f0f2f5]">
                <button onClick={registrarRealizados} disabled={guardando === "realizado"} className="flex items-center gap-1.5 text-[11px] font-semibold px-2.5 py-1 rounded-sm bg-[#1500A0] text-white hover:brightness-110 disabled:opacity-50">
                  {guardando === "realizado" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />} Registrar realizados
                </button>
                <span className="text-[10px] text-[#7f8c8d]">Total {eur(realizados.reduce((s, l) => s + (l.precio || 0) * (l.cantidad || 1), 0))}</span>
              </div>
            </>
          )}
          {M("realizado")}
        </div>
      )}

      {res && (
        <>
          {/* Diagnóstico + Plan (resumen) → Observaciones del acto */}
          <Bloque icon={Stethoscope} titulo="Evolución (Diagnóstico y Plan)">
            {([["analisis", "Diagnóstico"], ["plan", "Plan / Tratamiento"]] as const).map(([k, lbl]) => (
              <div key={k} className="mb-1.5">
                <label className="text-[10px] font-semibold text-[#7f8c8d] uppercase">{lbl}</label>
                <textarea value={res.soap[k]} onChange={(e) => setSoap(k, e.target.value)} rows={2}
                  className="w-full border border-[#e5e7eb] rounded-sm text-[12px] text-[#333] px-2 py-1 bg-white focus:border-[#1ca0d1] outline-none resize-none" />
              </div>
            ))}
            <p className="text-[10px] text-[#9aa7c2]">Diagnóstico y Plan se vuelcan a las Observaciones del acto al guardar.</p>
            <Accion label="Guardar en la ficha" icon={Stethoscope} onClick={guardarFicha} loading={guardando === "soap"} msg={M("soap")} />
          </Bloque>

          {/* Presupuesto propuesto (editable) */}
          <Bloque icon={Calculator} titulo={`Presupuesto propuesto (${res.presupuesto.length})`}
            extra={<span className="text-[11px] font-semibold text-[#1500A0]">{eur(res.presupuesto.reduce((s, l) => s + (l.precio || 0) * (l.cantidad || 1), 0))}</span>}>
            {res.presupuesto.length === 0 ? <p className="text-[11px] text-slate-400 italic">Sin tratamientos detectados.</p> : (
              <div className="border border-[#e5e7eb] rounded-sm divide-y divide-[#f0f2f5]">
                {res.presupuesto.map((l, i) => (
                  <div key={i} className="flex items-center gap-1.5 px-2 py-1 text-[11px]">
                    <span className={`flex-1 min-w-0 truncate ${l.tratamiento_id ? "text-[#1500A0] font-medium" : "text-[#6D28D9]"}`} title={l.tratamiento}>{l.tratamiento}{!l.tratamiento_id && " (no encontrado)"}</span>
                    <input value={l.pieza ?? ""} onChange={(e) => updPresu(i, { pieza: e.target.value || null })} placeholder="pza" className="w-10 border border-[#e5e7eb] rounded-sm px-1 py-0.5 text-[10px] text-center outline-none focus:border-[#1ca0d1]" />
                    <input type="number" min={1} value={l.cantidad || 1} onChange={(e) => updPresu(i, { cantidad: Math.max(1, Number(e.target.value) || 1) })} className="w-10 border border-[#e5e7eb] rounded-sm px-1 py-0.5 text-[10px] text-center outline-none focus:border-[#1ca0d1]" title="Cantidad" />
                    <input type="number" min={0} step="0.01" value={l.precio} onChange={(e) => updPresu(i, { precio: Number(e.target.value) || 0 })} className="w-16 border border-[#e5e7eb] rounded-sm px-1 py-0.5 text-[10px] text-right outline-none focus:border-[#1ca0d1]" title="Precio unitario (€)" />
                    <button onClick={() => delPresu(i)} title="Quitar" className="text-[#C026D3] hover:bg-[#E6EDFF] rounded-sm p-0.5 shrink-0"><Trash2 className="w-3 h-3" /></button>
                  </div>
                ))}
              </div>
            )}
            <Accion label="Crear presupuesto" icon={Calculator} onClick={crearPresupuesto} loading={guardando === "presu"} msg={M("presu")} />
          </Bloque>

          {/* Medicación posible (editable) — pendiente de validar y generar */}
          <Bloque icon={Pill} titulo={`Medicación posible (${res.receta.length}) · pendiente de validar`}
            extra={<button onClick={addRec} className="text-[10px] font-semibold text-[#1500A0] hover:underline">+ Añadir</button>}>
            {res.receta.length === 0 ? <p className="text-[11px] text-slate-400 italic">Sin medicación propuesta. Añade una si procede.</p> : (
              <div className="border border-[#e5e7eb] rounded-sm divide-y divide-[#f0f2f5]">
                {res.receta.map((m, i) => (
                  <div key={i} className="flex items-center gap-1.5 px-2 py-1">
                    <input value={m.medicamento} onChange={(e) => updRec(i, { medicamento: e.target.value })} placeholder="Medicamento (p.ej. Ibuprofeno 600 mg)" className="flex-1 min-w-0 border border-[#e5e7eb] rounded-sm px-1.5 py-0.5 text-[11px] text-[#1500A0] font-medium outline-none focus:border-[#1ca0d1]" />
                    <input value={m.posologia} onChange={(e) => updRec(i, { posologia: e.target.value })} placeholder="Posología (1 comp./8 h, 3 días)" className="flex-1 min-w-0 border border-[#e5e7eb] rounded-sm px-1.5 py-0.5 text-[11px] text-[#7f8c8d] outline-none focus:border-[#1ca0d1]" />
                    <button onClick={() => delRec(i)} title="Quitar" className="text-[#C026D3] hover:bg-[#E6EDFF] rounded-sm p-0.5 shrink-0"><Trash2 className="w-3 h-3" /></button>
                  </div>
                ))}
              </div>
            )}
            <Accion label="Validar y generar receta" icon={Pill} onClick={generarReceta} loading={guardando === "receta"} msg={M("receta")} disabled={!res.receta.some((m) => m.medicamento.trim())} />
          </Bloque>

          {/* Mensaje al paciente — solo si NO se delega al padre (cockpit lo lleva a su borrador) */}
          {!onMensaje && (
            <Bloque icon={MessageCircle} titulo="Mensaje al paciente (WhatsApp)">
              <textarea value={res.mensaje} onChange={(e) => setRes((r) => (r ? { ...r, mensaje: e.target.value } : r))} rows={3}
                className="w-full border border-[#e5e7eb] rounded-sm text-[12px] text-[#333] px-2 py-1.5 bg-white focus:border-[#1ca0d1] outline-none resize-none" />
              <Accion label="Enviar por WhatsApp" icon={Send} onClick={enviarMensaje} loading={guardando === "mensaje"} msg={M("mensaje")} />
            </Bloque>
          )}
          {onMensaje && res.mensaje.trim() && <p className="text-[10px] text-[#0F8C7D] flex items-center gap-1"><MessageCircle className="w-3 h-3" /> Mensaje para el paciente listo en el borrador de WhatsApp.</p>}
        </>
      )}
    </div>
  );

  if (inline) return cuerpo;

  return (
    <Modal
      title={<span className="flex items-center gap-2"><Sparkles className="w-4 h-4" /> Dictado de la visita</span>}
      subtitle="la IA propone, el doctor valida"
      onClose={() => onClose?.()}
      size="lg"
      closeOnBackdrop={false}
      footer={
        <ModalButton variant="magenta" icon={X} onClick={() => onClose?.()}>Cerrar</ModalButton>
      }
    >
      <ModalBody className="!p-0 bg-[#FFFFFF]">
        {cuerpo}
      </ModalBody>
    </Modal>
  );
}

function Accion({ label, icon: Icon, onClick, loading, msg, disabled }: {
  label: string; icon: React.ElementType; onClick: () => void; loading: boolean; msg?: React.ReactNode; disabled?: boolean;
}) {
  return (
    <div className="flex items-center gap-2 mt-2 pt-2 border-t border-[#f0f2f5]">
      <button onClick={onClick} disabled={loading || disabled}
        className="flex items-center gap-1.5 text-[11px] font-semibold px-2.5 py-1 rounded-sm bg-[#1500A0] text-white hover:brightness-110 disabled:opacity-50 disabled:cursor-not-allowed">
        {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Icon className="w-3.5 h-3.5" />} {label}
      </button>
      {msg}
    </div>
  );
}

function Bloque({ icon: Icon, titulo, extra, children }: { icon: React.ElementType; titulo: string; extra?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="bg-white border border-[#e5e7eb] rounded-sm">
      <div className="flex items-center gap-1.5 px-3 py-1.5 border-b border-[#e5e7eb]">
        <Icon className="w-3.5 h-3.5 text-[#1ca0d1]" />
        <span className="text-[11px] font-semibold uppercase tracking-wide text-[#1500A0]">{titulo}</span>
        {extra && <span className="ml-auto">{extra}</span>}
      </div>
      <div className="p-3">{children}</div>
    </div>
  );
}
