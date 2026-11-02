"use client";
/**
 * Agenda — calendario de citas. Solo BBDD nueva (makingsmiles, /agenda).
 * Vista Día (columnas por gabinete) y Semana (columnas por día); rejilla horaria
 * desde el horario del centro; tarjetas de cita con color por estado; modal crear/editar/anular.
 */
import { useEffect, useMemo, useRef, useState, Fragment } from "react";
import { useRouter } from "next/navigation";
import { ChevronLeft, ChevronRight, ChevronUp, X, Phone, Ban, ChevronDown, Check, CalendarClock, Stethoscope,
  Clock, LogIn, Settings, Maximize2, ListChecks, Tags, Columns3, Box, CalendarPlus, Hourglass, CheckCircle2, XCircle, CalendarCheck, CircleSlash, BadgeCheck, Circle, IdCard, FileText, Calendar, type LucideIcon } from "lucide-react";
import { Medallon, TABLERO } from "@/features/inicio/clay";

// Icono por estado de cita (estados_cita: 0 planificada · 1 anulada · 2 recepción · 3 sala espera
// · 4 consulta · 5 finalizada · 6 fallada · 7 confirmada · 8 cancelada · 9 aceptada).
const ESTADO_ICONO: Record<number, LucideIcon> = {
  0: Clock, 1: Ban, 2: LogIn, 3: Hourglass, 4: Stethoscope,
  5: CheckCircle2, 6: XCircle, 7: CalendarCheck, 8: CircleSlash, 9: BadgeCheck,
};
import { api } from "@/shared/lib/api";
import { Modal, ModalBody, ModalButton } from "@/shared/components";
import { imprimirJustificante } from "@/features/patients/lib/justificanteDoc";
import { CitaCockpit } from "./CitaCockpit";

// Modo de consulta según el tipo de cita: evaluación/revisión (asistente) vs tratamiento planificado.
const RE_EVAL = /control|primera|revisi|urgenc|valoraci|diagn|estudio|consulta|visita/i;
const modoDeCita = (tipo?: string | null): "evaluacion" | "tratamiento" =>
  tipo && !RE_EVAL.test(tipo) ? "tratamiento" : "evaluacion";

type Cita = {
  id: number; fecha: string; hora: string; duracion_min: number;
  gabinete_id: number | null; colaborador_id: number | null;
  estado_id: number | null; estado_nombre: string | null; estado_color: string;
  tipo_cita_id: number | null; tipo_nombre: string | null;
  paciente_id: number | null; nombre: string; apellidos: string; num_historia: string | null; telefono: string | null;
  notas: string | null; confirmada: boolean;
};
type Ref = {
  agendas: { id: number; nombre: string; color?: string | null }[];
  gabinetes: { id: number; nombre: string }[];
  estados: { id: number; codigo: string; nombre: string; color: string }[];
  tipos_cita: { id: number; nombre: string; color?: string | null }[];
  colaboradores: { id: number; nombre: string; color?: string | null }[];
  horario: { dias?: { abierto: boolean; t1a: string; t1b: string; t2a: string; t2b: string }[]; intervalo?: number | null; vistaDefecto?: string | null };
  duraciones?: { colaborador_id: number; tipo_cita_id: number; duracion_min: number }[];
  festivos: string[];
  bloqueos?: { fecha_inicio: string; fecha_fin: string; motivo?: string | null; colaborador_id?: number | null; gabinete_id?: number | null }[];
  horarios?: { colaborador_id: number; gabinete_id: number | null; dia_semana: number; hora_inicio: string; hora_fin: string }[];
};
type Draft = Partial<Cita> & { id?: number; email?: string | null };
type Pac = { id: number; nombre: string; apellidos: string; num_historia: string | null; telefono: string | null };

const SLOT_H = 32;                    // alto de celda (CSS 4: .slot-cell 32px)
// Paleta de fondo de cita (verbatim del .37): alternada por orden cronológico.
const CITA_COLORS = ["#1D5CB6", "#2598EE", "#2DD8F5", "#CCF3FF", "#B8D4F5", "#D6EAFF", "#E8F3FD"];
const CITA_DARK = new Set(["#1D5CB6", "#2598EE"]);
// Estética GesdenOne medida en Uploads/Agenda (agenda-gesdenone.css), pasada a la paleta corporativa
// (sin rojo/naranja/verde). Pastel por gabinete: crema, lavanda, azul hielo, amarillo pálido…
const COL_TINTS = ["#FBE9E7", "#FFF3E0", "#FFF8E1"]; // fondo por columna: pasteles de la captura (melocotón · naranja · ámbar)
const COL_HEADER_BG = "#0091EA";      // cabecera de columna (th, CSS 4)
const BARRA = "#005BB5";              // barra de Agenda (--primary-blue, CSS 4)
const LINEA_MEDIA = "#E0E6ED";        // --border-color (CSS 4)
const LINEA_CUARTO = "#FFFFFF";       // línea entre tramos (blanca)
const SEP_COLUMNA = "#E0E6ED";        // separador entre columnas (--border-color)
const PAUSA = "#E2DED4";              // --break-slot-bg (opacity .7)
const AHORA = "#D9534F";              // línea de hora actual (--accent-red, CSS 4)
const ALTO_CAB = 36;                  // cabecera de doctores: padding 10px + texto 0.8rem
const ANCHO_HORAS = 60;               // ancho columna de horas (CSS pegado)
const toMin = (h: string) => { const [a, b] = (h || "0:0").split(":").map(Number); return a * 60 + b; };
const pad = (n: number) => String(n).padStart(2, "0");
const fromMin = (m: number) => `${pad(Math.floor(m / 60))}:${pad(m % 60)}`;
const ymd = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const addDays = (d: Date, n: number) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
const DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"];
const DIAS_CORTO = ["LUN", "MAR", "MIÉ", "JUE", "VIE", "SÁB", "DOM"];
const idxDia = (d: Date) => (d.getDay() + 6) % 7; // 0=Lunes
function errMsg(e: unknown) {
  const raw = e instanceof Error ? e.message : String(e);
  const i = raw.indexOf("{");
  if (i >= 0) { try { const dd = JSON.parse(raw.slice(i)).detail; if (typeof dd === "string") return dd; } catch {} }
  return raw.replace(/\s*\{.*\}\s*$/, "") || "Error";
}

// Reparte citas solapadas en carriles (sub-columnas) para que no se pisen.
function layoutLanes(cs: Cita[]): Map<number, { lane: number; lanes: number }> {
  const res = new Map<number, { lane: number; lanes: number }>();
  const ev = cs.map((c) => ({ id: c.id, s: toMin(c.hora), e: toMin(c.hora) + (c.duracion_min || 30) }))
    .sort((a, b) => a.s - b.s || a.e - b.e);
  let i = 0;
  while (i < ev.length) {
    let end = ev[i].e; const group = [ev[i]]; let j = i + 1;
    while (j < ev.length && ev[j].s < end) { group.push(ev[j]); end = Math.max(end, ev[j].e); j++; }
    const laneEnds: number[] = [];
    for (const g of group) {
      let lane = laneEnds.findIndex((le) => le <= g.s);
      if (lane === -1) { lane = laneEnds.length; laneEnds.push(g.e); } else laneEnds[lane] = g.e;
      res.set(g.id, { lane, lanes: 0 });
    }
    for (const g of group) res.get(g.id)!.lanes = laneEnds.length;
    i = j;
  }
  return res;
}

export default function AgendaPage() {
  const router = useRouter();
  const [ref, setRef] = useState<Ref | null>(null);
  const [citas, setCitas] = useState<Cita[]>([]);
  const [fecha, setFecha] = useState(() => new Date());
  const [vista, setVista] = useState<"Día" | "Semana" | "Mes">("Día");
  const [verEstados, setVerEstados] = useState(true); // panel de estados (columna izquierda, vista Día)
  const [sel, setSel] = useState<Draft | null>(null);
  const [clip, setClip] = useState<{ cita: Cita; modo: "copiar" | "cortar" } | null>(null);
  const [menu, setMenu] = useState<{ x: number; y: number; cita?: Cita; date?: Date; hora?: string; gabId?: number } | null>(null);
  const [msg, setMsg] = useState<{ t: string; e?: boolean }>({ t: "" });
  const flash = (t: string, e = false) => { setMsg({ t, e }); setTimeout(() => setMsg({ t: "" }), 3000); };
  // Filtros de la barra (réplica de producción): anuladas, gabinetes visibles, doctor.
  const [verAnuladas, setVerAnuladas] = useState(false);
  const [gabsOcultos, setGabsOcultos] = useState<Set<number>>(new Set());
  const [docFiltro, setDocFiltro] = useState<number | null>(null);
  const [drop, setDrop] = useState<"" | "gab" | "doc" | "agenda" | "motivo">("");
  const [tipoFiltro, setTipoFiltro] = useState<number | null>(null); // "Motivo de la visita"
  const [agendaSel, setAgendaSel] = useState<number | null>(null);
  const [clay, setClay] = useState<boolean>(() => { try { return localStorage.getItem("agenda-clay") === "1"; } catch { return false; } });
  const cambiarEstetica = () => setClay((v) => { const n = !v; try { localStorage.setItem("agenda-clay", n ? "1" : "0"); } catch {} return n; });
  const [aviso, setAviso] = useState<string | null>(null); // emergente: franja no disponible
  const [abierta, setAbierta] = useState<number | null>(null); // cita con cockpit desplegado (empuja las de debajo)
  // Minuto actual (tic cada 30s) → línea de "ahora" de la rejilla (estética GesdenOne).
  const [ahoraMin, setAhoraMin] = useState(() => { const n = new Date(); return n.getHours() * 60 + n.getMinutes(); });
  useEffect(() => {
    const t = setInterval(() => { const n = new Date(); setAhoraMin(n.getHours() * 60 + n.getMinutes()); }, 30000);
    return () => clearInterval(t);
  }, []);
  const dateRef = useRef<HTMLInputElement>(null);
  const rejillaRef = useRef<HTMLDivElement>(null);   // scroll de la rejilla → botón esquina salta a "ahora"
  // Altura del cockpit: DINÁMICA — crece con su contenido (p.ej. al estructurar la Escucha) para que
  // nada quede oculto tras la ventana fija. Se mide con ResizeObserver y empuja las citas lo justo.
  const cockpitRef = useRef<HTMLDivElement>(null);
  const [PANEL_H, setPanelH] = useState(470);
  useEffect(() => {
    const el = cockpitRef.current;
    if (!el || abierta == null) { setPanelH(470); return; }
    const medir = () => setPanelH(Math.min(Math.max(el.scrollHeight + 4, 320), 1200));
    medir();
    const ro = new ResizeObserver(medir);
    ro.observe(el);
    return () => ro.disconnect();
  }, [abierta]);

  // Referencias por agenda: gabinetes/estados/tipos e intervalo/vista son de la agenda elegida.
  useEffect(() => {
    const a = agendaSel ? `?agenda_id=${agendaSel}` : "";
    api.get<Ref>(`/agenda/referencias${a}`).then((r) => {
      setRef(r);
      setAgendaSel((prev) => prev ?? r.agendas?.[0]?.id ?? null);
      const vd = r.horario?.vistaDefecto;
      if (vd === "Día" || vd === "Semana") setVista(vd);
    }).catch((e) => flash(errMsg(e), true));
  }, [agendaSel]);

  const semana = useMemo(() => { const lun = addDays(fecha, -idxDia(fecha)); return Array.from({ length: 7 }, (_, i) => addDays(lun, i)); }, [fecha]);
  // Vista Mes: 6 semanas completas (lunes a domingo) que contienen el mes de `fecha`.
  const mesDias = useMemo(() => { const d1 = new Date(fecha.getFullYear(), fecha.getMonth(), 1); const lun = addDays(d1, -idxDia(d1)); return Array.from({ length: 42 }, (_, i) => addDays(lun, i)); }, [fecha]);
  // Doctores del filtro: nombre en formato título ("IRENE GARCÍA" → "Irene García") y en orden alfabético.
  const doctores = useMemo(() => (ref?.colaboradores ?? [])
    .map((c) => ({ ...c, nombre: c.nombre.toLowerCase().replace(/(^|\s)(\p{L})/gu, (_m, s: string, l: string) => s + l.toUpperCase()).replace(/\b(De|Del|La|Las|Los|Y)\b(?=\s)/g, (w) => w.toLowerCase()) }))
    .sort((a, b) => a.nombre.localeCompare(b.nombre, "es")), [ref]);

  async function cargar() {
    try {
      const q = vista === "Día" ? `fecha=${ymd(fecha)}`
        : vista === "Semana" ? `desde=${ymd(semana[0])}&hasta=${ymd(semana[6])}`
        : `desde=${ymd(mesDias[0])}&hasta=${ymd(mesDias[41])}`;
      const a = agendaSel ? `&agenda_id=${agendaSel}` : "";
      const d = await api.get<{ citas: Cita[] }>(`/agenda/citas?${q}&incluir_anuladas=${verAnuladas}${a}`);
      setCitas(d.citas);
    } catch (e) { flash(errMsg(e), true); }
  }
  // Las citas no dependen de las referencias → se cargan en paralelo (sin cascada).
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { cargar(); }, [fecha, vista, verAnuladas, agendaSel]);

  // Rejilla de horas del día. Si hay turno partido (mañana t1a–t1b + tarde t2a–t2b),
  // el hueco intermedio NO se expande: se colapsa a UNA fila "Pausa" (rows[].tipo).
  const slots = useMemo(() => {
    const intervalo = ref?.horario?.intervalo || 15;
    const dia = ref?.horario?.dias?.[idxDia(vista === "Día" ? fecha : semana[0])];
    const t1a = dia?.t1a, t1b = dia?.t1b, t2a = dia?.t2a, t2b = dia?.t2b;
    const horas = [t1a, t1b, t2a, t2b].filter(Boolean) as string[];
    let ini = "09:00", fin = "21:00";
    if (horas.length) { ini = horas.reduce((a, b) => (toMin(b) < toMin(a) ? b : a)); fin = horas.reduce((a, b) => (toMin(b) > toMin(a) ? b : a)); }
    // ¿Turno partido con hueco real entre mañana y tarde?
    const gap = !!(t1a && t1b && t2a && t2b) && toMin(t2a as string) > toMin(t1b as string);
    const pIni = gap ? toMin(t1b as string) : 0, pFin = gap ? toMin(t2a as string) : 0;
    const t1aMin = gap ? toMin(t1a as string) : toMin(ini);
    const nMan = gap ? Math.round((pIni - t1aMin) / intervalo) : 0; // nº filas de mañana

    type Row = { tipo: "slot"; hora: string } | { tipo: "pausa" };
    const rows: Row[] = [];
    const list: string[] = [];
    const push = (m: number) => { const h = fromMin(m); rows.push({ tipo: "slot", hora: h }); list.push(h); };
    if (gap) {
      for (let m = t1aMin; m < pIni; m += intervalo) push(m);
      rows.push({ tipo: "pausa" });
      for (let m = pFin; m < toMin(t2b as string); m += intervalo) push(m);
    } else {
      for (let m = toMin(ini); m < toMin(fin); m += intervalo) push(m);
    }
    // Minuto → Y visual (la pausa, colapsada, ocupa una sola fila SLOT_H).
    const yOf = (m: number) => {
      if (!gap) return ((m - toMin(ini)) / intervalo) * SLOT_H;
      if (m < pIni) return ((m - t1aMin) / intervalo) * SLOT_H;          // mañana (incl. borde t1b)
      if (m < pFin) return nMan * SLOT_H;                                 // dentro de la pausa
      return (nMan + 1) * SLOT_H + ((m - pFin) / intervalo) * SLOT_H;     // tarde
    };
    return { rows, list, intervalo, yOf, totalH: rows.length * SLOT_H };
  }, [ref, fecha, vista, semana]);

  const cols = useMemo(() => {
    if (vista === "Semana") return semana.map((d, i) => ({ key: ymd(d), label: `${DIAS_CORTO[i]} ${d.getDate()}`, date: d, gabId: undefined as number | undefined }));
    if (!ref?.gabinetes?.length) return [{ key: "all", label: "Agenda", date: fecha, gabId: -1 }];
    const base = ref.gabinetes
      .filter((g) => !gabsOcultos.has(g.id))
      .map((g) => ({ key: String(g.id), label: g.nombre, date: fecha, gabId: g.id }));
    // columna "Sin gabinete" solo si hay citas del día sin gabinete asignado
    if (citas.some((c) => !c.gabinete_id)) base.push({ key: "sin", label: "Sin gabinete", date: fecha, gabId: 0 });
    return base;
  }, [vista, ref, semana, fecha, gabsOcultos, citas]);

  // Doctor(es) asignado(s) a un gabinete el día mostrado (de colaborador_horarios).
  const docDeGab = (gabId?: number) => {
    if (!gabId || gabId <= 0 || !ref?.horarios?.length) return null;
    const dia = idxDia(vista === "Día" ? fecha : semana[0]);
    const ids = [...new Set(ref.horarios.filter((h) => h.gabinete_id === gabId && h.dia_semana === dia).map((h) => h.colaborador_id))];
    const nombres = ids.map((id) => ref!.colaboradores.find((c) => c.id === id)?.nombre).filter(Boolean) as string[];
    return nombres.length ? nombres.join(" · ") : null;
  };

  const citasDeCol = (col: { date: Date; gabId?: number }) => citas.filter((c) => {
    if (docFiltro && c.colaborador_id !== docFiltro) return false; // filtro por doctor
    if (tipoFiltro && c.tipo_cita_id !== tipoFiltro) return false; // filtro por motivo de la visita
    if (vista === "Semana") return c.fecha === ymd(col.date);
    if (col.gabId === -1) return true;        // columna única cuando no hay gabinetes definidos
    if (col.gabId === 0) return !c.gabinete_id; // columna "Sin gabinete"
    return c.gabinete_id === col.gabId;
  });

  // estados_cita.id es un autoincremental GLOBAL (no por centro): NUNCA hardcodear qué id
  // es "anulada" — se resuelve por su código, tal como ya hace el catálogo cargado.
  const anuladaId = ref?.estados.find((e) => e.codigo === "anulada")?.id ?? null;
  const planificadaId = ref?.estados.find((e) => e.codigo === "planificada")?.id ?? null;

  // Orden cronológico global → índice para alternar el color de fondo (como el .37).
  const citaOrden = useMemo(() => {
    const m = new Map<number, number>();
    [...citas].sort((a, b) => (a.fecha + a.hora).localeCompare(b.fecha + b.hora)).forEach((c, i) => m.set(c.id, i));
    return m;
  }, [citas]);

  const topFor = (hora: string) => slots.yOf(toMin(hora));
  const heightFor = (hora: string, dur: number) => Math.max(slots.yOf(toMin(hora) + dur) - slots.yOf(toMin(hora)) - 2, 16);

  // Cockpit desplegado (solo vista Día): calcula desde dónde se empuja hacia abajo.
  const citaAbierta = vista === "Día" && abierta != null ? citas.find((c) => c.id === abierta) : null;
  const expandBottom = citaAbierta?.hora ? topFor(citaAbierta.hora) + Math.max(heightFor(citaAbierta.hora, citaAbierta.duracion_min), 26) + 2 : null;
  const off = (top: number) => (expandBottom != null && top >= expandBottom ? PANEL_H : 0); // desplazamiento de lo que va debajo
  // Y de la línea de "ahora" en la rejilla (null si el minuto cae fuera del horario visible).
  const yAhora = (() => {
    const y = slots.yOf(ahoraMin);
    return y >= 0 && y <= slots.totalH ? y : null;
  })();
  const insertRowIdx = expandBottom != null ? slots.rows.findIndex((_, i) => i * SLOT_H >= expandBottom) : -1;
  const gridExtra = expandBottom != null ? PANEL_H : 0;

  // ¿Se puede citar en este hueco? Devuelve el motivo si NO (festivo, cierre, fuera de horario, bloqueo).
  const noDisponible = (date: Date, hora: string, gabId?: number): string | null => {
    if (!ref) return null;
    const f = ymd(date);
    if (ref.festivos?.includes(f)) return "Día festivo — la clínica no atiende ese día.";
    const dia = ref.horario?.dias?.[idxDia(date)];
    if (!dia || !dia.abierto) return "La clínica permanece cerrada ese día.";
    const m = toMin(hora);
    const enTurno =
      (!!dia.t1a && !!dia.t1b && m >= toMin(dia.t1a) && m < toMin(dia.t1b)) ||
      (!!dia.t2a && !!dia.t2b && m >= toMin(dia.t2a) && m < toMin(dia.t2b));
    if (!enTurno) return "Fuera del horario de apertura del centro.";
    const dt = `${f}T${hora}`;
    for (const b of ref.bloqueos ?? []) {
      if (b.gabinete_id && gabId && b.gabinete_id !== gabId) continue;
      if (dt >= b.fecha_inicio.slice(0, 16) && dt < b.fecha_fin.slice(0, 16)) return b.motivo ? `Agenda bloqueada: ${b.motivo}` : "Franja bloqueada en la agenda.";
    }
    return null;
  };

  const nuevaEn = (date: Date, hora: string, gabId?: number) => {
    const motivo = noDisponible(date, hora, gabId);
    if (motivo) { setAviso(motivo); return; }
    setSel({ fecha: ymd(date), hora, duracion_min: 30, estado_id: null, gabinete_id: gabId && gabId > 0 ? gabId : null });
  };
  // Hora propuesta al crear desde la barra: hoy, el primer tramo que aún no ha pasado; otro día, la apertura.
  const horaSugerida = () =>
    (ymd(fecha) === ymd(new Date()) && slots.list.find((h) => toMin(h) >= ahoraMin)) || slots.list[0] || "10:00";
  async function moverCita(id: number, date: Date, hora: string, gabId?: number) {
    const motivo = noDisponible(date, hora, gabId);
    if (motivo) { setAviso(motivo); return; }
    try { await api.put(`/agenda/citas/${id}/mover`, { fecha: ymd(date), hora, gabinete_id: gabId && gabId > 0 ? gabId : null }); flash("Cita movida ✓"); cargar(); }
    catch (e) { flash(errMsg(e), true); }
  }
  async function anularCita(id: number) {
    try { await api.put(`/agenda/citas/${id}/anular`, {}); flash("Cita anulada ✓"); cargar(); }
    catch (e) { flash(errMsg(e), true); }
  }
  async function cambiarEstado(id: number, estadoId: number) {
    try { await api.put(`/agenda/citas/${id}/estado`, { estado_id: estadoId }); flash("Estado actualizado ✓"); cargar(); }
    catch (e) { flash(errMsg(e), true); }
  }
  async function pegar(date: Date, hora: string, gabId?: number) {
    if (!clip) return;
    const motivo = noDisponible(date, hora, gabId);
    if (motivo) { setAviso(motivo); return; }
    const c = clip.cita; const gab = gabId && gabId > 0 ? gabId : null;
    try {
      if (clip.modo === "cortar") {
        await api.put(`/agenda/citas/${c.id}/mover`, { fecha: ymd(date), hora, gabinete_id: gab });
      } else {
        await api.post("/agenda/citas", {
          fecha: ymd(date), hora, duracion_min: c.duracion_min, agenda_id: agendaSel, gabinete_id: gab,
          colaborador_id: c.colaborador_id, estado_id: null, tipo_cita_id: c.tipo_cita_id,
          paciente_id: c.paciente_id, nombre: c.nombre, apellidos: c.apellidos,
          telefono_movil: c.telefono, num_historia: c.num_historia, notas: c.notas,
        });
      }
      setClip(null); flash(clip.modo === "cortar" ? "Cita movida ✓" : "Cita pegada ✓"); cargar();
    } catch (e) { flash(errMsg(e), true); }
  }
  const tituloFecha = vista === "Día"
    ? fecha.toLocaleDateString("es-ES", { weekday: "long", day: "numeric", month: "long", year: "numeric" })
    : `${semana[0].toLocaleDateString("es-ES", { day: "numeric", month: "short" })} – ${semana[6].toLocaleDateString("es-ES", { day: "numeric", month: "short" })}`;
  const esFestivo = ref?.festivos?.includes(ymd(fecha));
  const agendaNombre = ref?.agendas?.find((a) => a.id === agendaSel)?.nombre ?? "Agenda";
  const mesAnio = fecha.toLocaleDateString("es-ES", { month: "long", year: "numeric" }).toUpperCase();
  // Píldora de fecha compacta GesdenOne: ‹ [Jue. 09/07/2020] › (día abreviado con punto + dd/mm/aaaa).
  const wd = fecha.toLocaleDateString("es-ES", { weekday: "short" });
  const fechaCorta = `${wd.charAt(0).toUpperCase() + wd.slice(1)}. ${pad(fecha.getDate())}/${pad(fecha.getMonth() + 1)}/${fecha.getFullYear()}`;
  const mesTexto = (() => { const t = fecha.toLocaleDateString("es-ES", { month: "long", year: "numeric" }); return t.charAt(0).toUpperCase() + t.slice(1); })();
  // ‹ › avanzan un día, una semana o un mes según la vista.
  const moverFecha = (n: number) => setFecha(vista === "Día" ? addDays(fecha, n) : vista === "Semana" ? addDays(fecha, 7 * n) : new Date(fecha.getFullYear(), fecha.getMonth() + n, 1));
  // Botón del panel de estados: abre/cierra; si estaba abierto el de cita, lo cierra y muestra estados.
  const alternarEstados = () => {
    if (sel) { setSel(null); setVerEstados(true); }
    else if (vista !== "Día") { setVista("Día"); setVerEstados(true); }
    else setVerEstados((v) => !v);
  };
  const estadosAbierto = !sel && verEstados && vista === "Día";

  if (!ref) return <div className="p-10 text-[#7f8c8d]">Cargando agenda…</div>;

  return (
    <div style={{ ...(clay ? TABLERO : {}), fontFamily: "'Segoe UI', Tahoma, Geneva, Verdana, sans-serif" }} className="flex flex-col h-full">
      {msg.t && <div className={`fixed top-12 right-6 z-50 px-4 py-2.5 rounded-sm text-[12px] font-semibold shadow-lg ${msg.e ? "bg-[#C026D3] text-white" : "bg-[#2DD9C3] text-[#1500A0]"}`}>{msg.t}</div>}

      {/* Barra superior: [AGENDA ONE = selector de agenda] [+ · iconos y filtros] … [buscador · día · herramientas · ampliación] */}
      <div className="flex-shrink-0 flex items-stretch h-[34.2px] uppercase text-[12px] text-[#333333] relative z-30 bg-white">
        {/* Título rosa = selector de agenda (muestra la agenda activa) */}
        <div className="relative min-w-24 flex-shrink-0 flex items-stretch bg-[#1500A0]">
          <button onClick={() => setDrop(drop === "agenda" ? "" : "agenda")} title="Elegir agenda" aria-haspopup="menu" aria-expanded={drop === "agenda"}
            className="px-3 flex items-center justify-center gap-1 cursor-pointer">
            <span className="font-semibold text-[16px] tracking-tighter leading-none text-[#FF66B2] whitespace-nowrap" style={{ textShadow: "0 0 6px rgba(255,102,178,0.35)" }}>
              {agendaNombre.toUpperCase()}
            </span>
            <ChevronDown className="w-3 h-3 text-[#FF66B2]" />
          </button>
          {drop === "agenda" && (
            <div className="absolute left-0 top-full mt-1 z-30 bg-white border border-[#e5e7eb] rounded-sm shadow-lg py-1 min-w-[180px] normal-case">
              <div className="px-3 py-1 text-[10px] uppercase tracking-wide text-[#9aa7c2] border-b border-[#eef1f6] mb-0.5">Agendas</div>
              {(ref.agendas ?? []).map((a) => (
                <button key={a.id} onClick={() => { setAgendaSel(a.id); setDrop(""); }}
                  className={`w-full flex items-center gap-2 px-3 py-1.5 text-[12px] hover:bg-[#E6EDFF] ${agendaSel === a.id ? "font-bold text-[#1500A0]" : "text-[#7f8c8d]"}`}>
                  {a.color ? <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: a.color }} /> : null}
                  {a.nombre}
                  {agendaSel === a.id ? <Check className="w-3 h-3 ml-auto text-[#1500A0]" /> : null}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Nueva cita (+) · panel de estados · vistas · inicio · filtros (Gabinetes, Doctores, Motivos, Anuladas, 3D) */}
        <div className="flex items-center gap-0.5 px-2 bg-white text-[#1500A0]">
          <button onClick={() => (sel ? setSel(null) : nuevaEn(fecha, horaSugerida()))} title="Crear una cita" aria-pressed={!!sel}
            className={`p-1 rounded-[4px] transition-all duration-150 active:scale-90 ${sel ? "bg-[#1500A0] text-white" : "hover:bg-[#e6edff]"}`}><CalendarPlus className="w-4 h-4" /></button>
          <button onClick={alternarEstados} title={estadosAbierto ? "Cerrar panel de estados" : "Panel de estados"} aria-pressed={estadosAbierto}
            className={`p-1 rounded-[4px] transition-all duration-150 active:scale-90 ${estadosAbierto ? "bg-[#1500A0] text-white" : "hover:bg-[#e6edff]"}`}><ListChecks className="w-4 h-4" /></button>
          {/* Vista: Día · Semana · Mes */}
          <div role="group" aria-label="Vista" className="flex items-center mx-1 rounded-[4px] border border-[#1500A0] overflow-hidden normal-case">
            {(["Día", "Semana", "Mes"] as const).map((v) => (
              <button key={v} onClick={() => setVista(v)} aria-pressed={vista === v} title={`Ver por ${v.toLowerCase()}`}
                className={`px-2.5 h-[22px] text-[11px] font-semibold transition-colors border-l border-[#1500A0] first:border-l-0 ${vista === v ? "bg-[#1500A0] text-white" : "text-[#1500A0] hover:bg-[#e6edff]"}`}>{v}</button>
            ))}
          </div>

          <span className="w-px h-4 bg-[#e5e7eb] mx-1" />

          {/* Gabinetes */}
          <div className="relative">
            <button onClick={() => setDrop(drop === "gab" ? "" : "gab")} aria-haspopup="menu" aria-expanded={drop === "gab"}
              title={gabsOcultos.size ? `Gabinetes (${gabsOcultos.size} ocultos)` : "Gabinetes"}
              className={`p-1 rounded-[4px] transition-all duration-150 active:scale-90 ${gabsOcultos.size ? "bg-[#1500A0] text-white" : "hover:bg-[#e6edff]"}`}><Columns3 className="w-4 h-4" /></button>
            {drop === "gab" && (
              <div className="absolute left-0 top-full mt-1 z-30 bg-white border border-[#e5e7eb] rounded-sm shadow-lg py-1 min-w-[170px] normal-case">
                <div className="px-3 py-1 text-[10px] uppercase tracking-wide text-[#9aa7c2] border-b border-[#eef1f6] mb-0.5">Gabinetes</div>
                {ref.gabinetes.map((g) => {
                  const on = !gabsOcultos.has(g.id);
                  return (
                    <button key={g.id} onClick={() => setGabsOcultos((s) => { const n = new Set(s); if (n.has(g.id)) n.delete(g.id); else n.add(g.id); return n; })}
                      className="w-full flex items-center gap-2 px-3 py-1.5 text-[12px] text-[#1500A0] hover:bg-[#E6EDFF]">
                      <span className={`w-3.5 h-3.5 rounded-sm border flex items-center justify-center ${on ? "bg-[#1500A0] border-[#1500A0]" : "border-[#cbd5e1]"}`}>{on && <Check className="w-2.5 h-2.5 text-white" />}</span>
                      {g.nombre}
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          {/* Doctores */}
          {ref?.colaboradores?.length ? (
            <div className="relative">
              <button onClick={() => setDrop(drop === "doc" ? "" : "doc")} aria-haspopup="menu" aria-expanded={drop === "doc"}
                title={docFiltro ? `Doctor: ${doctores.find((c) => c.id === docFiltro)?.nombre ?? ""}` : "Doctores"}
                className={`p-1 rounded-[4px] transition-all duration-150 active:scale-90 ${docFiltro ? "bg-[#1500A0] text-white" : "hover:bg-[#e6edff]"}`}><Stethoscope className="w-4 h-4" /></button>
              {drop === "doc" && (
                <div className="absolute left-0 top-full mt-1 z-30 bg-white border border-[#e5e7eb] rounded-sm shadow-lg py-1 min-w-[200px] w-max max-h-[360px] overflow-y-auto normal-case">
                  <div className="px-3 py-1 text-[10px] uppercase tracking-wide text-[#9aa7c2] border-b border-[#eef1f6] mb-0.5">Doctores</div>
                  <button onClick={() => { setDocFiltro(null); setDrop(""); }} className={`w-full text-left px-3 py-1.5 text-[12px] hover:bg-[#E6EDFF] ${!docFiltro ? "font-bold text-[#1500A0]" : "text-[#7f8c8d]"}`}>Todos</button>
                  {doctores.map((c) => (
                    <button key={c.id} onClick={() => { setDocFiltro(c.id); setDrop(""); }}
                      className={`w-full flex items-center gap-2 px-3 py-1.5 text-[12px] whitespace-nowrap hover:bg-[#E6EDFF] ${docFiltro === c.id ? "font-bold text-[#1500A0]" : "text-[#7f8c8d]"}`}>
                      <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: c.color || "#1500A0" }} />
                      {c.nombre}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ) : null}

          {/* Motivos de la visita */}
          {ref?.tipos_cita?.length ? (
            <div className="relative">
              <button onClick={() => setDrop(drop === "motivo" ? "" : "motivo")} aria-haspopup="menu" aria-expanded={drop === "motivo"}
                title={tipoFiltro ? `Motivo: ${ref.tipos_cita.find((t) => t.id === tipoFiltro)?.nombre ?? ""}` : "Motivos de la visita"}
                className={`p-1 rounded-[4px] transition-all duration-150 active:scale-90 ${tipoFiltro ? "bg-[#1500A0] text-white" : "hover:bg-[#e6edff]"}`}><Tags className="w-4 h-4" /></button>
              {drop === "motivo" && (
                <div className="absolute left-0 top-full mt-1 z-30 bg-white border border-[#e5e7eb] rounded-sm shadow-lg py-1 min-w-[220px] max-h-[300px] overflow-auto normal-case">
                  <div className="px-3 py-1 text-[10px] uppercase tracking-wide text-[#9aa7c2] border-b border-[#eef1f6] mb-0.5">Motivo de la visita</div>
                  <button onClick={() => { setTipoFiltro(null); setDrop(""); }} className={`w-full text-left px-3 py-1.5 text-[12px] hover:bg-[#E6EDFF] ${!tipoFiltro ? "font-bold text-[#1500A0]" : "text-[#7f8c8d]"}`}>Todos</button>
                  {ref.tipos_cita.map((t) => (
                    <button key={t.id} onClick={() => { setTipoFiltro(t.id); setDrop(""); }}
                      className={`w-full text-left px-3 py-1.5 text-[12px] hover:bg-[#E6EDFF] ${tipoFiltro === t.id ? "font-bold text-[#1500A0]" : "text-[#7f8c8d]"}`}>{t.nombre}</button>
                  ))}
                </div>
              )}
            </div>
          ) : null}

          {/* Anuladas · 3D */}
          <button onClick={() => setVerAnuladas((v) => !v)} aria-pressed={verAnuladas} title={verAnuladas ? "Ocultar anuladas" : "Ver anuladas"}
            className={`p-1 rounded-[4px] transition-all duration-150 active:scale-90 ${verAnuladas ? "bg-[#1500A0] text-white" : "hover:bg-[#e6edff]"}`}><Ban className="w-4 h-4" /></button>
          <button onClick={cambiarEstetica} aria-pressed={clay} title={clay ? "Vista clásica" : "Vista 3D"}
            className={`p-1 rounded-[4px] transition-all duration-150 active:scale-90 ${clay ? "bg-[#1500A0] text-white" : "hover:bg-[#e6edff]"}`}><Box className="w-4 h-4" /></button>
        </div>

        <div className="flex-1 bg-white" />

        {/* Derecha: buscador · día · herramientas · ampliación */}
        <div className="w-[240px] px-2 py-1 flex items-center bg-white">
         <div className="relative flex-1 flex items-center">
          <input placeholder="Buscar paciente…" className="w-full pl-8 pr-2 py-1.5 bg-[#FFFFFF] border border-transparent rounded-[4px] text-[12px] outline-none normal-case placeholder:text-slate-400 focus:ring-1 focus:ring-[#3388FF] focus:border-[#3388FF]" readOnly onClick={() => nuevaEn(fecha, slots.list[0] || "10:00")} />
          <svg className="absolute left-2.5 w-3.5 h-3.5 text-slate-400" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
         </div>
        </div>

        <div className="flex items-center gap-0.5 px-2 bg-white text-[#1500A0]">
          <button onClick={() => moverFecha(-1)} title="Anterior" className="p-1 rounded-[4px] transition-all duration-150 active:scale-90 hover:bg-[#e6edff]"><ChevronLeft className="w-4 h-4" /></button>
          <div className="relative">
            <button onClick={() => dateRef.current?.showPicker?.()}
              className="text-[13px] font-semibold px-2 text-[#1500A0] whitespace-nowrap min-w-[150px] text-center hover:bg-[#e6edff] rounded-[4px]">
              {vista === "Mes" ? mesTexto : fechaCorta}
            </button>
            <input ref={dateRef} type="date" value={ymd(fecha)} onChange={(e) => e.target.value && setFecha(new Date(e.target.value + "T00:00:00"))} className="absolute inset-0 w-full opacity-0 pointer-events-none" tabIndex={-1} />
          </div>
          <button onClick={() => moverFecha(1)} title="Siguiente" className="p-1 rounded-[4px] transition-all duration-150 active:scale-90 hover:bg-[#e6edff]"><ChevronRight className="w-4 h-4" /></button>
          <button onClick={() => setFecha(new Date())} className="ml-1 text-[11px] font-semibold px-2 py-1 rounded-[4px] border border-[#1500A0] text-[#1500A0] hover:bg-[#e6edff]">Hoy</button>
          {esFestivo && <span className="ml-1 text-[11px] font-semibold text-white bg-[#FF007F] px-2 py-0.5 rounded-[4px]">Festivo</span>}
        </div>

        <div className="flex items-center gap-0.5 px-2 bg-white text-[#1500A0]">
          <button onClick={() => router.push("/configuracion/clinica/agenda")} title="Herramientas: configuración de la agenda" className="p-1 rounded-[4px] transition-all duration-150 active:scale-90 hover:bg-[#e6edff]"><Settings className="w-4 h-4" /></button>
          <button onClick={() => { (document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen()).catch((e) => flash(errMsg(e), true)); }} title="Ampliar (pantalla completa)" className="p-1 rounded-[4px] transition-all duration-150 active:scale-90 hover:bg-[#e6edff]"><Maximize2 className="w-4 h-4" /></button>
        </div>
      </div>
      {/* Una sola línea bajo la barra, de lado a lado */}
      <div className="h-[2px] bg-[#1500A0] flex-shrink-0" />

      {/* Backdrop para cerrar los desplegables al clicar fuera */}
      {drop && <div className="fixed inset-0 z-20" onClick={() => setDrop("")} />}

      {/* Cuerpo: la franja azul de la barra sigue 14 px POR DETRÁS de los paneles (rasgo GesdenOne) */}
      <div className="flex-1 flex min-h-0 relative" style={clay ? undefined : { background: "#FFFFFF" }}>

      {/* Panel "Crear una cita" (GesdenOne): ocupa la columna izquierda mientras está abierto */}
      {sel && <CitaModal key={sel.id ?? "nueva"} draft={sel} ref_={ref} agendaId={agendaSel} onClose={() => setSel(null)} onSaved={(t) => { setSel(null); flash(t); cargar(); }} flash={flash} />}

      {/* Kanban lateral izquierdo (GesdenOne): 4 secciones de estado */}
      {estadosAbierto && (
        <aside className={`w-[340px] shrink-0 overflow-y-auto ${clay ? "bg-[#172890] rounded-sm" : "bg-white border-r border-[#E0E6ED]"}`}>
          {/* Mismo lenguaje que "Crear una cita": cabecera azul, margen 12px, cada estado como un campo con borde */}
          <div className="flex items-center justify-between px-3 bg-white border-b border-[#E0E6ED]" style={{ height: ALTO_CAB }}>
            <h2 className="text-[16px] text-[#1500A0]">Citas del día</h2>
            <span className="text-[12px] text-[#7f8c8d] tabular-nums">{citas.length} {citas.length === 1 ? "cita" : "citas"}</span>
          </div>
          <div className="p-3 flex flex-col gap-3">
          {[
            { label: "Planificado", codigo: "planificada", color: "#4EC6E5" },
            { label: "Sala de espera", codigo: "recepcion", color: "#2598EE" },
            { label: "En consulta", codigo: "consulta", color: "#8b5cf6" },
            { label: "Finalizado", codigo: "finalizada", color: "#1500A0" },
          ].map(({ label, codigo, color }) => {
            const estadoId = ref.estados.find((e) => e.codigo === codigo)?.id;
            const items = citas.filter((c) => estadoId != null ? c.estado_id === estadoId : false);
            return (
              <section key={codigo} aria-label={label}>
                <div className="flex items-center justify-between mb-1">
                  <span className={`flex items-center gap-1.5 text-[12px] ${clay ? "text-white" : "text-[#333]"}`}><span className="w-2 h-2 rounded-full" style={{ background: color }} />{label}</span>
                  <span className={`text-[12px] tabular-nums ${clay ? "text-white/80" : "text-[#7f8c8d]"}`}>{items.length}</span>
                </div>
                <div className="border border-[#D5DBE5] rounded-[4px] bg-white overflow-hidden">
                  {items.length === 0 ? (
                    <p className="h-[32px] flex items-center px-2 text-[13px] text-[#9aa7c2]">Sin citas</p>
                  ) : items.map((c) => {
                    const tipoCodigo = c.tipo_nombre ? c.tipo_nombre.slice(0, 4).toUpperCase() : "CITA";
                    return (
                      <div key={c.id} onClick={() => setSel({ ...c })}
                        className="flex items-center gap-2 h-[32px] px-2 border-b border-[#E0E6ED] last:border-b-0 hover:bg-[#E6EDFF] transition-colors cursor-pointer text-[13px]">
                        <span className="shrink-0 w-[48px] h-[20px] grid place-items-center rounded-[4px] text-[10px] font-semibold text-white" style={{ background: color }}>{tipoCodigo}</span>
                        <span className="tabular-nums text-[#1500A0] shrink-0">{c.hora}</span>
                        <span className="text-[#333] truncate flex-1">{c.nombre} {c.apellidos}</span>
                        <span className="shrink-0 text-[11px] text-[#7f8c8d]">
                          {ref.colaboradores.find((col) => col.id === c.colaborador_id)?.nombre?.slice(0, 3).toUpperCase() ?? ""}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </section>
            );
          })}
          </div>
        </aside>
      )}

      {/* Vista Mes: 6 semanas; cada día muestra sus primeras citas y al pulsarlo abre ese día */}
      {vista === "Mes" ? (
        <div className="flex-1 overflow-auto bg-white flex flex-col">
          <div className="grid grid-cols-7 sticky top-0 z-10 shrink-0" style={{ background: COL_HEADER_BG }}>
            {DIAS_CORTO.map((d) => <div key={d} className="grid place-items-center text-[12px] font-bold text-white" style={{ height: ALTO_CAB }}>{d}</div>)}
          </div>
          <div className="grid grid-cols-7 grid-rows-6 flex-1 border-l border-[#E0E6ED]">
            {mesDias.map((d) => {
              const k = ymd(d);
              const delDia = citas
                .filter((c) => c.fecha === k && (!docFiltro || c.colaborador_id === docFiltro) && (!tipoFiltro || c.tipo_cita_id === tipoFiltro))
                .sort((a, b) => toMin(a.hora) - toMin(b.hora));
              const fuera = d.getMonth() !== fecha.getMonth();
              const hoy = k === ymd(new Date());
              const festivo = ref.festivos?.includes(k);
              return (
                <button key={k} type="button" onClick={() => { setFecha(d); setVista("Día"); }} title={`Ver el ${d.toLocaleDateString("es-ES", { weekday: "long", day: "numeric", month: "long" })}`}
                  className={`min-h-[96px] p-1.5 flex flex-col gap-0.5 text-left border-r border-b border-[#E0E6ED] hover:bg-[#E6EDFF] transition-colors overflow-hidden ${fuera ? "opacity-40" : ""}`}>
                  <span className="flex items-center justify-between w-full">
                    <span className={`text-[12px] font-semibold w-6 h-6 grid place-items-center rounded-full ${hoy ? "bg-[#1500A0] text-white" : festivo ? "text-[#FF007F]" : "text-[#333]"}`}>{d.getDate()}</span>
                    {delDia.length > 0 && <span className="text-[11px] text-[#7f8c8d] tabular-nums">{delDia.length}</span>}
                  </span>
                  {delDia.slice(0, 3).map((c) => (
                    <span key={c.id} className="truncate text-[11px] text-[#333]"><span className="tabular-nums text-[#1500A0] mr-1">{c.hora}</span>{c.nombre} {c.apellidos}</span>
                  ))}
                  {delDia.length > 3 && <span className="text-[11px] font-semibold text-[#1500A0]">+{delDia.length - 3} más</span>}
                </button>
              );
            })}
          </div>
        </div>
      ) : (
      /* Rejilla — layout y estética GesdenOne (columnas con fondo pastel por doctor/gabinete) */
      <div ref={rejillaRef} className={`flex-1 overflow-auto ${clay ? "bg-[#1e2fa0] rounded-sm" : "bg-white"}`}>
        <div className={"relative flex w-full"}>
          {/* eje de horas */}
          <div className="sticky left-0 z-10 bg-[#FAFAFA] shrink-0" style={{ width: ANCHO_HORAS }}>
            <div className="sticky top-0 z-10 grid place-items-center" style={{ height: ALTO_CAB, background: COL_HEADER_BG }}>
              {/* Cuadradito azul de la esquina (GesdenOne) → salta a la hora actual de la rejilla */}
              <button type="button" title="Ir a la hora actual" onClick={() => { rejillaRef.current?.scrollTo({ top: Math.max((yAhora ?? 0) - 80, 0), behavior: "smooth" }); }}
                className="w-6 h-6 rounded-[4px] bg-[#013B82] text-white grid place-items-center hover:brightness-110 focus-visible:outline focus-visible:outline-2 focus-visible:outline-white cursor-pointer">
                <Clock className="w-3.5 h-3.5" />
              </button>
            </div>
            {slots.rows.map((r, i) => (
              <Fragment key={r.tipo === "pausa" ? `pa-${i}` : r.hora}>
                {i === insertRowIdx && <div style={{ height: PANEL_H }} className="bg-white border-b border-[#f0f2f5]" />}
                {r.tipo === "pausa" ? (
                  <div className="flex items-center justify-center" style={{ height: SLOT_H, background: PAUSA, opacity: 0.7, borderBottom: `1px solid ${LINEA_MEDIA}` }}>
                    <span className="text-[11px] text-[#5d5a4e]">Pausa</span>
                  </div>
                ) : (
                  <div className="flex items-start justify-center pt-1" style={{ height: SLOT_H, borderRight: `1px solid ${LINEA_MEDIA}`, borderBottom: `1px solid ${LINEA_CUARTO}` }}>
                    {/* GesdenOne: etiqueta solo en :00 y :30 — los cuartos van como línea punteada sin número */}
                    {r.hora.endsWith(":00") || r.hora.endsWith(":30")
                      ? <span className="tabular-nums text-[11px] font-semibold text-[#666]">{r.hora}</span>
                      : null}
                  </div>
                )}
              </Fragment>
            ))}
          </div>
          {/* columnas */}
          {cols.map((col, colIdx) => {
            const tint = COL_TINTS[colIdx % COL_TINTS.length];
            return (
            <div key={col.key} className={`relative flex-1 ${vista === "Semana" ? "min-w-[140px]" : "min-w-0"}`} style={{ borderLeft: `1px solid ${SEP_COLUMNA}` }}>
              {/* Header de columna estilo GesdenOne: fondo cyan, texto blanco bold */}
              <div className="sticky top-0 z-10 flex items-center justify-center gap-1.5 px-2.5 min-w-0" style={{ height: ALTO_CAB, background: COL_HEADER_BG, borderRight: "1px solid rgba(255,255,255,0.2)" }}>
                <span className="text-[13px] font-semibold text-white truncate shrink-0">{col.label}</span>
                {docDeGab(col.gabId) && <span className="text-[12px] text-white/85 truncate">{docDeGab(col.gabId)}</span>}
              </div>
              {/* celdas (clic = nueva) */}
              <div className="relative" style={{ height: slots.totalH + gridExtra }}>
                {slots.rows.map((r, i) => {
                  if (r.tipo === "pausa") return (
                    <div key={`pa-${i}`} className="absolute left-0 right-0 flex items-center justify-center pointer-events-none"
                      style={{ top: i * SLOT_H + off(i * SLOT_H), height: SLOT_H, background: PAUSA, opacity: 0.7 }}>
                      <span className="text-[11px] text-[#5d5a4e]">Pausa</span>
                    </div>
                  );
                  const h = r.hora;
                  const nd = noDisponible(col.date, h, col.gabId);
                  return (
                  <div key={h} onClick={() => nuevaEn(col.date, h, col.gabId)}
                    onContextMenu={(e) => { e.preventDefault(); if (nd) { setAviso(nd); return; } setMenu({ x: e.clientX, y: e.clientY, date: col.date, hora: h, gabId: col.gabId }); }}
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={(e) => { e.preventDefault(); const id = Number(e.dataTransfer.getData("text/plain")); if (id) moverCita(id, col.date, h, col.gabId); }}
                    title={nd || undefined}
                    className={`absolute left-0 right-0 ${nd ? "cursor-not-allowed" : "cursor-pointer hover:brightness-[0.97]"}`}
                    style={{ top: i * SLOT_H + off(i * SLOT_H), height: SLOT_H, borderBottom: `1px solid ${LINEA_CUARTO}`, background: nd ? (clay ? "#1a2580" : "#E9ECEF") : (clay ? "rgba(255,255,255,0.04)" : tint) }} />
                  );
                })}
                {/* citas (carriles para solapamientos) */}
                {(() => {
                  const cc = citasDeCol(col).filter((c) => c.hora);
                  const lay = layoutLanes(cc);
                  return cc.map((c) => {
                    const ln = lay.get(c.id) || { lane: 0, lanes: 1 };
                    const w = 100 / ln.lanes;
                    const solo = ln.lanes === 1;
                    const isAnulada = anuladaId != null && c.estado_id === anuladaId;
                    const bgCol = CITA_COLORS[(citaOrden.get(c.id) ?? 0) % CITA_COLORS.length];
                    const dark = CITA_DARK.has(bgCol);
                    const txt = dark ? "#FFFFFF" : "#1500A0";
                    const txt2 = dark ? "rgba(255,255,255,0.85)" : "#374151";
                    return (
                  <div key={c.id} draggable
                    onDragStart={(e) => e.dataTransfer.setData("text/plain", String(c.id))}
                    onContextMenu={(e) => { e.preventDefault(); e.stopPropagation(); setMenu({ x: e.clientX, y: e.clientY, cita: c }); }}
                    onClick={(e) => { e.stopPropagation(); setSel({ ...c }); }}
                    className={`absolute rounded-md px-2 py-1 overflow-hidden cursor-pointer z-10 ${isAnulada ? "line-through opacity-60" : ""}`}
                    style={{
                      top: topFor(c.hora) + 1 + off(topFor(c.hora)), height: Math.max(heightFor(c.hora, c.duracion_min), 26),
                      left: solo ? 4 : `calc(${w * ln.lane}% + 2px)`,
                      right: solo ? 4 : undefined, width: solo ? undefined : `calc(${w}% - 4px)`,
                      background: clay
                        ? `linear-gradient(180deg, rgba(255,255,255,.35) 0%, rgba(255,255,255,0) 55%, rgba(0,0,0,.06) 100%), ${isAnulada ? "#BDBDBD" : bgCol}`
                        : isAnulada ? "#BDBDBD" : bgCol,
                      border: "1px solid rgba(21,0,160,0.4)", boxShadow: clay ? "0 2px 6px rgba(0,0,0,0.18), inset 0 1px 0 rgba(255,255,255,0.4)" : "0 1px 2px rgba(0,0,0,0.08)",
                    }}>
                    <div className="flex items-center gap-1.5 text-[12px] leading-[1.2]" style={{ color: txt }}>
                      <span title={c.estado_nombre ?? undefined} className="shrink-0 inline-flex">
                        {(() => { const EI = (c.estado_id != null ? ESTADO_ICONO[c.estado_id] : null) || Circle; return <EI className="w-3.5 h-3.5" style={{ color: c.estado_color || txt }} />; })()}
                      </span>
                      {c.num_historia ? <span className="font-semibold shrink-0 text-[11px]" style={{ color: txt2 }}>#{c.num_historia}</span> : null}
                      <span className="font-semibold truncate">{`${c.nombre} ${c.apellidos}`.trim() || "—"}</span>
                      {c.tipo_nombre ? <span className="text-[11px] truncate min-w-0" style={{ color: txt2 }}>· {c.tipo_nombre}</span> : null}
                      <div className="ml-auto flex items-center gap-1.5 shrink-0">
                        {vista === "Día" && <button type="button" title={abierta === c.id ? "Cerrar consulta" : "Abrir consulta"} onClick={(e) => { e.stopPropagation(); setAbierta((a) => (a === c.id ? null : c.id)); }} className="hover:opacity-80" style={{ color: txt }}><ChevronDown className={`w-4 h-4 transition-transform ${abierta === c.id ? "rotate-180" : ""}`} /></button>}
                        {c.telefono ? <button type="button" title="Abrir conversación de WhatsApp" onClick={(e) => { e.stopPropagation(); router.push(`/comunicacion?tel=${encodeURIComponent(c.telefono!)}`); }} className="flex items-center gap-0.5 text-[11px] hover:underline cursor-pointer" style={{ color: txt2 }}><Phone className="w-2.5 h-2.5" />{c.telefono}</button> : null}
                        {c.paciente_id ? <button type="button" title="Abrir ficha del paciente" onClick={(e) => { e.stopPropagation(); router.push(`/pacientes/${c.paciente_id}/ficha`); }} className="hover:opacity-70" style={{ color: txt }}><IdCard className="w-3.5 h-3.5" /></button> : null}
                      </div>
                    </div>
                  </div>
                    );
                  });
                })()}
                {/* Línea de hora actual — rojo (--color-time-indicator del CSS pegado). */}
                {yAhora != null && ymd(col.date) === ymd(new Date()) && (
                  <div aria-hidden className="absolute left-0 right-0 z-[5] pointer-events-none" style={{ top: yAhora + off(yAhora) - 1 }}>
                    <div className="h-[2px] w-full" style={{ background: AHORA }} />
                    {colIdx === 0 && (
                      <span className="absolute rounded-full"
                        style={{ left: -4, top: -3, width: 8, height: 8, background: AHORA }} />
                    )}
                  </div>
                )}
              </div>
            </div>
          );})}
          {/* Cockpit desplegado a todo el ancho (empuja las citas de debajo por el gap insertado) */}
          {citaAbierta && expandBottom != null && (
            <div className="absolute z-30 bg-white border-y-2 border-[#1500A0] shadow-[0_6px_20px_rgba(21,0,160,0.15)] overflow-y-auto"
              style={{ left: ANCHO_HORAS, right: 0, top: ALTO_CAB + expandBottom, height: PANEL_H }}>
              <div ref={cockpitRef}>
                <CitaCockpit pid={citaAbierta.paciente_id} telefono={citaAbierta.telefono} nombre={`${citaAbierta.nombre} ${citaAbierta.apellidos}`.trim()} doctorId={citaAbierta.colaborador_id} />
              </div>
            </div>
          )}
        </div>
      </div>
      )}

      </div>

      {menu && (
        <div className="fixed inset-0 z-40" onClick={() => setMenu(null)} onContextMenu={(e) => { e.preventDefault(); setMenu(null); }}>
          <div className="absolute bg-white border border-[#e5e7eb] rounded-sm shadow-lg py-1 text-[12px] min-w-[160px] max-h-[85vh] overflow-y-auto" style={{ left: menu.x, top: menu.y }} onClick={(e) => e.stopPropagation()}>
            {menu.cita ? (
              <>
                {menu.cita.paciente_id && (
                  <button className="w-full text-left px-3 py-1.5 hover:bg-[#E6EDFF] flex items-center gap-1.5 font-semibold text-[#065AED] border-b border-[#f0f2f5]"
                    onClick={() => { router.push(`/pacientes/${menu.cita!.paciente_id}/ficha?modo=${modoDeCita(menu.cita!.tipo_nombre)}`); setMenu(null); }}>
                    <Stethoscope className="w-3.5 h-3.5 text-[#1ca0d1]" /> Abrir consulta
                  </button>
                )}
                <button className="w-full text-left px-3 py-1.5 hover:bg-[#E6EDFF]" onClick={() => { setSel({ ...menu.cita! }); setMenu(null); }}>Editar</button>
                {/* Cambio rápido de estado (sin abrir el modal) */}
                <div className="px-3 pt-1.5 pb-0.5 text-[10px] uppercase tracking-wide text-[#9aa7c2] border-t border-[#f0f2f5]">Cambiar estado</div>
                <div className="grid grid-cols-2 gap-0.5 px-1 pb-1 w-[236px]">
                  {(ref?.estados ?? []).map((es) => {
                    const EI = ESTADO_ICONO[es.id] || Circle;
                    const activo = menu.cita!.estado_id === es.id;
                    return (
                      <button key={es.id} title={es.nombre} onClick={() => { cambiarEstado(menu.cita!.id, es.id); setMenu(null); }}
                        className={`flex items-center gap-1.5 px-2 py-1 rounded-sm text-left ${activo ? "bg-[#FFFFFF]" : "hover:bg-[#E6EDFF]"}`}>
                        <EI className="w-3.5 h-3.5 shrink-0" style={{ color: es.color || "#64748b" }} />
                        <span className={`truncate text-[11px] ${activo ? "font-semibold text-[#1500A0]" : "text-[#33415c]"}`}>{es.nombre}</span>
                      </button>
                    );
                  })}
                </div>
                <button className="w-full text-left px-3 py-1.5 hover:bg-[#E6EDFF] flex items-center gap-1.5 border-t border-[#f0f2f5]"
                  onClick={() => { const id = menu.cita!.id; setMenu(null); imprimirJustificante(id).catch((e) => flash(errMsg(e), true)); }}>
                  <FileText className="w-3.5 h-3.5 text-[#1ca0d1]" /> Justificante de asistencia
                </button>
                <button className="w-full text-left px-3 py-1.5 hover:bg-[#E6EDFF]" onClick={() => { setClip({ cita: menu.cita!, modo: "copiar" }); setMenu(null); flash("Cita copiada — clic derecho en un hueco para pegar"); }}>Copiar</button>
                <button className="w-full text-left px-3 py-1.5 hover:bg-[#E6EDFF]" onClick={() => { setClip({ cita: menu.cita!, modo: "cortar" }); setMenu(null); flash("Cita cortada — clic derecho en un hueco para pegar"); }}>Cortar</button>
                <button className="w-full text-left px-3 py-1.5 hover:bg-[#E6EDFF] text-[#1500A0]" onClick={() => { anularCita(menu.cita!.id); setMenu(null); }}>Anular</button>
              </>
            ) : (
              <>
                <button className="w-full text-left px-3 py-1.5 hover:bg-[#E6EDFF]" onClick={() => { nuevaEn(menu.date!, menu.hora!, menu.gabId); setMenu(null); }}>Nueva cita aquí</button>
                {clip && <button className="w-full text-left px-3 py-1.5 hover:bg-[#E6EDFF] font-semibold text-[#065AED]" onClick={() => { pegar(menu.date!, menu.hora!, menu.gabId); setMenu(null); }}>Pegar {clip.modo === "cortar" ? "(mover)" : "(copia)"}</button>}
              </>
            )}
          </div>
        </div>
      )}

      {/* Emergente: no se puede citar en esta franja (festivo / cierre / bloqueo) */}
      {aviso && (
        <Modal
          title={<span className="flex items-center gap-2"><Ban className="w-5 h-5 shrink-0" />No se puede crear cita aquí</span>}
          onClose={() => setAviso(null)}
          size="sm"
          zIndex={60}
          footer={
            <ModalButton variant="primary" onClick={() => setAviso(null)}>Entendido</ModalButton>
          }
        >
          <ModalBody>
            <p className="text-[12px] text-[#374151] leading-relaxed">{aviso}</p>
          </ModalBody>
        </Modal>
      )}
    </div>
  );
}

function CitaModal({ draft, ref_, agendaId, onClose, onSaved, flash }: {
  draft: Draft; ref_: Ref; agendaId: number | null; onClose: () => void; onSaved: (t: string) => void; flash: (t: string, e?: boolean) => void;
}) {
  const [d, setD] = useState<Draft>(draft);
  // estados_cita.id es global, no por centro — se resuelve por código, nunca "el primero de la lista".
  const planificadaId = ref_.estados.find((e) => e.codigo === "planificada")?.id ?? ref_.estados[0]?.id ?? null;
  const s = (k: keyof Draft, v: unknown) => setD((p) => ({ ...p, [k]: v }));
  const esEdicion = !!d.id;
  const [buscar, setBuscar] = useState("");
  const [res, setRes] = useState<Pac[]>([]);
  useEffect(() => {
    if (buscar.trim().length < 2) { setRes([]); return; }
    const t = setTimeout(async () => {
      try { const r = await api.get<{ pacientes: Pac[] }>(`/agenda/pacientes/buscar?q=${encodeURIComponent(buscar.trim())}`); setRes(r.pacientes); } catch { setRes([]); }
    }, 250);
    return () => clearTimeout(t);
  }, [buscar]);
  const elegir = (p: Pac) => { setD((x) => ({ ...x, paciente_id: p.id, nombre: p.nombre, apellidos: p.apellidos, telefono: p.telefono || x.telefono, num_historia: p.num_historia })); setBuscar(""); setRes([]); };
  const manual = (k: keyof Draft, v: string) => setD((p) => ({ ...p, [k]: v, paciente_id: null }));

  // Duración por defecto del doctor para este tipo de cita (Config→Colaboradores→"Tiempos por tipo
  // de cita"). Solo en cita nueva: al elegir/cambiar doctor+tipo, sugiere su duración configurada.
  useEffect(() => {
    if (esEdicion || !d.colaborador_id || !d.tipo_cita_id) return;
    const m = ref_.duraciones?.find((x) => x.colaborador_id === d.colaborador_id && x.tipo_cita_id === d.tipo_cita_id);
    if (m) s("duracion_min", m.duracion_min);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [d.colaborador_id, d.tipo_cita_id]);

  // Plan de próxima cita que dejó el doctor (para recepción): se muestra y permite usar su duración.
  const [plan, setPlan] = useState<{ items: { tratamiento: string }[]; minutos: number } | null>(null);
  useEffect(() => {
    if (!d.paciente_id) { setPlan(null); return; }
    api.get<{ plan: { items: { tratamiento: string }[]; minutos: number } | null }>(`/pacientes/${d.paciente_id}/plan-proxima`)
      .then((r) => setPlan(r.plan)).catch(() => setPlan(null));
  }, [d.paciente_id]);

  async function guardar() {
    const body = {
      fecha: d.fecha, hora: d.hora, duracion_min: d.duracion_min ?? 30, agenda_id: agendaId,
      gabinete_id: d.gabinete_id ?? null, colaborador_id: d.colaborador_id ?? null,
      estado_id: d.estado_id ?? null, tipo_cita_id: d.tipo_cita_id ?? null,
      paciente_id: d.paciente_id ?? null, nombre: d.nombre ?? null, apellidos: d.apellidos ?? null,
      telefono_movil: d.telefono ?? null, num_historia: d.num_historia ?? null, notas: d.notas ?? null,
      email: d.email?.trim() || null,
    };
    try {
      if (esEdicion) await api.put(`/agenda/citas/${d.id}`, body);
      else await api.post("/agenda/citas", body);
      // Si el paciente tenía un plan del doctor, esta cita lo consume → marcarlo agendado.
      if (!esEdicion && d.paciente_id && plan && (plan.items?.length ?? 0) > 0) {
        try { await api.post(`/pacientes/${d.paciente_id}/plan-proxima/agendar`, {}); } catch { /* no bloquea la cita */ }
      }
      onSaved(esEdicion ? "Cita guardada ✓" : "Cita creada ✓");
    } catch (e) { flash(e instanceof Error ? e.message.replace(/.*→\s*\d+\s*/, "") : "Error", true); }
  }
  async function anular() {
    if (!d.id) return;
    try { await api.put(`/agenda/citas/${d.id}/anular`, {}); onSaved("Cita anulada ✓"); }
    catch (e) { flash(e instanceof Error ? e.message : "Error", true); }
  }

  const L = "text-[12px] text-[#333] block mb-1";
  const I = "w-full h-[32px] px-2 border border-[#D5DBE5] rounded-[4px] text-[13px] bg-white text-[#333] outline-none transition-[border-color,box-shadow] duration-150 hover:border-[#9aa7c2] focus:border-[#1500A0] focus:shadow-[0_0_0_3px_rgba(21,0,160,0.12)]";
  // Hora en dos cajas [11] : [00] (GesdenOne); se compone d.hora "HH:MM".
  const [hh, mm] = (d.hora || "10:00").split(":");
  const hStr = String(parseInt(hh || "0", 10) || 0).padStart(2, "0");
  const mStr = String(parseInt(mm || "0", 10) || 0).padStart(2, "0");
  const caja = (valor: string, max: number, esHoras: boolean) => (
    <input type="number" min={0} max={max} value={valor} aria-label={esHoras ? "Horas" : "Minutos"}
      onChange={(e) => {
        const p = e.target.value === "" ? 0 : Math.max(0, Math.min(max, Number(e.target.value)));
        s("hora", esHoras ? `${String(p).padStart(2, "0")}:${mStr}` : `${hStr}:${String(p).padStart(2, "0")}`);
      }}
      className="w-[64px] h-[32px] text-center text-[13px] border border-[#ccc] rounded-[4px] bg-white text-[#333] tabular-nums outline-none focus:border-[#1500A0]" />
  );
  // Motivos agrupados al estilo GesdenOne: Od. General / Urgencias / ATM / 1ª Visita.
  const gruposMotivo = (() => {
    const t = ref_.tipos_cita || [];
    const satelite = [
      { etiqueta: "Urgencias", rx: /urgenc/i },
      { etiqueta: "ATM", rx: /\batm|f[eé]rula/i },
      { etiqueta: "1ª Visita", rx: /1ª\s*visita|primera\s*visita|1a\s*visita/i },
    ].map((g) => ({ etiqueta: g.etiqueta, items: t.filter((x) => g.rx.test(x.nombre)) }));
    const tomados = new Set(satelite.flatMap((g) => g.items));
    return [{ etiqueta: "Od. General", items: t.filter((x) => !tomados.has(x)) }, ...satelite].filter((g) => g.items.length > 0);
  })();
  return (
    <aside className="w-[340px] shrink-0 bg-white border-r border-[#E0E6ED] overflow-y-auto animate-[msEntrar_.22s_cubic-bezier(.2,.8,.2,1)]">
      <style>{"@keyframes msEntrar{from{opacity:0;transform:translateX(-14px)}to{opacity:1;transform:none}}"}</style>
      <div className="flex items-center justify-between px-3 bg-white border-b border-[#E0E6ED]" style={{ height: ALTO_CAB }}>
        <h2 className="text-[16px] text-[#1500A0]">{esEdicion ? "Editar cita" : "Crear una cita"}</h2>
        <button type="button" onClick={onClose} title="Cerrar" className="p-1 rounded-[4px] text-[#666] hover:bg-[#E6EDFF]"><X className="w-4 h-4" /></button>
      </div>
      <div className="p-3 grid grid-cols-2 gap-x-6 gap-y-3">
        <div className="col-span-2 relative">
          <label className={L}>Buscar paciente {d.paciente_id ? <span className="text-[#1500A0] font-semibold">· ficha vinculada</span> : <span className="text-[#7f8c8d]">· o rellena los datos (sin ficha)</span>}</label>
          <input value={buscar} onChange={(e) => setBuscar(e.target.value)} placeholder="Nombre, apellidos o nº historia…" className={I} />
          {res.length > 0 && (
            <div className="absolute z-20 left-0 right-0 top-full mt-0.5 bg-white border border-[#BFE4F7] rounded-sm shadow-lg max-h-56 overflow-auto">
              {res.map((p) => (
                <button key={p.id} onClick={() => elegir(p)} className="w-full text-left px-3 py-1.5 text-[12px] hover:bg-[#E6EDFF] border-b border-[#f4f6f9]">
                  <b className="text-[#065AED]">{p.nombre} {p.apellidos}</b>
                  <span className="text-[#7f8c8d] ml-2">{p.num_historia ? `#${p.num_historia}` : ""} {p.telefono || ""}</span>
                </button>
              ))}
            </div>
          )}
        </div>
        <div><label className={L}>Nombre</label><input value={d.nombre || ""} onChange={(e) => manual("nombre", e.target.value)} className={I} /></div>
        <div><label className={L}>Apellidos</label><input value={d.apellidos || ""} onChange={(e) => manual("apellidos", e.target.value)} className={I} /></div>
        <div><label className={L}>Correo electrónico</label><input type="email" value={d.email || ""} onChange={(e) => s("email", e.target.value)} className={I} /></div>
        <div><label className={L}>Teléfono</label><input type="tel" value={d.telefono || ""} onChange={(e) => s("telefono", e.target.value)} className={I} /></div>
        <div className="col-span-2"><label className={L}>Fecha</label><input type="date" value={d.fecha || ""} onChange={(e) => s("fecha", e.target.value)} className={I} /></div>
        <div>
          <label className={L}>Hora</label>
          <div className="flex items-center gap-1.5">
            {caja(hStr, 23, true)}
            <span className="text-[15px] text-[#8a94a6] font-bold select-none">:</span>
            {caja(mStr, 59, false)}
          </div>
        </div>
        <div><label className={L}>Duración</label>
          <input type="number" min={5} max={480} step={5} value={d.duracion_min ?? 30} aria-label="Duración en minutos"
            onChange={(e) => s("duracion_min", Math.max(5, Math.min(480, Number(e.target.value) || 30)))} className={I} />
        </div>
        <div className="col-span-2"><label className={L}>Motivo de la visita</label>
          <select value={d.tipo_cita_id ?? ""} onChange={(e) => s("tipo_cita_id", e.target.value ? Number(e.target.value) : null)} className={I}>
            <option value="">-- Seleccione uno --</option>
            {gruposMotivo.map((g) => (
              <optgroup key={g.etiqueta} label={g.etiqueta}>
                {g.items.map((x) => <option key={x.id} value={x.id}>{x.nombre}</option>)}
              </optgroup>
            ))}
          </select>
        </div>
        <div><label className={L}>Doctor</label>
          <select value={d.colaborador_id ?? ""} onChange={(e) => s("colaborador_id", e.target.value ? Number(e.target.value) : null)} className={I}>
            <option value="">Sin doctor</option>
            {ref_.colaboradores.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}
          </select>
        </div>
        <div><label className={L}>Gabinete</label>
          <select value={d.gabinete_id ?? ""} onChange={(e) => s("gabinete_id", e.target.value ? Number(e.target.value) : null)} className={I}>
            <option value="">—</option>
            {ref_.gabinetes.map((g) => <option key={g.id} value={g.id}>{g.nombre}</option>)}
          </select>
        </div>
        {esEdicion && (
          <div className="col-span-2"><label className={L}>Estado</label>
            <select value={d.estado_id ?? planificadaId ?? ""} onChange={(e) => s("estado_id", Number(e.target.value))} className={I}>
              {ref_.estados.map((es) => <option key={es.id} value={es.id}>{es.nombre}</option>)}
            </select>
          </div>
        )}
        {plan && (plan.items?.length ?? 0) > 0 && (
          <div className="col-span-2 flex items-center gap-2 bg-[#FFFFFF] border border-[#b0dcea] rounded-sm px-3 py-2 text-[12px]">
            <CalendarClock className="w-4 h-4 text-[#1500A0] shrink-0" />
            <span className="text-[#1500A0] font-semibold shrink-0">Plan del doctor:</span>
            <span className="text-[#374151] truncate flex-1">{plan.items.map((i) => i.tratamiento).join(", ")} · ~{plan.minutos} min</span>
            <button type="button" onClick={() => s("duracion_min", plan.minutos)}
              className="shrink-0 px-2 py-0.5 rounded-sm text-[10px] font-bold uppercase bg-[#1500A0] text-white hover:brightness-110">Usar {plan.minutos} min</button>
          </div>
        )}
        <div className="col-span-2"><label className={L}>Observaciones</label><textarea rows={4} value={d.notas || ""} onChange={(e) => s("notas", e.target.value)} className={`${I} !h-auto py-1 resize-none`} /></div>
        {/* Aceptar / Cancelar a todo el ancho (GesdenOne), en azul y rosa corporativos en vez de verde y rojo */}
        <button type="button" onClick={guardar}
          className="h-[38px] rounded-[4px] bg-[#1500A0] text-white text-[15px] flex items-center justify-center gap-2 shadow-[0_3px_10px_rgba(21,0,160,0.28)] hover:brightness-125 hover:-translate-y-px active:translate-y-0 active:scale-[.98] transition">
          <Check className="w-4 h-4" strokeWidth={3} />Aceptar
        </button>
        <button type="button" onClick={onClose}
          className="h-[38px] rounded-[4px] bg-[#FF66B2] text-white text-[15px] flex items-center justify-center gap-2 shadow-[0_3px_10px_rgba(255,102,178,0.35)] hover:brightness-110 hover:-translate-y-px active:translate-y-0 active:scale-[.98] transition">
          <X className="w-4 h-4" strokeWidth={3} />Cancelar
        </button>
        {esEdicion && (
          <button type="button" onClick={anular}
            className="col-span-2 h-[32px] rounded-[4px] border border-[#1500A0] text-[#1500A0] text-[13px] flex items-center justify-center gap-2 hover:bg-[#E6EDFF]">
            <Ban className="w-4 h-4" />Anular cita
          </button>
        )}
      </div>
    </aside>
  );
}

