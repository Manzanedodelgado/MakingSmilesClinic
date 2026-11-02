"use client";
/**
 * Tab ODONTOGRAMA — editor del estado de la boca. Portado VERBATIM del .37
 * (lógica de exclusiones, edición rápida, exploraciones), adaptado a nuestra
 * capa de datos: carga/guarda hallazgos vía patientService (PUT autosave).
 * Motor de render idéntico (OdontogramaOverlay/TratamientoSVG).
 */
import { useState, useMemo, useEffect, useRef } from "react";
import { X, Loader2, Plus, Edit2, Trash2, Check } from "lucide-react";
import { Modal, ModalBody, ModalFooter, ModalButton, MODAL_INPUT } from "@/shared/components";
import OdontogramaOverlay, { PiezaMarcada } from "./odontograma/OdontogramaOverlay";
import { CANALES_ENDO } from "./odontograma/TratamientoSVG";
import { construirOdontogramaClinico, ESTADO_COLOR } from "./odontograma/odontogramaData";
import { patientService } from "../services/patientService";
import type { Hallazgo } from "../types/patient";

type Realizado = { piezas: string; tratamiento: string; fecha: string };

const leyenda = [
  { label: "Sano", color: "#20BEAB" },
  { label: "Caries", color: "#7C3AED" },
  { label: "Obturación", color: "#00B0FF" },
  { label: "Endodoncia", color: "#424242" },
  { label: "Perno", color: "#7C3AED" },
  { label: "Corona", color: "#E9C22E" },
  { label: "Implante", color: "#1DE9B6" },
  { label: "Ortodoncia", color: "#9aa0a6" },
  { label: "Limpieza", color: "#00BCD4" },
  { label: "Raspado", color: "#E01B84" },
  { label: "Curetaje", color: "#E01B84" },
  { label: "Exodoncia", color: "#D500F9" },
  { label: "Ausente", color: "#D500F9" },
  { label: "Prótesis", color: "#F8BBD0" },
  { label: "Prótesis Removible", color: "#F8BBD0" },
  { label: "Retenedor Removible", color: "#81D4FA" },
  { label: "Retenedor Fijo", color: "#3c4043" },
  { label: "Ortodoncia Invisible", color: "#42A5F5" },
  { label: "Injerto", color: "#A21CAF" },
  { label: "Gingivectomia", color: "#9C27B0" },
  { label: "Alargamiento Coronario", color: "#C026D3" },
  { label: "Quistectomia", color: "#C026D3" },
];

const ZONAS: Record<string, string[]> = {
  "1": ["18", "17", "16", "15", "14", "13", "12", "11"],
  "2": ["21", "22", "23", "24", "25", "26", "27", "28"],
  "3": ["31", "32", "33", "34", "35", "36", "37", "38"],
  "4": ["48", "47", "46", "45", "44", "43", "42", "41"],
  "5": ["13", "12", "11", "21", "22", "23"],
  "6": ["43", "42", "41", "31", "32", "33"],
};

const ZONA_OPTIONS = [
  { value: "1", label: "Q1 — Superior Derecho" },
  { value: "2", label: "Q2 — Superior Izquierdo" },
  { value: "3", label: "Q3 — Inferior Izquierdo" },
  { value: "4", label: "Q4 — Inferior Derecho" },
  { value: "5", label: "Anterior Superior" },
  { value: "6", label: "Anterior Inferior" },
];

// TtosMed: 0=por pieza, 1=por cuadrante/zona, 2=boca completa
const TIPO_TRATAMIENTO: Record<string, number> = {
  SANO: 0, CARIES: 0, "OBTURACIÓN": 0, ENDODONCIA: 0, PERNO: 0,
  CORONA: 0, IMPLANTE: 0, EXODONCIA: 0, AUSENTE: 0, QUISTECTOMIA: 0, INJERTO: 0,
  "PRÓTESIS": 0, "PRÓTESIS REMOVIBLE": 1, ORTODONCIA: 1,
  "RETENEDOR REMOVIBLE": 1, "RETENEDOR FIJO": 1, "ORTODONCIA INVISIBLE": 1,
  LIMPIEZA: 1, RASPADO: 1, CURETAJE: 1, HIGIENE: 2, TARTRECTOMIA: 2,
};

const hoy = () => new Date().toLocaleDateString("es-ES", { day: "2-digit", month: "2-digit", year: "numeric" });
type FormItem = { id: string; pieza: string; caras: string[] };

export function Odontograma({ patientId }: { patientId: number }) {
  const [hallazgos, setHallazgos] = useState<Hallazgo[]>([]);
  const [realizados, setRealizados] = useState<Realizado[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");
  const [edad, setEdad] = useState<number | null>(null);
  const loadedRef = useRef(false);
  const flash = (t: string) => { setMsg(t); setTimeout(() => setMsg(""), 2500); };


  useEffect(() => {
    let alive = true;
    setLoading(true); loadedRef.current = false;
    patientService.cabecera(patientId).then((c) => { if (alive) setEdad(c.edad); }).catch(() => {});
    patientService.odontograma(patientId)
      .then((d) => { if (alive) { setHallazgos(Array.isArray(d.teeth) ? d.teeth : []); setRealizados(Array.isArray(d.realizados) ? d.realizados : []); } })
      .catch(() => { if (alive) { setHallazgos([]); setRealizados([]); } })
      .finally(() => { if (alive) { setLoading(false); loadedRef.current = true; } });
    return () => { alive = false; };
  }, [patientId]);

  // Autosave (debounce 500ms) — solo tras la carga inicial.
  useEffect(() => {
    if (!loadedRef.current) return;
    const t = setTimeout(() => {
      setSaving(true);
      patientService.guardarOdontograma(patientId, hallazgos)
        .catch(() => flash("Error al guardar"))
        .finally(() => setSaving(false));
    }, 500);
    return () => clearTimeout(t);
  }, [hallazgos, patientId]);

  // Odontograma VISUAL con exclusiones estrictas (verbatim .37).
  const { piezasOdontograma, hallazgosMostrados } = useMemo(() => {
    // Lista (tabla de O2): hallazgos INICIAL ordenados por fecha ("—" primero, inserción como desempate).
    const filtrados = hallazgos.filter((h) => h.tipoRegistro === "INICIAL");
    const sorted = filtrados.map((h, originalIndex) => ({ h, originalIndex })).sort((a, b) => {
      if (a.h.fecha === "—" && b.h.fecha !== "—") return -1;
      if (b.h.fecha === "—" && a.h.fecha !== "—") return 1;
      if (a.h.fecha === "—" && b.h.fecha === "—") return b.originalIndex - a.originalIndex;
      const tA = new Date(a.h.fecha.split("/").reverse().join("-")).getTime();
      const tB = new Date(b.h.fecha.split("/").reverse().join("-")).getTime();
      if (tA !== tB) return tA - tB;
      return b.originalIndex - a.originalIndex;
    }).map((x) => x.h);
    // RENDER = la MISMA función compartida que O1/O4/O5 (construirOdontogramaClinico). UNA sola
    // fuente de verdad: hallazgos INICIAL + realizados, con las prioridades de resolverExclusiones.
    const piezas: PiezaMarcada[] = construirOdontogramaClinico(hallazgos, realizados, { soloInicial: true });
    return { piezasOdontograma: piezas, hallazgosMostrados: sorted };
  }, [hallazgos, realizados]);

  // ── edición rápida (clic en diente con herramienta + caras) ──
  const [modoEdicion, setModoEdicion] = useState(false);
  const [herramientaActiva, setHerramientaActiva] = useState<string | null>(null);
  const [carasActivas, setCarasActivas] = useState<Record<string, boolean>>({ O: false, M: false, D: false, V: false, L: false, C: false });
  const toggleEdicion = () => {
    if (modoEdicion) { setModoEdicion(false); setHerramientaActiva(null); }
    else { setModoEdicion(true); setHerramientaActiva("CARIES"); }
  };
  const handleToothClick = (pieza: string) => {
    if (!modoEdicion || !herramientaActiva) return;
    const carasArray = ["O", "M", "D", "V", "L", "C"].filter((c) => carasActivas[c]);
    const strCaras = carasArray.length > 0 ? carasArray.join("") : "-";
    setHallazgos((prev) => [{ pieza, estado: herramientaActiva, cara: strCaras, obs: "", tipoRegistro: "INICIAL", fecha: hoy() }, ...prev]);
  };

  // ── tabla de exploraciones (agrupadas por estado+fecha) ──
  type Grupo = { pieza: string; estado: string; colorEstado: string; obs?: string; fecha: string; original: Hallazgo };
  const hallazgosAgrupados = useMemo<Grupo[]>(() => {
    const map = new Map<string, { items: Hallazgo[]; label: string }>();
    for (const h of hallazgosMostrados) {
      let labelEstado = h.estado;
      if (h.estado === "ENDODONCIA") {
        const rads = CANALES_ENDO[h.pieza]?.length || 1;
        labelEstado = rads > 1 ? "Endodoncia bi y multirradicular" : "Endodoncia unirradicular";
      }
      const key = `${labelEstado}|${h.fecha}`;
      const entry = map.get(key) || { items: [], label: labelEstado };
      entry.items.push(h);
      map.set(key, entry);
    }
    const fmt = (p: string, c?: string) => (c && c !== "-" ? `${p}(${c})` : p);
    return Array.from(map.values()).map(({ items, label }) => ({
      pieza: items.map((g) => fmt(g.pieza, g.cara)).join(", "),
      estado: label, colorEstado: items[0].estado, obs: items[0].obs, fecha: items[0].fecha, original: items[0],
    })).reverse();
  }, [hallazgosMostrados]);

  // ── modal nueva/editar exploración ──
  const [modalExploracion, setModalExploracion] = useState(false);
  const [form, setForm] = useState<{ estado: string; tipoRegistro: string; obs: string; items: FormItem[] }>(
    { estado: "CARIES", tipoRegistro: "INICIAL", obs: "", items: [{ id: "1", pieza: "", caras: [] }] });
  const [identificadorAEditar, setIdentificadorAEditar] = useState<string | null>(null);
  const resetForm = () => setForm({ estado: "CARIES", tipoRegistro: "INICIAL", obs: "", items: [{ id: Date.now().toString(), pieza: "", caras: [] }] });
  const tipoActual = TIPO_TRATAMIENTO[form.estado] ?? 0;

  function resolverPiezas(input: string): string[] {
    const parts = input.split(",").map((p) => p.trim()).filter(Boolean);
    const result: string[] = [];
    for (const part of parts) {
      const val = part.toUpperCase();
      if (ZONAS[val]) { result.push(...ZONAS[val]); continue; }
      if (val === "Q1") { result.push(...ZONAS["1"]); continue; }
      if (val === "Q2") { result.push(...ZONAS["2"]); continue; }
      if (val === "Q3") { result.push(...ZONAS["3"]); continue; }
      if (val === "Q4") { result.push(...ZONAS["4"]); continue; }
      if (val === "SUP" || val === "SUPERIOR") { result.push(...ZONAS["1"], ...ZONAS["2"]); continue; }
      if (val === "INF" || val === "INFERIOR") { result.push(...ZONAS["4"], ...ZONAS["3"]); continue; }
      result.push(part);
    }
    return result;
  }

  const abrirEdicionTratamiento = (orig: Hallazgo) => {
    const key = `${orig.estado}|${orig.fecha}`;
    const toEdit = hallazgos.filter((h) => `${h.estado}|${h.fecha}` === key);
    const items: FormItem[] = toEdit.length > 0
      ? toEdit.map((h, i) => ({ id: Date.now().toString() + i, pieza: h.pieza, caras: h.cara && h.cara !== "-" ? h.cara.split("") : [] }))
      : [{ id: Date.now().toString(), pieza: "", caras: [] }];
    setForm({ estado: orig.estado, tipoRegistro: toEdit[0]?.tipoRegistro || "INICIAL", obs: orig.obs || "", items });
    setIdentificadorAEditar(key);
    setModalExploracion(true);
  };

  const PIEZAS_TODAS = [...ZONAS["1"], ...ZONAS["2"], ...ZONAS["4"], ...ZONAS["3"]];

  const handleGuardarExploracion = () => {
    const tienePieza = form.items.length > 0 && form.items[0].pieza.trim();
    if (tipoActual === 0 && !tienePieza) return void flash("Debes indicar al menos una pieza");
    if (tipoActual === 1 && !tienePieza) return void flash("Indica cuadrante (Q1–Q4) o arcada (SUP/INF)");
    const fecha = identificadorAEditar ? identificadorAEditar.split("|")[1] : hoy();
    const nuevos: Hallazgo[] = [];
    if (tipoActual === 2 && !tienePieza) {
      PIEZAS_TODAS.forEach((p) => nuevos.push({ pieza: p, estado: form.estado, cara: "-", obs: form.obs, tipoRegistro: form.tipoRegistro, fecha }));
    } else {
      form.items.forEach((item) => {
        if (!item.pieza.trim()) return;
        const strCaras = item.caras.length > 0 ? item.caras.join("") : "-";
        resolverPiezas(item.pieza).forEach((p) => nuevos.push({ pieza: p, estado: form.estado, cara: strCaras, obs: form.obs, tipoRegistro: form.tipoRegistro, fecha }));
      });
    }
    if (identificadorAEditar) {
      const filtrados = hallazgos.filter((h) => `${h.estado}|${h.fecha}` !== identificadorAEditar);
      setHallazgos([...nuevos, ...filtrados]);
    } else setHallazgos([...nuevos, ...hallazgos]);
    setModalExploracion(false); setIdentificadorAEditar(null); resetForm();
  };

  const eliminarGrupo = (orig: Hallazgo) => {
    const key = `${orig.estado}|${orig.fecha}`;
    setHallazgos((prev) => prev.filter((x) => `${x.estado}|${x.fecha}` !== key));
  };

  return (
    <div className="flex-1 overflow-y-auto px-3 py-4 bg-white">
      {msg && <div className="fixed top-14 right-6 z-50 px-4 py-2.5 rounded-sm text-[12px] font-semibold shadow-lg bg-[#2DD9C3] text-[#1500A0]">{msg}</div>}

      {/* Header */}
      <div className="flex items-center justify-between mb-3 pl-2">
        {loading ? (
          <div className="flex items-center gap-2 text-[#7f8c8d]"><Loader2 className="w-4 h-4 animate-spin" /><span className="text-[11px]">Cargando…</span></div>
        ) : saving ? (
          <div className="flex items-center gap-2 text-[#7f8c8d]"><Loader2 className="w-4 h-4 animate-spin" /><span className="text-[11px]">Guardando…</span></div>
        ) : <div />}
        <button onClick={() => { resetForm(); setIdentificadorAEditar(null); setModalExploracion(true); }}
          className="bg-white text-[#1500A0] border border-[#9ca3af] hover:bg-[#E6EDFF] px-3 py-1 rounded-sm text-[12px] font-semibold uppercase tracking-wider flex items-center gap-1 cursor-pointer">
          <Plus className="w-3.5 h-3.5" /> Nueva exploración
        </button>
      </div>

      <div className="flex gap-3">
        {/* IZQUIERDA: Odontograma + Leyenda */}
        <div className="flex-1 flex flex-col gap-2">
          <div onDoubleClick={toggleEdicion}
            className={`bg-white rounded-sm flex flex-col transition-colors select-none ${modoEdicion ? "ring-4 ring-[#3388FF] bg-[#FFFFFF] cursor-crosshair" : "border border-[#e5e7eb]"}`}
            title="Doble clic para entrar/salir de Edición Rápida">
            <div className="p-2 flex flex-col items-center">
              {modoEdicion && (
                <div className="bg-[#3388FF] text-[#1500A0] text-[11px] font-semibold px-4 py-2 rounded-sm shadow mb-2 w-full flex flex-col items-center gap-2">
                  <span>MODO EDICIÓN — Herramienta + cara(s) + clic en diente</span>
                  {["CARIES", "OBTURACIÓN"].includes(herramientaActiva || "") && (
                    <div className="flex gap-1.5">
                      {["O", "M", "D", "V", "L", "C"].map((c) => (
                        <button key={c} onClick={(e) => { e.stopPropagation(); setCarasActivas({ ...carasActivas, [c]: !carasActivas[c] }); }}
                          className={`w-6 h-6 rounded-sm text-[11px] font-semibold transition-all ${carasActivas[c] ? "bg-[#1500A0] text-white border border-[#1500A0]" : "bg-white text-[#1500A0] border border-transparent shadow hover:border-[#1ca0d1]"}`}>{c}</button>
                      ))}
                    </div>
                  )}
                </div>
              )}
              <OdontogramaOverlay
                modo={modoEdicion ? "edit" : "view"}
                piezasMarcadas={piezasOdontograma}
                onPiezaClick={handleToothClick}
                piezaActiva={null}
                imgClassName="w-full h-auto object-contain max-h-[359px]"
                edad={edad}
              />
            </div>
          </div>

          {/* Leyenda — 4 columnas; clic = herramienta (en modo edición) */}
          <div className="bg-white border border-[#e5e7eb] rounded-sm grid grid-cols-4 gap-x-2 gap-y-0.5 px-3 py-1.5">
            {leyenda.map((l) => (
              <div key={l.label} onClick={() => modoEdicion && setHerramientaActiva(l.label.toUpperCase())}
                className={`flex items-center gap-1.5 px-1 py-0.5 rounded-sm transition-all ${modoEdicion ? "cursor-pointer hover:bg-[#E6EDFF]" : ""} ${herramientaActiva === l.label.toUpperCase() ? "bg-[#1500A0] ring-2 ring-[#3388FF]" : ""}`}>
                <div className="w-2 h-2 rounded-sm flex-shrink-0" style={{ background: l.color }} />
                <span className={`text-[10px] ${herramientaActiva === l.label.toUpperCase() ? "text-white font-semibold" : "text-slate-600 font-semibold"}`}>{l.label}</span>
              </div>
            ))}
          </div>
        </div>

        {/* DERECHA: Exploraciones */}
        <div className="flex-1 bg-white border border-[#e5e7eb] rounded-sm overflow-hidden self-start">
          <div className="bg-[#1500A0] text-white text-[12px] font-semibold uppercase px-3 py-1">Exploraciones</div>
          <div className="flex bg-[#FFFFFF] text-[#1500A0] text-[11px] font-semibold uppercase px-2 py-1.5 border-b border-[#e5e7eb]">
            <div className="w-20">Fecha</div>
            <div className="flex-1">Estado</div>
            <div className="w-32">Pieza (cara)</div>
            <div className="w-14" />
          </div>
          {hallazgosAgrupados.map((h, i) => (
            <div key={`${h.pieza}-${i}`} className="flex items-center border-b border-[#e5e7eb] text-[12px] px-2 py-1.5 hover:bg-[#E6EDFF] group">
              <div className="w-20 text-[#7f8c8d]">{h.fecha}</div>
              <div className="flex-1 flex items-center gap-1.5 text-slate-600 truncate mr-2" title={h.estado}>
                <span className="inline-block w-3 h-3 rounded-sm shrink-0" style={{ background: ESTADO_COLOR[h.colorEstado] || "#999", boxShadow: h.colorEstado === "CARIES" ? `0 0 6px ${ESTADO_COLOR[h.colorEstado]}, 0 0 2px #fff` : undefined }} />
                <span className="truncate">{h.estado}</span>
              </div>
              <div className="w-32 text-slate-600 truncate">{h.pieza}</div>
              <div className="w-14 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                <button onClick={() => abrirEdicionTratamiento(h.original)} className="p-1 hover:bg-[#E6EDFF] rounded-sm text-[#1500A0]" title="Editar"><Edit2 className="w-3 h-3" /></button>
                <button onClick={() => eliminarGrupo(h.original)} className="p-1 hover:bg-[#E6EDFF] rounded-sm text-[#1500A0]" title="Eliminar"><Trash2 className="w-3 h-3" /></button>
              </div>
            </div>
          ))}
          {hallazgosAgrupados.length === 0 && <div className="px-3 py-6 text-center text-[12px] text-slate-400 italic">Sin exploraciones</div>}
        </div>
      </div>

      {/* MODAL nueva/editar exploración */}
      {modalExploracion && (
        <Modal
          title={identificadorAEditar ? "Editar exploración" : "Nueva exploración"}
          size="sm"
          onClose={() => { setModalExploracion(false); setIdentificadorAEditar(null); resetForm(); }}
          closeOnBackdrop={false}
        >
          <ModalBody>
            <div className="flex flex-col gap-3">
              <div className="flex flex-col gap-1">
                <span className="text-[12px] text-[#1ca0d1] uppercase">Afectación</span>
                <select value={form.estado} onChange={(e) => setForm({ ...form, estado: e.target.value })} className={MODAL_INPUT}>
                  {leyenda.map((l) => <option key={l.label} value={l.label.toUpperCase()}>{l.label}</option>)}
                </select>
              </div>

              <div className="flex flex-col gap-2">
                <span className="text-[12px] text-[#1ca0d1] uppercase">
                  {tipoActual === 2 ? "Boca completa (sin pieza)" : tipoActual === 1 ? "Cuadrante / Arcada" : "Piezas afectadas"}
                </span>
                {tipoActual === 2 ? (
                  <div className="text-[12px] text-[#7f8c8d] italic px-2 py-1.5 bg-[#FFFFFF] border border-[#BFE4F7] rounded-sm">Se aplicará a todas las piezas automáticamente</div>
                ) : tipoActual === 1 ? (
                  <div className="flex flex-wrap gap-1.5">
                    {ZONA_OPTIONS.map((z) => {
                      const sel = form.items[0]?.pieza.split(",").map((s) => s.trim()).includes(z.value);
                      return (
                        <button key={z.value} type="button" onClick={() => {
                          const curr = form.items[0]?.pieza.split(",").map((s) => s.trim()).filter(Boolean);
                          const next = sel ? curr.filter((v) => v !== z.value) : [...curr, z.value];
                          const newItems = [...form.items]; newItems[0] = { ...newItems[0], pieza: next.join(",") };
                          setForm({ ...form, items: newItems });
                        }} className={`px-2 py-1 text-[12px] font-medium border rounded-full cursor-pointer transition-colors ${sel ? "bg-[#21A2E5] text-white border-[#21A2E5]" : "bg-white border-[#BFE4F7] text-[#073D8D] hover:bg-[#E6EDFF]"}`}>{z.label}</button>
                      );
                    })}
                  </div>
                ) : form.items.map((item, idx) => (
                  <div key={item.id} className="flex items-center gap-2">
                    <input value={item.pieza} onChange={(e) => { const ni = [...form.items]; ni[idx].pieza = e.target.value; setForm({ ...form, items: ni }); }}
                      type="text" placeholder="Ej: 14" className={`${MODAL_INPUT} !w-16 text-center`} />
                    <div className="flex-1 flex gap-1 justify-center">
                      {["O", "M", "D", "V", "L", "C"].map((c) => {
                        const isActive = item.caras.includes(c);
                        return (
                          <button key={c} onClick={() => { const ni = [...form.items]; if (isActive) ni[idx].caras = ni[idx].caras.filter((x) => x !== c); else ni[idx].caras.push(c); setForm({ ...form, items: ni }); }}
                            className={`w-7 h-7 text-[11px] font-semibold rounded-full border cursor-pointer transition-colors ${isActive ? "bg-[#21A2E5] text-white border-[#21A2E5]" : "bg-white text-[#073D8D] border-[#BFE4F7] hover:bg-[#E6EDFF]"}`}>{c}</button>
                        );
                      })}
                    </div>
                    <button onClick={() => { if (form.items.length === 1) return; setForm({ ...form, items: form.items.filter((x) => x.id !== item.id) }); }}
                      className="w-7 h-7 flex items-center justify-center text-[#C026D3] hover:bg-[#E6EDFF] rounded-full cursor-pointer disabled:opacity-30" disabled={form.items.length === 1}><X className="w-4 h-4" /></button>
                  </div>
                ))}
                {tipoActual === 0 && (
                  <button onClick={() => setForm({ ...form, items: [...form.items, { id: Date.now().toString(), pieza: "", caras: [] }] })}
                    className="inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[11px] font-semibold bg-white border border-[#BFE4F7] text-[#073D8D] hover:bg-[#E6EDFF] cursor-pointer w-fit">+ Añadir otra pieza a este tratamiento</button>
                )}
              </div>

              <div className="flex flex-col gap-1 mt-2">
                <span className="text-[12px] text-[#1ca0d1] uppercase">Tratamiento</span>
                <textarea value={form.obs} onChange={(e) => setForm({ ...form, obs: e.target.value })} placeholder="Descripción del tratamiento…" className={`${MODAL_INPUT} resize-none`} rows={2} />
              </div>
            </div>
          </ModalBody>
          <ModalFooter>
            {identificadorAEditar && (
              <ModalButton variant="magenta" icon={Trash2} className="mr-auto"
                onClick={() => { setHallazgos(hallazgos.filter((h) => `${h.estado}|${h.fecha}` !== identificadorAEditar)); setModalExploracion(false); setIdentificadorAEditar(null); resetForm(); }}>
                Eliminar
              </ModalButton>
            )}
            <ModalButton variant="magenta" icon={X} onClick={() => { setModalExploracion(false); setIdentificadorAEditar(null); resetForm(); }}>Cancelar</ModalButton>
            <ModalButton variant="primary" icon={Check} onClick={handleGuardarExploracion}>
              {identificadorAEditar ? "Guardar cambios" : "Guardar exploración"}
            </ModalButton>
          </ModalFooter>
        </Modal>
      )}
    </div>
  );
}
