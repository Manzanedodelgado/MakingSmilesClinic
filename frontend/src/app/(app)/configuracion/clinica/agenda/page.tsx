"use client";
/**
 * Config · Clínica · Agenda — calco de GesdenOne (Uploads/Gesden One/Captura 2026-10-15 7.10.47).
 *   Cabecera azul AGENDA: selector de agenda + secciones Horarios · Agendas · Motivos · Estados.
 *   Horarios: Personal · Ubicación · Equipo | Horario del recurso · Excepciones · Vacaciones.
 *   Agendas, Motivos y Estados: misma gramática (tabla, lápiz/✕ en Acción, botón redondo + y formulario en línea).
 * Tablas reales: agendas · tipos_cita · estados_cita · gabinetes · colaborador_horarios · bloqueos_agenda.
 */
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { PlusCircle, PencilOff, XCircle, CalendarPlus, Check, X, Trash2 } from "lucide-react";
import { api } from "@/shared/lib/api";

type Agenda = { id: number; nombre: string; color?: string | null; intervalo_min?: number | null; vista_defecto?: string | null; orden?: number | null; activo: boolean };
type Tipo = { id: number; nombre: string; color?: string | null; agenda_id?: number | null; activo: boolean };
type Estado = { id: number; nombre: string; color?: string | null; agenda_id?: number | null; orden?: number | null; activo: boolean };
type Gab = { id: number; nombre: string; agenda_id?: number | null; activo: boolean };
type Colab = { id: number; nombre: string; color?: string | null; num_colegiado?: string | null; staff_tipo?: string | null; activo?: boolean };
type Horario = { id: number; colaborador_id: number; agenda_id?: number | null; gabinete_id?: number | null; dia_semana: number; hora_inicio: string; hora_fin: string; pausa_inicio?: string | null; pausa_fin?: string | null; activo: boolean };
type Blq = { id: number; colaborador_id: number | null; gabinete_id: number | null; fecha_inicio: string; fecha_fin: string; motivo: string | null };
type AgendaData = { agendas: Agenda[]; tipos_cita: Tipo[]; estados_cita: Estado[]; gabinetes: Gab[]; colaboradores: Colab[]; horarios: Horario[]; bloqueos: Blq[] };
type Recurso = { tipo: "personal"; id: number } | { tipo: "ubicacion"; id: number };

const S = (v: unknown) => (v == null ? "" : String(v));
function errMsg(e: unknown) {
  const raw = e instanceof Error ? e.message : String(e);
  const i = raw.indexOf("{");
  if (i >= 0) { try { const d = JSON.parse(raw.slice(i)).detail; if (typeof d === "string") return d; if (Array.isArray(d)) return d.map((x) => x.msg).filter(Boolean).join(" · "); } catch {} }
  return raw.replace(/\s*\{.*\}\s*$/, "") || "Error";
}

const DIAS = ["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"];
const HORAS = Array.from({ length: 96 }, (_, i) => `${String(Math.floor(i / 4)).padStart(2, "0")}:${String((i % 4) * 15).padStart(2, "0")}`);
const POR_PAGINA = 10;
const hoyYMD = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
// "IRENE GARCÍA DE LA FUENTE" → "Irene García de la Fuente"
const titulo = (s: string) => s.toLowerCase().replace(/(^|\s)(\p{L})/gu, (_m, a: string, l: string) => a + l.toUpperCase()).replace(/\b(De|Del|La|Las|Los|Y)\b(?=\s)/g, (w) => w.toLowerCase());
const fechaES = (iso: string) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}`;
const hms = (hhmm: string) => (hhmm ? `${hhmm.slice(0, 5)}:00` : "");                       // GesdenOne: 09:00:00
// Días de la semana que toca un periodo (máx. 7 píldoras), como la columna "Días" de GesdenOne.
function diasDe(ini: string, fin: string) {
  const a = new Date(ini.slice(0, 10) + "T12:00"), b = new Date(fin.slice(0, 10) + "T12:00");
  const out = new Set<number>();
  for (const d = new Date(a); d <= b && out.size < 7; d.setDate(d.getDate() + 1)) out.add((d.getDay() + 6) % 7);
  return [...out].sort((x, y) => x - y);
}
const esVac = (b: Blq) => /vacac/i.test(b.motivo || "");

// ── Medidas y colores de la captura ──
const AZUL = "#003CA3";        // franja de cabecera: azul de GesdenOne, muestreado de la captura
const CIAN = "#1E9BE8";        // botones redondos, casillas, pestañas inactivas, página activa
const VERDE = "#8DC63F";       // píldoras de días
const TH = "text-left font-normal text-[12px] text-[#333] px-[6px] py-[5px] border-b-2 border-[#dee2e6] whitespace-nowrap";
const TD = "px-[6px] py-[7px] text-[12px] text-[#555] border-b border-[#eceff1] whitespace-nowrap";
// Tablas de las tarjetas de la derecha (medidas de la captura: cabecera 36 + 2 de borde #D3D3D3, fila de 32 px).
const THT = "text-left font-normal text-[12px] leading-[16px] text-[#333] px-[6px] pt-[15px] pb-[5px] border-b-2 border-[#d3d3d3] whitespace-nowrap";
const TDT = "px-[6px] pt-[7px] pb-[7px] text-[12px] leading-[17px] text-[#555] border-b border-[#eceff1] whitespace-nowrap";
const CAMPO = "h-[30px] px-2 border border-[#ced4da] rounded-[3px] text-[12px] bg-white text-[#333] outline-none focus:border-[#80bdff] focus:shadow-[0_0_0_3px_rgba(0,123,255,0.18)]";
const TARJETA = "bg-white rounded-[3px] shadow-[0_3px_12px_rgba(0,0,0,0.12)] min-w-0";

function BotonRedondo({ onClick, title, icono: I = PlusCircle }: { onClick: () => void; title: string; icono?: typeof PlusCircle }) {
  return (
    <button type="button" onClick={onClick} title={title} aria-label={title}
      className="w-[46px] h-[46px] rounded-full text-white grid place-items-center shadow-[0_3px_8px_rgba(0,0,0,0.3)] hover:brightness-110 active:scale-95 transition"
      style={{ background: CIAN }}>
      <I className="w-[20px] h-[20px]" strokeWidth={1.75} />
    </button>
  );
}
function Casilla({ on, onClick, title }: { on: boolean; onClick?: () => void; title?: string }) {
  return (
    <button type="button" onClick={onClick} title={title} disabled={!onClick} aria-pressed={on}
      className={`w-[17px] h-[17px] rounded-[3px] grid place-items-center mx-auto ${on ? "text-white" : "bg-[#f1f3f5]"} ${onClick ? "cursor-pointer hover:brightness-110" : "cursor-default"}`}
      style={on ? { background: "#4AA8DC" } : undefined}>
      {on && <Check className="w-3 h-3" strokeWidth={3.5} />}
    </button>
  );
}
const PildoraDia = ({ d }: { d: number }) => <span className="px-[6px] py-[2px] rounded-[3px] text-[9px] leading-[12px] text-white" style={{ background: VERDE }}>{DIAS[d]}</span>;
function Acciones({ onEdit, onDel }: { onEdit?: () => void; onDel: () => void }) {
  return (
    <span className="flex items-center gap-2 h-[17px] text-[#b0bec5]">
      {onEdit && <button type="button" onClick={onEdit} title="Editar" className="hover:text-[#1E9BE8] transition-colors"><PencilOff className="w-[13px] h-[13px]" /></button>}
      <button type="button" onClick={onDel} title="Borrar" className="hover:text-[#FF007F] transition-colors"><XCircle className="w-[13px] h-[13px]" /></button>
    </span>
  );
}
function Botonera({ onOk, onCancel }: { onOk: () => void; onCancel: () => void }) {
  return (
    <div className="flex items-center gap-2">
      <button type="button" onClick={onOk} className="h-[30px] px-3 rounded-[3px] bg-[#1500A0] text-white text-[12px] inline-flex items-center gap-1.5 hover:brightness-125 transition"><Check className="w-3.5 h-3.5" />Aceptar</button>
      <button type="button" onClick={onCancel} className="h-[30px] px-3 rounded-[3px] bg-[#FF66B2] text-white text-[12px] inline-flex items-center gap-1.5 hover:brightness-110 transition"><X className="w-3.5 h-3.5" />Cancelar</button>
    </div>
  );
}
function Tarjeta({ titulo: t, extra, children }: { titulo: string; extra?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className={TARJETA}>
      <header className="flex items-center justify-between gap-2 px-[10px] pt-[6px] h-[33px] border-b border-[#e6e6e6]">
        <h2 className="text-[14.5px] text-[#333] font-normal">{t}</h2>{extra}
      </header>
      <div className="px-[12px] pb-[18px]">{children}</div>
    </section>
  );
}

export default function AgendaPage() {
  const router = useRouter();
  const [ad, setAd] = useState<AgendaData | null>(null);
  const [estados, setEstados] = useState<Estado[]>([]);
  const [agSel, setAgSel] = useState<number | null>(null);
  const [seccion, setSeccion] = useState<"horarios" | "agendas" | "motivos" | "estados">("horarios");
  const [msg, setMsg] = useState<{ t: string; e?: boolean }>({ t: "" });
  const flash = (t: string, e = false) => { setMsg({ t, e }); setTimeout(() => setMsg({ t: "" }), 3000); };

  const [pestana, setPestana] = useState<"personal" | "ubicacion" | "equipo">("personal");
  const [pagina, setPagina] = useState(0);
  const [rec, setRec] = useState<Recurso | null>(null);

  // Formularios en línea (se abren con los botones redondos)
  const vacioFr = { ids: [] as number[], dias: [] as number[], hora_inicio: "09:00", hora_fin: "14:00", pausa_inicio: "", pausa_fin: "", gabinete_id: "" };
  const [fr, setFr] = useState<typeof vacioFr | null>(null);
  const [frEx, setFrEx] = useState<{ motivo: string; inicio: string; fin: string } | null>(null);
  const [frVac, setFrVac] = useState<{ inicio: string; fin: string } | null>(null);
  const [verPasadas, setVerPasadas] = useState(false);

  // Formularios en línea de Agendas, Motivos y Estados (id = editar esa fila; sin id = alta)
  const [frAg, setFrAg] = useState<{ id?: number; nombre: string; color: string; intervalo_min: string; vista_defecto: string; activo: boolean } | null>(null);
  const [frTipo, setFrTipo] = useState<{ id?: number; nombre: string; color: string } | null>(null);
  const [frEst, setFrEst] = useState<{ id?: number; nombre: string; color: string; orden: string } | null>(null);
  useEffect(() => { setFrAg(null); setFrTipo(null); setFrEst(null); }, [seccion, agSel]);

  async function load() {
    const a = await api.get<AgendaData>("/configuracion/agenda");
    setAd(a); setEstados(a.estados_cita.map((x) => ({ ...x })));
    setAgSel((prev) => prev ?? a.agendas?.[0]?.id ?? null);
  }
  useEffect(() => { load().catch((e) => flash(errMsg(e), true)); }, []);
  const reload = (txt: string) => () => { flash(txt); load(); };
  const cerrarFormularios = () => { setFr(null); setFrEx(null); setFrVac(null); };

  // ── Recursos de la agenda ──
  const personal = useMemo(() => (ad?.colaboradores ?? [])
    .map((c) => ({ ...c, nombre: titulo(c.nombre) }))
    .sort((a, b) => a.nombre.localeCompare(b.nombre, "es")), [ad]);
  const gabs = useMemo(() => (ad?.gabinetes ?? []).filter((g) => g.agenda_id === agSel), [ad, agSel]);
  // Franjas de esta agenda (las que no tienen agenda valen para todas).
  const horariosAg = useMemo(() => (ad?.horarios ?? []).filter((h) => h.agenda_id == null || h.agenda_id === agSel), [ad, agSel]);
  const lista = pestana === "personal" ? personal : pestana === "ubicacion" ? gabs : [];
  const paginas = Math.max(1, Math.ceil(lista.length / POR_PAGINA));
  const visibles = lista.slice(pagina * POR_PAGINA, (pagina + 1) * POR_PAGINA);
  useEffect(() => { setPagina(0); }, [pestana, agSel]);
  // Selección por defecto: primer recurso de la pestaña.
  useEffect(() => {
    if (pestana === "personal" && (rec?.tipo !== "personal" || !personal.some((c) => c.id === rec.id))) setRec(personal[0] ? { tipo: "personal", id: personal[0].id } : null);
    if (pestana === "ubicacion" && (rec?.tipo !== "ubicacion" || !gabs.some((g) => g.id === rec.id))) setRec(gabs[0] ? { tipo: "ubicacion", id: gabs[0].id } : null);
    if (pestana === "equipo") setRec(null);
  }, [pestana, personal, gabs]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { cerrarFormularios(); }, [rec?.tipo, rec?.id]);

  const colabSel = rec?.tipo === "personal" ? personal.find((c) => c.id === rec.id) : undefined;
  const gabSel = rec?.tipo === "ubicacion" ? gabs.find((g) => g.id === rec.id) : undefined;
  const gabNombre = (id?: number | null) => (id ? ad?.gabinetes.find((g) => g.id === id)?.nombre ?? `#${id}` : "");
  const colNombre = (id?: number | null) => (id ? personal.find((c) => c.id === id)?.nombre ?? `#${id}` : "");

  // Horario del recurso: franjas iguales (mismas horas, pausa y gabinete) se agrupan en una fila con sus días.
  const filasHorario = useMemo(() => {
    const propias = horariosAg.filter((h) => colabSel ? h.colaborador_id === colabSel.id : gabSel ? h.gabinete_id === gabSel.id : false);
    const grupos = new Map<string, { ids: number[]; dias: number[]; h: Horario }>();
    for (const h of propias) {
      const k = [h.colaborador_id, h.hora_inicio, h.hora_fin, h.pausa_inicio ?? "", h.pausa_fin ?? "", h.gabinete_id ?? ""].join("|");
      const g = grupos.get(k) ?? { ids: [], dias: [], h };
      g.ids.push(h.id); g.dias.push(h.dia_semana); grupos.set(k, g);
    }
    return [...grupos.values()].map((g) => ({ ...g, dias: [...new Set(g.dias)].sort((a, b) => a - b) }))
      .sort((a, b) => a.h.hora_inicio.localeCompare(b.h.hora_inicio) || a.dias[0] - b.dias[0]);
  }, [horariosAg, colabSel, gabSel]);
  const describir = (h: Horario) => {
    const tramo = h.pausa_inicio && h.pausa_fin ? `partida ${h.pausa_inicio}–${h.pausa_fin}` : h.hora_inicio < "14:00" ? "mañana" : "tarde";
    const quien = colabSel ? gabNombre(h.gabinete_id) : colNombre(h.colaborador_id);
    return [tramo.charAt(0).toUpperCase() + tramo.slice(1), quien].filter(Boolean).join(" · ");
  };

  const bloqRecurso = useMemo(() => (ad?.bloqueos ?? []).filter((b) =>
    colabSel ? b.colaborador_id === colabSel.id : gabSel ? b.gabinete_id === gabSel.id && b.colaborador_id == null : false), [ad, colabSel, gabSel]);
  const hoy = hoyYMD();
  const excepciones = bloqRecurso.filter((b) => !esVac(b));
  const excPasadas = excepciones.filter((b) => b.fecha_fin.slice(0, 10) < hoy).length;
  const excVisibles = (verPasadas ? excepciones : excepciones.filter((b) => b.fecha_fin.slice(0, 10) >= hoy))
    .sort((a, b) => a.fecha_inicio.localeCompare(b.fecha_inicio));
  const vacaciones = bloqRecurso.filter(esVac).sort((a, b) => b.fecha_inicio.localeCompare(a.fecha_inicio));

  // ── Agenda y parámetros ──
  async function guardarAgenda() {
    if (!frAg) return;
    if (!frAg.nombre.trim()) { flash("Pon un nombre a la agenda", true); return; }
    const previa = frAg.id ? ad?.agendas.find((a) => a.id === frAg.id) : undefined;
    const cuerpo = {
      nombre: frAg.nombre.trim(), color: frAg.color, orden: previa?.orden ?? null, activo: frAg.activo,
      intervalo_min: frAg.intervalo_min === "" ? null : Number(frAg.intervalo_min), vista_defecto: frAg.vista_defecto,
    };
    try {
      if (frAg.id) await api.put(`/configuracion/agenda/agendas/${frAg.id}`, cuerpo);
      else await api.post("/configuracion/agenda/agendas", cuerpo);
      setFrAg(null); reload(frAg.id ? "Agenda guardada ✓" : "Agenda creada ✓")();
    } catch (e) { flash(errMsg(e), true); }
  }
  async function delAgenda(a: Agenda) {
    if (!confirm(`¿Borrar la agenda ${a.nombre}?`)) return;
    try { await api.del(`/configuracion/agenda/agendas/${a.id}`); if (agSel === a.id) setAgSel(null); reload("Agenda borrada ✓")(); }
    catch (e) { flash(errMsg(e), true); }
  }

  // ── Ubicación (gabinetes) ──
  async function addGab() { const n = prompt("Nombre del gabinete (p.ej. Dental Box 3):"); if (!n) return; try { await api.post("/configuracion/agenda/gabinetes", { nombre: n, agenda_id: agSel, activo: true }); reload("Gabinete añadido ✓")(); } catch (e) { flash(errMsg(e), true); } }
  async function toggleGab(g: Gab) { try { await api.put(`/configuracion/agenda/gabinetes/${g.id}`, { nombre: g.nombre, agenda_id: g.agenda_id, activo: !g.activo }); reload(g.activo ? "Gabinete deshabilitado ✓" : "Gabinete habilitado ✓")(); } catch (e) { flash(errMsg(e), true); } }
  async function delGab(g: Gab) { if (!confirm(`¿Borrar el gabinete ${g.nombre}?`)) return; try { await api.del(`/configuracion/agenda/gabinetes/${g.id}`); reload("Gabinete borrado ✓")(); } catch (e) { flash(errMsg(e), true); } }

  // ── Horario del recurso ──
  async function guardarFranja() {
    if (!fr || !colabSel) return;
    if (!fr.dias.length) { flash("Marca al menos un día", true); return; }
    if (fr.hora_fin <= fr.hora_inicio) { flash("La hora final debe ser posterior a la inicial", true); return; }
    const pausa = !!(fr.pausa_inicio && fr.pausa_fin);
    if ((fr.pausa_inicio || fr.pausa_fin) && !pausa) { flash("La pausa necesita hora de inicio y de fin", true); return; }
    try {
      // Editar = crear las franjas nuevas y después borrar las antiguas del grupo.
      for (const d of fr.dias) await api.post("/configuracion/agenda/horarios", {
        colaborador_id: colabSel.id, agenda_id: agSel, dia_semana: d,
        hora_inicio: fr.hora_inicio, hora_fin: fr.hora_fin,
        pausa_inicio: pausa ? fr.pausa_inicio : null, pausa_fin: pausa ? fr.pausa_fin : null,
        gabinete_id: fr.gabinete_id ? Number(fr.gabinete_id) : null, activo: true,
      });
      for (const id of fr.ids) await api.del(`/configuracion/agenda/horarios/${id}`);
      setFr(null); reload(fr.ids.length ? "Horario actualizado ✓" : "Horario añadido ✓")();
    } catch (e) { flash(errMsg(e), true); }
  }
  async function borrarFranjas(ids: number[]) {
    if (!confirm("¿Borrar este horario?")) return;
    try { for (const id of ids) await api.del(`/configuracion/agenda/horarios/${id}`); reload("Horario borrado ✓")(); }
    catch (e) { flash(errMsg(e), true); }
  }

  // ── Excepciones y vacaciones (bloqueos de agenda) ──
  async function guardarExcepcion() {
    if (!frEx) return;
    if (!frEx.inicio || !frEx.fin) { flash("La excepción necesita fecha y hora de inicio y de fin", true); return; }
    if (frEx.fin <= frEx.inicio) { flash("El final debe ser posterior al inicio", true); return; }
    try {
      await api.post("/configuracion/agenda/bloqueos", {
        colaborador_id: colabSel?.id ?? null, gabinete_id: gabSel?.id ?? null,
        fecha_inicio: frEx.inicio, fecha_fin: frEx.fin, motivo: frEx.motivo.trim() || "Excepción",
      });
      setFrEx(null); reload("Excepción añadida ✓")();
    } catch (e) { flash(errMsg(e), true); }
  }
  async function guardarVacaciones() {
    if (!frVac || !colabSel) return;
    if (!frVac.inicio || !frVac.fin) { flash("Las vacaciones necesitan fecha de inicio y de fin", true); return; }
    try {
      await api.post("/configuracion/agenda/bloqueos", {
        colaborador_id: colabSel.id, fecha_inicio: `${frVac.inicio}T00:00`, fecha_fin: `${frVac.fin}T23:59`, motivo: "Vacaciones",
      });
      setFrVac(null); reload("Vacaciones añadidas ✓")();
    } catch (e) { flash(errMsg(e), true); }
  }
  async function delBlq(id: number) {
    if (!confirm("¿Borrar este periodo?")) return;
    try { await api.del(`/configuracion/agenda/bloqueos/${id}`); reload("Periodo borrado ✓")(); }
    catch (e) { flash(errMsg(e), true); }
  }

  // ── Motivos de la visita (tipos de cita): catálogo del centro; "En esta agenda" = agenda_id ──
  async function alternarTipo(t: Tipo) {
    const dentro = t.agenda_id === agSel;
    try { await api.put(`/configuracion/agenda/tipos/${t.id}`, { nombre: t.nombre, color: t.color, agenda_id: dentro ? null : agSel, activo: t.activo }); reload(dentro ? "Motivo quitado de la agenda ✓" : "Motivo añadido a la agenda ✓")(); }
    catch (e) { flash(errMsg(e), true); }
  }
  async function guardarTipo() {
    if (!frTipo) return;
    if (!frTipo.nombre.trim()) { flash("Pon un nombre al motivo", true); return; }
    const previo = frTipo.id ? ad?.tipos_cita.find((t) => t.id === frTipo.id) : undefined;
    const cuerpo = { nombre: frTipo.nombre.trim(), color: frTipo.color, agenda_id: previo ? previo.agenda_id ?? null : agSel, activo: previo?.activo ?? true };
    try {
      if (frTipo.id) await api.put(`/configuracion/agenda/tipos/${frTipo.id}`, cuerpo);
      else await api.post("/configuracion/agenda/tipos", cuerpo);
      setFrTipo(null); reload(frTipo.id ? "Motivo guardado ✓" : "Motivo creado ✓")();
    } catch (e) { flash(errMsg(e), true); }
  }
  async function delTipo(t: Tipo) {
    if (!confirm(`¿Borrar el motivo ${t.nombre}?`)) return;
    try { await api.del(`/configuracion/agenda/tipos/${t.id}`); reload("Motivo borrado ✓")(); }
    catch (e) { flash(errMsg(e), true); }
  }

  // ── Estados de cita de la agenda ──
  async function guardarEstado() {
    if (!frEst) return;
    if (!frEst.nombre.trim()) { flash("Pon un nombre al estado", true); return; }
    const previo = frEst.id ? estados.find((x) => x.id === frEst.id) : undefined;
    const cuerpo = { nombre: frEst.nombre.trim(), color: frEst.color, agenda_id: previo ? previo.agenda_id ?? null : agSel,
      orden: frEst.orden === "" ? null : Number(frEst.orden), activo: previo?.activo ?? true };
    try {
      if (frEst.id) await api.put(`/configuracion/agenda/estados/${frEst.id}`, cuerpo);
      else await api.post("/configuracion/agenda/estados", cuerpo);
      setFrEst(null); reload(frEst.id ? "Estado guardado ✓" : "Estado creado ✓")();
    } catch (e) { flash(errMsg(e), true); }
  }
  async function delEstado(e: Estado) {
    if (!confirm(`¿Borrar el estado ${e.nombre}?`)) return;
    try { await api.del(`/configuracion/agenda/estados/${e.id}`); reload("Estado borrado ✓")(); }
    catch (er) { flash(errMsg(er), true); }
  }

  if (!ad) return <div className="p-10 flex items-center justify-center text-[#7f8c8d]">Cargando agenda…</div>;

  const estadosAg = estados.filter((e) => e.agenda_id === agSel).sort((a, b) => (a.orden ?? 0) - (b.orden ?? 0));
  const tiposOrden = [...ad.tipos_cita].sort((a, b) => Number(b.agenda_id === agSel) - Number(a.agenda_id === agSel) || a.nombre.localeCompare(b.nombre, "es"));
  const agendaNombre = ad.agendas.find((a) => a.id === agSel)?.nombre ?? "";
  const SECCIONES = [["horarios", "Horarios"], ["agendas", "Agendas"], ["motivos", "Motivos de la visita"], ["estados", "Estados de cita"]] as const;
  const Muestra = ({ c }: { c?: string | null }) => <span className="inline-block w-[14px] h-[14px] rounded-[3px] align-middle border border-black/10" style={{ background: c || "#ccc" }} />;

  return (
    <div className="relative flex-1 bg-[#EEF2F7] -mx-5 -mt-5 -mb-5 min-h-[calc(100%+40px)] pb-6">
      {msg.t && <div className={`fixed top-14 right-6 z-50 px-4 py-2.5 rounded-sm text-[12px] font-semibold shadow-lg ${msg.e ? "bg-[#C026D3] text-white" : "bg-[#2DD9C3] text-[#1500A0]"}`}>{msg.t}</div>}

      {/* Franja azul: cabecera + 16 px que siguen por detrás de las tarjetas (como en GesdenOne) */}
      <div className="absolute inset-x-0 top-0 h-[90px]" style={{ background: AZUL }} />

      <header className="relative flex items-center gap-3 h-[74px] px-[38px] text-white">
        <span className="text-[24px] tracking-[0.2px] mr-3">AGENDA</span>
        <select value={agSel ?? ""} onChange={(e) => setAgSel(Number(e.target.value))} aria-label="Agenda que se configura"
          className="h-[32px] w-[212px] px-2 rounded-[2px] text-[12px] text-white bg-[#2F6FE0] border-2 border-[#8FD3FE] outline-none">
          {ad.agendas.map((a) => <option key={a.id} value={a.id} className="text-[#333] bg-white">{a.nombre}</option>)}
        </select>
        <nav role="tablist" aria-label="Secciones" className="flex items-end h-full ml-6">
          {SECCIONES.map(([k, t]) => (
            <button key={k} type="button" role="tab" aria-selected={seccion === k} onClick={() => setSeccion(k)}
              className={`h-full px-4 text-[13px] border-b-[3px] transition-colors ${seccion === k ? "border-white text-white" : "border-transparent text-white/70 hover:text-white"}`}>{t}</button>
          ))}
        </nav>
      </header>

      {seccion === "horarios" && (
      <div className="relative grid grid-cols-1 xl:grid-cols-[445px_minmax(0,1fr)] gap-[30px] px-[25px] items-start">
        {/* ── Recursos ── */}
        <section className={`${TARJETA} px-[13px] pt-[9px] pb-[18px]`}>
          <div role="tablist" className="flex border-b border-[#dee2e6]">
            {([["personal", "Personal"], ["ubicacion", "Ubicación"], ["equipo", "Equipo"]] as const).map(([k, t]) => (
              <button key={k} type="button" role="tab" aria-selected={pestana === k} onClick={() => setPestana(k)}
                className={`px-[16px] py-[8px] text-[14px] -mb-px border rounded-t-[3px] ${pestana === k ? "border-[#dee2e6] border-b-white bg-white text-[#495057]" : "border-transparent hover:border-[#e9ecef]"}`}
                style={pestana === k ? undefined : { color: CIAN }}>{t}</button>
            ))}
          </div>
          <div className="overflow-x-auto mt-[16px]">
            <table className="w-full min-w-[418px] border-collapse">
              <thead><tr>
                <th className={`${TH} border-r border-r-[#eceff1]`}>Nombre</th><th className={`${TH} border-r border-r-[#eceff1]`}>Código</th><th className={`${TH} border-r border-r-[#eceff1]`}>Descripción</th>
                <th className={`${TH} border-r border-r-[#eceff1]`}>Habilitado</th><th className={TH}>Planificado</th>
              </tr></thead>
              <tbody>
                {pestana === "personal" && (visibles as typeof personal).map((c) => {
                  const on = rec?.tipo === "personal" && rec.id === c.id;
                  return (
                    <tr key={c.id} onClick={() => setRec({ tipo: "personal", id: c.id })} aria-selected={on}
                      className={`cursor-pointer ${on ? "bg-[#ececec]" : "hover:bg-[#f2f2f2]"}`}>
                      <td className={`${TD} border-r border-r-[#eceff1]`}>{c.nombre.split(" ")[0]}</td>
                      <td className={`${TD} border-r border-r-[#eceff1] text-center tabular-nums`}>{c.id}</td>
                      <td className={`${TD} border-r border-r-[#eceff1] max-w-[150px] truncate`} title={c.nombre}>{c.nombre}</td>
                      <td className={`${TD} border-r border-r-[#eceff1]`}><Casilla on={c.activo !== false} title="Se cambia en Config → Colaboradores" /></td>
                      <td className={TD}><Casilla on={horariosAg.some((h) => h.colaborador_id === c.id)} /></td>
                    </tr>
                  );
                })}
                {pestana === "ubicacion" && (visibles as Gab[]).map((g) => {
                  const on = rec?.tipo === "ubicacion" && rec.id === g.id;
                  return (
                    <tr key={g.id} onClick={() => setRec({ tipo: "ubicacion", id: g.id })} aria-selected={on}
                      className={`group cursor-pointer ${on ? "bg-[#ececec]" : "hover:bg-[#f2f2f2]"}`}>
                      <td className={`${TD} border-r border-r-[#eceff1]`}>{g.nombre}</td>
                      <td className={`${TD} border-r border-r-[#eceff1] text-center tabular-nums`}>{g.id}</td>
                      <td className={`${TD} border-r border-r-[#eceff1]`}>
                        <span className="inline-flex items-center gap-2">Gabinete
                          <button type="button" onClick={(e) => { e.stopPropagation(); delGab(g); }} title="Borrar gabinete" className="opacity-0 group-hover:opacity-100 text-[#b0bec5] hover:text-[#FF007F] transition"><Trash2 className="w-3.5 h-3.5" /></button>
                        </span>
                      </td>
                      <td className={`${TD} border-r border-r-[#eceff1]`} onClick={(e) => e.stopPropagation()}><Casilla on={g.activo} onClick={() => toggleGab(g)} title={g.activo ? "Deshabilitar" : "Habilitar"} /></td>
                      <td className={TD}><Casilla on={horariosAg.some((h) => h.gabinete_id === g.id)} /></td>
                    </tr>
                  );
                })}
                {visibles.length === 0 && (
                  <tr><td colSpan={5} className="px-2 py-6 text-center text-[12px] text-[#9aa7c2]">
                    {pestana === "equipo" ? "No hay equipos dados de alta" : pestana === "ubicacion" ? "Sin gabinetes en esta agenda" : "Sin personal activo"}
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
          <nav aria-label="Páginas" className="flex justify-center mt-[16px]">
            <div className="inline-flex border border-[#dee2e6] rounded-[3px] overflow-hidden text-[12px] text-[#6c757d]">
              {([["«", 0], ["‹", Math.max(0, pagina - 1)]] as const).map(([t, p]) => <button key={t} type="button" onClick={() => setPagina(p)} className="w-[31px] h-[32px] hover:bg-[#e9ecef] border-r border-[#dee2e6]">{t}</button>)}
              {Array.from({ length: paginas }, (_, i) => (
                <button key={i} type="button" onClick={() => setPagina(i)} aria-current={pagina === i}
                  className={`w-[31px] h-[32px] border-r border-[#dee2e6] ${pagina === i ? "text-white" : "hover:bg-[#e9ecef]"}`}
                  style={pagina === i ? { background: CIAN } : undefined}>{i + 1}</button>
              ))}
              {([["›", Math.min(paginas - 1, pagina + 1)], ["»", paginas - 1]] as const).map(([t, p], i) => <button key={t} type="button" onClick={() => setPagina(p)} className={`w-[31px] h-[32px] hover:bg-[#e9ecef] ${i === 0 ? "border-r border-[#dee2e6]" : ""}`}>{t}</button>)}
            </div>
          </nav>
          {pestana !== "equipo" && (
            <div className="mt-[18px] ml-[10px]">
              {pestana === "personal"
                ? <BotonRedondo onClick={() => router.push("/configuracion/clinica/personal")} title="Dar de alta personal (Config → Personal)" />
                : <BotonRedondo onClick={addGab} title="Nuevo gabinete" />}
            </div>
          )}
        </section>

        {/* ── Recurso seleccionado ── */}
        <div className="flex flex-col gap-[32px] min-w-0">
          <Tarjeta titulo="Horario del recurso">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[1080px] table-fixed border-collapse">
                <colgroup><col style={{ width: 170 }} /><col style={{ width: 80 }} /><col style={{ width: 80 }} /><col style={{ width: 300 }} /><col style={{ width: 290 }} /><col style={{ width: 75 }} /><col style={{ width: 80 }} /><col /></colgroup>
                <thead><tr>
                  <th className={THT}>Descripción</th><th className={THT}>Fecha de inicio</th><th className={THT}>Fecha final</th><th className={THT}>Días</th>
                  <th className={THT}>Servicios</th><th className={THT}>Hora de inicio</th><th className={THT}>Hora de finalización</th><th className={THT}>Acción</th>
                </tr></thead>
                <tbody>
                  {filasHorario.map(({ ids, dias, h }) => (
                    <tr key={ids.join("-")} className="hover:bg-[#f2f2f2]">
                      <td className={TDT}>{describir(h)}</td>
                      <td className={`${TDT} text-[#9aa7c2]`} title="El horario se repite cada semana sin fecha de inicio">—</td>
                      <td className={`${TDT} text-[#9aa7c2]`} title="El horario se repite cada semana sin fecha final">—</td>
                      <td className={TDT}><span className="flex gap-[6px]">{dias.map((d) => <PildoraDia key={d} d={d} />)}</span></td>
                      <td className={`${TDT} text-[#9aa7c2]`} title="Las franjas aún no se ligan a servicios">—</td>
                      <td className={`${TDT} tabular-nums`}>{hms(h.hora_inicio)}</td>
                      <td className={`${TDT} tabular-nums`}>{hms(h.hora_fin)}</td>
                      <td className={TDT}>
                        {colabSel
                          ? <Acciones onEdit={() => setFr({ ids, dias, hora_inicio: h.hora_inicio, hora_fin: h.hora_fin, pausa_inicio: S(h.pausa_inicio), pausa_fin: S(h.pausa_fin), gabinete_id: S(h.gabinete_id) })} onDel={() => borrarFranjas(ids)} />
                          : <span className="text-[11px] text-[#9aa7c2]">en su doctor</span>}
                      </td>
                    </tr>
                  ))}
                  {filasHorario.length === 0 && <tr><td colSpan={8} className="px-2 py-5 text-[12px] text-[#9aa7c2]">{!rec ? (pestana === "equipo" ? "Los equipos aún no se pueden dar de alta" : "Selecciona un recurso") : colabSel ? "Sin horario en esta agenda" : "Ningún doctor tiene horario en este gabinete"}</td></tr>}
                </tbody>
              </table>
            </div>
            {fr && colabSel && (
              <div className="mt-3 p-3 border border-[#dee2e6] rounded-[3px] flex flex-wrap items-end gap-3">
                <div><span className="block text-[11px] text-[#555] mb-1">Días</span>
                  <div className="flex gap-1">
                    {DIAS.map((d, i) => {
                      const on = fr.dias.includes(i);
                      return <button key={d} type="button" aria-pressed={on} onClick={() => setFr({ ...fr, dias: on ? fr.dias.filter((x) => x !== i) : [...fr.dias, i].sort() })}
                        className={`w-[34px] h-[30px] rounded-[3px] text-[11px] ${on ? "text-white" : "border border-[#ced4da] text-[#555]"}`} style={on ? { background: VERDE } : undefined}>{d}</button>;
                    })}
                  </div>
                </div>
                <label className="text-[11px] text-[#555]">Hora de inicio<br />
                  <select value={fr.hora_inicio} onChange={(e) => setFr({ ...fr, hora_inicio: e.target.value })} className={`${CAMPO} mt-1`}>{HORAS.map((x) => <option key={x}>{x}</option>)}</select></label>
                <label className="text-[11px] text-[#555]">Pausa (opcional)<br />
                  <span className="inline-flex items-center gap-1 mt-1">
                    <select value={fr.pausa_inicio} onChange={(e) => setFr({ ...fr, pausa_inicio: e.target.value })} className={CAMPO}><option value="">—</option>{HORAS.map((x) => <option key={x}>{x}</option>)}</select>–
                    <select value={fr.pausa_fin} onChange={(e) => setFr({ ...fr, pausa_fin: e.target.value })} className={CAMPO}><option value="">—</option>{HORAS.map((x) => <option key={x}>{x}</option>)}</select>
                  </span></label>
                <label className="text-[11px] text-[#555]">Hora de finalización<br />
                  <select value={fr.hora_fin} onChange={(e) => setFr({ ...fr, hora_fin: e.target.value })} className={`${CAMPO} mt-1`}>{HORAS.map((x) => <option key={x}>{x}</option>)}</select></label>
                <label className="text-[11px] text-[#555]">Gabinete<br />
                  <select value={fr.gabinete_id} onChange={(e) => setFr({ ...fr, gabinete_id: e.target.value })} className={`${CAMPO} mt-1`}>
                    <option value="">—</option>{gabs.map((g) => <option key={g.id} value={g.id}>{g.nombre}</option>)}
                  </select></label>
                <Botonera onOk={guardarFranja} onCancel={() => setFr(null)} />
              </div>
            )}
            {colabSel && !fr && <div className="mt-[26px] ml-[10px]"><BotonRedondo onClick={() => setFr({ ...vacioFr })} title="Añadir horario" /></div>}
          </Tarjeta>

          <Tarjeta titulo="Excepciones" extra={excPasadas > 0 ? (
            <button type="button" onClick={() => setVerPasadas((v) => !v)} className="text-[11px] hover:underline" style={{ color: CIAN }}>
              {verPasadas ? "Ocultar pasadas" : `Ver ${excPasadas} pasadas`}
            </button>) : undefined}>
            <div className="overflow-auto max-h-[320px]">
              <table className="w-full min-w-[1080px] table-fixed border-collapse">
                <colgroup><col style={{ width: 170 }} /><col style={{ width: 80 }} /><col style={{ width: 80 }} /><col style={{ width: 300 }} /><col style={{ width: 290 }} /><col style={{ width: 75 }} /><col style={{ width: 80 }} /><col /></colgroup>
                <thead className="sticky top-0 bg-white"><tr>
                  <th className={THT}>Descripción</th><th className={THT}>Fecha de inicio</th><th className={THT}>Fecha final</th><th className={THT}>Días</th>
                  <th className={THT}>Servicios</th><th className={THT}>Hora de inicio</th><th className={THT}>Hora de finalización</th><th className={THT}>Acción</th>
                </tr></thead>
                <tbody>
                  {excVisibles.map((b) => (
                    <tr key={b.id} className="hover:bg-[#f2f2f2]">
                      <td className={`${TDT} max-w-[200px] truncate`} title={b.motivo || ""}>{b.motivo || "Bloqueo"}</td>
                      <td className={`${TDT} tabular-nums`}>{fechaES(b.fecha_inicio)}</td>
                      <td className={`${TDT} tabular-nums`}>{fechaES(b.fecha_fin)}</td>
                      <td className={TDT}><span className="flex gap-[6px]">{diasDe(b.fecha_inicio, b.fecha_fin).map((d) => <PildoraDia key={d} d={d} />)}</span></td>
                      <td className={TDT} />
                      <td className={`${TDT} tabular-nums`}>{b.fecha_inicio.slice(11, 19) || "00:00:00"}</td>
                      <td className={`${TDT} tabular-nums`}>{b.fecha_fin.slice(11, 19) || "23:59:00"}</td>
                      <td className={TDT}><Acciones onDel={() => delBlq(b.id)} /></td>
                    </tr>
                  ))}
                  {excVisibles.length === 0 && rec && <tr><td colSpan={8} className="px-[6px] pt-[7px] pb-[7px] leading-[17px] text-[12px] text-[#9aa7c2]">Sin excepciones próximas</td></tr>}
                </tbody>
              </table>
            </div>
            {frEx && (
              <div className="mt-3 p-3 border border-[#dee2e6] rounded-[3px] flex flex-wrap items-end gap-3">
                <label className="text-[11px] text-[#555] flex-1 min-w-[180px]">Descripción<br />
                  <input value={frEx.motivo} onChange={(e) => setFrEx({ ...frEx, motivo: e.target.value })} placeholder="Baja, formación, juicio…" className={`${CAMPO} mt-1 w-full`} /></label>
                <label className="text-[11px] text-[#555]">Inicio<br />
                  <input type="datetime-local" value={frEx.inicio} onChange={(e) => setFrEx({ ...frEx, inicio: e.target.value, fin: frEx.fin && frEx.fin > e.target.value ? frEx.fin : e.target.value })} className={`${CAMPO} mt-1`} /></label>
                <label className="text-[11px] text-[#555]">Final<br />
                  <input type="datetime-local" value={frEx.fin} min={frEx.inicio} onChange={(e) => setFrEx({ ...frEx, fin: e.target.value })} className={`${CAMPO} mt-1`} /></label>
                <Botonera onOk={guardarExcepcion} onCancel={() => setFrEx(null)} />
              </div>
            )}
            {rec && !frEx && <div className="mt-[26px] ml-[10px]"><BotonRedondo onClick={() => setFrEx({ motivo: "", inicio: `${hoy}T09:00`, fin: `${hoy}T14:00` })} title="Añadir excepción" /></div>}
          </Tarjeta>

          <Tarjeta titulo="Vacaciones">
            <div className="overflow-auto max-h-[260px]">
              <table className="w-full border-collapse">
                <thead className="sticky top-0 bg-white"><tr><th className={THT}>Fecha</th><th className={`${THT} w-[80px]`} /></tr></thead>
                <tbody>
                  {vacaciones.map((b) => (
                    <tr key={b.id} className="hover:bg-[#f2f2f2]">
                      <td className={`${TDT} tabular-nums`}>{fechaES(b.fecha_inicio)} – {fechaES(b.fecha_fin)}</td>
                      <td className={TDT}><Acciones onDel={() => delBlq(b.id)} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {frVac && colabSel && (
              <div className="mt-3 p-3 border border-[#dee2e6] rounded-[3px] flex flex-wrap items-end gap-3">
                <label className="text-[11px] text-[#555]">Desde<br />
                  <input type="date" value={frVac.inicio} onChange={(e) => setFrVac({ inicio: e.target.value, fin: frVac.fin && frVac.fin >= e.target.value ? frVac.fin : e.target.value })} className={`${CAMPO} mt-1`} /></label>
                <label className="text-[11px] text-[#555]">Hasta<br />
                  <input type="date" value={frVac.fin} min={frVac.inicio} onChange={(e) => setFrVac({ ...frVac, fin: e.target.value })} className={`${CAMPO} mt-1`} /></label>
                <Botonera onOk={guardarVacaciones} onCancel={() => setFrVac(null)} />
              </div>
            )}
            {colabSel && !frVac && <div className="mt-[37px] ml-[10px]"><BotonRedondo onClick={() => setFrVac({ inicio: hoy, fin: hoy })} title="Añadir vacaciones" icono={CalendarPlus} /></div>}
          </Tarjeta>
        </div>
      </div>

      )}

      {seccion !== "horarios" && (
        <div className="relative px-[25px]">
          {seccion === "agendas" && (
            <Tarjeta titulo="Agendas">
              <div className="overflow-x-auto">
                <table className="w-full border-collapse">
                  <thead><tr>
                    <th className={THT}>Nombre</th><th className={THT}>Color</th><th className={THT}>Intervalo</th><th className={THT}>Vista por defecto</th>
                    <th className={`${THT} text-center`}>Habilitada</th><th className={THT}>Acción</th>
                  </tr></thead>
                  <tbody>
                    {ad.agendas.map((a) => frAg?.id === a.id ? null : (
                      <tr key={a.id} onClick={() => setAgSel(a.id)} className={`cursor-pointer ${a.id === agSel ? "bg-[#ececec]" : "hover:bg-[#f2f2f2]"}`}>
                        <td className={TDT}>{a.nombre}</td>
                        <td className={TDT}><Muestra c={a.color} /></td>
                        <td className={`${TDT} tabular-nums`}>{a.intervalo_min ? `${a.intervalo_min} minutos` : "—"}</td>
                        <td className={TDT}>{a.vista_defecto || "Semana"}</td>
                        <td className={TDT}><Casilla on={a.activo} /></td>
                        <td className={TDT} onClick={(e) => e.stopPropagation()}>
                          <Acciones onEdit={() => setFrAg({ id: a.id, nombre: a.nombre, color: a.color || "#065AED", intervalo_min: S(a.intervalo_min), vista_defecto: a.vista_defecto || "Semana", activo: a.activo })}
                            onDel={() => delAgenda(a)} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {frAg && (
                <div className="mt-3 p-3 border border-[#dee2e6] rounded-[3px] flex flex-wrap items-end gap-3">
                  <label className="text-[11px] text-[#555] flex-1 min-w-[180px]">Nombre<br />
                    <input autoFocus value={frAg.nombre} onChange={(e) => setFrAg({ ...frAg, nombre: e.target.value })} placeholder="p.ej. Odontología" className={`${CAMPO} mt-1 w-full`} /></label>
                  <label className="text-[11px] text-[#555]">Color<br />
                    <input type="color" value={frAg.color} onChange={(e) => setFrAg({ ...frAg, color: e.target.value })} className="mt-1 w-[42px] h-[30px] rounded-[3px] border border-[#ced4da] cursor-pointer" /></label>
                  <label className="text-[11px] text-[#555]">Intervalo<br />
                    <select value={frAg.intervalo_min} onChange={(e) => setFrAg({ ...frAg, intervalo_min: e.target.value })} className={`${CAMPO} mt-1`}>
                      <option value="">—</option>{[5, 10, 15, 20, 30, 60].map((m) => <option key={m} value={m}>{m} minutos</option>)}
                    </select></label>
                  <label className="text-[11px] text-[#555]">Vista por defecto<br />
                    <select value={frAg.vista_defecto} onChange={(e) => setFrAg({ ...frAg, vista_defecto: e.target.value })} className={`${CAMPO} mt-1`}>
                      {["Día", "Semana"].map((v) => <option key={v} value={v}>{v}</option>)}
                    </select></label>
                  <label className="text-[11px] text-[#555] flex flex-col items-center gap-[7px]">Habilitada
                    <Casilla on={frAg.activo} onClick={() => setFrAg({ ...frAg, activo: !frAg.activo })} /></label>
                  <Botonera onOk={guardarAgenda} onCancel={() => setFrAg(null)} />
                </div>
              )}
              {!frAg && <div className="mt-[26px] ml-[10px]"><BotonRedondo onClick={() => setFrAg({ nombre: "", color: "#065AED", intervalo_min: "15", vista_defecto: "Semana", activo: true })} title="Nueva agenda" /></div>}
            </Tarjeta>
          )}

          {seccion === "motivos" && (
            <Tarjeta titulo="Motivos de la visita" extra={<span className="text-[12px] text-[#7f8c8d]">Marca los que se ofrecen en <b className="font-semibold text-[#333]">{agendaNombre}</b></span>}>
              <div className="overflow-auto max-h-[60vh]">
                <table className="w-full border-collapse">
                  <thead className="sticky top-0 bg-white"><tr>
                    <th className={THT}>Nombre</th><th className={THT}>Color</th><th className={`${THT} text-center`}>En esta agenda</th><th className={THT}>Acción</th>
                  </tr></thead>
                  <tbody>
                    {tiposOrden.map((t) => frTipo?.id === t.id ? null : (
                      <tr key={t.id} className="hover:bg-[#f2f2f2]">
                        <td className={TDT}>{t.nombre}</td>
                        <td className={TDT}><Muestra c={t.color} /></td>
                        <td className={TDT}><Casilla on={t.agenda_id === agSel} onClick={() => alternarTipo(t)} title={t.agenda_id === agSel ? "Quitar de esta agenda" : "Añadir a esta agenda"} /></td>
                        <td className={TDT}><Acciones onEdit={() => setFrTipo({ id: t.id, nombre: t.nombre, color: t.color || "#065AED" })} onDel={() => delTipo(t)} /></td>
                      </tr>
                    ))}
                    {ad.tipos_cita.length === 0 && <tr><td colSpan={4} className="px-2 py-5 text-[12px] text-[#9aa7c2]">Sin motivos creados</td></tr>}
                  </tbody>
                </table>
              </div>
              {frTipo && (
                <div className="mt-3 p-3 border border-[#dee2e6] rounded-[3px] flex flex-wrap items-end gap-3">
                  <label className="text-[11px] text-[#555] flex-1 min-w-[200px]">Nombre<br />
                    <input autoFocus value={frTipo.nombre} onChange={(e) => setFrTipo({ ...frTipo, nombre: e.target.value })} onKeyDown={(e) => e.key === "Enter" && guardarTipo()} placeholder="p.ej. Revisión" className={`${CAMPO} mt-1 w-full`} /></label>
                  <label className="text-[11px] text-[#555]">Color<br />
                    <input type="color" value={frTipo.color} onChange={(e) => setFrTipo({ ...frTipo, color: e.target.value })} className="mt-1 w-[42px] h-[30px] rounded-[3px] border border-[#ced4da] cursor-pointer" /></label>
                  <Botonera onOk={guardarTipo} onCancel={() => setFrTipo(null)} />
                </div>
              )}
              {!frTipo && <div className="mt-[26px] ml-[10px]"><BotonRedondo onClick={() => setFrTipo({ nombre: "", color: "#065AED" })} title="Nuevo motivo" /></div>}
            </Tarjeta>
          )}

          {seccion === "estados" && (
            <Tarjeta titulo="Estados de cita" extra={<span className="text-[12px] text-[#7f8c8d]">Agenda <b className="font-semibold text-[#333]">{agendaNombre}</b></span>}>
              <div className="overflow-x-auto">
                <table className="w-full border-collapse">
                  <thead><tr>
                    <th className={`${THT} w-[70px]`}>Orden</th><th className={THT}>Nombre</th><th className={THT}>Color</th><th className={THT}>Acción</th>
                  </tr></thead>
                  <tbody>
                    {estadosAg.map((e) => frEst?.id === e.id ? null : (
                      <tr key={e.id} className="hover:bg-[#f2f2f2]">
                        <td className={`${TDT} tabular-nums`}>{e.orden ?? "—"}</td>
                        <td className={TDT}><span className="px-[8px] py-[2px] rounded-[3px] text-[11px] text-white" style={{ background: e.color || "#3498db" }}>{e.nombre}</span></td>
                        <td className={TDT}><Muestra c={e.color} /></td>
                        <td className={TDT}><Acciones onEdit={() => setFrEst({ id: e.id, nombre: e.nombre, color: e.color || "#3498db", orden: S(e.orden) })} onDel={() => delEstado(e)} /></td>
                      </tr>
                    ))}
                    {estadosAg.length === 0 && <tr><td colSpan={4} className="px-2 py-5 text-[12px] text-[#9aa7c2]">Sin estados en esta agenda</td></tr>}
                  </tbody>
                </table>
              </div>
              {frEst && (
                <div className="mt-3 p-3 border border-[#dee2e6] rounded-[3px] flex flex-wrap items-end gap-3">
                  <label className="text-[11px] text-[#555]">Orden<br />
                    <input type="number" min={1} value={frEst.orden} onChange={(e) => setFrEst({ ...frEst, orden: e.target.value })} className={`${CAMPO} mt-1 w-[70px]`} /></label>
                  <label className="text-[11px] text-[#555] flex-1 min-w-[200px]">Nombre<br />
                    <input autoFocus value={frEst.nombre} onChange={(e) => setFrEst({ ...frEst, nombre: e.target.value })} onKeyDown={(e) => e.key === "Enter" && guardarEstado()} placeholder="p.ej. En sala" className={`${CAMPO} mt-1 w-full`} /></label>
                  <label className="text-[11px] text-[#555]">Color<br />
                    <input type="color" value={frEst.color} onChange={(e) => setFrEst({ ...frEst, color: e.target.value })} className="mt-1 w-[42px] h-[30px] rounded-[3px] border border-[#ced4da] cursor-pointer" /></label>
                  <Botonera onOk={guardarEstado} onCancel={() => setFrEst(null)} />
                </div>
              )}
              {!frEst && <div className="mt-[26px] ml-[10px]"><BotonRedondo onClick={() => setFrEst({ nombre: "", color: "#3498db", orden: "" })} title="Nuevo estado" /></div>}
            </Tarjeta>
          )}
        </div>
      )}
    </div>
  );
}
