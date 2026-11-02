"use client";
/**
 * Cuadro de registrar consulta — DOS MODOS (visión del usuario):
 *  · "Revisión / Evaluación": registro manual del acto + asistente de escucha activa.
 *    El asistente (Escuchar / Escuchar Pro) es IA por voz en el .37 (useEscuchaClinica,
 *    Gemini/Groq); aquí queda como PLACEHOLDER hasta construir ese backend (fase Orquesta).
 *  · "Tratamiento planificado": líneas pendientes del presupuesto aceptado; el doctor marca
 *    lo que se hace HOY (se registra como realizado, enlazado a la línea) y lo de la PRÓXIMA
 *    cita + minutos (resumen para recepción antes de dar la cita).
 *  Modo inicial: ?modo=tratamiento|evaluacion (lo fijará la agenda según el tipo de cita).
 *  Catálogo y presupuestos = datos reales; voz/IA = pendiente (marcado como tal).
 */
import { useCallback, useEffect, useMemo, useRef, useState, type ElementType } from "react";
import { Check, X, Pill, Save, Stethoscope, ClipboardList, CalendarClock, Trash2 } from "lucide-react";
import { LABEL, INPUT, SELECT, TEXTAREA } from "@/shared/components";
import { api } from "@/shared/lib/api";
import { iconoTratamiento } from "@/shared/lib/iconoTratamiento";
import { patientService } from "../services/patientService";
import { useDirtyForm } from "../store/patientSession";
import type { Presupuesto, PlanProxima, PrevistoGroup, TratamientoCatalogo } from "../types/patient";
import { ZonaEditor, scopeDeCatalogo, valorInicialAmbito } from "./AmbitoPicker";

const hoy = () => new Date().toISOString().slice(0, 10);
const eur = (n: number) => n.toLocaleString("es-ES", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";
const initialModo = (): "evaluacion" | "tratamiento" =>
  (typeof window !== "undefined" && new URLSearchParams(window.location.search).get("modo") === "tratamiento")
    ? "tratamiento" : "evaluacion";

type Plan = "" | "hoy" | "proxima";
// Ítem unificado del plan: viene de un PREVISTO (con su fase/etiqueta) o, si el presupuesto
// aún no tiene plan (antiguos), de una LÍNEA del presupuesto aceptado (híbrido, sin perder nada).
type PlanItem = { key: string; tratamiento_id: number | null; tratamiento: string; pieza: string | null; zona_boca: string | null; importe: number; colaborador_id: number | null; etiqueta: string | null; previsto_id: number | null; linea_id: number };
type PlanPpto = { id: number; num: number | null; estado: string; fecha: string | null; items: PlanItem[] };

function ModeBtn({ active, icon: Icon, label, onClick, subrayado = false }: { active: boolean; icon: ElementType; label: string; onClick: () => void; subrayado?: boolean }) {
  return (
    <button onClick={onClick}
      className={subrayado
        ? `flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-[13px] font-semibold border-b-2 -mb-px transition-colors ${active ? "border-[#1CA0D1] text-[#1CA0D1]" : "border-transparent text-slate-500 hover:text-[#1CA0D1]"}`
        : `flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-sm text-[11px] font-semibold uppercase tracking-wide border transition-colors ${active ? "bg-[#3388FF] text-white border-[#3388FF]" : "bg-white text-[#1500A0] border-[#cfe1ff] hover:bg-[#E6EDFF]"}`}>
      <Icon className="w-3.5 h-3.5" /> {label}
    </button>
  );
}

export function AltaActo({ patientId, onSaved, onCancelar, onSucio, variante = "pagina" }: {
  patientId: number; onSaved?: () => void; onCancelar?: () => void;
  onSucio?: (sucio: boolean) => void; variante?: "pagina" | "emergente";
}) {
  const [modo, setModo] = useState<"evaluacion" | "tratamiento">(initialModo);
  const [fecha, setFecha] = useState(hoy());
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ── Doctor del acto (obligatorio: no hay tratamiento realizado sin doctor) ──
  const [doctores, setDoctores] = useState<{ id: number; nombre: string }[]>([]);
  const [colaboradorId, setColaboradorId] = useState<number | "">("");

  // ── Evaluación: catálogo + piezas + observaciones ──
  const [tratamiento, setTratamiento] = useState("");
  const [tratSel, setTratSel] = useState<TratamientoCatalogo | null>(null);
  const [piezas, setPiezas] = useState("");
  const [zona, setZona] = useState<string | null>(null);   // ámbito amplio (arcada/cuadrante/sextante)
  // ── Nota clínica SOAP de la visita (modelo .37). Fase 1: se compone como texto en
  //    el acto; Fase 2 la moverá a la tabla `soap` (subjetivo/objetivo/analisis/plan). ──
  const [subjetivo, setSubjetivo] = useState("");     // S — lo que cuenta el paciente (motivo, síntomas, medicación que refiere)
  const [objetivo, setObjetivo] = useState("");       // O — lo que veo / exploración
  const [obs, setObs] = useState("");                 // A — diagnóstico
  const [planClinico, setPlanClinico] = useState(""); // P — plan de tratamiento
  const [q, setQ] = useState("");
  const [res, setRes] = useState<TratamientoCatalogo[]>([]);
  const [open, setOpen] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Tratamiento planificado: PLAN de previstos (con fases) + fallback a líneas de ppto antiguos ──
  const [budgets, setBudgets] = useState<Presupuesto[]>([]);
  const [previstoGroups, setPrevistoGroups] = useState<PrevistoGroup[]>([]);
  const [pptoId, setPptoId] = useState("");
  const [planes, setPlanes] = useState<Record<string, { plan: Plan; min: number }>>({});
  const [planGuardado, setPlanGuardado] = useState<PlanProxima | null>(null);

  const cargarBudgets = useCallback(async () => {
    try {
      const [resp, prev] = await Promise.all([
        patientService.presupuestos(patientId),
        patientService.previstos(patientId).catch(() => ({ presupuestos: [] })),
      ]);
      setBudgets(resp.presupuestos.filter((b) => b.estado === "Aceptado" || b.estado === "En curso"));
      setPrevistoGroups(prev.presupuestos ?? []);
      setDoctores(resp.colaboradores ?? []);
    } catch (e) { console.error("alta-acto: no se pudo cargar presupuestos/previstos", e); }
  }, [patientId]);
  useEffect(() => { cargarBudgets(); }, [cargarBudgets]);

  // Plan unificado: previstos (con fase) primero; los ppto aceptados SIN previstos → desde sus líneas.
  const planPptos = useMemo<PlanPpto[]>(() => {
    const conPrev = new Set(previstoGroups.map((g) => g.id));
    const dePrevistos: PlanPpto[] = previstoGroups.map((g) => ({
      id: g.id, num: g.num, estado: g.estado, fecha: g.fecha,
      items: g.previstos.map((p) => ({ key: `pv${p.id}`, tratamiento_id: p.tratamiento_id, tratamiento: p.tratamiento, pieza: p.pieza, zona_boca: p.zona_boca, importe: p.importe, colaborador_id: p.colaborador_id, etiqueta: p.etiqueta, previsto_id: p.id, linea_id: p.linea_id })),
    }));
    const deLineas: PlanPpto[] = budgets.filter((b) => !conPrev.has(b.id)).map((b) => ({
      id: b.id, num: b.num, estado: b.estado, fecha: b.fecha,
      items: b.lineas.map((l) => ({ key: `ln${l.id}`, tratamiento_id: l.tratamiento_id, tratamiento: l.tratamiento, pieza: l.pieza, zona_boca: l.zona_boca, importe: l.precio, colaborador_id: l.colaborador_id, etiqueta: null, previsto_id: null, linea_id: l.id })),
    }));
    return [...dePrevistos, ...deLineas].sort((a, b) => (b.num ?? 0) - (a.num ?? 0));
  }, [previstoGroups, budgets]);
  useEffect(() => { setPptoId((prev) => prev || (planPptos[0] ? String(planPptos[0].id) : "")); }, [planPptos]);

  // Doctor por defecto = el colaborador del usuario logueado (si lo es).
  useEffect(() => {
    api.get<{ colaborador_id: number | null }>("/auth/me")
      .then((m) => { if (m.colaborador_id) setColaboradorId((prev) => prev || m.colaborador_id!); })
      .catch((e) => { console.error("alta-acto: /auth/me falló", e); });
  }, []);

  const cargarPlan = useCallback(async () => {
    try { setPlanGuardado((await patientService.planProxima(patientId)).plan); } catch { /* */ }
  }, [patientId]);
  useEffect(() => { cargarPlan(); }, [cargarPlan]);

  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    if (q.trim().length < 2) { setRes([]); return; }
    timer.current = setTimeout(async () => {
      try { setRes((await patientService.catalogoTratamientos(patientId, q.trim())).tratamientos); setOpen(true); } catch { setRes([]); }
    }, 250);
    return () => { if (timer.current) clearTimeout(timer.current); };
  }, [q, patientId]);

  const fmt = (s: string | null) => (s ? new Date(s).toLocaleDateString("es-ES") : "");
  const limpiarEval = () => {
    setTratamiento(""); setTratSel(null); setPiezas(""); setZona(null); setQ(""); setError(null);
    setSubjetivo(""); setObjetivo(""); setObs(""); setPlanClinico("");
  };

  // El ámbito (pieza/arcada/cuadrante/sextante/general) lo dicta el catálogo del tratamiento.
  const ambito = scopeDeCatalogo(tratSel?.tipo_actuacion);
  // Al elegir un tratamiento, fijamos el ámbito y su valor por defecto.
  const elegirTratamiento = (t: TratamientoCatalogo) => {
    setTratamiento(t.nombre); setTratSel(t); setQ(""); setRes([]); setOpen(false);
    const { pieza, zona_boca } = valorInicialAmbito(scopeDeCatalogo(t.tipo_actuacion));
    setPiezas(pieza); setZona(zona_boca);
  };

  const pptoSel = planPptos.find((b) => String(b.id) === pptoId) || null;
  const items = pptoSel?.items ?? [];
  const setPlan = (key: string, plan: Plan) =>
    setPlanes((p) => ({ ...p, [key]: { plan: p[key]?.plan === plan ? "" : plan, min: p[key]?.min ?? 30 } }));
  const setMin = (key: string, min: number) =>
    setPlanes((p) => ({ ...p, [key]: { plan: p[key]?.plan ?? "", min: Math.max(0, min) } }));
  const hoyItems = items.filter((i) => planes[i.key]?.plan === "hoy");
  const proxItems = items.filter((i) => planes[i.key]?.plan === "proxima");
  const proxMin = proxItems.reduce((s, i) => s + (planes[i.key]?.min ?? 0), 0);

  // ¿Hay algo escrito en la anamnesis de la visita?
  const hayNota = () => !!(subjetivo.trim() || objetivo.trim() || obs.trim() || planClinico.trim());
  // Fase 1: la nota SOAP se compone como texto en `notas` del acto. Fase 2 → tabla `soap`.
  const componerNota = () => [
    subjetivo.trim()   && `S: ${subjetivo.trim()}`,
    objetivo.trim()    && `O: ${objetivo.trim()}`,
    obs.trim()         && `Dx: ${obs.trim()}`,
    planClinico.trim() && `Plan: ${planClinico.trim()}`,
  ].filter(Boolean).join(" · ");

  async function guardarEval() {
    if (!tratSel && !hayNota()) return;
    if (!colaboradorId) { setError("Indica el doctor del tratamiento."); return; }
    setSaving(true); setError(null);
    try {
      await patientService.crearActo(patientId, {
        tratamiento_id: tratSel?.id ?? null, piezas: piezas || null, zona_boca: zona, fecha,
        importe: tratSel?.precio ?? null, notas: componerNota() || null,
        colaborador_id: colaboradorId,
      });
      limpiarEval(); onSaved?.();
    } catch (e) { setError(e instanceof Error ? e.message.replace(/^POST.*?→ \d+ /, "") : "No se pudo guardar"); }
    finally { setSaving(false); }
  }

  // Un acto a medio rellenar (modo evaluación) cuenta como cambio sin guardar.
  const sucio = modo === "evaluacion" && (!!tratSel || hayNota());
  useDirtyForm("nuevo-acto", sucio, guardarEval);
  useEffect(() => { onSucio?.(sucio); }, [sucio, onSucio]);

  async function guardarConsulta() {
    if (hoyItems.length === 0 && proxItems.length === 0) { setError("Marca al menos un tratamiento (Hoy o Próxima)."); return; }
    setSaving(true); setError(null);
    try {
      for (const it of hoyItems) {
        await patientService.crearActo(patientId, {
          tratamiento_id: it.tratamiento_id, piezas: it.pieza, zona_boca: it.zona_boca ?? null, fecha,
          importe: it.importe, presupuesto_linea_id: it.linea_id, previsto_id: it.previsto_id,
          colaborador_id: it.colaborador_id ?? (colaboradorId || null),
          notas: it.etiqueta ?? (pptoSel ? `Del presupuesto #${pptoSel.num}` : null),
        });
      }
      if (proxItems.length > 0) {
        await patientService.guardarPlanProxima(patientId, {
          minutos: proxMin, presupuesto_id: pptoSel?.id ?? null,
          items: proxItems.map((it) => ({ linea_id: it.linea_id, tratamiento: it.tratamiento, pieza: it.pieza, minutos: planes[it.key]?.min ?? 0 })),
        });
      }
      setPlanes((p) => { const n = { ...p }; [...hoyItems, ...proxItems].forEach((it) => delete n[it.key]); return n; });
      await cargarBudgets();   // recarga el plan: los realizados (previstos consumidos) salen del plan
      await cargarPlan();
      onSaved?.();
    } catch (e) { setError(e instanceof Error ? e.message.replace(/^P(OST|UT).*?→ \d+ /, "") : "No se pudo guardar"); }
    finally { setSaving(false); }
  }

  async function borrarPlan() {
    try { await patientService.borrarPlanProxima(patientId); setPlanGuardado(null); } catch { /* */ }
  }

  return (
    <div className="flex flex-col gap-2 h-full">
      {/* Selector de modo */}
      <div className={variante === "emergente" ? "flex border-b border-[#D5E3EE]" : "flex gap-1"}>
        <ModeBtn active={modo === "evaluacion"} icon={Stethoscope} label="Revisión / Evaluación" onClick={() => setModo("evaluacion")} subrayado={variante === "emergente"} />
        <ModeBtn active={modo === "tratamiento"} icon={ClipboardList} label="Tratamiento planificado" onClick={() => setModo("tratamiento")} subrayado={variante === "emergente"} />
      </div>

      {modo === "evaluacion" ? (
        /* ───────────── MODO EVALUACIÓN / REVISIÓN ───────────── */
        <>
          {/* Cuerpo desplazable: cabecera + perfil + anamnesis de la visita */}
          <div className="flex-1 min-h-0 overflow-y-auto pr-0.5 flex flex-col gap-2">
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className={LABEL}>Fecha</label>
                <input type="date" value={fecha} onChange={(e) => setFecha(e.target.value)} className={INPUT} />
              </div>
              <div>
                <label className={LABEL}>Doctor</label>
                <select value={colaboradorId} onChange={(e) => setColaboradorId(e.target.value ? Number(e.target.value) : "")} className={SELECT}>
                  <option value="">— Selecciona doctor —</option>
                  {doctores.map((d) => <option key={d.id} value={d.id}>{d.nombre}</option>)}
                </select>
              </div>
            </div>

            {/* Nota clínica SOAP de la visita (modelo .37) */}
            <div>
              <label className={LABEL}>Lo que cuenta el paciente</label>
              <textarea value={subjetivo} onChange={(e) => setSubjetivo(e.target.value)} rows={2}
                placeholder="Síntomas, motivo de consulta, medicación que refiere…" className={`${TEXTAREA} min-h-[46px]`} />
            </div>
            <div>
              <label className={LABEL}>Lo que veo / exploración</label>
              <textarea value={objetivo} onChange={(e) => setObjetivo(e.target.value)} rows={2}
                placeholder="Hallazgos, exploración, pruebas, radiografías…" className={`${TEXTAREA} min-h-[46px]`} />
            </div>
            <div>
              <label className={LABEL}>Diagnóstico</label>
              <textarea value={obs} onChange={(e) => setObs(e.target.value)} rows={2}
                placeholder="Juicio clínico, conclusión diagnóstica…" className={`${TEXTAREA} min-h-[46px]`} />
            </div>

            {/* Plan / Tratamiento: catálogo + zona + próximos pasos */}
            <div className="rounded-sm border border-[#e5e7eb] p-2 flex flex-col gap-2">
              <span className="text-[10px] font-semibold uppercase tracking-wide text-[#1ca0d1]">Plan / Tratamiento</span>
              <div className="grid grid-cols-[2fr_1fr] gap-2">
                <div className="relative">
                  <label className={LABEL}>Tratamiento (catálogo)</label>
                  <input value={tratamiento || q} onChange={(e) => { setTratamiento(""); setQ(e.target.value); }}
                    placeholder="Buscar tratamiento…" className={`${INPUT} pr-7`} />
                  {(tratamiento || q) && (
                    <button type="button" onClick={() => { setTratamiento(""); setQ(""); setOpen(false); }}
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-[#9ca3af] hover:text-[#C026D3]">
                      <X className="w-3.5 h-3.5" />
                    </button>
                  )}
                  {open && res.length > 0 && (
                    <div className="absolute z-20 left-0 right-0 mt-0.5 max-h-52 overflow-y-auto bg-white border border-[#e5e7eb] rounded-sm shadow-lg">
                      {res.map((t) => (
                        <button key={t.id} onClick={() => elegirTratamiento(t)}
                          className="w-full flex items-center gap-2 px-2 py-1.5 text-left hover:bg-[#E6EDFF] text-[12px]">
                          <span className="font-mono text-[10px] text-[#1500A0] bg-[#FFFFFF] px-1 rounded-sm">{t.codigo}</span>
                          <span className="flex-1 truncate text-[#333333]">{t.nombre}</span>
                          <span className="text-slate-500">{eur(t.precio)}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                <div>
                  <label className={LABEL}>Pieza / zona</label>
                  {tratSel ? (
                    <div className="h-[34px] flex items-center">
                      <ZonaEditor pieza={piezas} zona_boca={zona} lockScope={ambito}
                        onChange={({ pieza, zona_boca }) => { setPiezas(pieza); setZona(zona_boca); }} />
                    </div>
                  ) : (
                    <input disabled placeholder="Elige un tratamiento…" className={`${INPUT} opacity-60`} />
                  )}
                </div>
              </div>
              <div>
                <label className={LABEL}>Plan de tratamiento</label>
                <textarea value={planClinico} onChange={(e) => setPlanClinico(e.target.value)} rows={2}
                  placeholder="Tratamiento realizado, próximos pasos, prescripción…" className={`${TEXTAREA} min-h-[46px]`} />
              </div>
            </div>
          </div>

          {/* Footer fijo: receta + acciones */}
          <div className="flex items-center gap-1.5 flex-wrap shrink-0 pt-1.5 border-t border-[#f0f2f5]">
            <button title="Nueva receta (pendiente)" className="flex items-center gap-1 px-2.5 py-1.5 rounded-sm text-[11px] font-semibold uppercase tracking-wide bg-[#1500A0] text-white hover:bg-[#0d0080]"><Pill className="w-3.5 h-3.5" /> Nueva receta</button>
            <div className="ml-auto flex items-center gap-1.5">
              <button onClick={() => { limpiarEval(); onCancelar?.(); }} className={variante === "emergente" ? "px-4 py-1.5 rounded-full text-[12px] font-semibold bg-[#C026D3] text-white hover:brightness-110" : "px-3 py-1.5 rounded-sm text-[11px] font-semibold uppercase tracking-wide border border-[#e5e7eb] text-slate-500 hover:bg-[#E6EDFF]"}>Cancelar</button>
              <button onClick={guardarEval} disabled={saving || !colaboradorId || (!tratSel && !hayNota())}
                className="flex items-center gap-1 px-3 py-1.5 rounded-sm text-[11px] font-semibold uppercase tracking-wide bg-[#1500A0] text-white hover:bg-[#0d0080] disabled:opacity-50 disabled:cursor-not-allowed">
                <Save className="w-3.5 h-3.5" /> {saving ? "Guardando…" : "Guardar"}
              </button>
            </div>
          </div>
        </>
      ) : (
        /* ───────────── MODO TRATAMIENTO PLANIFICADO ───────────── */
        <>
          {/* Cuerpo desplazable: mismo patrón que el modo Evaluación — antes esto no tenía
              scroll y un presupuesto con muchas líneas se cortaba sin poder verlas todas. */}
          <div className="flex-1 min-h-0 overflow-y-auto pr-0.5 flex flex-col gap-2">
            <div className="grid grid-cols-[1fr_2fr] gap-2">
              <div>
                <label className={LABEL}>Fecha</label>
                <input type="date" value={fecha} onChange={(e) => setFecha(e.target.value)} className={INPUT} />
              </div>
              <div>
                <label className={LABEL}>Presupuesto (plan)</label>
                <select value={pptoId} onChange={(e) => { setPptoId(e.target.value); setPlanes({}); }} className={SELECT}>
                  {planPptos.length === 0 && <option value="">— Sin plan / presupuesto aceptado —</option>}
                  {planPptos.map((b) => <option key={b.id} value={b.id}>Ppto #{b.num} · {b.estado} · {fmt(b.fecha)}</option>)}
                </select>
              </div>
            </div>

            {planGuardado && (planGuardado.items?.length ?? 0) > 0 && (
              <div className="flex items-center gap-2 bg-[#FFFFFF] border border-[#DDD6FE] rounded-sm px-3 py-2 text-[12px]">
                <CalendarClock className="w-4 h-4 text-[#7C3AED] shrink-0" />
                <span className="text-[#7C3AED] font-semibold shrink-0">Plan próxima cita:</span>
                <span className="text-slate-600 truncate flex-1">{planGuardado.items.map((i) => i.tratamiento).join(", ")} · ~{planGuardado.minutos} min</span>
                <button onClick={borrarPlan} title="Borrar plan" className="text-slate-400 hover:text-[#C026D3] shrink-0"><Trash2 className="w-3.5 h-3.5" /></button>
              </div>
            )}

            {planPptos.length === 0 ? (
              <p className="text-[12px] text-slate-400 italic py-4 text-center">Este paciente no tiene plan ni presupuestos aceptados.</p>
            ) : (
              <div className="border border-[#e5e7eb] rounded-sm overflow-hidden">
                <table className="w-full text-[12px]">
                  <thead>
                    <tr className="sticky top-0 z-10 bg-[#FFFFFF] text-[10px] font-bold text-[#7f8c8d] uppercase shadow-[0_1px_0_#e5e7eb]">
                      <th className="px-2 py-1.5 text-left">Tratamiento pendiente</th>
                      <th className="px-2 py-1.5 text-left w-16">Pieza</th>
                      <th className="px-2 py-1.5 text-center w-16">Fase</th>
                      <th className="px-2 py-1.5 text-right w-20">Importe</th>
                      <th className="px-2 py-1.5 text-center w-44">Plan</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((it) => {
                      const pl = planes[it.key]?.plan ?? "";
                      return (
                        <tr key={it.key} className={`border-t border-[#f0f2f5] ${pl === "hoy" ? "bg-[#FFFFFF]" : pl === "proxima" ? "bg-[#FFFFFF]" : "hover:bg-[#E6EDFF]"}`}>
                          <td className="px-2 py-1.5">
                            <span className="flex items-center gap-2 min-w-0">
                              <span className="w-6 h-6 rounded-md bg-white border border-[#e5e7eb] flex items-center justify-center shrink-0">
                                {/* eslint-disable-next-line @next/next/no-img-element */}
                                <img src={iconoTratamiento(it.tratamiento)} alt="" className="w-4 h-4" />
                              </span>
                              <span className="truncate text-[12.5px] font-medium text-[#065AED]">{it.tratamiento}</span>
                            </span>
                          </td>
                          <td className="px-2 py-1.5 text-slate-500">{it.pieza || "—"}</td>
                          <td className="px-2 py-1.5 text-center">
                            {it.etiqueta && <span className="text-[10px] font-semibold text-[#7C3AED] bg-[#FFFFFF] border border-[#DDD6FE] rounded-sm px-1 py-0.5 whitespace-nowrap">{it.etiqueta}</span>}
                          </td>
                          <td className="px-2 py-1.5 text-right font-semibold text-[#1500A0]">{eur(it.importe)}</td>
                          <td className="px-2 py-1.5">
                            <div className="flex items-center justify-center gap-1">
                              <button onClick={() => setPlan(it.key, "hoy")}
                                className={`px-2 py-0.5 rounded-sm text-[10px] font-semibold uppercase border ${pl === "hoy" ? "bg-[#2DD9C3] text-[#1500A0] border-[#1AA897]" : "bg-white text-[#1ca0d1] border-[#cfe1ff] hover:bg-[#E6EDFF]"}`}>Hoy</button>
                              <button onClick={() => setPlan(it.key, "proxima")}
                                className={`px-2 py-0.5 rounded-sm text-[10px] font-semibold uppercase border ${pl === "proxima" ? "bg-[#7C3AED] text-white border-[#7C3AED]" : "bg-white text-[#7C3AED] border-[#DDD6FE] hover:bg-[#E6EDFF]"}`}>Próxima</button>
                              {pl === "proxima" && (
                                <span className="flex items-center gap-0.5">
                                  <input type="text" inputMode="numeric" value={planes[it.key]?.min ?? 30}
                                    onChange={(e) => setMin(it.key, parseInt(e.target.value.replace(/[^0-9]/g, "")) || 0)}
                                    className="w-9 text-center border border-[#e5e7eb] rounded-sm text-[11px] py-0.5 outline-none focus:border-[#1ca0d1]" />
                                  <span className="text-[10px] text-slate-400">min</span>
                                </span>
                              )}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                    {items.length === 0 && <tr><td colSpan={5} className="px-2 py-4 text-center text-slate-400 italic">Sin tratamientos pendientes en este presupuesto.</td></tr>}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Footer fijo: resumen (hoy/próxima) + guardar — mismo patrón que el modo Evaluación */}
          {planPptos.length > 0 && (
            <div className="flex flex-wrap items-center gap-3 text-[12px] bg-[#FFFFFF] border border-[#e5e7eb] rounded-sm px-3 py-2 shrink-0">
              <span className="flex items-center gap-1 text-[#1500A0] font-semibold"><Check className="w-3.5 h-3.5 text-[#2DD9C3]" /> Hoy: {hoyItems.length} tratamiento(s)</span>
              <span className="flex items-center gap-1 text-[#7C3AED] font-semibold"><CalendarClock className="w-3.5 h-3.5" /> Próxima cita: {proxItems.length} tratamiento(s){proxItems.length > 0 ? ` · ~${proxMin} min` : ""}</span>
              {proxItems.length > 0 && <span className="text-slate-500 truncate">→ {proxItems.map((it) => it.tratamiento).join(", ")}</span>}
              <button onClick={guardarConsulta} disabled={saving || (hoyItems.length === 0 && proxItems.length === 0)}
                className="ml-auto flex items-center gap-1 px-3 py-1.5 rounded-sm text-[11px] font-semibold uppercase tracking-wide bg-[#1500A0] text-white hover:bg-[#0d0080] disabled:opacity-50 disabled:cursor-not-allowed">
                <Save className="w-3.5 h-3.5" /> {saving ? "Guardando…" : "Guardar consulta"}
              </button>
            </div>
          )}
        </>
      )}

      {error && <p className="text-[11px] text-[#C026D3]">{error}</p>}
    </div>
  );
}
