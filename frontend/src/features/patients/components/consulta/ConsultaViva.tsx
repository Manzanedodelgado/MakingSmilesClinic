"use client";
/**
 * LA CONSULTA VIVA — un puesto de consulta NUEVO (no copia la .37).
 * No hay formulario SOAP que rellenar: hay un MAPA DE INCÓGNITAS que se cierran.
 *   · izquierda  → flujo vivo: lo que se dice/observa entra como evidencia
 *   · centro     → la boca (odontograma real); el diente del que se habla manda
 *   · derecha    → incógnitas: preguntas clínicas con su confianza, que se cierran
 * El SOAP/plan son el SUBPRODUCTO de cerrar incógnitas, no el punto de partida.
 * Fase 1 (esto): todo sobre datos REALES del paciente, sin IA. ESCUCHA/copiloto vienen después.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { X, Loader2, Mic, Send, Stethoscope, ClipboardCheck, Lightbulb } from "lucide-react";
import { patientService } from "../../services/patientService";
import { Modal, ModalBody, ModalFooter, ModalButton, MODAL_INPUT } from "@/shared/components";
import type { PacienteCabecera, AlertasData, Presupuestos, OdontogramaData } from "../../types/patient";
import OdontogramaOverlay from "../odontograma/OdontogramaOverlay";
import { construirOdontogramaClinico } from "../odontograma/odontogramaData";
import { IncognitasPanel } from "./IncognitasPanel";
import { derivarIncognitas, nuevaIncognita, type Incognita } from "./incognitas";
import { analizar, type Decision } from "./cerebro";

const CONF_MAX = 95;
const clamp = (n: number) => Math.max(0, Math.min(100, n));

export function ConsultaViva({ patientId }: { patientId: number }) {
  const [cab, setCab] = useState<PacienteCabecera | null>(null);
  const [odo, setOdo] = useState<OdontogramaData | null>(null);
  const [incognitas, setIncognitas] = useState<Incognita[]>([]);
  const [activaId, setActivaId] = useState<string | null>(null);
  const [piezaActiva, setPiezaActiva] = useState<string | null>(null);
  const [flujo, setFlujo] = useState<{ texto: string; pieza: string | null; explica: string }[]>([]);
  const [texto, setTexto] = useState("");
  const [cerrar, setCerrar] = useState(false);
  const [registrando, setRegistrando] = useState(false);
  const [registrado, setRegistrado] = useState<number | null>(null);  // n actos registrados, -1 = error
  const [tratamientosNuevos, setTratamientosNuevos] = useState<Array<{texto: string; pieza: string | null}>>([]);
  const [nuevoTtoTexto, setNuevoTtoTexto] = useState("");
  const [nuevoTtoPieza, setNuevoTtoPieza] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let alive = true;
    Promise.allSettled([
      patientService.cabecera(patientId),
      patientService.alertas(patientId),
      patientService.presupuestos(patientId),
      patientService.odontograma(patientId),
    ]).then(([c, a, p, o]) => {
      if (!alive) return;
      const cab = c.status === "fulfilled" ? c.value : null;
      const alertas = a.status === "fulfilled" ? (a.value as AlertasData) : null;
      const presupuestos = p.status === "fulfilled" ? (p.value as Presupuestos) : null;
      const odontograma = o.status === "fulfilled" ? (o.value as OdontogramaData) : null;
      setCab(cab); setOdo(odontograma);
      setIncognitas(derivarIncognitas({ alertas, presupuestos, odontograma }));
    });
    return () => { alive = false; };
  }, [patientId]);

  const piezas = useMemo(
    () => construirOdontogramaClinico(odo?.teeth ?? [], odo?.realizados ?? [], { soloInicial: true }),
    [odo],
  );

  // ── mutaciones de incógnitas ──
  const patch = (id: string, fn: (i: Incognita) => Incognita) =>
    setIncognitas((xs) => xs.map((i) => (i.id === id ? fn(i) : i)));

  const subir = (id: string) => patch(id, (i) => ({ ...i, confianza: clamp(i.confianza + 15) }));
  const proponer = (id: string) => patch(id, (i) => ({
    ...i, confianza: clamp(Math.max(i.confianza, 80)),
    propuesta: i.propuesta ?? { texto: i.pregunta.replace(/^¿|\?$/g, ""), precio: null },
  }));
  const resolver = (id: string) => { patch(id, (i) => ({ ...i, estado: "resuelta" })); if (activaId === id) setActivaId(null); };
  const descartar = (id: string) => { patch(id, (i) => ({ ...i, estado: "descartada" })); if (activaId === id) setActivaId(null); };

  // ── flujo vivo: una evidencia entra y mueve la incógnita activa (o crea una nueva) ──
  const [pensando, setPensando] = useState(false);
  const [escuchando, setEscuchando] = useState(false);
  const recRef = useRef<any>(null);

  // Núcleo: una frase (tecleada o dictada) → el cerebro la enruta al mapa de incógnitas.
  const procesar = useCallback(async (raw: string) => {
    const t = raw.trim();
    if (!t || pensando) return;
    const abiertas = incognitas.filter((i) => i.estado === "abierta").map((i) => ({
      id: i.id, pregunta: i.pregunta, pieza: i.pieza, confianza: i.confianza, propuesta: i.propuesta?.texto ?? null,
    }));
    setPensando(true);
    let d: Decision;
    try {
      d = (await patientService.consultaAnalizar(patientId, { evidencia: t, incognitas: abiertas })) as unknown as Decision;
    } catch {
      d = analizar(t, incognitas, piezaActiva);   // respaldo heurístico si el LLM no responde
    } finally {
      setPensando(false);
    }
    setFlujo((f) => [...f, { texto: t, pieza: d.pieza ?? piezaActiva, explica: d.explica }]);
    if (d.pieza) setPiezaActiva(d.pieza);              // enfoca la boca en la pieza detectada
    const ni = d.nueva?.pregunta ? nuevaIncognita({ ...d.nueva, evidencias: [t] }) : null;
    setIncognitas((xs) => {
      let next = xs;
      if (d.targetId) {
        next = next.map((i) => i.id === d.targetId
          ? { ...i, evidencias: [...i.evidencias, t], confianza: Math.min(CONF_MAX, i.confianza + (d.deltaConf || 0)), propuesta: d.propuesta ?? i.propuesta }
          : i);
      }
      if (ni) next = [...next, ni];
      return next;
    });
    setActivaId(ni ? ni.id : d.targetId);              // selecciona la incógnita movida
  }, [piezaActiva, incognitas, patientId, pensando]);

  const meterEvidencia = useCallback(() => {
    const t = texto; setTexto(""); procesar(t); inputRef.current?.focus();
  }, [texto, procesar]);

  // ESCUCHA por voz — Web Speech API del navegador (es-ES). Real en Chrome, sin clave ni backend.
  // Soporte detectado tras montar (evita mismatch de hidratación servidor/cliente).
  const [soportaVoz, setSoportaVoz] = useState(false);
  const toggleEscucha = useCallback(() => {
    if (escuchando) { try { recRef.current?.stop(); } catch { /* */ } return; }
    const SR = (window as any).webkitSpeechRecognition || (window as any).SpeechRecognition;
    if (!SR) return;
    const rec = new SR();
    rec.lang = "es-ES"; rec.continuous = true; rec.interimResults = false;
    rec.onresult = (e: any) => {
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) procesar(e.results[i][0].transcript);
      }
    };
    rec.onend = () => setEscuchando(false);
    rec.onerror = () => setEscuchando(false);
    recRef.current = rec; rec.start(); setEscuchando(true);
  }, [escuchando, procesar]);
  useEffect(() => {
    setSoportaVoz(!!((window as any).webkitSpeechRecognition || (window as any).SpeechRecognition));
    return () => { try { recRef.current?.stop(); } catch { /* */ } };
  }, []);

  const onPiezaClick = (pieza: string) => {
    setPiezaActiva((p) => (p === pieza ? null : pieza));
    const hit = incognitas.find((i) => i.pieza === pieza && i.estado === "abierta");
    if (hit) setActivaId(hit.id);
  };

  const abiertas = incognitas.filter((i) => i.estado === "abierta").length;
  const resueltas = incognitas.filter((i) => i.estado === "resuelta");
  const planPropuesto = resueltas.filter((i) => i.propuesta);

  // Aprobar y registrar: crea los actos de los tratamientos resueltos (subproducto de la consulta).
  async function aprobarYregistrar() {
    setRegistrando(true); setRegistrado(null);
    try {
      const nota = resueltas.flatMap((i) => i.evidencias).join(" · ") || null;
      const tratamientos = [
        ...planPropuesto.map((i) => ({ texto: i.propuesta!.texto, pieza: i.pieza, precio: i.propuesta!.precio })),
        ...tratamientosNuevos.map((t) => ({ texto: t.texto, pieza: t.pieza, precio: null })),
      ];
      const r = await patientService.consultaCerrar(patientId, { nota, tratamientos });
      setRegistrado(r.n);
    } catch {
      setRegistrado(-1);
    } finally {
      setRegistrando(false);
    }
  }

  const agregarTratamientoNuevo = () => {
    if (!nuevoTtoTexto.trim()) return;
    setTratamientosNuevos((t) => [...t, { texto: nuevoTtoTexto.trim(), pieza: nuevoTtoPieza }]);
    setNuevoTtoTexto("");
    setNuevoTtoPieza(null);
  };

  const eliminarTratamientoNuevo = (idx: number) => {
    setTratamientosNuevos((t) => t.filter((_, i) => i !== idx));
  };

  return (
    <div className="flex flex-col h-full bg-[#FFFFFF]">
      {/* Cabecera del área (formato PageHeader del .37: barra 34.2px + 2 líneas) */}
      <div className="flex items-center gap-3 h-[42px] px-4 bg-[#000080] text-white shrink-0">
        <Stethoscope className="w-4 h-4 text-[#2DD9C3] shrink-0" />
        <span className="text-[20px] font-bold tracking-tight whitespace-nowrap">Consulta</span>
        {cab && (
          <span className="text-[12px] text-white/90 whitespace-nowrap">
            · {cab.apellidos}, {cab.nombre}{cab.edad != null ? ` · ${cab.edad}a` : ""}
          </span>
        )}
        {cab?.alertas_lista?.slice(0, 3).map((a, k) => (
          <span key={k} className="text-[10px] font-semibold bg-[#C026D3]/25 border border-[#C026D3]/50 rounded-sm px-1.5 py-0.5">⚠ {a}</span>
        ))}
        <span className="ml-auto text-[11px] text-white/80 whitespace-nowrap">{abiertas} preguntas pendientes</span>
      </div>
      <div aria-hidden className="h-[10px] -mb-[10px] bg-[#000080] shrink-0" />

      {/* 3 columnas */}
      <div className="flex-1 min-h-0 grid grid-cols-[1fr_1.3fr_1.2fr] gap-3 p-3">
        {/* IZQUIERDA — flujo vivo */}
        <div className="flex flex-col min-h-0 bg-white border border-[#e5e7eb] rounded-sm">
          <div className="flex items-center gap-1.5 px-2.5 py-2 border-b border-[#e5e7eb]">
            <Mic className="w-3.5 h-3.5 text-[#1ca0d1]" />
            <span className="text-[10px] font-semibold uppercase tracking-wide text-[#1ca0d1]">Notas de la visita</span>
            <button onClick={toggleEscucha} disabled={!soportaVoz}
              title={soportaVoz ? (escuchando ? "Parar el dictado" : "Dictar por voz") : "Tu navegador no soporta dictado por voz"}
              className={`ml-auto flex items-center gap-1 px-2 py-0.5 rounded-sm text-[10px] font-semibold uppercase disabled:opacity-40 disabled:cursor-not-allowed ${escuchando ? "bg-[#C026D3] text-white animate-pulse" : "bg-[#2DD9C3] text-[#1500A0] hover:brightness-105"}`}>
              <Mic className="w-3 h-3" /> {escuchando ? "Dictando…" : "Dictar"}
            </button>
          </div>
          <div className="flex-1 min-h-0 overflow-y-auto p-2 flex flex-col gap-1.5">
            {flujo.length === 0 ? (
              <p className="text-[11px] text-slate-400 italic">
                Escribe lo que dice u observas (síntoma, hallazgo, medicación…). Entra como <b>dato</b> de la pregunta activa{piezaActiva ? <> (pieza <b>{piezaActiva}</b>)</> : null}.
              </p>
            ) : flujo.map((e, k) => (
              <div key={k} className="text-[11px] text-[#374151] border-l-2 border-[#2DD9C3] pl-2">
                {e.pieza && <span className="text-[9px] font-mono text-[#1500A0] bg-[#FFFFFF] px-1 rounded-sm mr-1">{e.pieza}</span>}
                {e.texto}
                {e.explica && <span className="ml-1 text-[9px] text-[#1ca0d1] italic">· {e.explica}</span>}
              </div>
            ))}
          </div>
          <div className="p-2 border-t border-[#e5e7eb] flex items-center gap-1.5">
            <input ref={inputRef} value={texto} onChange={(e) => setTexto(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") meterEvidencia(); }}
              placeholder="Lo que dice / observas…"
              className="flex-1 border border-[#e5e7eb] rounded-sm text-[12px] px-2 py-1 outline-none focus:border-[#1ca0d1]" />
            <button onClick={meterEvidencia} disabled={!texto.trim() || pensando} title="La IA asigna el dato a su pregunta"
              className="flex items-center justify-center w-7 h-7 rounded-sm bg-[#1500A0] text-white hover:bg-[#0d0080] disabled:opacity-40">
              {pensando ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
            </button>
          </div>
        </div>

        {/* CENTRO — la boca */}
        <div className="flex flex-col min-h-0 bg-white border border-[#e5e7eb] rounded-sm">
          <div className="flex items-center gap-1.5 px-2.5 py-2 border-b border-[#e5e7eb]">
            <span className="text-[10px] font-semibold uppercase tracking-wide text-[#1ca0d1]">Odontograma</span>
            {piezaActiva && (
              <span className="ml-auto flex items-center gap-1 text-[10px] font-mono text-[#1500A0] bg-[#FFFFFF] px-1.5 py-0.5 rounded-sm">
                {piezaActiva} <button onClick={() => setPiezaActiva(null)}><X className="w-3 h-3" /></button>
              </span>
            )}
          </div>
          <div className="flex-1 min-h-0 overflow-auto grid place-items-center p-2">
            <OdontogramaOverlay modo="view" piezasMarcadas={piezas} edad={cab?.edad ?? null}
              piezaActiva={piezaActiva} onPiezaClick={onPiezaClick}
              imgClassName="max-h-[420px] w-auto block select-none" />
          </div>
          <p className="text-[10px] text-slate-400 italic px-2.5 py-1.5 border-t border-[#e5e7eb]">
            Toca un diente para ver sus preguntas y asociarle el dato.
          </p>
        </div>

        {/* DERECHA — incógnitas */}
        <div className="flex flex-col min-h-0 bg-white border border-[#e5e7eb] rounded-sm">
          <div className="flex items-center gap-1.5 px-2.5 py-2 border-b border-[#e5e7eb]">
            <span className="text-[10px] font-semibold uppercase tracking-wide text-[#1ca0d1]">Preguntas de la visita</span>
          </div>
          <div className="flex-1 min-h-0 p-2">
            <IncognitasPanel incognitas={incognitas} activaId={activaId}
              onSelect={(id) => setActivaId((p) => (p === id ? null : id))}
              onSubir={subir} onProponer={proponer} onResolver={resolver} onDescartar={descartar} />
          </div>
        </div>
      </div>

      {/* Footer — cerrar visita */}
      <div className="flex items-center gap-3 px-4 py-2 bg-white border-t border-[#e5e7eb] shrink-0">
        <span className="text-[11px] text-slate-500">
          {resueltas.length} respondidas · {planPropuesto.length} tratamientos propuestos
        </span>
        <button onClick={() => setCerrar(true)} disabled={resueltas.length === 0}
          className="ml-auto flex items-center gap-1.5 px-4 py-1.5 rounded-sm text-[12px] font-semibold uppercase tracking-wide bg-[#2DD9C3] text-[#1500A0] hover:brightness-105 disabled:opacity-40 disabled:cursor-not-allowed">
          <ClipboardCheck className="w-4 h-4" /> Cerrar visita y registrar
        </button>
      </div>

      {/* Resumen del cierre (lo que se registraría) */}
      {cerrar && (
        <Modal
          title="Cierre de la visita"
          size="md"
          onClose={() => setCerrar(false)}
        >
          <ModalBody>
            <div className="flex flex-col gap-3">
              <div className="flex items-center gap-2 bg-[#FFFFFF] border border-[#BFE4F7] rounded-sm px-3 py-2 text-[11px] text-[#073D8D] font-semibold">
                🔒 La IA propone; el doctor revisa y aprueba antes de registrar.
              </div>
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-wide text-[#1ca0d1] mb-1">Nota clínica (de los datos recogidos)</p>
                {resueltas.flatMap((i) => i.evidencias).length === 0
                  ? <p className="text-[11px] text-slate-400 italic">Sin datos recogidos.</p>
                  : <ul className="text-[12px] text-[#374151] flex flex-col gap-0.5">
                      {resueltas.flatMap((i) => i.evidencias).map((e, k) => <li key={k} className="border-l-2 border-[#2DD9C3] pl-2">{e}</li>)}
                    </ul>}
              </div>
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-wide text-[#1ca0d1] mb-1">Plan propuesto por la IA</p>
                {planPropuesto.length === 0
                  ? <p className="text-[11px] text-slate-400 italic">Sin tratamientos propuestos.</p>
                  : planPropuesto.map((i) => (
                      <div key={i.id} className="flex items-center gap-1.5 text-[12px] text-[#1500A0] font-semibold py-0.5">
                        <Lightbulb className="w-3.5 h-3.5" /> {i.propuesta!.texto}
                        {i.pieza && <span className="text-[10px] font-mono bg-[#FFFFFF] px-1 rounded-sm">{i.pieza}</span>}
                      </div>
                    ))}
              </div>

              <div className="border-t border-[#BFE4F7] pt-3">
                <p className="text-[10px] font-semibold uppercase tracking-wide text-[#1ca0d1] mb-2">Añadir otros tratamientos</p>
                <div className="flex flex-col gap-2">
                  <div className="flex gap-1.5 items-center">
                    <input
                      type="text"
                      value={nuevoTtoTexto}
                      onChange={(e) => setNuevoTtoTexto(e.target.value)}
                      onKeyDown={(e) => { if (e.key === "Enter") agregarTratamientoNuevo(); }}
                      placeholder="p.ej. Endodoncia, Corona..."
                      className={`${MODAL_INPUT} flex-1`}
                    />
                    <select
                      value={nuevoTtoPieza || ""}
                      onChange={(e) => setNuevoTtoPieza(e.target.value || null)}
                      className={`${MODAL_INPUT} !w-16`}
                    >
                      <option value="">Pieza</option>
                      {piezas.map((p) => (
                        <option key={p.pieza} value={p.pieza}>{p.pieza}</option>
                      ))}
                    </select>
                    <ModalButton variant="primary" onClick={agregarTratamientoNuevo} disabled={!nuevoTtoTexto.trim()}>
                      + Añadir
                    </ModalButton>
                  </div>
                  {tratamientosNuevos.map((t, idx) => (
                    <div key={idx} className="flex items-center justify-between text-[12px] text-[#1500A0] font-semibold py-0.5 px-2 bg-[#FFFFFF] border border-[#BFE4F7] rounded-sm">
                      <span className="flex items-center gap-1.5">
                        ✎ {t.texto}
                        {t.pieza && <span className="text-[10px] font-mono bg-[#FFFFFF] px-1 rounded-sm">{t.pieza}</span>}
                      </span>
                      <button
                        onClick={() => eliminarTratamientoNuevo(idx)}
                        className="text-slate-400 hover:text-[#C026D3]"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </ModalBody>
          <ModalFooter>
            {registrado != null && (
              <span className={`text-[11px] font-semibold mr-auto ${registrado >= 0 ? "text-[#0F8C7D]" : "text-[#C026D3]"}`}>
                {registrado >= 0 ? `✓ ${registrado} acto(s) registrado(s) en el historial` : "Error al registrar"}
              </span>
            )}
            <ModalButton variant="magenta" icon={X} onClick={() => { setCerrar(false); setRegistrado(null); setTratamientosNuevos([]); setNuevoTtoTexto(""); setNuevoTtoPieza(null); }}>Cerrar</ModalButton>
            <ModalButton variant="primary" disabled={registrando || (planPropuesto.length === 0 && tratamientosNuevos.length === 0)} onClick={aprobarYregistrar}>
              {registrando ? <Loader2 className="w-4 h-4 animate-spin" /> : <ClipboardCheck className="w-4 h-4" strokeWidth={2.5} />}
              {registrando ? "Registrando…" : `Aprobar y registrar (${planPropuesto.length + tratamientosNuevos.length})`}
            </ModalButton>
          </ModalFooter>
        </Modal>
      )}
    </div>
  );
}
