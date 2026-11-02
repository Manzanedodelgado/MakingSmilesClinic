"use client";
/**
 * Editor de informes — "tabla dinámica moderna" sobre la BD.
 *  • ORIGEN = VISTA curada (con campos calculados) → informe de una entidad.
 *  • ORIGEN = TABLA → informe MULTI-TABLA: navegas por tablas y vas AÑADIENDO columnas de
 *    varias; el motor las une solo por las claves foráneas reales.
 * Salida en modo LISTA (filtrada, ordenable, export CSV) o TABLA DINÁMICA (pivot de Excel,
 * sobre una sola tabla/vista). Todo con claves del catálogo/servidor → cero SQL en cliente.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { X, ArrowUp, ArrowDown, Play, Plus, Save, Download, Trash2, FilePlus2, List, Table2 } from "lucide-react";
import { informesService } from "../informesService";
import type {
  Catalogo, CampoCatalogo, TablaResumen, Filtro, Orden, Agregacion, ModoInforme,
  ResultadoInforme, ResultadoPivote, ColumnaResultado, InformeGuardadoResumen,
  MultiCol, MultiFiltro, MultiOrden, RelFiltro, RelacionCatalogo, OperadorMeta,
} from "../types";

const UNIDADES = [{ v: "dias", l: "días" }, { v: "meses", l: "meses" }, { v: "anios", l: "años" }];
const AGGS: { v: Agregacion; l: string }[] = [
  { v: "count", l: "Recuento" }, { v: "sum", l: "Suma" }, { v: "avg", l: "Media" },
  { v: "min", l: "Mínimo" }, { v: "max", l: "Máximo" },
];

const fmtNum = (v: unknown): string => {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  return Number.isFinite(n) ? n.toLocaleString("es-ES", { maximumFractionDigits: 2 }) : String(v);
};
const fmtCelda = (v: unknown, tipo: string): string => {
  if (v === null || v === undefined || v === "") return "—";
  if (tipo === "bool") return v === true ? "Sí" : v === false ? "No" : String(v);
  if (tipo === "fecha") { const s = String(v); const m = s.match(/^(\d{4})-(\d{2})-(\d{2})/); return m ? `${m[3]}/${m[2]}/${m[1]}` : s; }
  if (tipo === "numero") return fmtNum(v);
  return String(v);
};

export function InformesBuilder() {
  const [cat, setCat] = useState<Catalogo | null>(null);
  const [tablas, setTablas] = useState<TablaResumen[]>([]);
  const [selTipo, setSelTipo] = useState<"ent" | "tab">("ent");
  const [selKey, setSelKey] = useState("");
  const [campos, setCampos] = useState<CampoCatalogo[]>([]);
  const [porDefecto, setPorDefecto] = useState<string[]>([]);
  const [modo, setModo] = useState<ModoInforme>("lista");
  // LISTA (vista de una entidad)
  const [columnas, setColumnas] = useState<string[]>([]);
  const [orden, setOrden] = useState<Orden[]>([]);
  const [limite, setLimite] = useState(500);
  const [filtros, setFiltros] = useState<Filtro[]>([]);
  const [relaciones, setRelaciones] = useState<RelFiltro[]>([]);   // filtros TIENE / NO TIENE …
  // MULTI-TABLA (columnas de varias tablas)
  const [multiCols, setMultiCols] = useState<MultiCol[]>([]);
  const [multiFiltros, setMultiFiltros] = useState<MultiFiltro[]>([]);
  const [multiOrden, setMultiOrden] = useState<MultiOrden[]>([]);
  // PIVOTE
  const [filasP, setFilasP] = useState<string[]>([]);
  const [columnaPiv, setColumnaPiv] = useState("");
  const [medidaAgg, setMedidaAgg] = useState<Agregacion>("count");
  const [medidaCampo, setMedidaCampo] = useState("");
  const [resPiv, setResPiv] = useState<ResultadoPivote | null>(null);
  // resultado LISTA (vale para vista y multi)
  const [res, setRes] = useState<ResultadoInforme | null>(null);
  // común
  const [cargando, setCargando] = useState(false);
  const [guardados, setGuardados] = useState<InformeGuardadoResumen[]>([]);
  const [selId, setSelId] = useState<number | null>(null);
  const [nombre, setNombre] = useState("");
  const [msg, setMsg] = useState<{ t: string; err?: boolean }>({ t: "" });
  const [runToken, setRunToken] = useState(0);

  const flash = (t: string, err = false) => { setMsg({ t, err }); setTimeout(() => setMsg({ t: "" }), 3200); };
  const esTab = selTipo === "tab";
  const multiLista = esTab && modo === "lista";
  const campoByKey = useMemo(() => { const m: Record<string, CampoCatalogo> = {}; campos.forEach((c) => { m[c.key] = c; }); return m; }, [campos]);
  const camposNum = useMemo(() => campos.filter((c) => c.tipo === "numero"), [campos]);
  const entRelaciones = useMemo<RelacionCatalogo[]>(() => (selTipo === "ent" ? cat?.entidades.find((e) => e.key === selKey)?.relaciones || [] : []), [cat, selTipo, selKey]);
  // limpia subfiltros incompletos antes de enviar
  const relacionesValidas = useCallback(() => relaciones.map((r) => ({ ...r, subfiltros: r.subfiltros.filter((f) => { const m = cat?.operadores[f.op]; if (!m) return false; if (m.args >= 1 && (f.valor === "" || f.valor == null)) return false; if (m.args === 2 && (f.valor2 === "" || f.valor2 == null)) return false; return true; }) })), [relaciones, cat]);

  const cargarGuardados = useCallback(() => { informesService.guardados().then(setGuardados).catch(() => {}); }, []);
  useEffect(() => {
    Promise.all([informesService.catalogo(), informesService.tablas()]).then(([c, t]) => {
      setCat(c); setTablas(t.tablas);
      if (c.entidades[0]) cambiarOrigen("ent", c.entidades[0].key, c);
    }).catch(() => {});
    cargarGuardados();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Cambiar la tabla/vista que se está NAVEGANDO. En modo tabla las columnas ya añadidas
  // (multiCols) se conservan al saltar de tabla; en vista se resetea a esa entidad.
  async function cambiarOrigen(tipo: "ent" | "tab", key: string, catArg?: Catalogo) {
    const c = catArg || cat;
    setSelTipo(tipo); setSelKey(key);
    let cs: CampoCatalogo[] = [], pd: string[] = [];
    try {
      if (tipo === "ent") { const e = c?.entidades.find((x) => x.key === key); cs = e?.campos || []; pd = e?.por_defecto || []; }
      else { const r = await informesService.tablaCampos(key); cs = r.campos; pd = r.por_defecto; }
    } catch { flash("No se pudieron cargar las columnas", true); }
    setCampos(cs); setPorDefecto(pd);
    // config de una-sola-tabla (vista / pivote) siempre se refresca al origen nuevo
    setColumnas([...pd]); setFiltros([]); setOrden([]); setRelaciones([]);
    setFilasP(cs[0] ? [cs[0].key] : []); setColumnaPiv("");
    const num = cs.find((x) => x.tipo === "numero"); setMedidaCampo(num?.key ?? ""); setMedidaAgg("count");
    setRes(null); setResPiv(null);
    if (tipo === "ent") { setMultiCols([]); setMultiFiltros([]); setMultiOrden([]); }   // vista: fuera lo multi
  }
  function nuevo() {
    setSelId(null); setNombre("");
    setMultiCols([]); setMultiFiltros([]); setMultiOrden([]); setRelaciones([]);
    if (cat?.entidades[0]) cambiarOrigen("ent", cat.entidades[0].key);
  }

  // ── multi: añadir/quitar columnas de la tabla que navegas ──
  const enInforme = (tabla: string, campo: string) => multiCols.some((m) => m.tabla === tabla && m.campo === campo);
  function toggleMultiCol(c: CampoCatalogo) {
    setMultiCols((cs) => enInforme(selKey, c.key)
      ? cs.filter((m) => !(m.tabla === selKey && m.campo === c.key))
      : [...cs, { tabla: selKey, campo: c.key, tipo: c.tipo, label: c.label, operadores: c.operadores }]);
  }
  const quitarMultiCol = (m: MultiCol) => setMultiCols((cs) => cs.filter((x) => !(x.tabla === m.tabla && x.campo === m.campo)));

  // ── filtros vista (single) ──
  function addFiltro() { if (campos[0]) setFiltros((fs) => [...fs, { campo: campos[0].key, op: campos[0].operadores[0], valor: "", unidad: "anios" }]); }
  function updFiltro(i: number, patch: Partial<Filtro>) { setFiltros((fs) => fs.map((f, j) => (j === i ? { ...f, ...patch } : f))); }
  function cambiarCampoFiltro(i: number, k: string) { const c = campoByKey[k]; updFiltro(i, { campo: k, op: c.operadores[0], valor: "", valor2: "", unidad: "anios" }); }
  const filtrosValidos = useCallback(() => filtros.filter((f) => {
    const m = cat?.operadores[f.op]; if (!m) return false;
    if (m.args >= 1 && (f.valor === "" || f.valor == null)) return false;
    if (m.args === 2 && (f.valor2 === "" || f.valor2 == null)) return false;
    return true;
  }), [filtros, cat]);

  // ── filtros multi ──
  function addMultiFiltro() { const c = multiCols[0]; if (c) setMultiFiltros((fs) => [...fs, { tabla: c.tabla, campo: c.campo, op: c.operadores[0], valor: "", unidad: "anios" }]); }
  function updMultiFiltro(i: number, patch: Partial<MultiFiltro>) { setMultiFiltros((fs) => fs.map((f, j) => (j === i ? { ...f, ...patch } : f))); }
  function cambiarCampoMultiFiltro(i: number, tabla: string, campo: string) {
    const c = multiCols.find((m) => m.tabla === tabla && m.campo === campo);
    updMultiFiltro(i, { tabla, campo, op: c?.operadores[0] || "igual", valor: "", valor2: "", unidad: "anios" });
  }
  const multiFiltrosValidos = useCallback(() => multiFiltros.filter((f) => {
    const m = cat?.operadores[f.op]; if (!m) return false;
    if (m.args >= 1 && (f.valor === "" || f.valor == null)) return false;
    if (m.args === 2 && (f.valor2 === "" || f.valor2 == null)) return false;
    return true;
  }), [multiFiltros, cat]);

  // ── ejecutar ──
  const ejecutar = useCallback(async () => {
    if (!selKey && !multiCols.length) return;
    setCargando(true);
    try {
      if (modo === "pivote") {
        if (filasP.length === 0) { flash("Elige al menos un campo de fila", true); setCargando(false); return; }
        if (medidaAgg !== "count" && !medidaCampo) { flash("Elige el campo de la medida", true); setCargando(false); return; }
        const origen = esTab ? { tabla: selKey } : { entidad: selKey };
        setResPiv(await informesService.pivote({ ...origen, filas: filasP, columna: columnaPiv || null, medida: { agg: medidaAgg, campo: medidaAgg === "count" ? null : medidaCampo }, filtros: [] }));
      } else if (esTab) {
        if (multiCols.length === 0) { flash("Añade columnas de una o varias tablas", true); setCargando(false); return; }
        setRes(await informesService.multiEjecutar({
          columnas: multiCols.map((m) => ({ tabla: m.tabla, campo: m.campo })),
          filtros: multiFiltrosValidos(), orden: multiOrden, limite,
        }));
      } else {
        if (columnas.length === 0) { flash("Marca al menos una columna", true); setCargando(false); return; }
        setRes(await informesService.ejecutar({ entidad: selKey, columnas, filtros: filtrosValidos(), orden, relaciones: relacionesValidas(), limite }));
      }
    } catch (e) { flash(e instanceof Error ? e.message.replace(/.*→\s*\d+\s*/, "") : "Error al ejecutar", true); }
    finally { setCargando(false); }
  }, [selKey, esTab, modo, columnas, orden, limite, filtros, multiCols, multiFiltrosValidos, multiOrden, filasP, columnaPiv, medidaAgg, medidaCampo, filtrosValidos, relacionesValidas]);

  useEffect(() => { if (res) ejecutar(); /* eslint-disable-next-line */ }, [orden, multiOrden]);
  useEffect(() => { if (runToken) ejecutar(); /* eslint-disable-next-line */ }, [runToken]);

  function ordenarLista(col: ColumnaResultado) {
    if (esTab) {
      setMultiOrden((o) => (o[0]?.tabla === col.tabla && o[0]?.campo === col.campo
        ? [{ tabla: col.tabla!, campo: col.campo!, dir: o[0].dir === "asc" ? "desc" : "asc" }]
        : [{ tabla: col.tabla!, campo: col.campo!, dir: "asc" }]));
    } else {
      setOrden((o) => (o[0]?.campo === col.key ? [{ campo: col.key, dir: o[0].dir === "asc" ? "desc" : "asc" }] : [{ campo: col.key, dir: "asc" }]));
    }
  }
  const dirDe = (col: ColumnaResultado): "asc" | "desc" | null => {
    if (esTab) return multiOrden[0]?.tabla === col.tabla && multiOrden[0]?.campo === col.campo ? multiOrden[0].dir : null;
    return orden[0]?.campo === col.key ? orden[0].dir : null;
  };

  const totalesPivote = useMemo(() => {
    if (!resPiv) return null;
    const cols = resPiv.columnas; const colTot: Record<string, number> = {};
    if (cols) cols.forEach((c) => { colTot[c.valor] = resPiv.filas.reduce((s, f) => s + (Number(f.__celdas?.[c.valor]) || 0), 0); });
    const gran = cols ? Object.values(colTot).reduce((a, b) => a + b, 0) : resPiv.filas.reduce((s, f) => s + (Number(f.__val) || 0), 0);
    return { colTot, gran };
  }, [resPiv]);

  async function exportar() {
    try {
      if (modo === "pivote") { if (resPiv) exportarPivote(resPiv, totalesPivote, selKey); return; }
      if (esTab) await informesService.multiExportar({ columnas: multiCols.map((m) => ({ tabla: m.tabla, campo: m.campo })), filtros: multiFiltrosValidos(), orden: multiOrden, limite });
      else await informesService.exportar({ entidad: selKey, columnas, filtros: filtrosValidos(), orden, relaciones: relacionesValidas(), limite });
    } catch { flash("No se pudo exportar", true); }
  }

  async function guardar() {
    if (!nombre.trim()) { flash("Ponle un nombre al informe", true); return; }
    let definicion: Record<string, unknown>, entidad: string;
    if (modo === "pivote") {
      definicion = { modo: "pivote", sel: { tipo: selTipo, key: selKey }, filas: filasP, columna: columnaPiv || null, medida: { agg: medidaAgg, campo: medidaAgg === "count" ? null : medidaCampo }, filtros: [] };
      entidad = selKey;
    } else if (esTab) {
      definicion = { modo: "multi", sel: { tipo: "multi", key: selKey }, multiCols, multiFiltros, multiOrden, limite };
      entidad = "multi";
    } else {
      definicion = { modo: "lista", sel: { tipo: "ent", key: selKey }, columnas, filtros, orden, relaciones, limite };
      entidad = selKey;
    }
    try {
      if (selId) { await informesService.actualizar(selId, { nombre: nombre.trim(), entidad, definicion }); flash("Informe actualizado ✓"); }
      else { const r = await informesService.crear({ nombre: nombre.trim(), entidad, definicion }); setSelId(r.id); flash("Informe guardado ✓"); }
      cargarGuardados();
    } catch { flash("No se pudo guardar", true); }
  }
  async function abrir(id: number) {
    try {
      const inf = await informesService.obtener(id);
      const d = inf.definicion || {};
      const m: ModoInforme = d.modo === "pivote" ? "pivote" : "lista";
      setNombre(inf.nombre); setSelId(inf.id); setModo(m); setRes(null); setResPiv(null);
      if (d.sel?.tipo === "multi") {
        const mcols = (d as { multiCols?: MultiCol[] }).multiCols || [];
        const browse = mcols[0]?.tabla || (d.sel.key ?? "");
        setSelTipo("tab"); setSelKey(browse);
        if (browse) { try { const r = await informesService.tablaCampos(browse); setCampos(r.campos); setPorDefecto(r.por_defecto); } catch { /* */ } }
        setMultiCols(mcols);
        setMultiFiltros((d as { multiFiltros?: MultiFiltro[] }).multiFiltros || []);
        setMultiOrden((d as { multiOrden?: MultiOrden[] }).multiOrden || []);
        setRelaciones([]);
        setLimite(d.limite || 500);
      } else {
        const sel = d.sel || { tipo: "ent" as const, key: inf.entidad };
        let cs: CampoCatalogo[] = [], pd: string[] = [];
        if (sel.tipo === "tab") { try { const r = await informesService.tablaCampos(sel.key); cs = r.campos; pd = r.por_defecto; } catch { /* */ } }
        else { const e = cat?.entidades.find((x) => x.key === sel.key); cs = e?.campos || []; pd = e?.por_defecto || []; }
        setSelTipo(sel.tipo === "tab" ? "tab" : "ent"); setSelKey(sel.key); setCampos(cs); setPorDefecto(pd);
        setMultiCols([]); setMultiFiltros([]); setMultiOrden([]);
        setColumnas(d.columnas || pd); setFiltros(d.filtros || []); setOrden(d.orden || []); setRelaciones(d.relaciones || []);
        setFilasP(d.filas || (cs[0] ? [cs[0].key] : [])); setColumnaPiv(d.columna || "");
        setMedidaAgg(d.medida?.agg || "count"); setMedidaCampo(d.medida?.campo || "");
        setLimite(d.limite || 500);
      }
      setRunToken((t) => t + 1);
    } catch { flash("No se pudo abrir", true); }
  }
  async function borrar(id: number) {
    try { await informesService.borrar(id); if (selId === id) nuevo(); cargarGuardados(); flash("Informe borrado"); }
    catch { flash("No se pudo borrar", true); }
  }

  const hayResultado = modo === "pivote" ? !!resPiv : !!res;

  return (
    <div className="flex gap-2.5 h-full min-h-0">
      {msg.t && <div className="fixed top-14 right-6 z-50 px-4 py-2.5 rounded-sm font-semibold text-[12px] shadow-lg"
        style={{ background: msg.err ? "#C026D3" : "#2DD9C3", color: msg.err ? "#fff" : "#1500A0" }}>{msg.t}</div>}

      {/* ── Guardados ── */}
      <aside className="w-56 shrink-0 bg-white border border-[#e5e7eb] rounded-sm flex flex-col">
        <button onClick={nuevo} className="m-2.5 flex items-center justify-center gap-1.5 h-8 rounded-sm text-[12px] font-semibold uppercase tracking-wide text-[#1500A0] bg-[#2DD9C3] hover:bg-[#20BEAB]">
          <FilePlus2 className="w-3.5 h-3.5" /> Nuevo informe
        </button>
        <div className="px-2.5 pb-1 text-[10px] uppercase tracking-wide text-[#9aa7c2] font-semibold">Guardados ({guardados.length})</div>
        <div className="overflow-y-auto flex-1">
          {guardados.map((g) => (
            <div key={g.id} className={`group flex items-center border-b border-[#f4f6f9] ${selId === g.id ? "bg-[#FFFFFF]" : "hover:bg-[#E6EDFF]"}`}>
              <button onClick={() => abrir(g.id)} className="flex-1 min-w-0 text-left px-2.5 py-1.5">
                <div className={`truncate text-[12px] ${selId === g.id ? "text-[#1500A0] font-semibold" : "text-[#33415c]"}`}>{g.nombre}</div>
                <div className="truncate text-[10px] text-[#9aa7c2]">{g.entidad === "multi" ? "Varias tablas" : (cat?.entidades.find((e) => e.key === g.entidad)?.label || g.entidad)}</div>
              </button>
              <button onClick={() => borrar(g.id)} title="Borrar" className="px-2 text-slate-300 hover:text-[#C026D3] opacity-0 group-hover:opacity-100"><Trash2 className="w-3.5 h-3.5" /></button>
            </div>
          ))}
          {guardados.length === 0 && <p className="px-2.5 py-3 text-[11px] text-slate-400 italic">Sin informes guardados.</p>}
        </div>
      </aside>

      {/* ── Editor ── */}
      <section className="flex-1 min-w-0 bg-white border border-[#e5e7eb] rounded-sm flex flex-col">
        {/* barra */}
        <div className="p-2.5 border-b border-[#e5e7eb] flex items-center gap-2 flex-wrap shrink-0">
          <div className="flex rounded-sm border border-[#e5e7eb] overflow-hidden">
            <button onClick={() => setModo("lista")} className={`flex items-center gap-1 px-2.5 h-8 text-[12px] ${modo === "lista" ? "bg-[#1500A0] text-white" : "bg-white text-[#33415c] hover:bg-[#E6EDFF]"}`}><List className="w-3.5 h-3.5" /> Lista</button>
            <button onClick={() => setModo("pivote")} className={`flex items-center gap-1 px-2.5 h-8 text-[12px] ${modo === "pivote" ? "bg-[#1500A0] text-white" : "bg-white text-[#33415c] hover:bg-[#E6EDFF]"}`}><Table2 className="w-3.5 h-3.5" /> Tabla dinámica</button>
          </div>
          <select value={`${selTipo}:${selKey}`} onChange={(e) => { const v = e.target.value; const i = v.indexOf(":"); cambiarOrigen(v.slice(0, i) as "ent" | "tab", v.slice(i + 1)); }}
            className="h-8 px-2 text-[12px] font-semibold text-[#1500A0] border border-[#e5e7eb] rounded-sm outline-none focus:border-[#1ca0d1] max-w-[220px]">
            <optgroup label="Vistas (campos calculados)">{cat?.entidades.map((e) => <option key={e.key} value={`ent:${e.key}`}>{e.label}</option>)}</optgroup>
            <optgroup label="Tablas (combina varias)">{tablas.map((t) => <option key={t.nombre} value={`tab:${t.nombre}`}>{t.label}</option>)}</optgroup>
          </select>
          <input value={nombre} onChange={(e) => setNombre(e.target.value)} placeholder="Nombre del informe…" className="h-8 px-2 text-[12px] border border-[#e5e7eb] rounded-sm outline-none focus:border-[#1ca0d1] w-40" />
          <div className="ml-auto flex items-center gap-2">
            <button onClick={guardar} className="flex items-center gap-1.5 h-8 px-3 text-[12px] border border-[#e5e7eb] rounded-sm hover:bg-[#E6EDFF] text-[#33415c]"><Save className="w-3.5 h-3.5" /> {selId ? "Actualizar" : "Guardar"}</button>
            <button onClick={exportar} disabled={!hayResultado} className="flex items-center gap-1.5 h-8 px-3 text-[12px] border border-[#e5e7eb] rounded-sm hover:bg-[#E6EDFF] text-[#33415c] disabled:opacity-40"><Download className="w-3.5 h-3.5" /> CSV</button>
            <button onClick={ejecutar} className="flex items-center gap-1.5 h-8 px-4 text-[12px] font-semibold uppercase tracking-wide rounded-sm text-white bg-[#1500A0] hover:bg-[#0d0072]"><Play className="w-3.5 h-3.5" /> Ejecutar</button>
          </div>
        </div>

        {/* CONFIG */}
        {modo === "pivote" ? (
          <ConfigPivote {...{ campos, camposNum, filasP, setFilasP, columnaPiv, setColumnaPiv, medidaAgg, setMedidaAgg, medidaCampo, setMedidaCampo }} />
        ) : esTab ? (
          <div className="px-2.5 py-2 border-b border-[#eef1f6] shrink-0 space-y-2">
            <div>
              <div className="text-[10px] uppercase tracking-wide text-[#1ca0d1] font-semibold mb-1.5">Columnas de «{selKey}» — pulsa para añadir</div>
              <div className="flex flex-wrap gap-1.5">
                {campos.map((c) => { const on = enInforme(selKey, c.key); return (
                  <button key={c.key} onClick={() => toggleMultiCol(c)} className={`px-2 py-1 rounded-full text-[11px] border transition-colors ${on ? "bg-[#1500A0] text-white border-[#1500A0]" : "bg-white text-[#33415c] border-[#e5e7eb] hover:border-[#1ca0d1]"}`}>{on ? "✓ " : ""}{c.label}</button>
                ); })}
              </div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wide text-[#1ca0d1] font-semibold mb-1.5">Columnas del informe ({multiCols.length}) — de varias tablas, se unen solas</div>
              <div className="flex flex-wrap gap-1.5">
                {multiCols.map((m) => (
                  <span key={`${m.tabla}.${m.campo}`} className="inline-flex items-center gap-1 pl-2 pr-1 py-1 rounded-full text-[11px] bg-[#FFFFFF] text-[#1500A0] border border-[#c9d9f3]">
                    <span className="opacity-60">{m.tabla}.</span>{m.campo}
                    <button onClick={() => quitarMultiCol(m)} className="hover:text-[#C026D3]"><X className="w-3 h-3" /></button>
                  </span>
                ))}
                {multiCols.length === 0 && <span className="text-[11px] text-slate-400 italic">Aún sin columnas. Navega tablas arriba y ve añadiendo.</span>}
              </div>
            </div>
          </div>
        ) : (
          <div className="px-2.5 py-2 border-b border-[#eef1f6] shrink-0">
            <div className="text-[10px] uppercase tracking-wide text-[#1ca0d1] font-semibold mb-1.5">Columnas</div>
            <div className="flex flex-wrap gap-1.5">
              {campos.map((c) => { const on = columnas.includes(c.key); return (
                <button key={c.key} onClick={() => setColumnas((cs) => cs.includes(c.key) ? cs.filter((x) => x !== c.key) : [...cs, c.key])} className={`px-2 py-1 rounded-full text-[11px] border transition-colors ${on ? "bg-[#1500A0] text-white border-[#1500A0]" : "bg-white text-[#33415c] border-[#e5e7eb] hover:border-[#1ca0d1]"}`}>{c.label}</button>
              ); })}
            </div>
          </div>
        )}

        {/* FILTROS */}
        {modo !== "pivote" && (esTab ? (
          <FiltrosBar titulo="Filtros" onAdd={addMultiFiltro} vacio={multiFiltros.length === 0}>
            {multiFiltros.map((f, i) => { const col = multiCols.find((m) => m.tabla === f.tabla && m.campo === f.campo); const meta = cat?.operadores[f.op]; const tipo = col?.tipo || "texto"; const inputType = meta?.input === "fecha" || tipo === "fecha" ? "date" : tipo === "numero" ? "number" : "text"; return (
              <div key={i} className="flex items-center gap-1.5 flex-wrap">
                <select value={`${f.tabla}::${f.campo}`} onChange={(e) => { const [t, c] = e.target.value.split("::"); cambiarCampoMultiFiltro(i, t, c); }} className="h-7 px-1.5 text-[11px] border border-[#e5e7eb] rounded-sm outline-none focus:border-[#1ca0d1] text-[#33415c]">
                  {multiCols.map((m) => <option key={`${m.tabla}.${m.campo}`} value={`${m.tabla}::${m.campo}`}>{m.tabla}.{m.campo}</option>)}
                </select>
                <select value={f.op} onChange={(e) => updMultiFiltro(i, { op: e.target.value, valor: "", valor2: "" })} className="h-7 px-1.5 text-[11px] border border-[#e5e7eb] rounded-sm outline-none focus:border-[#1ca0d1] text-[#1500A0]">
                  {(col?.operadores || []).map((op) => <option key={op} value={op}>{cat?.operadores[op]?.label || op}</option>)}
                </select>
                {meta && meta.args >= 1 && <input type={meta.unidad ? "number" : inputType} value={f.valor ?? ""} onChange={(e) => updMultiFiltro(i, { valor: e.target.value })} className="h-7 px-1.5 text-[11px] border border-[#e5e7eb] rounded-sm outline-none focus:border-[#1ca0d1] w-28" />}
                {meta && meta.args === 2 && <><span className="text-[11px] text-[#9aa7c2]">y</span><input type={inputType} value={f.valor2 ?? ""} onChange={(e) => updMultiFiltro(i, { valor2: e.target.value })} className="h-7 px-1.5 text-[11px] border border-[#e5e7eb] rounded-sm outline-none focus:border-[#1ca0d1] w-28" /></>}
                {meta?.unidad && <select value={f.unidad ?? "anios"} onChange={(e) => updMultiFiltro(i, { unidad: e.target.value })} className="h-7 px-1.5 text-[11px] border border-[#e5e7eb] rounded-sm outline-none focus:border-[#1ca0d1] text-[#33415c]">{UNIDADES.map((u) => <option key={u.v} value={u.v}>{u.l}</option>)}</select>}
                <button onClick={() => setMultiFiltros((fs) => fs.filter((_, j) => j !== i))} className="text-slate-300 hover:text-[#C026D3]"><X className="w-3.5 h-3.5" /></button>
              </div>
            ); })}
          </FiltrosBar>
        ) : (
          <FiltrosBar titulo="Filtros" onAdd={addFiltro} vacio={filtros.length === 0}>
            {filtros.map((f, i) => { const campo = campoByKey[f.campo]; const meta = cat?.operadores[f.op]; const tipo = campo?.tipo || "texto"; const inputType = meta?.input === "fecha" || tipo === "fecha" ? "date" : tipo === "numero" ? "number" : "text"; return (
              <div key={i} className="flex items-center gap-1.5 flex-wrap">
                <select value={f.campo} onChange={(e) => cambiarCampoFiltro(i, e.target.value)} className="h-7 px-1.5 text-[11px] border border-[#e5e7eb] rounded-sm outline-none focus:border-[#1ca0d1] text-[#33415c]">{campos.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}</select>
                <select value={f.op} onChange={(e) => updFiltro(i, { op: e.target.value, valor: "", valor2: "" })} className="h-7 px-1.5 text-[11px] border border-[#e5e7eb] rounded-sm outline-none focus:border-[#1ca0d1] text-[#1500A0]">{campo?.operadores.map((op) => <option key={op} value={op}>{cat?.operadores[op]?.label || op}</option>)}</select>
                {meta && meta.args >= 1 && <input type={meta.unidad ? "number" : inputType} value={f.valor ?? ""} onChange={(e) => updFiltro(i, { valor: e.target.value })} className="h-7 px-1.5 text-[11px] border border-[#e5e7eb] rounded-sm outline-none focus:border-[#1ca0d1] w-28" />}
                {meta && meta.args === 2 && <><span className="text-[11px] text-[#9aa7c2]">y</span><input type={inputType} value={f.valor2 ?? ""} onChange={(e) => updFiltro(i, { valor2: e.target.value })} className="h-7 px-1.5 text-[11px] border border-[#e5e7eb] rounded-sm outline-none focus:border-[#1ca0d1] w-28" /></>}
                {meta?.unidad && <select value={f.unidad ?? "anios"} onChange={(e) => updFiltro(i, { unidad: e.target.value })} className="h-7 px-1.5 text-[11px] border border-[#e5e7eb] rounded-sm outline-none focus:border-[#1ca0d1] text-[#33415c]">{UNIDADES.map((u) => <option key={u.v} value={u.v}>{u.l}</option>)}</select>}
                <button onClick={() => setFiltros((fs) => fs.filter((_, j) => j !== i))} className="text-slate-300 hover:text-[#C026D3]"><X className="w-3.5 h-3.5" /></button>
              </div>
            ); })}
          </FiltrosBar>
        ))}

        {/* RELACIONES (TIENE / NO TIENE … que cumplen …) — solo en Vista + Lista */}
        {modo !== "pivote" && !esTab && entRelaciones.length > 0 && (
          <RelacionesEditor relaciones={entRelaciones} value={relaciones} onChange={setRelaciones} ops={cat?.operadores || {}} />
        )}

        {/* RESULTADOS */}
        <div className="flex-1 min-h-0 overflow-auto">
          {cargando ? <div className="p-4 text-[12px] text-[#9aa7c2]">Ejecutando…</div>
            : modo === "pivote" ? <ResultadoPivot res={resPiv} totales={totalesPivote} />
              : <ResultadoLista res={res} dirDe={dirDe} onOrdenar={ordenarLista} multi={esTab} />}
        </div>

        {/* PIE */}
        {modo !== "pivote" && res && (
          <div className="px-3 py-1.5 text-[11px] text-[#7f8c8d] border-t border-[#eef1f6] flex items-center gap-3 shrink-0">
            <b className="text-[#1500A0]">{res.total.toLocaleString("es-ES")}</b> resultados
            {esTab && <span className="text-[#9aa7c2]">· {res.columnas.length} columnas de varias tablas</span>}
            {res.truncado && <span className="text-[#7C3AED]">· mostrando {res.filas.length} (exporta a CSV para verlos todos)</span>}
            <span className="ml-auto flex items-center gap-1">Máx<input type="number" min={1} max={5000} value={limite} onChange={(e) => setLimite(Math.max(1, Math.min(5000, Number(e.target.value) || 500)))} className="w-16 h-6 px-1.5 border border-[#e5e7eb] rounded-sm outline-none focus:border-[#1ca0d1]" /></span>
          </div>
        )}
        {modo === "pivote" && resPiv && (
          <div className="px-3 py-1.5 text-[11px] text-[#7f8c8d] border-t border-[#eef1f6] shrink-0"><b className="text-[#1500A0]">{resPiv.n_filas.toLocaleString("es-ES")}</b> grupos · medida: {resPiv.medida_label}</div>
        )}
      </section>
    </div>
  );
}

// ── barra de filtros reutilizable ──
function FiltrosBar({ titulo, onAdd, vacio, children }: { titulo: string; onAdd: () => void; vacio: boolean; children: React.ReactNode }) {
  return (
    <div className="px-2.5 py-2 border-b border-[#eef1f6] shrink-0">
      <div className="flex items-center justify-between mb-1.5">
        <div className="text-[10px] uppercase tracking-wide text-[#1ca0d1] font-semibold">{titulo}</div>
        <button onClick={onAdd} className="flex items-center gap-1 text-[11px] text-[#1500A0] hover:underline"><Plus className="w-3 h-3" /> Añadir filtro</button>
      </div>
      <div className="flex flex-col gap-1.5">{children}{vacio && <p className="text-[11px] text-slate-400 italic">Sin filtros.</p>}</div>
    </div>
  );
}

// ── editor de RELACIONES (TIENE / NO TIENE … que cumplen …) ──
function RelacionesEditor({ relaciones, value, onChange, ops }: {
  relaciones: RelacionCatalogo[]; value: RelFiltro[]; onChange: (v: RelFiltro[]) => void; ops: Record<string, OperadorMeta>;
}) {
  const relByKey: Record<string, RelacionCatalogo> = {};
  relaciones.forEach((r) => { relByKey[r.key] = r; });
  const SEL = "h-7 px-1.5 text-[11px] border border-[#e5e7eb] rounded-sm outline-none focus:border-[#1ca0d1] bg-white";
  const add = () => onChange([...value, { relacion: relaciones[0].key, modo: "tiene", subfiltros: [] }]);
  const upd = (i: number, patch: Partial<RelFiltro>) => onChange(value.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const setSub = (i: number, subfiltros: Filtro[]) => upd(i, { subfiltros });
  const addSub = (i: number) => { const c = (relByKey[value[i].relacion]?.campos || [])[0]; if (c) setSub(i, [...value[i].subfiltros, { campo: c.key, op: c.operadores[0], valor: "", unidad: "anios" }]); };
  const updSub = (i: number, j: number, patch: Partial<Filtro>) => setSub(i, value[i].subfiltros.map((s, k) => (k === j ? { ...s, ...patch } : s)));

  return (
    <div className="px-2.5 py-2 border-b border-[#eef1f6] shrink-0">
      <div className="flex items-center justify-between mb-1.5">
        <div className="text-[10px] uppercase tracking-wide text-[#1ca0d1] font-semibold">Relaciones (tiene / no tiene…)</div>
        <button onClick={add} className="flex items-center gap-1 text-[11px] text-[#1500A0] hover:underline"><Plus className="w-3 h-3" /> Añadir relación</button>
      </div>
      <div className="flex flex-col gap-2">
        {value.map((r, i) => {
          const rc = relByKey[r.relacion]?.campos || [];
          return (
            <div key={i} className="rounded-sm border border-[#e5e7eb] bg-[#FFFFFF] p-2">
              <div className="flex items-center gap-1.5 flex-wrap">
                <select value={r.modo} onChange={(e) => upd(i, { modo: e.target.value as "tiene" | "no_tiene" })} className={`${SEL} font-semibold ${r.modo === "no_tiene" ? "text-[#C026D3]" : "text-[#0F8C7D]"}`}>
                  <option value="tiene">TIENE</option><option value="no_tiene">NO TIENE</option>
                </select>
                <select value={r.relacion} onChange={(e) => upd(i, { relacion: e.target.value, subfiltros: [] })} className={`${SEL} text-[#1500A0] font-semibold`}>
                  {relaciones.map((x) => <option key={x.key} value={x.key}>{x.label}</option>)}
                </select>
                <span className="text-[11px] text-[#7f8c8d]">que cumplan:</span>
                <button onClick={() => addSub(i)} className="text-[11px] text-[#1500A0] hover:underline flex items-center gap-0.5"><Plus className="w-3 h-3" /> condición</button>
                <button onClick={() => onChange(value.filter((_, j) => j !== i))} className="ml-auto text-slate-300 hover:text-[#C026D3]"><X className="w-3.5 h-3.5" /></button>
              </div>
              <div className="flex flex-col gap-1 mt-1.5 pl-3 border-l-2 border-[#e5e7eb]">
                {r.subfiltros.map((s, j) => {
                  const campo = rc.find((x) => x.key === s.campo); const meta = ops[s.op]; const tipo = campo?.tipo || "texto";
                  const inputType = meta?.input === "fecha" || tipo === "fecha" ? "date" : tipo === "numero" ? "number" : "text";
                  return (
                    <div key={j} className="flex items-center gap-1.5 flex-wrap">
                      <select value={s.campo} onChange={(e) => { const c = rc.find((x) => x.key === e.target.value); updSub(i, j, { campo: e.target.value, op: c?.operadores[0] || "igual", valor: "", valor2: "", unidad: "anios" }); }} className={`${SEL} text-[#33415c]`}>
                        {rc.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
                      </select>
                      <select value={s.op} onChange={(e) => updSub(i, j, { op: e.target.value, valor: "", valor2: "" })} className={`${SEL} text-[#1500A0]`}>
                        {(campo?.operadores || []).map((op) => <option key={op} value={op}>{ops[op]?.label || op}</option>)}
                      </select>
                      {meta && meta.args >= 1 && <input type={meta.unidad ? "number" : inputType} value={s.valor ?? ""} onChange={(e) => updSub(i, j, { valor: e.target.value })} className={`${SEL} w-24`} />}
                      {meta && meta.args === 2 && <><span className="text-[11px] text-[#9aa7c2]">y</span><input type={inputType} value={s.valor2 ?? ""} onChange={(e) => updSub(i, j, { valor2: e.target.value })} className={`${SEL} w-24`} /></>}
                      {meta?.unidad && <select value={s.unidad ?? "anios"} onChange={(e) => updSub(i, j, { unidad: e.target.value })} className={`${SEL} text-[#33415c]`}>{UNIDADES.map((u) => <option key={u.v} value={u.v}>{u.l}</option>)}</select>}
                      <button onClick={() => setSub(i, r.subfiltros.filter((_, k) => k !== j))} className="text-slate-300 hover:text-[#C026D3]"><X className="w-3 h-3" /></button>
                    </div>
                  );
                })}
                {r.subfiltros.length === 0 && <span className="text-[11px] text-slate-400 italic">Sin condiciones → cualquier «{relByKey[r.relacion]?.label.toLowerCase()}».</span>}
              </div>
            </div>
          );
        })}
        {value.length === 0 && <p className="text-[11px] text-slate-400 italic">Sin relaciones. Ej.: NO TIENE «Tratamientos realizados» que empiece por «IMPLANTE».</p>}
      </div>
    </div>
  );
}

// ── config de la tabla dinámica ──
function ConfigPivote({ campos, camposNum, filasP, setFilasP, columnaPiv, setColumnaPiv, medidaAgg, setMedidaAgg, medidaCampo, setMedidaCampo }: {
  campos: CampoCatalogo[]; camposNum: CampoCatalogo[]; filasP: string[]; setFilasP: (f: (p: string[]) => string[]) => void;
  columnaPiv: string; setColumnaPiv: (v: string) => void; medidaAgg: Agregacion; setMedidaAgg: (a: Agregacion) => void; medidaCampo: string; setMedidaCampo: (v: string) => void;
}) {
  return (
    <div className="px-2.5 py-2 border-b border-[#eef1f6] shrink-0 space-y-2">
      <div>
        <div className="text-[10px] uppercase tracking-wide text-[#1ca0d1] font-semibold mb-1.5">Filas (agrupar por)</div>
        <div className="flex flex-wrap gap-1.5">
          {campos.map((c) => { const on = filasP.includes(c.key); return <button key={c.key} onClick={() => setFilasP((fs) => fs.includes(c.key) ? fs.filter((x) => x !== c.key) : [...fs, c.key])} className={`px-2 py-1 rounded-full text-[11px] border transition-colors ${on ? "bg-[#1500A0] text-white border-[#1500A0]" : "bg-white text-[#33415c] border-[#e5e7eb] hover:border-[#1ca0d1]"}`}>{c.label}</button>; })}
        </div>
      </div>
      <div className="flex items-center gap-4 flex-wrap">
        <label className="flex items-center gap-1.5 text-[11px] text-[#33415c]"><span className="uppercase tracking-wide text-[#1ca0d1] font-semibold text-[10px]">Columnas (cruce)</span>
          <select value={columnaPiv} onChange={(e) => setColumnaPiv(e.target.value)} className="h-7 px-1.5 text-[11px] border border-[#e5e7eb] rounded-sm outline-none focus:border-[#1ca0d1]"><option value="">— ninguna —</option>{campos.filter((c) => !filasP.includes(c.key)).map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}</select>
        </label>
        <label className="flex items-center gap-1.5 text-[11px] text-[#33415c]"><span className="uppercase tracking-wide text-[#1ca0d1] font-semibold text-[10px]">Medida</span>
          <select value={medidaAgg} onChange={(e) => setMedidaAgg(e.target.value as Agregacion)} className="h-7 px-1.5 text-[11px] border border-[#e5e7eb] rounded-sm outline-none focus:border-[#1ca0d1] text-[#1500A0] font-semibold">{AGGS.map((a) => <option key={a.v} value={a.v}>{a.l}</option>)}</select>
          {medidaAgg !== "count" && <select value={medidaCampo} onChange={(e) => setMedidaCampo(e.target.value)} className="h-7 px-1.5 text-[11px] border border-[#e5e7eb] rounded-sm outline-none focus:border-[#1ca0d1]"><option value="">— campo —</option>{camposNum.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}</select>}
        </label>
      </div>
    </div>
  );
}

function exportarPivote(res: ResultadoPivote, totales: { colTot: Record<string, number>; gran: number } | null, nombre: string) {
  const dims = res.dimensiones; const cols = res.columnas;
  const head = [...dims.map((d) => d.label), ...(cols ? [...cols.map((c) => c.label), "Total"] : [res.medida_label])];
  const lineas = [head.join(";")];
  res.filas.forEach((f) => { const celdas = cols ? [...cols.map((c) => f.__celdas?.[c.valor] ?? ""), f.__total ?? ""] : [f.__val ?? ""]; lineas.push([...dims.map((d) => String(f[d.key] ?? "")), ...celdas].join(";")); });
  if (totales) { const tot = cols ? [...cols.map((c) => totales.colTot[c.valor]), totales.gran] : [totales.gran]; lineas.push(["Total", ...dims.slice(1).map(() => ""), ...tot].join(";")); }
  const blob = new Blob(["﻿" + lineas.join("\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob); const a = document.createElement("a"); a.href = url; a.download = `informe_${nombre}.csv`; a.click(); URL.revokeObjectURL(url);
}

// ── tabla LISTA (vista o multi) ──
function ResultadoLista({ res, dirDe, onOrdenar, multi }: { res: ResultadoInforme | null; dirDe: (c: ColumnaResultado) => "asc" | "desc" | null; onOrdenar: (c: ColumnaResultado) => void; multi: boolean }) {
  if (!res) return <div className="h-full grid place-items-center text-[12px] text-[#9aa7c2]">{multi ? "Añade columnas de una o varias tablas y pulsa «Ejecutar»." : "Pulsa «Ejecutar» para ver los resultados."}</div>;
  if (res.filas.length === 0) return <div className="p-4 text-[12px] text-[#9aa7c2]">Sin resultados para esos filtros.</div>;
  return (
    <table className="text-[12px] border-collapse w-full">
      <thead className="sticky top-0 bg-[#FFFFFF] z-10"><tr>
        {res.columnas.map((c) => { const d = dirDe(c); return (
          <th key={c.key} onClick={() => onOrdenar(c)} title="Ordenar" className="text-left px-3 py-2 border-b border-[#e5e7eb] whitespace-nowrap text-[#1500A0] font-semibold cursor-pointer select-none hover:bg-[#E6EDFF]">
            <span className="inline-flex items-center gap-1">{c.label}{d && (d === "asc" ? <ArrowUp className="w-3 h-3" /> : <ArrowDown className="w-3 h-3" />)}</span>
          </th>
        ); })}
      </tr></thead>
      <tbody>{res.filas.map((f, i) => (
        <tr key={i} className="hover:bg-[#E6EDFF]">{res.columnas.map((c) => <td key={c.key} className="px-3 py-1.5 border-b border-[#f4f6f9] whitespace-nowrap max-w-[280px] truncate" title={fmtCelda(f[c.key], c.tipo)}>{fmtCelda(f[c.key], c.tipo)}</td>)}</tr>
      ))}</tbody>
    </table>
  );
}

// ── tabla DINÁMICA ──
function ResultadoPivot({ res, totales }: { res: ResultadoPivote | null; totales: { colTot: Record<string, number>; gran: number } | null }) {
  if (!res) return <div className="h-full grid place-items-center text-[12px] text-[#9aa7c2]">Pulsa «Ejecutar» para ver la tabla dinámica.</div>;
  if (res.filas.length === 0) return <div className="p-4 text-[12px] text-[#9aa7c2]">Sin datos para esa configuración.</div>;
  const cols = res.columnas;
  return (
    <table className="text-[12px] border-collapse w-full">
      <thead className="sticky top-0 bg-[#FFFFFF] z-10"><tr>
        {res.dimensiones.map((d) => <th key={d.key} className="text-left px-3 py-2 border-b border-[#e5e7eb] whitespace-nowrap text-[#1500A0] font-semibold">{d.label}</th>)}
        {cols ? <>{cols.map((c) => <th key={c.valor} className="text-right px-3 py-2 border-b border-[#e5e7eb] whitespace-nowrap text-[#1500A0] font-semibold">{c.label}</th>)}<th className="text-right px-3 py-2 border-b border-[#e5e7eb] text-[#1500A0] font-semibold bg-[#FFFFFF]">Total</th></> : <th className="text-right px-3 py-2 border-b border-[#e5e7eb] text-[#1500A0] font-semibold">{res.medida_label}</th>}
      </tr></thead>
      <tbody>
        {res.filas.map((f, i) => (
          <tr key={i} className="hover:bg-[#E6EDFF]">
            {res.dimensiones.map((d) => <td key={d.key} className="px-3 py-1.5 border-b border-[#f4f6f9] whitespace-nowrap text-[#33415c]">{f[d.key] == null || f[d.key] === "" ? "(vacío)" : String(f[d.key])}</td>)}
            {cols ? <>{cols.map((c) => <td key={c.valor} className="px-3 py-1.5 border-b border-[#f4f6f9] text-right tabular-nums">{fmtNum(f.__celdas?.[c.valor])}</td>)}<td className="px-3 py-1.5 border-b border-[#f4f6f9] text-right tabular-nums font-semibold text-[#1500A0] bg-[#FFFFFF]">{fmtNum(f.__total)}</td></> : <td className="px-3 py-1.5 border-b border-[#f4f6f9] text-right tabular-nums font-semibold text-[#1500A0]">{fmtNum(f.__val)}</td>}
          </tr>
        ))}
        {totales && (
          <tr className="bg-[#FFFFFF] sticky bottom-0">
            <td className="px-3 py-2 font-bold text-[#1500A0] border-t border-[#d4def0]" colSpan={res.dimensiones.length}>Total general</td>
            {cols ? <>{cols.map((c) => <td key={c.valor} className="px-3 py-2 text-right tabular-nums font-bold text-[#1500A0] border-t border-[#d4def0]">{fmtNum(totales.colTot[c.valor])}</td>)}<td className="px-3 py-2 text-right tabular-nums font-bold text-[#1500A0] border-t border-[#d4def0]">{fmtNum(totales.gran)}</td></> : <td className="px-3 py-2 text-right tabular-nums font-bold text-[#1500A0] border-t border-[#d4def0]">{fmtNum(totales.gran)}</td>}
          </tr>
        )}
      </tbody>
    </table>
  );
}
