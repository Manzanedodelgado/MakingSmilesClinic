"use client";
/**
 * Config · Clínica · Colaboradores — fichas de los profesionales (tabla
 * `colaboradores`): identidad + económico/comisión + firma (upload→URL, sin
 * base64). Master-detail con estética idéntica al .37.
 */
import { useEffect, useRef, useState } from "react";
import { X, Users2, Save, Settings2, ImageIcon, Clock, CalendarClock, Plus, CalendarX, CalendarOff, Palmtree } from "lucide-react";
import { api, API_BASE } from "@/shared/lib/api";
import { ClinicalCard, SectionHeader, ClinicalButton, INPUT, LABEL, SELECT, EMPTY } from "@/shared/components";
import { type EstadoFiltro } from "../../_components/ListFilter";
import { errMsg } from "@/shared/lib/errores";

type Colab = {
  id: number; usuario_id?: number | null;
  // identidad LEÍDA del usuario (fuente única) — read-only aquí, se edita en Personal
  nombre: string; apellidos?: string | null; color?: string | null; tipo_contrato?: string | null;
  // propio del colaborador
  num_colegiado?: string | null; nif?: string | null; firma_url?: string | null;
  contrato_inicio?: string | null; contrato_fin?: string | null;
  factura_produccion: boolean; pct_produccion?: number | null;
  aplica_laboratorio: boolean; tpc_gastos?: number | null;
  aplica_irpf: boolean; irpf_pct?: number | null;
  ausencia_inicio?: string | null; ausencia_fin?: string | null;
  tratamientos_exentos?: number[]; precio_tratamiento_exento?: number | null;
  duraciones?: Dur[]; horarios?: Horario[]; activo: boolean;
};
type Trat = { id: number; codigo: string; nombre: string };
type Tipo = { id: number; nombre: string; color?: string | null };
type Dur = { tipo_cita_id: number; duracion_min: number };
type Horario = { id: number; dia_semana: number; hora_inicio: string; hora_fin: string; pausa_inicio?: string | null; pausa_fin?: string | null; gabinete_id?: number | null };
// Excepciones/Vacaciones del recurso (captura 7.10.47) — viven en bloqueos de agenda con motivo libre.
type Blq = { id: number; fecha_inicio: string; fecha_fin: string; motivo: string | null; colaborador_id: number | null; gabinete_id: number | null };
type Gab = { id: number; nombre: string };
type Draft = Partial<Colab>;

const DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"];
const HORAS = Array.from({ length: 48 }, (_, i) => `${String(Math.floor(i / 2)).padStart(2, "0")}:${i % 2 ? "30" : "00"}`);

const img = (u?: unknown) => (u ? `${API_BASE}${u}` : "");

export default function ColaboradoresPage() {
  const [lista, setLista] = useState<Colab[]>([]);
  const [trats, setTrats] = useState<Trat[]>([]);
  const [tipos, setTipos] = useState<Tipo[]>([]);
  const [gabinetes, setGabinetes] = useState<Gab[]>([]);
  const [fr, setFr] = useState({ dia_semana: "0", hora_inicio: "10:00", hora_fin: "14:00", pausa_inicio: "", pausa_fin: "", gabinete_id: "" });
  const [sel, setSel] = useState<Draft | null>(null);
  const [estado, setEstado] = useState<EstadoFiltro>("activos");
  const [msg, setMsg] = useState<{ t: string; e?: boolean }>({ t: "" });
  const firmaRef = useRef<HTMLInputElement>(null);

  const filtrada = lista.filter((c) => {
    if (estado === "activos" && !c.activo) return false;
    if (estado === "inactivos" && c.activo) return false;
    return true;
  });
  const flash = (t: string, e = false) => { setMsg({ t, e }); setTimeout(() => setMsg({ t: "" }), 3000); };

  async function load() {
    const x = await api.get<{ colaboradores: Colab[] }>("/configuracion/colaboradores");
    setLista(x.colaboradores);
  }
  useEffect(() => {
    load();
    api.get<{ tratamientos: Trat[] }>("/configuracion/tratamientos").then((x) => setTrats(x.tratamientos)).catch(() => {});
    api.get<{ tipos_cita: Tipo[] }>("/configuracion/tipos-cita").then((x) => setTipos(x.tipos_cita)).catch(() => {});
    api.get<{ gabinetes: Gab[] }>("/configuracion/gabinetes").then((x) => setGabinetes(x.gabinetes)).catch(() => {});
  }, []);

  const s = (k: keyof Draft, v: unknown) => setSel((p) => ({ ...(p as Draft), [k]: v }));

  // exentos (múltiples)
  const exentos = sel?.tratamientos_exentos ?? [];
  const addExento = (id: number) => { if (id && !exentos.includes(id)) s("tratamientos_exentos", [...exentos, id]); };
  const delExento = (id: number) => s("tratamientos_exentos", exentos.filter((x) => x !== id));
  // tiempos por tipo de cita (min) — se selecciona en el desplegable y se edita el tiempo
  const duraciones = sel?.duraciones ?? [];
  const addDur = (tid: number) => { if (tid && !duraciones.some((d) => d.tipo_cita_id === tid)) s("duraciones", [...duraciones, { tipo_cita_id: tid, duracion_min: 30 }]); };
  const setDurMin = (tid: number, val: string) => s("duraciones", duraciones.map((d) => d.tipo_cita_id === tid ? { ...d, duracion_min: val === "" ? 0 : Number(val) } : d));
  const delDur = (tid: number) => s("duraciones", duraciones.filter((d) => d.tipo_cita_id !== tid));
  const tipoOf = (tid: number) => tipos.find((t) => t.id === tid);

  // calendario/horario del doctor — persistencia inmediata vía endpoints de agenda
  const gabNombre = (id?: number | null) => (id ? gabinetes.find((g) => g.id === id)?.nombre || `#${id}` : "—");
  async function refreshHorarios() {
    const x = await api.get<{ colaboradores: Colab[] }>("/configuracion/colaboradores");
    setLista(x.colaboradores);
    const fresh = x.colaboradores.find((c) => c.id === sel?.id);
    if (fresh) setSel((p) => ({ ...(p as Draft), horarios: fresh.horarios }));
  }
  async function addFranja() {
    if (!sel?.id) return;
    // Turno partido: la pausa necesita inicio Y fin (o ninguno). Mañana = Desde→pausa, tarde = pausa→Hasta.
    const pausa = !!(fr.pausa_inicio && fr.pausa_fin);
    if ((fr.pausa_inicio || fr.pausa_fin) && !pausa) { flash("La pausa necesita hora de inicio y de fin", true); return; }
    try {
      await api.post("/configuracion/agenda/horarios", {
        colaborador_id: sel.id, dia_semana: Number(fr.dia_semana),
        hora_inicio: fr.hora_inicio, hora_fin: fr.hora_fin,
        pausa_inicio: pausa ? fr.pausa_inicio : null, pausa_fin: pausa ? fr.pausa_fin : null,
        gabinete_id: fr.gabinete_id ? Number(fr.gabinete_id) : null, activo: true,
      });
      flash("Franja añadida ✓"); refreshHorarios();
    } catch (e) { flash(errMsg(e), true); }
  }
  async function delFranja(id: number) {
    try { await api.del(`/configuracion/agenda/horarios/${id}`); flash("Franja borrada ✓"); refreshHorarios(); }
    catch (e) { flash(errMsg(e), true); }
  }

  // Excepciones y Vacaciones del recurso (GesdenOne "Horario del recurso" 7.10.47): bloqueos de agenda
  // por colaborador — motivo libre o "Vacaciones". Alta/borrado inmediato contra configuracion/agenda.
  const [blqs, setBlqs] = useState<Blq[]>([]);
  const [frEx, setFrEx] = useState({ motivo: "", inicio: "", fin: "" });
  const [virVac, setVirVac] = useState({ inicio: "", fin: "" });
  const deRecurso = (blqs || []).filter((b) => b.colaborador_id === sel?.id);
  const esVac = (b: Blq) => /vacac/i.test(b.motivo || "");
  async function refreshBloqueos() {
    try {
      const x = await api.get<{ bloqueos?: Blq[] }>("/configuracion/agenda");
      setBlqs(x.bloqueos || []);
    } catch { setBlqs([]); }
  }
  useEffect(() => { refreshBloqueos(); }, []);
  const YMD = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  async function addExcepcion() {
    if (!sel?.id) return;
    if (!frEx.inicio || !frEx.fin) { flash("La excepción necesita fecha/hora de inicio y de fin", true); return; }
    try {
      await api.post("/configuracion/agenda/bloqueos", {
        colaborador_id: sel.id, fecha_inicio: frEx.inicio, fecha_fin: frEx.fin,
        motivo: frEx.motivo.trim() || "Excepción",
      });
      setFrEx({ motivo: "", inicio: "", fin: "" });
      flash("Excepción añadida ✓"); refreshBloqueos();
    } catch (e) { flash(errMsg(e), true); }
  }
  async function addVacaciones() {
    if (!sel?.id) return;
    if (!virVac.inicio || !virVac.fin) { flash("Las vacaciones necesitan fecha de inicio y de fin", true); return; }
    try {
      await api.post("/configuracion/agenda/bloqueos", {
        colaborador_id: sel.id, fecha_inicio: `${virVac.inicio}T00:00`, fecha_fin: `${virVac.fin}T23:59`,
        motivo: "Vacaciones",
      });
      setVirVac({ inicio: "", fin: "" });
      flash("Vacaciones añadidas ✓"); refreshBloqueos();
    } catch (e) { flash(errMsg(e), true); }
  }
  async function delBlq(id: number) {
    try { await api.del(`/configuracion/agenda/bloqueos/${id}`); flash("Periodo borrado ✓"); refreshBloqueos(); }
    catch (e) { flash(errMsg(e), true); }
  }
  // Píldoras de día (Lun, Mié…) dentro de un periodo — como los badges "Días" de GesdenOne.
  const diasDe = (ini: string, fin: string) => {
    const out: string[] = [];
    const a = new Date(ini); const b = new Date(fin);
    if (isNaN(a.getTime()) || isNaN(b.getTime())) return out;
    for (const d = new Date(a); d <= b && out.length < 7; d.setDate(d.getDate() + 1))
      out.push(["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"][(d.getDay() + 6) % 7]);
    return out;
  };
  const lgPeriodo = (ini: string, fin: string) => {
    const f = (s: string, soloDia: boolean) => soloDia ? s.slice(0, 10).split("-").reverse().slice(0, 2).join("/") : s.slice(0, 16).replace("T", " ");
    return `${f(ini, false)} → ${f(fin, false)}`;
  };

  async function subirFirma(f?: File) {
    if (!f) return;
    try { const { url } = await api.upload("/uploads", f); s("firma_url", url); flash("Firma subida ✓"); }
    catch (e) { flash(errMsg(e), true); }
  }

  async function subirTalonario(colaboradorId?: number, f?: File) {
    if (!colaboradorId || !f) return;
    try {
      // Crear FormData y enviar archivo RAW al backend
      const formData = new FormData();
      formData.append('archivo', f);
      formData.append('colaborador_id', colaboradorId.toString());

      // Generar nombre del lote automático
      const fecha = new Date().toISOString().split('T')[0].replace(/-/g, '');
      const numeroLote = `TN-${fecha}-${Math.floor(Math.random() * 1000).toString().padStart(3, '0')}`;
      formData.append('numero_lote', numeroLote);

      // Enviar al backend (que parsea XML/CSV/XLSX)
      const res = await api.post<{ numeros_importados: number }>(`/configuracion/colaboradores/${colaboradorId}/talonario/importar`, formData);

      flash(`Talonario importado: ${(res as any).numeros_importados} números ✓`);
    } catch (e) {
      flash(errMsg(e), true);
    }
  }

  async function guardar() {
    if (!sel?.id) return;
    try {
      // Solo económico/profesional. Identidad (nombre/color/contrato) se edita en Personal.
      const body = {
        num_colegiado: sel.num_colegiado ?? null, nif: sel.nif ?? null, firma_url: sel.firma_url ?? null,
        contrato_inicio: sel.contrato_inicio || null, contrato_fin: sel.contrato_fin || null,
        factura_produccion: sel.factura_produccion ?? false, pct_produccion: sel.pct_produccion ?? null,
        aplica_laboratorio: sel.aplica_laboratorio ?? false, tpc_gastos: sel.tpc_gastos ?? null,
        aplica_irpf: sel.aplica_irpf ?? false, irpf_pct: sel.irpf_pct ?? null,
        ausencia_inicio: sel.ausencia_inicio || null, ausencia_fin: sel.ausencia_fin || null,
        tratamientos_exentos: sel.tratamientos_exentos ?? [],
        precio_tratamiento_exento: sel.precio_tratamiento_exento ?? null,
        duraciones: sel.duraciones ?? [],
        activo: sel.activo ?? true,
      };
      await api.put(`/configuracion/colaboradores/${sel.id}`, body);
      flash("Colaborador guardado ✓"); setSel(null); load();
    } catch (e) { flash(errMsg(e), true); }
  }

  return (
    <div className="min-h-full -m-5 p-5" style={{ background: "#E5DDD5" }}>
      {msg.t && (
        <div className={`fixed top-14 right-6 z-50 px-4 py-2.5 rounded-sm text-[12px] font-semibold shadow-lg ${msg.e ? "bg-[#C026D3] text-white" : "bg-[#2DD9C3] text-[#1500A0]"}`}>{msg.t}</div>
      )}
      {/* Selector desplegable */}
      <div className="flex items-center gap-2 mb-2.5 flex-wrap">
        <Users2 className="w-4 h-4 text-[#1500A0] shrink-0" />
        <select value={sel?.id ?? ""} onChange={(e) => { const id = Number(e.target.value); setSel(id ? { ...(lista.find((c) => c.id === id) as Colab) } : null); }} className={`${SELECT} max-w-xs`}>
          <option value="">— Selecciona un colaborador —</option>
          {filtrada.map((c) => <option key={c.id} value={c.id}>{c.nombre} {c.apellidos ?? ""}{c.activo ? "" : " · baja"}</option>)}
        </select>
        <select value={estado} onChange={(e) => setEstado(e.target.value as EstadoFiltro)} className={`${SELECT} max-w-[130px]`}>
          <option value="activos">Activos</option>
          <option value="inactivos">Bajas</option>
          <option value="todos">Todos</option>
        </select>
        <span className="text-[11px] text-[#7f8c8d]">{filtrada.length} {filtrada.length === 1 ? "colaborador" : "colaboradores"}</span>
        <span className="ml-auto text-[10px] text-[#7f8c8d]">Se dan de alta desde Personal</span>
      </div>

      {/* Ficha */}
      {!sel ? (
        <ClinicalCard className="!rounded-md"><div className="py-12 text-center"><span className={EMPTY}>Selecciona un colaborador en el desplegable</span></div></ClinicalCard>
          ) : (
            <div className="flex flex-col gap-2.5">
              <ClinicalCard className="!rounded-md">
                <SectionHeader
                  title={sel.nombre || "Nuevo colaborador"}
                  customIcon={<Users2 className="w-3.5 h-3.5 text-[#1500A0]" />}
                  action={
                    <div className="flex items-center gap-2">
                      <label className="flex items-center gap-1.5 text-[11px] font-semibold text-[#1500A0] cursor-pointer">
                        <input type="checkbox" checked={sel.activo ?? true} onChange={(e) => s("activo", e.target.checked)} className="accent-[#2DD9C3]" /> Activo
                      </label>
                      <ClinicalButton variant="secondary" size="sm" onClick={() => setSel(null)}>Cancelar</ClinicalButton>
                      <ClinicalButton variant="save" icon={Save} size="sm" onClick={guardar}>Guardar</ClinicalButton>
                    </div>
                  }
                />
                <div className="grid grid-cols-4 gap-3 items-end">
                  <div>
                    <label className={LABEL}>Nombre</label>
                    <input value={sel.nombre || ""} disabled className={`${INPUT} bg-[#FFFFFF] text-[#7f8c8d] cursor-not-allowed`} />
                  </div>
                  <div>
                    <label className={LABEL}>Apellidos</label>
                    <input value={sel.apellidos || ""} disabled className={`${INPUT} bg-[#FFFFFF] text-[#7f8c8d] cursor-not-allowed`} />
                  </div>
                  <div>
                    <label className={LABEL}>Talonario de recetas</label>
                    <input
                      type="file"
                      accept=".csv,.txt,.xml,.xls,.xlsx"
                      onChange={(e) => { subirTalonario(sel?.id, e.target.files?.[0]); e.target.value = ""; }}
                      className="block text-[12px] text-[#7f8c8d] file:mr-3 file:py-1 file:px-3 file:rounded-sm file:border-0 file:text-[11px] file:font-semibold file:bg-[#20BEAB] file:text-white hover:file:bg-[#1AA897] cursor-pointer"
                    />
                    <span className="text-[10px] text-[#7f8c8d] mt-1 block">XML, CSV, TXT: número, cve (verificación)</span>
                  </div>
                  <div className="flex items-end">
                    <span className="text-[10px] text-[#1AA897] bg-[#FFFFFF] border border-[#9FE6DB] rounded-sm px-2 py-1.5 font-semibold leading-tight">
                      Carga oficial de números del colegio
                    </span>
                  </div>
                </div>
                <div className="grid grid-cols-4 gap-3 mt-3 items-end">
                  <div><label className={LABEL}>Nº colegiado</label><input value={sel.num_colegiado || ""} onChange={(e) => s("num_colegiado", e.target.value)} className={`${INPUT} !rounded-md uppercase placeholder:normal-case`} /></div>
                  <div><label className={LABEL}>NIF</label><input value={sel.nif || ""} onChange={(e) => s("nif", e.target.value)} className={`${INPUT} !rounded-md uppercase placeholder:normal-case`} /></div>
                  {/* Firma */}
                  <div className="col-span-2">
                    <label className={LABEL}>Firma (documentos · recetas)</label>
                    <div className="flex items-center gap-3">
                      <div className="w-28 h-12 bg-white border border-[#e5e7eb] flex items-center justify-center overflow-hidden rounded-sm shadow-sm shrink-0">
                        {sel.firma_url ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={img(sel.firma_url)} alt="Firma" className="max-w-full max-h-full object-contain" />
                        ) : (
                          <ImageIcon className="w-5 h-5 text-[#7f8c8d]" />
                        )}
                      </div>
                      <input ref={firmaRef} type="file" accept="image/*" onChange={(e) => { subirFirma(e.target.files?.[0]); e.target.value = ""; }}
                        className="block text-[12px] text-[#7f8c8d] file:mr-3 file:py-1 file:px-3 file:rounded-sm file:border-0 file:text-[11px] file:font-semibold file:bg-[#2DD9C3] file:text-[#1500A0] hover:file:bg-[#20BEAB] cursor-pointer" />
                      {sel.firma_url && <button onClick={() => s("firma_url", "")} className="text-[11px] text-[#C026D3] hover:underline">Quitar</button>}
                    </div>
                  </div>
                </div>
              </ClinicalCard>

              {/* Económico */}
              <ClinicalCard className="!rounded-md">
                <SectionHeader title="Comisión & contrato" customIcon={<Settings2 className="w-3.5 h-3.5 text-[#1500A0]" />} />
                <div className="grid grid-cols-4 gap-3">
                  <div>
                    <label className={LABEL}>Tipo de contrato</label>
                    <input value={sel.tipo_contrato || "—"} disabled className={`${INPUT} bg-[#FFFFFF] text-[#7f8c8d] cursor-not-allowed`} />
                  </div>
                  <div><label className={LABEL}>% Producción</label><input type="number" value={sel.pct_produccion ?? ""} onChange={(e) => s("pct_produccion", e.target.value === "" ? null : Number(e.target.value))} className={`${INPUT} !rounded-md uppercase placeholder:normal-case`} /></div>
                  <div><label className={LABEL}>Contrato desde</label><input type="date" value={sel.contrato_inicio || ""} onChange={(e) => s("contrato_inicio", e.target.value)} className={`${INPUT} !rounded-md uppercase placeholder:normal-case`} /></div>
                  <div><label className={LABEL}>Contrato hasta</label><input type="date" value={sel.contrato_fin || ""} onChange={(e) => s("contrato_fin", e.target.value)} className={`${INPUT} !rounded-md uppercase placeholder:normal-case`} /></div>
                </div>
                <div className="grid grid-cols-4 gap-3 mt-3">
                  <div><label className={LABEL}>% IRPF</label><input type="number" disabled={!sel.aplica_irpf} value={sel.irpf_pct ?? ""} onChange={(e) => s("irpf_pct", e.target.value === "" ? null : Number(e.target.value))} className={`${INPUT} ${!sel.aplica_irpf ? "bg-[#FFFFFF] text-[#7f8c8d]" : ""}`} /></div>
                  <div><label className={LABEL}>% Gastos (lab)</label><input type="number" disabled={!sel.aplica_laboratorio} value={sel.tpc_gastos ?? ""} onChange={(e) => s("tpc_gastos", e.target.value === "" ? null : Number(e.target.value))} className={`${INPUT} ${!sel.aplica_laboratorio ? "bg-[#FFFFFF] text-[#7f8c8d]" : ""}`} /></div>
                </div>
                <div className="flex gap-3 flex-wrap mt-3">
                  <Check label="Factura producción (autónomo)" on={sel.factura_produccion ?? false} onChange={(v) => s("factura_produccion", v)} />
                  <Check label="Retención IRPF" on={sel.aplica_irpf ?? false} onChange={(v) => s("aplica_irpf", v)} />
                  <Check label="Descuenta laboratorio" on={sel.aplica_laboratorio ?? false} onChange={(v) => s("aplica_laboratorio", v)} />
                </div>
                <div className="grid grid-cols-4 gap-3 mt-3">
                  <div><label className={LABEL}>Ausencia desde</label><input type="date" value={sel.ausencia_inicio || ""} onChange={(e) => s("ausencia_inicio", e.target.value)} className={`${INPUT} !rounded-md uppercase placeholder:normal-case`} /></div>
                  <div><label className={LABEL}>Ausencia hasta</label><input type="date" value={sel.ausencia_fin || ""} onChange={(e) => s("ausencia_fin", e.target.value)} className={`${INPUT} !rounded-md uppercase placeholder:normal-case`} /></div>
                </div>
                <div className="grid grid-cols-4 gap-3 mt-3 items-start">
                  <div className="col-span-3">
                    <label className={LABEL}>Tratamientos exentos (sin comisión)</label>
                    <select value="" onChange={(e) => { addExento(Number(e.target.value)); e.target.value = ""; }} className={SELECT}>
                      <option value="">+ Añadir tratamiento…</option>
                      {trats.filter((t) => !exentos.includes(t.id)).map((t) => <option key={t.id} value={t.id}>{t.codigo} · {t.nombre}</option>)}
                    </select>
                    <div className="flex flex-wrap gap-1 mt-2">
                      {exentos.map((id) => {
                        const t = trats.find((x) => x.id === id);
                        return (
                          <span key={id} className="inline-flex items-center gap-1 bg-[#FFFFFF] border border-[#7dd3fc] text-[#0369a1] rounded-full px-2 py-0.5 text-[11px] font-semibold">
                            {t ? `${t.codigo} · ${t.nombre}` : `#${id}`}
                            <button onClick={() => delExento(id)}><X className="w-3 h-3" /></button>
                          </span>
                        );
                      })}
                      {exentos.length === 0 && <span className="text-[11px] text-slate-400 italic">Ninguno</span>}
                    </div>
                  </div>
                  <div><label className={LABEL}>Precio exento (€)</label><input type="number" step="0.01" value={sel.precio_tratamiento_exento ?? ""} onChange={(e) => s("precio_tratamiento_exento", e.target.value === "" ? null : Number(e.target.value))} className={`${INPUT} !rounded-md uppercase placeholder:normal-case`} /></div>
                </div>
              </ClinicalCard>

              {/* Tiempos por cita y Calendario — dos cajas al 50% */}
              <div className="grid grid-cols-2 gap-3 items-start">
              {/* Tiempos por tipo de cita — se selecciona en el desplegable y se edita el tiempo */}
              <ClinicalCard className="min-w-0 !rounded-md">
                <SectionHeader title="Tiempos por tipo de cita (min)" customIcon={<Clock className="w-3.5 h-3.5 text-[#1500A0]" />} />
                <select value="" onChange={(e) => { addDur(Number(e.target.value)); e.target.value = ""; }} className={SELECT}>
                  <option value="">+ Añadir tipo de cita…</option>
                  {tipos.filter((t) => !duraciones.some((d) => d.tipo_cita_id === t.id)).map((t) => <option key={t.id} value={t.id}>{t.nombre}</option>)}
                </select>
                <div className="flex flex-col gap-1.5 mt-2">
                  {duraciones.map((d) => {
                    const t = tipoOf(d.tipo_cita_id);
                    return (
                      <div key={d.tipo_cita_id} className="flex items-center gap-2 bg-[#FFFFFF] border border-[#e5e7eb] rounded-sm px-3 py-1.5">
                        <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: t?.color || "#cbd5e1" }} />
                        <span className="text-[12px] text-[#333] flex-1 truncate">{t?.nombre ?? `#${d.tipo_cita_id}`}</span>
                        <input type="number" min={0} step={15} value={d.duracion_min} onChange={(e) => setDurMin(d.tipo_cita_id, e.target.value)}
                          className="w-16 text-[11px] text-right text-[#1500A0] bg-white border border-[#e5e7eb] rounded-sm px-1 py-0.5" />
                        <span className="text-[10px] text-[#7f8c8d]">min</span>
                        <button onClick={() => delDur(d.tipo_cita_id)} className="text-[#C026D3]"><X className="w-3.5 h-3.5" /></button>
                      </div>
                    );
                  })}
                  {duraciones.length === 0 && <span className="text-[11px] text-slate-400 italic">Ninguno — selecciona un tipo de cita</span>}
                </div>
              </ClinicalCard>

              {/* Calendario y horario del doctor */}
              <ClinicalCard className="min-w-0 !rounded-md">
                <SectionHeader title="Calendario y horario" customIcon={<CalendarClock className="w-3.5 h-3.5 text-[#1500A0]" />} />
                <div className="grid grid-cols-[7rem_5rem_5rem_9.5rem_minmax(0,1fr)_auto] gap-2 items-end mb-3">
                  <div><label className={LABEL}>Día</label>
                    <select value={fr.dia_semana} onChange={(e) => setFr({ ...fr, dia_semana: e.target.value })} className={SELECT}>
                      {DIAS.map((d, i) => <option key={i} value={i}>{d}</option>)}
                    </select>
                  </div>
                  <div><label className={LABEL}>Desde</label>
                    <select value={fr.hora_inicio} onChange={(e) => setFr({ ...fr, hora_inicio: e.target.value })} className={SELECT}>{HORAS.map((h) => <option key={h} value={h}>{h}</option>)}</select>
                  </div>
                  <div><label className={LABEL}>Hasta</label>
                    <select value={fr.hora_fin} onChange={(e) => setFr({ ...fr, hora_fin: e.target.value })} className={SELECT}>{HORAS.map((h) => <option key={h} value={h}>{h}</option>)}</select>
                  </div>
                  {/* Turno partido: pausa opcional (mañana = Desde→pausa, tarde = pausa→Hasta) en UNA sola franja. */}
                  <div><label className={LABEL} title="Deja la jornada en dos tramos (turno partido) sin crear dos franjas">Pausa (opc.)</label>
                    <div className="flex items-center gap-1">
                      <select value={fr.pausa_inicio} onChange={(e) => setFr({ ...fr, pausa_inicio: e.target.value })} className={SELECT}>
                        <option value="">—</option>{HORAS.map((h) => <option key={h} value={h}>{h}</option>)}
                      </select>
                      <span className="text-[#7f8c8d] text-[11px]">–</span>
                      <select value={fr.pausa_fin} onChange={(e) => setFr({ ...fr, pausa_fin: e.target.value })} className={SELECT}>
                        <option value="">—</option>{HORAS.map((h) => <option key={h} value={h}>{h}</option>)}
                      </select>
                    </div>
                  </div>
                  <div><label className={LABEL}>Gabinete</label>
                    <select value={fr.gabinete_id} onChange={(e) => setFr({ ...fr, gabinete_id: e.target.value })} className={SELECT}>
                      <option value="">—</option>
                      {gabinetes.map((g) => <option key={g.id} value={g.id}>{g.nombre}</option>)}
                    </select>
                  </div>
                  <ClinicalButton variant="accent" icon={Plus} size="sm" onClick={addFranja}>Añadir</ClinicalButton>
                </div>
                <div className="flex flex-col gap-1">
                  {(sel.horarios ?? []).map((h) => (
                    <div key={h.id} className="grid grid-cols-[7rem_11rem_minmax(0,1fr)_auto] items-center gap-3 text-[12px] bg-[#FFFFFF] border border-[#e5e7eb] rounded-sm px-3 py-1.5">
                      <span className="text-[#1500A0] font-medium">{DIAS[h.dia_semana]}</span>
                      <span className="text-[#33415c] tabular-nums">{h.pausa_inicio && h.pausa_fin
                        ? `${h.hora_inicio}–${h.pausa_inicio} · ${h.pausa_fin}–${h.hora_fin}`
                        : `${h.hora_inicio}–${h.hora_fin}`}</span>
                      <span className="text-[#7f8c8d] truncate">Gab: {gabNombre(h.gabinete_id)}</span>
                      <button onClick={() => delFranja(h.id)} className="text-[#C026D3] justify-self-end"><X className="w-3.5 h-3.5" /></button>
                    </div>
                  ))}
                  {(sel.horarios ?? []).length === 0 && <span className="text-[11px] text-slate-400 italic">Sin horario definido</span>}
                </div>
              </ClinicalCard>

              {/* Excepciones del recurso (GesdenOne 7.10.47) */}
              <ClinicalCard className="min-w-0 !rounded-md">
                <SectionHeader title="Excepciones" customIcon={<CalendarX className="w-3.5 h-3.5 text-[#C026D3]" />} />
                <div className="grid grid-cols-[minmax(0,1fr)_10rem_10rem_auto] gap-2 items-end mb-3">
                  <div><label className={LABEL}>Motivo</label>
                    <input value={frEx.motivo} onChange={(e) => setFrEx({ ...frEx, motivo: e.target.value })} placeholder="Baja, formación causa judicial…" className={INPUT} />
                  </div>
                  <div><label className={LABEL}>Desde</label>
                    <input type="datetime-local" value={frEx.inicio} onChange={(e) => setFrEx({ ...frEx, inicio: e.target.value })} className={INPUT} />
                  </div>
                  <div><label className={LABEL}>Hasta</label>
                    <input type="datetime-local" value={frEx.fin} onChange={(e) => setFrEx({ ...frEx, fin: e.target.value })} className={INPUT} />
                  </div>
                  <ClinicalButton variant="accent" icon={Plus} size="sm" onClick={addExcepcion}>Añadir</ClinicalButton>
                </div>
                <div className="flex flex-col gap-1">
                  {deRecurso.filter((b) => !esVac(b)).map((b) => (
                    <div key={b.id} className="grid grid-cols-[minmax(0,1fr)_auto_11rem_auto] items-center gap-3 text-[12px] bg-[#FFFFFF] border border-[#e5e7eb] rounded-sm px-3 py-1.5">
                      <span className="text-[#33415c] truncate">{b.motivo || "Excepción"}</span>
                      <span className="hidden md:flex items-center gap-1">
                        {diasDe(b.fecha_inicio, b.fecha_fin).map((d, j) => (
                          <span key={j} className="px-1 py-0.5 rounded-sm text-[9px] font-semibold bg-[#20BEAB]/15 text-[#0F8C7D]">{d}</span>
                        ))}
                      </span>
                      <span className="text-[11px] text-[#7f8c8d] tabular-nums whitespace-nowrap">{lgPeriodo(b.fecha_inicio, b.fecha_fin)}</span>
                      <button onClick={() => delBlq(b.id)} title="Borrar periodo" className="text-[#C026D3] hover:opacity-75 justify-self-end"><X className="w-3.5 h-3.5" /></button>
                    </div>
                  ))}
                  {deRecurso.filter((b) => !esVac(b)).length === 0 && <span className="text-[11px] text-slate-400 italic">Sin excepciones — el horario vale todos los días</span>}
                </div>
              </ClinicalCard>

              {/* Vacaciones del recurso (GesdenOne 7.10.47) */}
              <ClinicalCard className="min-w-0 !rounded-md">
                <SectionHeader title="Vacaciones" customIcon={<Palmtree className="w-3.5 h-3.5 text-[#0F8C7D]" />} />
                <div className="grid grid-cols-[10rem_10rem_auto] gap-2 items-end mb-3 inline-grid w-fit">
                  <div><label className={LABEL}>Desde</label>
                    <input type="date" value={virVac.inicio} min={YMD(new Date())} onChange={(e) => setVirVac({ ...virVac, inicio: e.target.value, fin: e.target.value > virVac.fin ? e.target.value : virVac.fin })} className={INPUT} />
                  </div>
                  <div><label className={LABEL}>Hasta</label>
                    <input type="date" value={virVac.fin} min={virVac.inicio || YMD(new Date())} onChange={(e) => setVirVac({ ...virVac, fin: e.target.value })} className={INPUT} />
                  </div>
                  <ClinicalButton variant="accent" size="sm" onClick={addVacaciones}><CalendarOff className="w-4 h-4" />&nbsp;Añadir</ClinicalButton>
                </div>
                <div className="flex flex-col gap-1">
                  {deRecurso.filter(esVac).map((b) => (
                    <div key={b.id} className="grid grid-cols-[minmax(0,1fr)_auto_11rem_auto] items-center gap-3 text-[12px] bg-[#FFFFFF] border border-[#e5e7eb] rounded-sm px-3 py-1.5">
                      <span className="flex items-center gap-1.5 text-[#33415c] truncate"><Palmtree className="w-3.5 h-3.5 text-[#0F8C7D] shrink-0" />{b.motivo || "Vacaciones"}</span>
                      <span className="hidden md:flex items-center gap-1">
                        {diasDe(b.fecha_inicio, b.fecha_fin).map((d, j) => (
                          <span key={j} className="px-1 py-0.5 rounded-sm text-[9px] font-semibold bg-[#20BEAB]/15 text-[#0F8C7D]">{d}</span>
                        ))}
                      </span>
                      <span className="text-[11px] text-[#7f8c8d] tabular-nums whitespace-nowrap">{b.fecha_inicio.slice(5, 10).replace("-", "/")} → {b.fecha_fin.slice(5, 10).replace("-", "/")}</span>
                      <button onClick={() => delBlq(b.id)} title="Borrar periodo" className="text-[#C026D3] hover:opacity-75 justify-self-end"><X className="w-3.5 h-3.5" /></button>
                    </div>
                  ))}
                  {deRecurso.filter(esVac).length === 0 && <span className="text-[11px] text-slate-400 italic">Sin vacaciones registradas</span>}
                </div>
              </ClinicalCard>
              </div>
            </div>
          )}
    </div>
  );
}

function Check({ label, on, onChange }: { label: string; on: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center gap-2 cursor-pointer text-[11px] font-semibold text-[#1500A0] bg-[#FFFFFF] border border-[#e5e7eb] rounded-sm px-3 py-2">
      <input type="checkbox" checked={on} onChange={(e) => onChange(e.target.checked)} className="accent-[#2DD9C3] w-4 h-4" />
      {label}
    </label>
  );
}
