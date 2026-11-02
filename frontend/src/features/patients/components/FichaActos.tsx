"use client";
/** FICHA — historial de actos clínicos (tratamientos_realizados) + indicadores. Solo BBDD nueva. */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useEventStream } from "@/shared/hooks/useEventStream";
import { X, ClipboardList, Stethoscope, Sparkles, Pencil, Trash2, Mic, FileText, Radiation, Braces, Euro, Receipt, FileSignature, IdCard, RefreshCw, Save, Plus } from "lucide-react";
import { ClinicalCard, Modal, ModalBody, ModalButton, MODAL_INPUT } from "@/shared/components";
import { usePermisos } from "@/shared/hooks/usePermisos";
import { configService, type FichaLayoutItem } from "@/shared/services/configService";
import { iconoTratamiento } from "@/shared/lib/iconoTratamiento";
import { FICHA_LAYOUT_DEFAULT, esLayoutValido, FICHA_LAYOUT_IDS, type FichaBoxId } from "./fichaLayoutDefault";
import { patientService } from "../services/patientService";
import type { FichaActos as TFichaActos, ActoClinico, OdontogramaData } from "../types/patient";
import OdontogramaOverlay from "./odontograma/OdontogramaOverlay";
import { construirOdontogramaClinico } from "./odontograma/odontogramaData";
import { FichaCabecera } from "./ficha/FichaPanel";
import { fichaTema } from "./ficha/fichaTema";
import { PanelPaciente } from "./ficha/PanelPaciente";
import { PanelAlertas } from "./ficha/PanelAlertas";
import { PanelCitas } from "./ficha/PanelCitas";
import { PanelMedicacion } from "./ficha/PanelMedicacion";
import { NuevoActoModal } from "./ficha/NuevoActoModal";
import { zonaLabel } from "./AmbitoPicker";
import { Odontograma } from "./Odontograma";
import { Periodontograma } from "./periodontograma/Periodontograma";
import { Multimedia } from "./Multimedia";
import { Radiologia } from "./Radiologia";
import { EstudioOrtodoncia } from "./EstudioOrtodoncia";
import { Documentos } from "./Documentos";
import { EscuchaActiva } from "./EscuchaActiva";
import { EjecutarTratamiento } from "./EjecutarTratamiento";
import { PostConsultaDocumentos } from "./PostConsultaDocumentos";
import { PresupuestoModal } from "./PresupuestoModal";
import { Filiacion } from "./Filiacion";

const eur =(n: number) => n.toLocaleString("es-ES", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";
const fecha = (s: string | null) => (s ? new Date(s).toLocaleDateString("es-ES") : "—");

// Etiqueta legible de cada tratamiento (key del odontograma) → para la leyenda bajo el odontograma.
const TTO_LABEL: Record<string, string> = {
  caries: "Caries", obturacion: "Obturación", endodoncia: "Endodoncia", corona: "Corona",
  "corona-implante": "Corona s/implante", implante: "Implante", ortodoncia: "Ortodoncia",
  exodoncia: "Exodoncia", ausencia: "Ausencia", protesis: "Prótesis", "protesis-removible": "Prótesis removible",
  quistectomia: "Quistectomía", limpieza: "Limpieza", tartrectomia: "Tartrectomía", higiene: "Higiene",
  raspado: "Raspado", curetaje: "Curetaje", injerto: "Injerto", "injerto periodontal": "Injerto periodontal",
  gingivectomia: "Gingivectomía", "alargamiento coronario": "Alargamiento coronario", alargamiento: "Alargamiento",
  "retenedor removible": "Retenedor removible", "retenedor fijo": "Retenedor fijo",
  "ortodoncia invisible": "Ortodoncia invisible", alineadores: "Alineadores", perno: "Perno",
  "reconstruccion-perno": "Perno",
};

type ModalTab = "odontograma" | "periodontograma" | "multimedia" | "documentos" | "radiologia" | "estudioOrto" | "filiacion";
const MODAL_TITULO: Record<ModalTab, string> = {
  // Internamente: odontograma = Odontograma 2 (Tratamientos previos); periodontograma = Odontograma 3.
  odontograma: "Tratamientos Previos", periodontograma: "Periodontograma", multimedia: "Multimedia", documentos: "Documentos",
  radiologia: "Radiología", estudioOrto: "Estudio de ortodoncia", filiacion: "Filiación",
};

export function FichaActos({ patientId }: { patientId: number }) {
  const [data, setData] = useState<TFichaActos | null>(null);
  const [odo, setOdo] = useState<OdontogramaData | null>(null);   // hallazgos + realizados (= fuente de O2)
  const [edad, setEdad] = useState<number | null>(null);   // para dentición infantil/mixta por edad
  const [modal, setModal] = useState<ModalTab | null>(null);
  const [nuevoActoOpen, setNuevoActoOpen] = useState(false);
  // Estética 3D "clay" (la de INICIO/Agenda), en prueba: botón "3D" de la barra inferior; preferencia de este navegador.
  const [clay, setClay] = useState(true);
  useEffect(() => { try { if (localStorage.getItem("ficha.estetica") === "clasica") setClay(false); } catch { /* sin almacenamiento: queda 3D */ } }, []);
  const cambiarEstetica = () => setClay((v) => { try { localStorage.setItem("ficha.estetica", v ? "clasica" : "clay"); } catch { /* preferencia solo de esta sesión */ } return !v; });
  // En 3D solo cambian color, relieve y sombra de la barra inferior; los paneles usan siempre el aspecto claro.
  const [escuchaOpen, setEscuchaOpen] = useState(false);
  const [docCat, setDocCat] = useState<string>("Facturas");   // categoría con la que abrir el emergente de Documentos
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 3 caminos de consulta: 1=ejecución, 2=primera visita, 3=revisión
  const [camino, setCamino] = useState<1 | 2 | 3 | null>(null);
  const [ejecutarOpen, setEjecutarOpen] = useState(false);
  const [postConsultaOpen, setPostConsultaOpen] = useState(false);
  const [presupuestoOpen, setPresupuestoOpen] = useState(false);
  const [tratamientosExtractos, setTratamientosExtractos] = useState<Array<{ texto: string; pieza?: string; tratamiento_id?: number | null; precio?: number }>>([]);

  // Edición/borrado de un acto realizado. Si el acto ya está facturado a su doctor → aviso.
  const [editActo, setEditActo] = useState<ActoClinico | null>(null);
  const [form, setForm] = useState({ fecha: "", piezas: "", importe: "", observaciones: "" });
  const [saving, setSaving] = useState(false);
  const [marcandoFracasado, setMarcandoFracasado] = useState<number | null>(null);

  const cargar = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [actos, odont] = await Promise.all([
        patientService.actos(patientId),
        patientService.odontograma(patientId).catch(() => null),   // hallazgos+realizados (= O2)
      ]);
      setData(actos); setOdo(odont);
    }
    catch (e) { setError(e instanceof Error ? e.message : "No se pudo cargar la ficha"); }
    finally { setLoading(false); }
  }, [patientId]);
  useEffect(() => { cargar(); }, [cargar]);

  // Tiempo real: si a este paciente se le emite una factura o se le registra un
  // acto (p.ej. el doctor desde la app), la lista de actos/facturas se refresca.
  useEventStream({
    "factura.emitida": (d) => { if (d.paciente_id === patientId) void cargar(); },
  }, [patientId]);
  useEffect(() => {
    let alive = true;
    patientService.cabecera(patientId).then((c) => { if (alive) setEdad(c.edad); }).catch(() => {});
    return () => { alive = false; };
  }, [patientId]);

  // Detectar camino al abrir una sesión de consulta
  const abrirConsulta = useCallback(async () => {
    try {
      const res = await patientService.detectarCamino(patientId);
      setCamino(res.camino);
      // Abrir el componente correspondiente
      if (res.camino === 1) {
        setEjecutarOpen(true);
      } else {
        setEscuchaOpen(true);  // Caminos 2 y 3 usan Escucha
      }
    } catch (e) {
      console.error("Error detectando camino:", e);
      setEscuchaOpen(true);  // Fallback a Escucha
    }
  }, [patientId]);

  // Como la lista va de más antiguo (arriba) a más reciente (abajo), el scroll se
  // posiciona por defecto abajo del todo → el tratamiento más reciente a la vista.
  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [data]);

  // Cajas LIBRES (sin rejilla): cada una vive donde se suelta, encima de las demás
  // y de los márgenes si así se coloca — nada las recoloca solas. Se arrastran desde
  // su barra ":: mover" y se escalan desde la esquina ◢. La vista se guarda en este
  // navegador al instante; "Guardar en clínica" (permiso config.editar) la publica
  // para todos, traducida a la rejilla compartida de 12 columnas.
  const FICHA_COLS = 12, FICHA_FILA = 28, FICHA_MARGEN = 10;
  const CAJA_MIN = { w: 200, h: 140 };
  const FICHA_GEO_LOCAL = "ficha_geo_local_v3";   // v3: vuelve a seguir el layout de la clínica (27-oct-2026)
  const colAncho = (W: number) => (W - (FICHA_COLS - 1) * FICHA_MARGEN) / FICHA_COLS;
  /** Rejilla de la clínica (12 col) → px con el ancho actual. */
  const gridAPx = (L: FichaLayoutItem[], W: number): Record<FichaBoxId, CajaGeo> => {
    const out = {} as Record<FichaBoxId, CajaGeo>;
    const cw = colAncho(W);
    for (const it of L) {
      out[it.i as FichaBoxId] = {
        x: Math.round(it.x * (cw + FICHA_MARGEN)),
        y: Math.round(it.y * (FICHA_FILA + FICHA_MARGEN)),
        w: Math.max(CAJA_MIN.w, Math.round(it.w * cw + (it.w - 1) * FICHA_MARGEN)),
        h: Math.max(CAJA_MIN.h, Math.round(it.h * FICHA_FILA + (it.h - 1) * FICHA_MARGEN)),
      };
    }
    return out;
  };
  /** Px actuales → rejilla de la clínica (para publicar). null si no encaja. */
  const pxAGrid = (g: Record<FichaBoxId, CajaGeo>, W: number): FichaLayoutItem[] | null => {
    const cw = colAncho(W);
    if (!Number.isFinite(cw) || cw <= 0) return null;
    const pasoX = cw + FICHA_MARGEN, pasoY = FICHA_FILA + FICHA_MARGEN;
    const L: FichaLayoutItem[] = FICHA_LAYOUT_IDS.map((id) => {
      const b = g[id];
      const gw = Math.min(FICHA_COLS, Math.max(1, Math.round((b.w + FICHA_MARGEN) / pasoX)));
      return {
        i: id,
        x: Math.min(FICHA_COLS - gw, Math.max(0, Math.round(b.x / pasoX))),
        y: Math.max(0, Math.round(b.y / pasoY)),
        w: gw,
        h: Math.min(60, Math.max(1, Math.round((b.h + FICHA_MARGEN) / pasoY))),
      };
    });
    return esLayoutValido(L) ? L : null;
  };
  const geoValida = (g: unknown): g is Record<FichaBoxId, CajaGeo> => {
    if (typeof g !== "object" || g === null) return false;
    return FICHA_LAYOUT_IDS.every((id) => {
      const b = (g as Record<string, unknown>)[id] as Record<string, unknown> | undefined;
      return !!b && [b.x, b.y, b.w, b.h].every((v) => typeof v === "number" && Number.isFinite(v))
        && (b.w as number) >= 100 && (b.h as number) >= 80;
    });
  };

  const { has: tienePermiso } = usePermisos();
  const puedeReorganizar = tienePermiso("config.editar");
  const [servidor, setServidor] = useState<FichaLayoutItem[] | null>(null);
  const [geo, setGeo] = useState<Record<FichaBoxId, CajaGeo> | null>(null);
  const [orden, setOrden] = useState<FichaBoxId[]>([]);
  const [sucio, setSucio] = useState(false);
  const [guardandoLayout, setGuardandoLayout] = useState(false);
  const [errorLayout, setErrorLayout] = useState<string | null>(null);
  const metricasRef = useRef({ w: 0 });
  const geoAnchoRef = useRef(0);
  const [anchoW, setAnchoW] = useState(0);
  const informarAncho = (W: number) => {
    if (Math.abs(W - metricasRef.current.w) < 1) return;
    metricasRef.current.w = W;
    setAnchoW(W);
  };

  // Layout de la clínica. Si la petición falla (p. ej. el backend se está reiniciando) se REINTENTA antes de caer al
  // por defecto del código (8/4, distinto del de la clínica): el por defecto solo se usa como último recurso y
  // en ese caso no se guarda nada en el navegador (servidorOk), para no dejar pegada una disposición equivocada.
  const servidorOk = useRef(false);
  useEffect(() => {
    let alive = true;
    let intento = 0;
    const cargar = () => {
      configService.fichaLayout()
        .then((l) => { if (!alive) return; servidorOk.current = true; setServidor(esLayoutValido(l) ? l : FICHA_LAYOUT_DEFAULT); })
        .catch(() => {
          if (!alive) return;
          if (++intento < 4) { window.setTimeout(cargar, 1500 * intento); return; }
          servidorOk.current = false;
          setServidor(FICHA_LAYOUT_DEFAULT);
        });
    };
    cargar();
    return () => { alive = false; };
  }, []);

  // Geometría inicial: lo guardado en este navegador; si no, la rejilla de la clínica.
  useEffect(() => {
    if (!servidor || geo || anchoW < 50) return;
    let base: Record<FichaBoxId, CajaGeo> | null = null;
    try {
      const loc = JSON.parse(localStorage.getItem(FICHA_GEO_LOCAL) || "null");
      if (geoValida(loc)) base = loc;
    } catch { /* sin guardado local: se usa la clínica */ }
    setGeo(base ?? gridAPx(servidor, anchoW));
    geoAnchoRef.current = anchoW;
    setOrden((o) => (o.length ? o : [...FICHA_LAYOUT_IDS]));
    setSucio(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [servidor, geo, anchoW]);

  // Si cambia el ancho (ventana, zoom), las cajas escalan en proporción — no se pierden.
  useEffect(() => {
    if (!geo || anchoW < 50 || !geoAnchoRef.current) return;
    const k = anchoW / geoAnchoRef.current;
    if (Math.abs(k - 1) < 0.01) return;
    setGeo((g) => {
      if (!g) return g;
      const n = {} as Record<FichaBoxId, CajaGeo>;
      for (const id of FICHA_LAYOUT_IDS) {
        const b = g[id];
        n[id] = { ...b, x: Math.round(b.x * k), w: Math.min(anchoW, Math.max(CAJA_MIN.w, Math.round(b.w * k))) };
      }
      // Solo se actualiza lo guardado si el usuario YA tenía una disposición propia: reescalar no es "mover".
      try { if (localStorage.getItem(FICHA_GEO_LOCAL)) persistirGeo(n); } catch { /* sin almacenamiento */ }
      return n;
    });
    geoAnchoRef.current = anchoW;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [anchoW]);

  const persistirGeo = (g: Record<FichaBoxId, CajaGeo>) => {
    if (!servidorOk.current) return;   // layout de emergencia (la clínica no respondió): no se fija en el navegador
    try { localStorage.setItem(FICHA_GEO_LOCAL, JSON.stringify(g)); } catch { /* sin almacenamiento */ }
  };
  const alFrente = (id: FichaBoxId) => setOrden((o) => [...o.filter((x) => x !== id), id]);
  function ponerGeo(id: FichaBoxId, b: CajaGeo) {
    setGeo((g) => {
      if (!g) return g;
      const n = { ...g, [id]: b };
      persistirGeo(n);
      return n;
    });
    setSucio(true);
  }

  async function guardarEnClinica() {
    if (!geo) return;
    const L = pxAGrid(geo, metricasRef.current.w);
    if (!L) { setErrorLayout("Las cajas no encajan en la rejilla de la clínica — júntalas un poco y reinténtalo."); return; }
    setGuardandoLayout(true); setErrorLayout(null);
    try {
      await configService.guardarFichaLayout(L);
      setServidor(L);
      setSucio(false);
    } catch {
      setErrorLayout("No se pudo guardar en la clínica, tu vista local sigue guardada — reinténtalo.");
    } finally {
      setGuardandoLayout(false);
    }
  }

  function restablecerClinica() {
    if (!servidor || metricasRef.current.w < 50) return;
    const g = gridAPx(servidor, metricasRef.current.w);
    setGeo(g);
    persistirGeo(g);
    setSucio(false);
    setErrorLayout(null);
  }

  // O1 = render ACTIVO de O2: hallazgos (INICIAL) + realizados, con las MISMAS prioridades/exclusiones.
  const piezas = useMemo(
    () => construirOdontogramaClinico(odo?.teeth ?? [], odo?.realizados ?? [], { soloInicial: true }),
    [odo],
  );

  // Leyenda = tratamientos representados en el odontograma (color + etiqueta), sin repetir.
  const leyenda = useMemo(() => {
    const seen = new Map<string, string>(); // etiqueta → color
    for (const p of piezas) {
      const label = TTO_LABEL[p.tratamiento] ?? (p.tratamiento.charAt(0).toUpperCase() + p.tratamiento.slice(1));
      if (!seen.has(label)) seen.set(label, p.color ?? "#3388FF");
    }
    return [...seen.entries()].map(([label, color]) => ({ label, color }));
  }, [piezas]);

  function abrirEdit(a: ActoClinico) {
    if (a.factura_activa) return;
    setEditActo(a);
    setForm({
      fecha: a.fecha ? a.fecha.slice(0, 10) : "",
      piezas: a.piezas ?? "",
      importe: a.importe != null ? String(a.importe) : "",
      observaciones: a.observaciones ?? "",
    });
  }

  async function guardarEdit() {
    if (!editActo) return;
    setSaving(true);
    try {
      await patientService.editarActo(patientId, editActo.id, {
        fecha: form.fecha || undefined,
        piezas: form.piezas || null,
        importe: form.importe === "" ? null : Number(form.importe),
        notas: form.observaciones || null,
      });
      setEditActo(null);
      await cargar();
    } finally { setSaving(false); }
  }

  async function marcarFracasado(a: ActoClinico) {
    if (a.fracasado || a.factura_activa || a.importe <= 0) return;
    setMarcandoFracasado(a.id); setError(null);
    try {
      await patientService.marcarTratamientoFracasado(patientId, a.id);
      await cargar();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo abonar el tratamiento fracasado");
    } finally { setMarcandoFracasado(null); }
  }

  async function borrar(a: ActoClinico) {
    if (a.factura_activa) return;
    const msg = a.facturado
      ? "Este tratamiento YA está facturado a su doctor. ¿Seguro que quieres borrarlo?"
      : "¿Borrar este tratamiento realizado?";
    if (!window.confirm(msg)) return;
    await patientService.borrarActo(patientId, a.id);
    await cargar();
  }

  if (loading) return <p className="text-[12px] text-slate-400 p-4">Cargando ficha…</p>;
  if (error) return <p className="text-[12px] text-[#C026D3] p-4">{error}</p>;
  if (!data) return null;

  // Contenido del odontograma, reutilizado por: (a) una referencia OCULTA a tamaño natural que
  // mide su alto (odoH) para congelar Historial, y (b) la tarjeta visible al 50% de la derecha.
  const odoInner = (
    <>
      {/* ODONTOGRAMA 1 (interno) — Ficha de paciente */}
      <FichaCabecera titulo="Odontograma"
        accion={
          <div className="flex items-center gap-1">
            <button type="button" onClick={() => setModal("odontograma")} title="Tratamientos Previos"
              className="flex items-center justify-center w-7 h-7 rounded text-[#1B3A5C] hover:bg-[#1B3A5C]/10 transition-colors">
              <ClipboardList className="w-4 h-4" />
            </button>
            <button type="button" onClick={() => setModal("periodontograma")} title="Perio"
              className="flex items-center justify-center w-7 h-7 rounded text-[#1B3A5C] hover:bg-[#1B3A5C]/10 transition-colors">
              <Stethoscope className="w-4 h-4" />
            </button>
            <span className="flex items-center gap-1 pl-2 ml-1 border-l border-[#1B3A5C]/20 text-[#1B3A5C] text-[11px] whitespace-nowrap"
              title="Última limpieza / mantenimiento perio / curetaje…">
              <Sparkles className="w-3.5 h-3.5 shrink-0" />
              {fecha(data.indicadores.ultima_higiene)}
            </span>
          </div>
        }
      />
      <div className="p-3 relative flex-1 min-h-0 overflow-hidden">
        <div style={{ transform: "translate(-4%, -10%) scale(0.75)", transformOrigin: "center" }}>
          <OdontogramaOverlay modo="view" piezasMarcadas={piezas} edad={edad} />
        </div>
        <div className="absolute top-1/2 -translate-y-1/2 right-3 flex flex-col gap-1.5 max-h-[92%] overflow-auto">
          {leyenda.length === 0 ? (
            <span className="text-[10px] text-slate-400 italic">Sin tratamientos</span>
          ) : leyenda.map(({ label, color }) => (
            <span key={label} className="inline-flex items-center gap-1.5 text-[10px] text-[#374151] whitespace-nowrap">
              <span className="w-3 h-3 rounded-[3px] border border-black/10 shrink-0" style={{ background: color }} />
              {label}
            </span>
          ))}
        </div>
      </div>
    </>
  );

  // Contenido de "Historial de tratamientos" — extraído para poder envolverlo en un
  // contenedor distinto (grid movible) sin tocar nada de lo que hay dentro.
  const historialInner = (
    <>
      <FichaCabecera titulo="Historial de tratamientos"
        accion={<>
          <span className="text-[11px]" style={{ color: fichaTema.textoSuave }}>{data.actos.length} acto(s)</span>
          <button type="button" onClick={() => setNuevoActoOpen(true)}
            className="flex items-center gap-1 h-[22px] px-2.5 rounded-full text-[11px] font-semibold text-white bg-[#1CA0D1] hover:brightness-110 transition-[filter]">
            <Plus className="w-3.5 h-3.5" /> Nuevo acto
          </button>
        </>}
      />
      <div ref={scrollRef} className="flex-1 min-h-0 overflow-auto">
      <table className="w-full table-fixed text-[11px]">
        {/* anchos: Fecha · Pieza · Doctor · Tratamiento (flexible, el mayor) · Observaciones · Importe · Acciones */}
        <colgroup>
          <col style={{ width: 70 }} />
          <col style={{ width: 44 }} />
          <col style={{ width: 90 }} />
          <col />
          <col style={{ width: 110 }} />
          <col style={{ width: 72 }} />
          <col style={{ width: 70 }} />
          <col style={{ width: 90 }} />
        </colgroup>
        <thead>
          <tr className="sticky top-0 z-10 bg-white text-[#333] text-[12px]">
            <th className="text-left px-2 py-[5px] font-normal border-b-2 border-[#dee2e6]">Fecha</th>
            <th className="text-left px-2 py-[5px] font-normal border-b-2 border-[#dee2e6]">Pieza</th>
            <th className="text-left px-2 py-[5px] font-normal border-b-2 border-[#dee2e6]">Doctor</th>
            <th className="text-left px-2 py-[5px] font-normal border-b-2 border-[#dee2e6]">Tratamiento</th>
            <th className="text-left px-2 py-[5px] font-normal border-b-2 border-[#dee2e6]">Observaciones</th>
            <th className="text-right px-2 py-[5px] font-normal border-b-2 border-[#dee2e6]">Importe</th>
            <th className="text-center px-1 py-[5px] font-normal border-b-2 border-[#dee2e6]">Fracasado</th>
            <th className="px-2 py-[5px] border-b-2 border-[#dee2e6]" aria-label="Acciones" />
          </tr>
        </thead>
        <tbody>
          {[...data.actos].reverse().map((a) => (
            <tr key={a.id} className="group border-b border-[#f0f2f5] hover:bg-[#E6EDFF]">
              <td className="px-2 py-1.5 text-slate-600 whitespace-nowrap">{fecha(a.fecha)}</td>
              <td className="px-2 py-1.5 text-slate-500 truncate" title={zonaLabel(a.piezas, a.zona_boca ?? null) || ""}>{zonaLabel(a.piezas, a.zona_boca ?? null) || "—"}</td>
              <td className="px-2 py-1.5 text-slate-600 truncate" title={a.doctor}>{a.doctor}</td>
              <td className="px-2 py-1.5">
                <span className="flex items-center gap-2 min-w-0" title={a.tratamiento}>
                  <span className="w-6 h-6 rounded-md bg-[#FFFFFF] border border-[#e5e7eb] flex items-center justify-center shrink-0">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={iconoTratamiento(a.tratamiento)} alt="" className="w-4 h-4" />
                  </span>
                  <span className="truncate text-[12px] font-medium text-[#1a1a1a]">{a.tratamiento}</span>
                </span>
              </td>
              <td className="px-2 py-1.5 text-slate-500 truncate" title={a.observaciones || ""}>{a.observaciones || "—"}</td>
              <td className={"px-2 py-1.5 text-right font-semibold whitespace-nowrap " + (a.importe < 0 ? "text-[#C026D3]" : "text-[#1500A0]")}>{eur(a.importe)}</td>
              <td className="px-1 py-1.5 text-center">
                {a.importe > 0 && (a.factura_activa ? (
                  <button type="button" onClick={() => { setDocCat("Facturas"); setModal("documentos"); }}
                    className="text-[9px] font-semibold text-[#1500A0] underline" title={`Gestionar rectificativa de la factura ${a.factura_numero || "asociada"}`}>Factura · gestionar</button>
                ) : <label className="inline-flex items-center gap-1 text-[9px] text-slate-500 cursor-pointer" title="Crea el mismo tratamiento en negativo y abona el saldo">
                  <input type="checkbox" checked={Boolean(a.fracasado)} disabled={Boolean(a.fracasado) || marcandoFracasado === a.id}
                    onChange={() => void marcarFracasado(a)} className="accent-[#1500A0]" />
                  <span>{marcandoFracasado === a.id ? "…" : "Sí"}</span>
                </label>)}
                {a.importe < 0 && a.observaciones?.includes("Tratamiento fracasado") &&
                  <span className="text-[9px] font-semibold text-[#1d4ed8]">Abono</span>}
              </td>
              <td className="px-1.5 py-1.5 whitespace-nowrap text-right">
                <div className="inline-flex items-center gap-1">
                  <button type="button" onClick={() => abrirEdit(a)} disabled={Boolean(a.factura_activa)} title={a.factura_activa ? "Anula primero la factura " + (a.factura_numero || "asociada") : "Editar"}
                    className="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-[#1ca0d1] transition-opacity disabled:cursor-not-allowed disabled:text-slate-200"><Pencil className="w-3.5 h-3.5" /></button>
                  <button type="button" onClick={() => borrar(a)} disabled={Boolean(a.factura_activa)} title={a.factura_activa ? "Anula primero la factura " + (a.factura_numero || "asociada") : "Borrar"}
                    className="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-[#C026D3] transition-opacity disabled:cursor-not-allowed disabled:text-slate-200"><Trash2 className="w-3.5 h-3.5" /></button>
                </div>
              </td>
            </tr>
          ))}
          {data.actos.length === 0 && (
            <tr><td colSpan={8} className="px-2 py-6 text-center text-[12px] text-slate-400 italic">Sin actos clínicos registrados</td></tr>
          )}
        </tbody>
      </table>
      </div>
    </>
  );

  const pacienteInner = <PanelPaciente patientId={patientId} actos={data.actos} />;
  const alertasInner = <PanelAlertas patientId={patientId} />;
  const citasInner = <PanelCitas patientId={patientId} />;
  const medicacionInner = <PanelMedicacion patientId={patientId} />;

  // Contenido de "Multimedia" — extraído igual que los anteriores.
  const multimediaInner = (
    <>
      <FichaCabecera titulo="Multimedia"
        accion={
          <div className="flex items-center gap-3">
            <button type="button" onClick={() => setModal("estudioOrto")} title="Estudio de ortodoncia (fotos + RX + resultado)"
              className="flex items-center gap-1 text-[11px] text-[#1B3A5C] hover:text-[#1CA0D1] cursor-pointer">
              <Braces className="w-3.5 h-3.5" /> Estudio orto
            </button>
            <button type="button" onClick={() => setModal("radiologia")} title="Radiología (importar y clasificar RX)"
              className="flex items-center gap-1 text-[11px] text-[#1B3A5C] hover:text-[#1CA0D1] cursor-pointer">
              <Radiation className="w-3.5 h-3.5" /> Radiología
            </button>
          </div>
        } />
      <div className="flex-1 min-h-0"><Multimedia patientId={patientId} /></div>
    </>
  );

  const cajaPorId: Record<FichaBoxId, React.ReactNode> = {
    paciente: pacienteInner,
    alertas: alertasInner,
    medicacion: medicacionInner,
    citas: citasInner,
    odontograma: odoInner,
    historial: historialInner,
    multimedia: multimediaInner,
  };

  return (
    <div style={{ background: "#FFFFFF" }}
      className={`pl-3 pr-3 pb-3 pt-3 flex flex-col h-full overflow-hidden ${clay
        ? "[&_section[data-id]>div]:rounded-[3px] [&_section[data-id]>div]:border-0 [&_section[data-id]>div]:[box-shadow:0_1px_4px_rgba(0,0,0,0.14)]"
        : ""}`}>
      {errorLayout && <div className="shrink-0 pb-2 text-[11px] text-[#C026D3]">{errorLayout}</div>}
      {guardandoLayout && puedeReorganizar && <div className="shrink-0 pb-1 text-[10px] text-slate-400">Guardando disposición…</div>}

      <FichaLibre geo={geo} orden={orden} cajaPorId={cajaPorId}
        onAncho={informarAncho} alFrente={alFrente} ponerGeo={ponerGeo} />

      {/* Barra fija bajo el lienzo: micrófono + accesos rápidos + guardar/restablecer disposición. */}
      <div className="shrink-0 h-11 flex items-stretch gap-1.5 mt-3 mr-[52px]">
        <button type="button" title="Abrir sesión de consulta (detecta camino automáticamente)" onClick={abrirConsulta}
          className={`shrink-0 w-11 h-11 rounded-full flex items-center justify-center text-white bg-[#1E9BE8] hover:brightness-110 transition-[filter] shadow-[0_3px_8px_rgba(0,0,0,0.3)] active:scale-95`}>
          <Mic className="w-4.5 h-4.5" />
        </button>
        <div className={`flex-1 flex items-center gap-2`}>
          <button type="button" title="Nuevo presupuesto" onClick={() => setPresupuestoOpen(true)}
            className="flex-1 flex items-center justify-center gap-1.5 h-[30px] self-center px-3 rounded-[3px] text-[12px] text-white bg-[#1500A0] hover:brightness-125 transition">
            <Euro className="w-3.5 h-3.5" /> Presupuesto
          </button>
          <button type="button" title="Nueva factura" onClick={() => { setDocCat("Facturas"); setModal("documentos"); }}
            className="flex-1 flex items-center justify-center gap-1.5 h-[30px] self-center px-3 rounded-[3px] text-[12px] text-white bg-[#1500A0] hover:brightness-125 transition">
            <Receipt className="w-3.5 h-3.5" /> Factura
          </button>
          <button type="button" title="Nuevo recibo" onClick={() => { setDocCat("Recibo"); setModal("documentos"); }}
            className="flex-1 flex items-center justify-center gap-1.5 h-[30px] self-center px-3 rounded-[3px] text-[12px] text-white bg-[#1500A0] hover:brightness-125 transition">
            <FileText className="w-3.5 h-3.5" /> Recibo
          </button>
          <button type="button" title="Nuevo consentimiento" onClick={() => { setDocCat("Consentimientos"); setModal("documentos"); }}
            className="flex-1 flex items-center justify-center gap-1.5 h-[30px] self-center px-3 rounded-[3px] text-[12px] text-white bg-[#1500A0] hover:brightness-125 transition">
            <FileSignature className="w-3.5 h-3.5" /> Consentimiento
          </button>
          <button type="button" title="Filiación" onClick={() => setModal("filiacion")}
            className="flex-1 flex items-center justify-center gap-1.5 h-[30px] self-center px-3 rounded-[3px] text-[12px] text-white bg-[#1500A0] hover:brightness-125 transition">
            <IdCard className="w-3.5 h-3.5" /> Filiación
          </button>
        </div>
        {puedeReorganizar && (
          <button type="button" title={guardandoLayout ? "Guardando…" : sucio ? "Guardar disposición en la clínica" : "Disposición guardada"}
            onClick={guardarEnClinica} disabled={guardandoLayout || !sucio}
            className={`shrink-0 w-11 h-11 rounded-full flex items-center justify-center text-white bg-[#1E9BE8] hover:brightness-110 disabled:opacity-40 shadow-[0_3px_8px_rgba(0,0,0,0.3)] active:scale-95`}>
            <Save className="w-4.5 h-4.5" />
          </button>
        )}
        <button type="button" title="Volver a la disposición de la clínica"
          onClick={restablecerClinica}
          className={`shrink-0 w-11 h-11 rounded-full flex items-center justify-center text-slate-600 bg-white hover:bg-[#f1f3f5] shadow-[0_3px_8px_rgba(0,0,0,0.3)] active:scale-95`}>
          <RefreshCw className="w-4.5 h-4.5" />
        </button>
        <button type="button" onClick={cambiarEstetica} aria-pressed={clay}
          title={clay ? "Volver a la estética clásica" : "Probar la estética 3D"}
          className={`shrink-0 w-11 h-11 rounded-full flex items-center justify-center text-[11px] font-bold shadow-[0_3px_8px_rgba(0,0,0,0.3)] active:scale-95 ${clay ? "text-white bg-[#1E9BE8]" : "text-slate-600 bg-white hover:bg-[#f1f3f5]"}`}>
          3D
        </button>
      </div>

      {/* Emergente: abre Tratamientos Previos / Perio / Multimedia sin salir de la Ficha */}
      {modal && (
        <Modal
          title={MODAL_TITULO[modal]}
          onClose={() => setModal(null)}
          size="full"
          closeOnBackdrop={false}
          className="h-[86vh] !max-w-[1120px]"
        >
          <ModalBody className="!p-0 !overflow-hidden flex flex-col">
            <div className="flex-1 min-h-0 min-w-0 flex flex-col overflow-hidden">
              {modal === "odontograma" && <Odontograma patientId={patientId} />}
              {modal === "periodontograma" && <Periodontograma patientId={patientId} />}
              {modal === "multimedia" && <Multimedia patientId={patientId} />}
              {modal === "documentos" && <Documentos patientId={patientId} categoriaInicial={docCat} onFacturaActualizada={() => void cargar()} />}
              {modal === "radiologia" && <Radiologia patientId={patientId} />}
              {modal === "estudioOrto" && <EstudioOrtodoncia patientId={patientId} />}
              {modal === "filiacion" && <Filiacion patientId={patientId} />}
            </div>
          </ModalBody>
        </Modal>
      )}

      {nuevoActoOpen && <NuevoActoModal patientId={patientId} onClose={() => setNuevoActoOpen(false)} onSaved={cargar} />}
      {presupuestoOpen && (
        <PresupuestoModal patientId={patientId} onClose={() => setPresupuestoOpen(false)}
          onSuccess={() => { setPresupuestoOpen(false); cargar(); }} />
      )}
      {/* Editar acto realizado */}
      {editActo && (
        <Modal
          title={`Editar · ${editActo.tratamiento}`}
          onClose={() => setEditActo(null)}
          size="md"
          closeOnBackdrop={false}
          footer={
            <>
              <ModalButton variant="magenta" icon={X} onClick={() => setEditActo(null)}>Cancelar</ModalButton>
              <ModalButton variant="primary" icon={Save} onClick={guardarEdit} disabled={saving}>
                {saving ? "Guardando…" : "Guardar"}
              </ModalButton>
            </>
          }
        >
          <ModalBody>
            <div className="flex flex-col gap-3">
              {editActo.facturado && (
                <div className="text-[12px] text-[#5B21B6] bg-[#FFFFFF] border border-[#C4B5FD] rounded-md px-3 py-2">
                  Este tratamiento <b>ya está facturado a su doctor</b>. Modifícalo solo si es estrictamente necesario.
                </div>
              )}
              <div className="grid grid-cols-2 gap-3">
                <label className="flex flex-col gap-1 text-[11px] font-semibold text-[#21A2E5]">Fecha
                  <input type="date" value={form.fecha} onChange={(e) => setForm((f) => ({ ...f, fecha: e.target.value }))}
                    className={MODAL_INPUT} />
                </label>
                <label className="flex flex-col gap-1 text-[11px] font-semibold text-[#21A2E5]">Importe (€)
                  <input type="text" inputMode="decimal" value={form.importe} onChange={(e) => setForm((f) => ({ ...f, importe: e.target.value.replace(/[^0-9.,]/g, "").replace(",", ".") }))}
                    className={MODAL_INPUT} />
                </label>
              </div>
              <label className="flex flex-col gap-1 text-[11px] font-semibold text-[#21A2E5]">Piezas
                <input type="text" value={form.piezas} onChange={(e) => setForm((f) => ({ ...f, piezas: e.target.value }))} placeholder="11, 12…"
                  className={MODAL_INPUT} />
              </label>
              <label className="flex flex-col gap-1 text-[11px] font-semibold text-[#21A2E5]">Observaciones
                <textarea rows={2} value={form.observaciones} onChange={(e) => setForm((f) => ({ ...f, observaciones: e.target.value }))}
                  className={`${MODAL_INPUT} resize-none`} />
              </label>
            </div>
          </ModalBody>
        </Modal>
      )}
      {escuchaOpen && (
        <EscuchaActiva
          patientId={patientId}
          onClose={() => { setEscuchaOpen(false); setPostConsultaOpen(true); }}
          onTratamientosExtractos={setTratamientosExtractos}
        />
      )}
      {ejecutarOpen && <EjecutarTratamiento patientId={patientId} onClose={() => { setEjecutarOpen(false); setPostConsultaOpen(true); }} />}
      {postConsultaOpen && (
        <PostConsultaDocumentos
          patientId={patientId}
          onClose={() => { setPostConsultaOpen(false); cargar(); }}
          tratamientosExtractos={tratamientosExtractos}
        />
      )}
    </div>
  );
}

import { FichaLibre, type CajaGeo } from "./FichaLibre";
