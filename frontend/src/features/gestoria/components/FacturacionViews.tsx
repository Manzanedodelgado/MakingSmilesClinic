"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, X, FileText, Send, Check, CheckCircle, Upload, Trash2, Plus, Link2, Contact, Mail, Download, Sparkles, Layers, Pencil } from "lucide-react";
import { gestoriaService, eur, fecha as fmtFecha } from "../services/gestoriaService";
import { usePermisos } from "@/shared/hooks/usePermisos";
import { AreaTabs, Modal, ModalBody, ModalButton, ModalFooter, ModalSection, ModalTabs, MODAL_INPUT } from "@/shared/components";
import { Buscador, coincide } from "./Buscador";
import { MESES } from "../constants";
import type { Extracto, FacturaEmitida, Gasto, Movimiento, PagoPaciente, Proveedor, RevisionItem, Vencimiento } from "../types/gestoria";

const Y = new Date().getFullYear();
const YEARS = [Y, Y - 1, Y - 2];
// Formas de pago de una factura recibida. "Metálico" (efectivo/caja) NO genera apunte bancario.
const FORMAS_PAGO_GASTO = ["Transferencia", "Domiciliación / Recibo", "Tarjeta", "Tarjeta Deb. Juan A. Manzanedo", "Metálico", "Cheque / Pagaré"];
const esMetalico = (forma?: string | null) => /met[aá]lico|efectivo|caja|cash/i.test(forma ?? "");
// Tarjeta personal de Juan A. Manzanedo: pago fuera de la cuenta de la clínica → se concilia como apunte externo.
const esTarjetaExterna = (forma?: string | null) => /manzanedo/i.test(forma ?? "");
// Enlace a la factura: URL de Drive directa; ficheros locales /media van por el proxy /api.
const pdfHref = (url: string) => (url.startsWith("http") ? url : `/api${url}`);
const Th = ({ children, r }: { children?: React.ReactNode; r?: boolean }) => <th className={`py-1.5 px-3 font-semibold ${r ? "text-right" : "text-left"}`}>{children}</th>;
const Td = ({ children, r, cls }: { children?: React.ReactNode; r?: boolean; cls?: string }) => <td className={`py-1.5 px-3 ${cls || "text-slate-600"} ${r ? "text-right" : ""}`}>{children}</td>;
const Wrap = ({ children }: { children: React.ReactNode }) => <div className="flex-1 overflow-y-auto p-4 bg-white flex flex-col gap-4">{children}</div>;
// Descarga de datos (CSV con BOM para que Excel respete acentos). Disponible también en modo lectura.
function descargarCSV(nombre: string, cabeceras: string[], filas: (string | number)[][]) {
  const esc = (v: string | number) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const csv = [cabeceras, ...filas].map((f) => f.map(esc).join(";")).join("\r\n");
  const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = `${nombre}.csv`; a.click();
  URL.revokeObjectURL(url);
}
const BtnCSV = ({ onClick }: { onClick: () => void }) => (
  <button onClick={onClick} title="Descargar los datos en CSV (Excel)"
    className="inline-flex items-center gap-2 rounded-sm border border-[#065AED] px-3 py-1.5 text-[12px] font-semibold text-[#065AED] hover:bg-[#065AED]/5">
    <Download className="h-3.5 w-3.5" /> Descargar
  </button>
);
const Tbl = ({ head, children }: { head: React.ReactNode; children: React.ReactNode }) => (
  <div className="border border-[#e5e7eb] rounded-sm overflow-auto"><table className="w-full text-[12px]"><thead className="bg-[#1500A0] text-white text-[11px] uppercase tracking-wider sticky top-0 z-10">{head}</thead><tbody>{children}</tbody></table></div>
);
// Botón del modal con el "✓" de la referencia; mientras guarda, ese mismo hueco muestra el girador.
const IconoGuardar = ({ cargando, children }: { cargando: boolean; children: React.ReactNode }) => (
  <span className="inline-flex items-center gap-2">
    {cargando ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle className="w-3.5 h-3.5" />}
    {children}
  </span>
);

// Bandeja de revisión: apuntes de los que la herramienta PIDE un dato (hoy: interés de préstamos/leasing).
// El motor no inventa el reparto interés/principal; lo solicita aquí y contabiliza solo el interés.
function RevisionPanel({ items, onResolver }: { items: RevisionItem[]; onResolver: (it: RevisionItem, interes: string) => void }) {
  const [vals, setVals] = useState<Record<number, string>>({});
  return (
    <div className="border border-[#C4B5FD] bg-[#FFFFFF]/60 rounded-sm">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-[#DDD6FE] text-[12px] font-semibold text-[#5B21B6]">
        <span className="w-2 h-2 rounded-full bg-[#7C3AED]" />
        La herramienta necesita un dato · {items.length} {items.length === 1 ? "apunte" : "apuntes"} de préstamo/leasing
      </div>
      <table className="w-full text-[12px]">
        <tbody>
          {items.map((it) => (
            <tr key={it.movimientoId} className="border-b border-[#EDE8FD] last:border-0">
              <Td>{fmtFecha(it.fecha)}</Td>
              <Td><span className="text-slate-700">{it.concepto}</span></Td>
              <Td r>{eur(it.importe)}</Td>
              <td className="py-1.5 px-3">
                <div className="flex items-center gap-1.5 justify-end" title={it.motivo}>
                  <span className="text-[11px] text-[#5B21B6]">Interés</span>
                  <input inputMode="decimal" placeholder="0,00" value={vals[it.movimientoId] ?? ""}
                    onChange={(e) => setVals((v) => ({ ...v, [it.movimientoId]: e.target.value }))}
                    className="w-24 border border-[#C4B5FD] rounded-sm px-2 py-1 text-right text-[12px]" />
                  <span className="text-[11px] text-[#5B21B6]">€</span>
                  <button onClick={() => onResolver(it, vals[it.movimientoId] ?? "")}
                    disabled={!vals[it.movimientoId]}
                    className="rounded-sm bg-[#7C3AED] text-white px-2.5 py-1 text-[11px] font-semibold hover:bg-[#6D28D9] disabled:opacity-50">
                    Contabilizar
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Facturas() {
  const [anyo, setAnyo] = useState(Y);
  const [rows, setRows] = useState<FacturaEmitida[]>([]);
  const [total, setTotal] = useState(0);
  useEffect(() => { gestoriaService.facturas(anyo).then((r) => { setRows(r.data); setTotal(r.total); }); }, [anyo]);
  return (<Wrap>
    <div className="flex items-center justify-between"><span className="text-[12px] text-[#7f8c8d]"><b className="text-[#1500A0]">{total}</b> facturas emitidas</span>
      <select value={anyo} onChange={(e) => setAnyo(Number(e.target.value))} className="border border-[#e5e7eb] rounded-sm px-2 py-1 text-[11px]">{YEARS.map((y) => <option key={y}>{y}</option>)}</select></div>
    <Tbl head={<tr><Th>Nº</Th><Th>Fecha</Th><Th>Cliente</Th><Th>NIF</Th><Th>Estado</Th><Th r>Verifactu</Th></tr>}>
      {rows.length === 0 ? <tr><td colSpan={6} className="text-center py-8 text-gray-400 italic">Sin facturas en {anyo}</td></tr>
        : rows.map((f) => <tr key={f.id} className="border-b border-[#f0f3f7] even:bg-[#FFFFFF] hover:bg-[#E6EDFF]">
          <Td><b className="text-[#065AED]">{f.numero}</b></Td><Td>{fmtFecha(f.fecha)}</Td><Td>{f.cliente}</Td><Td>{f.nif ?? "—"}</Td>
          <td className="py-1.5 px-3"><span className={`px-1.5 py-0.5 rounded-sm text-[10px] uppercase ${f.estado === "anulada" ? "bg-[#FFFFFF] text-[#C026D3]" : f.estado === "abono" ? "bg-[#FFFFFF] text-[#6D28D9]" : "bg-[#FFFFFF] text-[#073D8D]"}`}>{f.estado}</span></td>
          <Td r>{f.verifactu ? "✓" : "—"}</Td></tr>)}
    </Tbl>
  </Wrap>);
}

const ANYOS_GASTOS = ["", "2026", "2025", "2024", "2023", "2022"];
const ESTADOS_GASTO = [["", "Todos los estados"], ["revisar", "Por revisar"], ["pendiente", "Pendientes"], ["pagada", "Pagadas"]];

function GastosBase({ titulo }: { titulo: string }) {
  const { puedeEditarGestoria } = usePermisos();
  const [rows, setRows] = useState<Gasto[]>([]);
  const [anyo, setAnyo] = useState("");
  const [estado, setEstado] = useState("");
  const [editando, setEditando] = useState<Gasto | null>(null);
  const [asociando, setAsociando] = useState<Gasto | null>(null);
  const [health, setHealth] = useState<{ estado: string; enRevisar: number; problemas: string[] } | null>(null);
  const [subiendo, setSubiendo] = useState(false);
  const [buzonBusy, setBuzonBusy] = useState(false);
  const [clasificando, setClasificando] = useState(false);
  const [verProveedores, setVerProveedores] = useState(false);
  const [zipBusy, setZipBusy] = useState(false);
  const [revision, setRevision] = useState<RevisionItem[]>([]);
  const [sinCategoria, setSinCategoria] = useState(0);
  const [incidenciasBuzon, setIncidenciasBuzon] = useState(0);
  const [msg, setMsg] = useState<string | null>(null);
  const [busca, setBusca] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  // Deep-link desde INICIO: ?gasto=<id> abre directamente el editor de esa factura.
  const gastoFoco = useRef<string | null>(
    typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("gasto") : null,
  );
  const cargarSinCategoria = useCallback(() => {
    gestoriaService.proveedoresSinCategoria().then((r) => setSinCategoria(r.count)).catch(() => {});
  }, []);
  const cargarIncidencias = useCallback(() => {
    gestoriaService.incidenciasCount().then((r) => setIncidenciasBuzon(r.count)).catch(() => {});
  }, []);
  const cargar = useCallback(() => {
    const rango = anyo ? { desde: `${anyo}-01-01`, hasta: `${anyo}-12-31` } : {};
    gestoriaService.gastos(estado || undefined, rango.desde, rango.hasta).then((r) => setRows(r.data));
    gestoriaService.facturasHealth().then(setHealth).catch(() => {});
    gestoriaService.revisionPendiente().then((r) => setRevision(r.data)).catch(() => {});
  }, [anyo, estado]);
  useEffect(() => { cargar(); cargarSinCategoria(); cargarIncidencias(); }, [cargar, cargarSinCategoria, cargarIncidencias]);
  // Cuando llegan las filas, si venimos con ?gasto=<id> abrimos su editor una sola vez.
  useEffect(() => {
    const id = gastoFoco.current;
    if (!id || !rows.length) return;
    const g = rows.find((x) => String(x.id) === id);
    if (g) { setEditando(g); setBusca(id); }
    gastoFoco.current = null;
  }, [rows]);
  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]; e.target.value = "";
    if (!file) return;
    setSubiendo(true); setMsg(null);
    try {
      const r = await gestoriaService.subirFactura(file);
      setMsg(r.duplicado ? "Ya estaba procesada." : r.ok ? `Procesada: ${r.proveedor ?? "—"} · ${r.total ?? 0}€ (${r.estado})` : `Error: ${r.error}`);
      cargar();
    } catch (err) { setMsg(`Error: ${err instanceof Error ? err.message : ""}`); }
    finally { setSubiendo(false); }
  };
  const procesarBuzon = async () => {
    setBuzonBusy(true); setMsg(null);
    try {
      // 1 · Previsualiza (sin IA ni escrituras): cuántos correos nuevos y su reparto.
      const p = await gestoriaService.procesarBuzon(false);
      if (!p.ok) { setMsg(`Buzón: ${p.error ?? "error"}`); return; }
      const revNuevos = p.revisadas?.nuevos ?? 0;
      if (p.nuevos === 0 && revNuevos === 0) { setMsg(`Buzón al día: ${p.enCarpeta} correos, nada nuevo por procesar.`); return; }
      const ok = window.confirm(
        `Buzón "${p.carpeta}": ${p.nuevos} correos nuevos de ${p.enCarpeta} ` +
        `(${p.yaEnBd} ya procesados).\n\n· ${p.facturasNuevas} facturas a leer\n` +
        `· ${p.basura} basura confiable → a la papelera\n` +
        `· ${p.descartadas} no son factura pero se dejan en el INBOX (por si acaso)\n` +
        `· ${p.incidencias} dudosos → a Incidencias, para que los revises tú\n` +
        (revNuevos ? `· ${revNuevos} confirmadas en Facturas revisadas, pendientes de registrar\n` : "") +
        `\nProcesar ahora (sin duplicar las que ya tienes)?`);
      if (!ok) { setMsg(`${p.nuevos} nuevos en el buzón (${p.facturasNuevas} facturas · ${p.incidencias} dudosas)${revNuevos ? ` · ${revNuevos} en revisadas` : ""}. Sin procesar.`); return; }
      // 2 · Ejecuta de verdad (con throttle anti-429 en el backend).
      const r = await gestoriaService.procesarBuzon(true);
      if (!r.ok) { setMsg(`Buzón: ${r.error ?? "error"}`); return; }
      const rev = r.revisadas;
      setMsg(`Buzón procesado: +${r.facturasNuevas} nuevas · ${r.basura} a papelera · ${r.descartadas} sin tocar en INBOX · ${r.incidencias} a revisar tú` +
        `${rev?.registradas ? ` · ${rev.registradas} confirmadas registradas (${rev.faltanDatos} a revisar)` : ""}` +
        `${r.errores ? ` · ${r.errores} errores` : ""}`);
      cargar(); cargarIncidencias();
    } catch (err) { setMsg(`Error: ${err instanceof Error ? err.message : ""}`); }
    finally { setBuzonBusy(false); }
  };
  const clasificarIA = async () => {
    setClasificando(true); setMsg("Gestor IA está leyendo los proveedores… (tarda un poco)");
    try {
      const r = await gestoriaService.clasificarGastosIA(true);
      setMsg(r.ok
        ? `Gestor IA clasificó ${r.aplicados} gastos (${Object.entries(r.porCategoria).map(([c, n]) => `${n} ${c}`).join(" · ")}). ${r.revisar} quedan para revisar.`
        : `Error: ${r.error ?? "IA no disponible"}`);
      cargar();
    } catch (e) { setMsg(`Error: ${e instanceof Error ? e.message : ""}`); }
    finally { setClasificando(false); }
  };
  const resolverPrestamo = async (it: RevisionItem, interesStr: string) => {
    const interes = Number(interesStr.replace(",", "."));
    if (!Number.isFinite(interes) || interes < 0 || interes > it.importe) {
      setMsg(`Interés inválido: debe estar entre 0 y ${eur(it.importe)}.`); return;
    }
    try {
      const r = await gestoriaService.resolverPrestamo(it.movimientoId, interes);
      setMsg(`Préstamo contabilizado: interés ${eur(r.interes)} (gasto) · principal ${eur(r.principal)} (capital, no deducible).`);
      cargar();
    } catch (e) { setMsg(`Error: ${e instanceof Error ? e.message : ""}`); }
  };
  const sano = health?.estado === "ok";
  const visibles = rows.filter((g) => coincide(busca, g.id, g.proveedor, g.numeroFactura, g.fecha, g.formaPago, g.total, g.concepto, g.cifEmisor, g.movimientoId));
  // EL MISMO fichero que Envío manda a la asesoría (gastos_{año}.csv, columnas completas del backend).
  const exportarCSV = () => gestoriaService.descargarSeccionCsv("gastos", Number(anyo) || new Date().getFullYear())
    .catch((e) => setMsg(`Error: ${e instanceof Error ? e.message : ""}`));
  const descargarZip = async () => {
    setZipBusy(true); setMsg(null);
    try {
      const rango = anyo ? { desde: `${anyo}-01-01`, hasta: `${anyo}-12-31` } : {};
      await gestoriaService.descargarFacturasZip(estado || undefined, rango.desde, rango.hasta);
    } catch (e) { setMsg(`Error: ${e instanceof Error ? e.message : ""}`); }
    finally { setZipBusy(false); }
  };
  return (<Wrap>
    {puedeEditarGestoria && revision.length > 0 && <RevisionPanel items={revision} onResolver={resolverPrestamo} />}
    <div className="flex items-center justify-between pr-2">
      <div className="flex items-center gap-2 text-[11px]">
        <span className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-sm font-semibold ${sano ? "bg-[#FFFFFF] text-[#0F8C7D]" : "bg-[#FFFFFF] text-[#6D28D9]"}`}>
          <span className={`w-2 h-2 rounded-full ${sano ? "bg-[#2DD9C3]" : "bg-[#7C3AED]"}`} />
          {sano ? "Operativo" : "Requiere atención"}
        </span>
        {health && (health.enRevisar > 0 || health.problemas.length > 0) &&
          <span className="text-[#777]">{[health.enRevisar ? `${health.enRevisar} por revisar` : "", ...health.problemas].filter(Boolean).join(" · ")}</span>}
        {msg && <span className="text-[#555]">{msg}</span>}
      </div>
      <div className="flex items-center gap-2">
        <Buscador value={busca} onChange={setBusca} placeholder="Buscar nº, proveedor, importe…" />
        <select value={estado} onChange={(e) => setEstado(e.target.value)} className="border border-[#e5e7eb] rounded-sm px-2 py-1 text-[11px]">
          {ESTADOS_GASTO.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <select value={anyo} onChange={(e) => setAnyo(e.target.value)} className="border border-[#e5e7eb] rounded-sm px-2 py-1 text-[11px]">
          {ANYOS_GASTOS.map((y) => <option key={y} value={y}>{y || "Todos los años"}</option>)}
        </select>
        <BtnCSV onClick={exportarCSV} />
        <button onClick={descargarZip} disabled={zipBusy} title="Descargar TODAS las facturas del filtro (PDF) en un ZIP"
          className="inline-flex items-center gap-1.5 rounded-sm border border-[#e5e7eb] px-2.5 py-1.5 text-[11px] font-semibold text-[#065AED] hover:bg-[#065AED]/5 disabled:opacity-60">
          {zipBusy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
          {zipBusy ? "Preparando…" : "Todas (PDF)"}
        </button>
        {puedeEditarGestoria && <>
        <button onClick={clasificarIA} disabled={clasificando} title="La IA razona sobre cada proveedor y clasifica los gastos sin categoría; lo dudoso lo deja en Revisar"
          className="inline-flex items-center gap-2 rounded-sm border border-[#065AED] px-3 py-1.5 text-[12px] font-semibold text-[#065AED] hover:bg-[#065AED]/5 disabled:opacity-60">
          {clasificando ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
          {clasificando ? "Clasificando…" : "Clasificar con IA"}
        </button>
        <button onClick={() => setVerProveedores(true)} title={sinCategoria > 0 ? `Directorio de proveedores · ${sinCategoria} sin categoría` : "Directorio de proveedores"}
          className="relative inline-flex items-center justify-center rounded-sm border border-[#e5e7eb] w-8 h-8 text-[#065AED] hover:bg-[#065AED]/5">
          <Contact className="h-4 w-4" />
          {sinCategoria > 0 && (
            <span className="absolute -top-1.5 -right-1.5 min-w-[16px] h-4 px-1 rounded-full bg-[#C026D3] text-white text-[9px] font-bold flex items-center justify-center leading-none">
              {sinCategoria > 99 ? "99+" : sinCategoria}
            </span>
          )}
        </button>
        <button onClick={procesarBuzon} disabled={buzonBusy}
          title={incidenciasBuzon > 0 ? `Leer el buzón de Gmail · ${incidenciasBuzon} correos en Incidencias esperando tu revisión` : "Leer el buzón de Gmail y dar de alta las facturas nuevas (sin duplicar)"}
          className="relative inline-flex items-center gap-2 rounded-sm border border-[#065AED] px-3 py-1.5 text-[12px] font-semibold text-[#065AED] hover:bg-[#065AED]/5 disabled:opacity-60">
          {buzonBusy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Mail className="h-3.5 w-3.5" />}
          {buzonBusy ? "Procesando…" : "Procesar buzón"}
          {incidenciasBuzon > 0 && (
            <span className="absolute -top-1.5 -right-1.5 min-w-[16px] h-4 px-1 rounded-full bg-[#C026D3] text-white text-[9px] font-bold flex items-center justify-center leading-none">
              {incidenciasBuzon > 99 ? "99+" : incidenciasBuzon}
            </span>
          )}
        </button>
        <input ref={fileRef} type="file" accept=".pdf,.jpg,.jpeg,.png" onChange={onFile} className="hidden" />
        <button onClick={() => fileRef.current?.click()} disabled={subiendo}
          className="inline-flex items-center gap-2 rounded-sm bg-[#065AED] px-3 py-1.5 text-[12px] font-semibold text-white hover:bg-[#054AC2] disabled:opacity-60">
          {subiendo ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />}
          {subiendo ? "Analizando…" : "Subir foto / escaneo"}
        </button>
        </>}
      </div>
    </div>
    <Tbl head={<tr><Th>Nº</Th><Th>Fecha</Th><Th>Proveedor</Th><Th>Nº fact.</Th><Th r>Total</Th><Th>Estado</Th><Th>Forma pago</Th><Th>Apunte banco</Th><Th>Ver</Th></tr>}>
      {visibles.length === 0 ? <tr><td colSpan={9} className="text-center py-8 text-gray-400 italic">{busca ? "Sin facturas que coincidan con la búsqueda." : `${titulo}: sin facturas en este filtro.`}</td></tr>
        : visibles.map((g) => <tr key={g.id} onClick={() => setEditando(g)} className="border-b border-[#f0f3f7] even:bg-[#FFFFFF] hover:bg-[#E6EDFF] cursor-pointer">
          <td className="py-1.5 px-3 text-slate-400 font-mono">{g.id}</td><Td>{fmtFecha(g.fecha)}</Td><Td>{g.proveedor ?? "—"}</Td><Td>{g.numeroFactura ?? "—"}</Td>
          <Td r>{eur(g.total)}</Td>
          <td className="py-1.5 px-3"><span className={`px-1.5 py-0.5 rounded-sm text-[10px] uppercase ${g.estado === "revisar" ? "bg-[#FFFFFF] text-[#6D28D9]" : g.estado === "pagada" ? "bg-[#FFFFFF] text-[#073D8D]" : "bg-white text-slate-600"}`}>{g.estado}</span></td>
          <td className="py-1.5 px-3 text-slate-600">
            <span className="flex flex-col leading-tight">
              <span>{g.formaPago ?? "—"}</span>
              {g.condicionesPago && (
                <span className="text-[10px] text-slate-400 italic" title="Condiciones que traía la factura (no es la forma de pago)">
                  {g.condicionesPago}
                </span>
              )}
            </span>
          </td>
          <td className="py-1.5 px-3" onClick={(e) => e.stopPropagation()}>{esMetalico(g.formaPago)
            ? <span className="inline-flex items-center gap-1 text-[10px] text-slate-500" title="Pago en metálico: no genera apunte bancario">💵 Efectivo · sin apunte</span>
            : esTarjetaExterna(g.formaPago)
            ? <span className="inline-flex items-center gap-1 text-[10px] text-[#0F8C7D] font-semibold" title="Pagado con tarjeta personal de Juan A. Manzanedo: se concilia como apunte externo">💳 Conciliado · tarjeta externa</span>
            : g.movimientoId
            ? <span className="inline-flex items-center gap-1.5 text-[10px] text-[#065AED]">
                <span className="flex flex-col leading-tight">
                  <span>{g.movimientoConcepto}</span>
                  {(g.movimientoFacturas ?? 0) > 1 && (
                    <span className="inline-flex items-center gap-1 text-[9px] font-semibold uppercase text-[#1500A0]"
                          title={`Ese mismo cargo pagó ${g.movimientoFacturas} facturas de golpe`}>
                      <Layers className="w-2.5 h-2.5 shrink-0" />pago unificado · {g.movimientoFacturas} facturas
                    </span>
                  )}
                </span>
                {puedeEditarGestoria && <button onClick={() => gestoriaService.desasociarGasto(g.id).then(cargar)} title="Desasociar" className="text-slate-400 hover:text-[#C026D3]"><X className="w-3 h-3" /></button>}</span>
            : puedeEditarGestoria
            ? <button onClick={() => setAsociando(g)} className="text-[10px] text-[#1ca0d1] hover:text-[#065AED] font-semibold underline">asociar apunte</button>
            : <span className="text-slate-300 text-[10px]">sin apunte</span>}</td>
          <td className="py-1.5 px-3" onClick={(e) => e.stopPropagation()}>{g.archivoPdfUrl
            ? <a href={pdfHref(g.archivoPdfUrl)} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-[#1ca0d1] hover:text-[#065AED] font-semibold"><FileText className="w-3.5 h-3.5" /> ver</a>
            : <span className="text-slate-300">—</span>}</td>
        </tr>)}
    </Tbl>
    {editando && <RevisarModal gasto={editando} onClose={() => setEditando(null)} onSaved={() => { setEditando(null); cargar(); }} />}
    {asociando && <AsociarModal titulo="Asociar apunte (Debe)" lado="Debe"
      subtitulo={`Factura: ${asociando.proveedor ?? "—"} · ${eur(asociando.total)}`}
      cargarLibres={gestoriaService.movimientosDebeLibres}
      asociar={(mid) => gestoriaService.asociarGasto(asociando.id, mid)}
      onClose={() => setAsociando(null)} onSaved={() => { setAsociando(null); cargar(); }} />}
    {verProveedores && <ProveedoresModal onClose={() => { setVerProveedores(false); cargarSinCategoria(); }} />}
  </Wrap>);
}

function ProveedoresModal({ onClose }: { onClose: () => void }) {
  const [rows, setRows] = useState<Proveedor[]>([]);
  const [cat, setCat] = useState<{ categorias: string[]; formasPago: string[] }>({ categorias: [], formasPago: [] });
  const [q, setQ] = useState("");
  const [fCat, setFCat] = useState("");
  const [edit, setEdit] = useState<number | "nuevo" | null>(null);
  const [form, setForm] = useState<Record<string, string>>({});
  const [seleccion, setSeleccion] = useState<Set<number>>(new Set());
  const cargar = useCallback(() => { gestoriaService.proveedores().then((r) => setRows(r.data)); setSeleccion(new Set()); }, []);
  useEffect(() => { cargar(); gestoriaService.proveedoresCatalogos().then(setCat); }, [cargar]);
  const vacio = { nombre: "", cif: "", emailContacto: "", telefono: "", direccion: "", iban: "", categoria: "", formaPago: "" };
  const nuevo = () => { setEdit("nuevo"); setForm({ ...vacio }); };
  const editar = (p: Proveedor) => {
    setEdit(p.id);
    setForm({ nombre: p.nombre, cif: p.cif ?? "", emailContacto: p.emailContacto ?? "", telefono: p.telefono ?? "",
      direccion: p.direccion ?? "", iban: p.iban ?? "", categoria: p.categoria ?? "", formaPago: p.formaPago ?? "" });
  };
  const guardar = async () => {
    if (!form.nombre?.trim()) { alert("El nombre es obligatorio."); return; }
    const payload = { nombre: form.nombre, cif: form.cif, email_contacto: form.emailContacto, telefono: form.telefono,
      direccion: form.direccion, iban: form.iban, categoria: form.categoria, forma_pago: form.formaPago };
    try {
      if (edit === "nuevo") await gestoriaService.crearProveedor(payload);
      else if (typeof edit === "number") await gestoriaService.actualizarProveedor(edit, payload);
      setEdit(null); cargar();
    } catch (e) { alert(`No se pudo guardar: ${e instanceof Error ? e.message : ""}`); }
  };
  const toggleSel = (id: number) => setSeleccion((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const fusionarSel = async () => {
    const elegidos = rows.filter((p) => seleccion.has(p.id));
    if (elegidos.length < 2) return;
    const canon = elegidos.reduce((a, b) => (b.numFacturas > a.numFacturas ? b : a));
    if (!confirm(`Fusionar ${elegidos.length} proveedores en "${canon.nombre}"? Sus facturas se reasignan y los demás se borran.`)) return;
    try {
      await gestoriaService.fusionarProveedores(canon.id, elegidos.filter((p) => p.id !== canon.id).map((p) => p.id));
      cargar();
    } catch (e) { alert(`No se pudo fusionar: ${e instanceof Error ? e.message : ""}`); }
  };
  const borrar = async (p: Proveedor) => {
    if (!confirm(`¿Borrar "${p.nombre}"? Sus ${p.numFacturas} facturas quedarán sin proveedor (conservan el nombre).`)) return;
    try { await gestoriaService.eliminarProveedor(p.id); cargar(); }
    catch (e) { alert(`No se pudo borrar: ${e instanceof Error ? e.message : ""}`); }
  };
  const set = (k: string, v: string) => setForm((p) => ({ ...p, [k]: v }));
  const inp = (k: string, ph: string) => (
    <input value={form[k] ?? ""} onChange={(e) => set(k, e.target.value)} placeholder={ph}
      className={MODAL_INPUT} />
  );
  const sel = (k: string, opts: string[], ph: string) => (
    <select value={form[k] ?? ""} onChange={(e) => set(k, e.target.value)}
      className={MODAL_INPUT}>
      <option value="">{ph}</option>{opts.map((o) => <option key={o} value={o}>{o}</option>)}
    </select>
  );
  const filaEdit = (numFac?: number) => (
    <tr className="bg-[#FFFFFF]">
      <td></td>
      <td className="p-1">{inp("nombre", "Nombre*")}</td>
      <td className="p-1">{inp("direccion", "Dirección")}</td>
      <td className="p-1">{inp("cif", "CIF* (ES/extranj.)")}</td>
      <td className="p-1">{inp("telefono", "Teléfono")}</td>
      <td className="p-1">{inp("emailContacto", "Email")}</td>
      <td className="p-1">{sel("categoria", cat.categorias, "— Categoría —")}</td>
      <td className="p-1">{inp("iban", "IBAN")}</td>
      <td className="p-1">{sel("formaPago", cat.formasPago, "— Pago —")}</td>
      <td className="text-right pr-2 text-slate-500">{numFac ?? ""}</td>
      <td className="p-1 whitespace-nowrap">
        <ModalButton variant="primary" icon={Check} onClick={guardar} className="mr-2">Guardar</ModalButton>
        <ModalButton variant="magenta" icon={X} onClick={() => setEdit(null)}>Cancelar</ModalButton>
      </td>
    </tr>
  );
  const sinCategoria = rows.filter((p) => !p.categoria).length;
  const filtradas = rows.filter((p) =>
    (!q || p.nombre.toLowerCase().includes(q.toLowerCase()) || (p.cif ?? "").toLowerCase().includes(q.toLowerCase()))
    && (!fCat || (fCat === "__sin__" ? !p.categoria : p.categoria === fCat)));
  return (
    <Modal
      title={
        <span className="flex items-center gap-2 flex-wrap">
          <span>Directorio de proveedores</span>
          <span className="text-[11px] font-normal text-[#5F7690]">({rows.length})</span>
          {sinCategoria > 0 && <button onClick={() => setFCat(fCat === "__sin__" ? "" : "__sin__")}
            title="Ver solo los proveedores sin categoría"
            className={`align-middle text-[10px] font-semibold px-2 py-0.5 rounded-full ${fCat === "__sin__" ? "bg-[#C026D3] text-white" : "bg-[#FFFFFF] text-[#C026D3] hover:bg-[#F3CDF8]"}`}>
            {sinCategoria} sin categoría</button>}
        </span>
      }
      onClose={onClose}
      closeOnBackdrop={false}
      size="full"
      className="h-[86vh]"
      footer={
        <>
          {seleccion.size >= 2 && <ModalButton variant="outline" icon={Link2} onClick={fusionarSel}>Fusionar ({seleccion.size})</ModalButton>}
          <ModalButton variant="primary" icon={Plus} onClick={nuevo}>Nuevo</ModalButton>
        </>
      }
    >
      <ModalBody className="!p-0">
        <div className="flex items-center gap-2 px-5 py-3 border-b border-[#BFE4F7] bg-white">
          <div className="w-56">
            <select value={fCat} onChange={(e) => setFCat(e.target.value)} className={MODAL_INPUT}>
              <option value="">Todas las categorías</option>
              <option value="__sin__">— Sin categoría —</option>
              {cat.categorias.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div className="w-64">
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar nombre o CIF…" className={MODAL_INPUT} />
          </div>
        </div>
        <table className="w-full text-[11px] border-collapse">
          <thead className="sticky top-0 z-10 bg-[#21A2E5] text-white"><tr>
            <th className="py-1.5 px-2"></th>
            <Th>Nombre</Th><Th>Dirección</Th><Th>CIF</Th><Th>Teléfono</Th><Th>Email</Th><Th>Categoría</Th><Th>IBAN</Th><Th>Pago</Th><Th r>Fact.</Th><Th>Acciones</Th>
          </tr></thead>
          <tbody>
            {edit === "nuevo" && filaEdit()}
            {filtradas.map((p) => edit === p.id ? filaEdit(p.numFacturas) : (
              <tr key={p.id} className={`border-b border-[#f0f3f7] hover:bg-[#E6EDFF] ${seleccion.has(p.id) ? "bg-[#FFFFFF]" : "even:bg-[#FFFFFF]"}`}>
                <td className="py-1.5 px-2 text-center"><input type="checkbox" checked={seleccion.has(p.id)} onChange={() => toggleSel(p.id)} /></td>
                <Td><span className="font-medium text-slate-700">{p.nombre}</span>{p.esLaboratorio && <span className="ml-1 text-[9px] bg-[#FFFFFF] text-[#073D8D] px-1 rounded">LAB</span>}</Td>
                <Td>{p.direccion ?? "—"}</Td>
                <Td>{p.cif ?? "—"}</Td>
                <Td>{p.telefono ?? "—"}</Td>
                <Td>{p.emailContacto ?? "—"}</Td>
                <td className="py-1.5 px-3">{p.categoria
                  ? <span className="text-slate-600">{p.categoria}</span>
                  : <span className="text-[10px] font-semibold text-[#C026D3] bg-[#FFFFFF] border border-[#C026D3] px-1.5 py-0.5 rounded-sm uppercase" title="Este proveedor no tiene categoría de gasto asignada">Sin categoría</span>}</td>
                <Td>{p.iban ?? "—"}</Td>
                <Td>{p.formaPago ?? "—"}</Td>
                <Td r>{p.numFacturas}</Td>
                <td className="py-1.5 px-3 whitespace-nowrap">
                  <button onClick={() => editar(p)} className="text-[#21A2E5] hover:text-[#073D8D] font-semibold mr-3">editar</button>
                  <button onClick={() => borrar(p)} className="text-[#C026D3] hover:text-[#A21CAF]">borrar</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </ModalBody>
    </Modal>
  );
}

function PdfPan({ gastoId }: { gastoId: number }) {
  const [pags, setPags] = useState<string[]>([]);
  const [cargando, setCargando] = useState(true);
  const [zoom, setZoom] = useState(1);
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const drag = useRef<{ x: number; y: number } | null>(null);
  useEffect(() => {
    let vivo = true;
    setCargando(true); setPos({ x: 0, y: 0 }); setZoom(1);
    gestoriaService.paginasGasto(gastoId).then((r) => { if (vivo) { setPags(r.paginas); setCargando(false); } })
      .catch(() => { if (vivo) setCargando(false); });
    return () => { vivo = false; };
  }, [gastoId]);
  const down = (e: React.MouseEvent) => { drag.current = { x: e.clientX - pos.x, y: e.clientY - pos.y }; };
  const move = (e: React.MouseEvent) => { if (drag.current) setPos({ x: e.clientX - drag.current.x, y: e.clientY - drag.current.y }); };
  const up = () => { drag.current = null; };
  const wheel = (e: React.WheelEvent) => {
    if (e.ctrlKey || e.metaKey) { setZoom((z) => Math.min(4, Math.max(0.3, z - e.deltaY * 0.0015))); return; }  // Ctrl/⌘+rueda = zoom
    setPos((p) => ({ x: p.x - e.deltaX, y: p.y - e.deltaY }));  // rueda = desplazar (vertical; horizontal con Shift)
  };
  if (cargando) return <div className="h-full flex items-center justify-center text-slate-400"><Loader2 className="w-5 h-5 animate-spin" /></div>;
  if (pags.length === 0) return <div className="h-full flex items-center justify-center text-slate-400 text-[12px] italic">No se pudo cargar el documento.</div>;
  return (
    <div className="relative h-full w-full overflow-hidden bg-slate-200 select-none cursor-grab active:cursor-grabbing"
      onMouseDown={down} onMouseMove={move} onMouseUp={up} onMouseLeave={up} onWheel={wheel}>
      <div className="absolute left-1/2 top-3" style={{ transform: `translate(calc(-50% + ${pos.x}px), ${pos.y}px) scale(${zoom})`, transformOrigin: "top center" }}>
        <div className="flex flex-col items-center gap-2">
          {pags.map((src, i) => <img key={i} src={src} draggable={false} alt={`pág ${i + 1}`} className="shadow-lg" style={{ width: 560, maxWidth: "none" }} />)}
        </div>
      </div>
      <div className="absolute bottom-3 right-3 flex items-center gap-1 bg-white/90 rounded-sm shadow px-1 py-0.5">
        <button onClick={() => setZoom((z) => Math.max(0.3, z - 0.2))} className="px-2 text-[#21A2E5] font-bold hover:bg-[#E6EDFF] rounded">−</button>
        <span className="text-[10px] text-slate-500 w-9 text-center">{Math.round(zoom * 100)}%</span>
        <button onClick={() => setZoom((z) => Math.min(4, z + 0.2))} className="px-2 text-[#21A2E5] font-bold hover:bg-[#E6EDFF] rounded">+</button>
        <button onClick={() => { setZoom(1); setPos({ x: 0, y: 0 }); }} title="Ajustar" className="px-1.5 text-[10px] text-slate-500 hover:bg-[#E6EDFF] rounded">⤢</button>
      </div>
    </div>
  );
}

function RevisarModal({ gasto, onClose, onSaved }: { gasto: Gasto; onClose: () => void; onSaved: () => void }) {
  const { puedeEditarGestoria: puedeEditar } = usePermisos();
  const [f, setF] = useState({
    proveedor_extraido: gasto.proveedor ?? "", cif_emisor: gasto.cifEmisor ?? "", numero_factura: gasto.numeroFactura ?? "",
    fecha: gasto.fecha, base_imponible: gasto.baseImponible, iva_pct: gasto.ivaPct, retencion: gasto.retencion ?? 0,
    suplido: gasto.suplido ?? 0,
    total: gasto.total, tipo_documento: gasto.tipoDocumento ?? "factura", divisa: gasto.divisa ?? "EUR",
    forma_pago: gasto.formaPago ?? "",
  });
  const [saving, setSaving] = useState(false);
  const [provs, setProvs] = useState<string[]>([]);
  useEffect(() => { gestoriaService.proveedores().then((r) => setProvs(r.data.map((p) => p.nombre))); }, []);
  const set = (k: string, v: string | number) => setF((p) => ({ ...p, [k]: v }));
  const guardar = async (marcarPagada = false) => {
    setSaving(true);
    try {
      await gestoriaService.actualizarGasto(gasto.id, marcarPagada ? { ...f, estado: "pagada" } : f);
      onSaved();
    } catch (e) { alert(`No se pudo guardar: ${e instanceof Error ? e.message : ""}`); }
    finally { setSaving(false); }
  };
  const eliminar = async () => {
    if (!confirm("¿Eliminar esta factura? No es un gasto real y se borrará de la lista. (No afecta al correo en Gmail).")) return;
    setSaving(true);
    try { await gestoriaService.eliminarGasto(gasto.id); onSaved(); }
    catch (e) { alert(`No se pudo eliminar: ${e instanceof Error ? e.message : ""}`); }
    finally { setSaving(false); }
  };
  // OJO: función invocada con {campo(...)}, NO un componente <Campo/>. Definir un componente aquí
  // dentro lo recrearía en cada tecla y el input perdería el foco al escribir.
  const campo = (label: string, k: keyof typeof f, type = "text", w = "") => (
    <label className={`flex flex-col gap-1 ${w}`} key={k}><span className="text-[10px] uppercase text-[#1ca0d1] font-semibold">{label}</span>
      <input type={type} value={f[k] as string | number} step={type === "number" ? "0.01" : undefined}
        onChange={(e) => set(k, type === "number" ? parseFloat(e.target.value) || 0 : e.target.value)}
        className={MODAL_INPUT} /></label>
  );
  return (
    <Modal title="Revisar factura" onClose={onClose} closeOnBackdrop={false} size="xl" className="h-[86vh]">
      <div className="flex flex-1 min-h-0 overflow-hidden">
        <div className="relative flex-1 bg-white min-w-0">
          {(gasto.archivoPdfUrl || gasto.correoUrl)
            ? <>
                {/* Sin PDF, el visor carga la CAPTURA del correo original (render del correo a imagen). */}
                <PdfPan gastoId={gasto.id} />
                {gasto.correoUrl && !gasto.archivoPdfUrl && <a href={gasto.correoUrl} target="_blank" rel="noopener noreferrer"
                  title="Si la captura no carga (IMAP no disponible), abre el correo en Gmail"
                  className="absolute top-2 left-2 z-10 inline-flex items-center gap-1.5 rounded-full bg-[#21A2E5] px-3 py-1 text-[11px] font-semibold text-white hover:bg-[#073D8D]">
                  <Mail className="w-3 h-3" /> Abrir en Gmail</a>}
              </>
            : <div className="h-full flex flex-col items-center justify-center gap-3 text-slate-400 text-[12px] px-6 text-center">
                <Mail className="w-8 h-8 opacity-40" />
                <div className="italic">Sin PDF ni correo asociado.<br />Concepto: <b className="text-slate-600">{gasto.concepto ?? "—"}</b></div>
              </div>}
        </div>
        <div className="w-[340px] shrink-0 flex flex-col min-h-0 border-l border-[#BFE4F7] bg-white">
          <div className="flex-1 min-h-0 overflow-y-auto p-4">
            <ModalSection tone="blue" title="Datos de la factura" icon={FileText} className="mb-3">
              <div className="flex flex-col gap-3">
                <label className="flex flex-col gap-1"><span className="text-[10px] uppercase text-[#1ca0d1] font-semibold">Proveedor</span>
                  <input list="rev-provs" value={f.proveedor_extraido} onChange={(e) => set("proveedor_extraido", e.target.value)}
                    placeholder="Elige uno o escribe uno nuevo…"
                    className={MODAL_INPUT} />
                  <datalist id="rev-provs">{provs.map((n) => <option key={n} value={n} />)}</datalist>
                </label>
                <label className="flex flex-col gap-1"><span className="text-[10px] uppercase text-[#1ca0d1] font-semibold">CIF / NIF / VAT (identidad fiscal)</span>
                  <input value={f.cif_emisor} onChange={(e) => set("cif_emisor", e.target.value.toUpperCase())}
                    placeholder="p.ej. B12345678 — sin esto el proveedor no entra al directorio"
                    className={MODAL_INPUT} />
                </label>
                <div className="flex gap-2">{campo("Nº factura", "numero_factura", "text", "flex-1")}{campo("Fecha", "fecha", "date", "flex-1")}</div>
                <div className="flex gap-2">
                  <label className="flex flex-col gap-1 flex-1"><span className="text-[10px] uppercase text-[#1ca0d1] font-semibold">Tipo</span>
                    <select value={f.tipo_documento} onChange={(e) => set("tipo_documento", e.target.value)}
                      className={MODAL_INPUT}>
                      <option value="factura">Factura</option><option value="abono">Abono</option><option value="rectificativa">Rectificativa</option>
                    </select></label>
                  <label className="flex flex-col gap-1 w-20"><span className="text-[10px] uppercase text-[#1ca0d1] font-semibold">Divisa</span>
                    <input value={f.divisa} onChange={(e) => set("divisa", e.target.value.toUpperCase().slice(0, 3))}
                      className={MODAL_INPUT} /></label>
                </div>
                <label className="flex flex-col gap-1"><span className="text-[10px] uppercase text-[#1ca0d1] font-semibold">Forma de pago</span>
                  <select value={f.forma_pago} onChange={(e) => set("forma_pago", e.target.value)}
                    className={MODAL_INPUT}>
                    <option value="">— Forma de pago —</option>
                    {f.forma_pago && !FORMAS_PAGO_GASTO.includes(f.forma_pago) &&
                      <option value={f.forma_pago}>{f.forma_pago} (actual)</option>}
                    {FORMAS_PAGO_GASTO.map((n) => <option key={n} value={n}>{n}</option>)}
                  </select>
                  {esMetalico(f.forma_pago) && <span className="text-[10px] text-slate-500">💵 En metálico no hay apunte bancario que asociar.</span>}
                  {esTarjetaExterna(f.forma_pago) && <span className="text-[10px] text-[#0F8C7D]">💳 Tarjeta externa (fuera de la cuenta de la clínica): se concilia como apunte externo, sin apunte propio.</span>}
                </label>
                <div className="flex gap-2">{campo("Base €", "base_imponible", "number", "flex-1")}{campo("IVA %", "iva_pct", "number", "flex-1")}</div>
                <div className="flex gap-2">{campo("Retención €", "retencion", "number", "flex-1")}{campo("Suplido €", "suplido", "number", "flex-1")}{campo("Total €", "total", "number", "flex-1")}</div>
              </div>
            </ModalSection>
            <p className="text-[10px] text-slate-500 leading-tight">El <b>suplido</b> (gasto exento que adelanta el proveedor, p.ej. Consenur) va aparte del IVA: <code>total = base + IVA − retención + suplido</code>. Al guardar con total y proveedor, pasa a <b>pendiente</b>.</p>
          </div>
          {puedeEditar && (
            <ModalFooter className="!flex-col !items-stretch !gap-2">
              <ModalButton variant="primary" onClick={() => guardar(false)} disabled={saving}>
                <IconoGuardar cargando={saving}>Guardar</IconoGuardar>
              </ModalButton>
              <ModalButton variant="outline" onClick={() => guardar(true)} disabled={saving}>Guardar y marcar pagada</ModalButton>
              <ModalButton variant="magenta" icon={Trash2} onClick={eliminar} disabled={saving}>Eliminar (no es factura)</ModalButton>
            </ModalFooter>
          )}
        </div>
      </div>
    </Modal>
  );
}
export const Gastos = () => (
  <>
    <GastosBase titulo="Facturas" />
    {/* <IAFacturasPanel centroId={0} puedeEditar={true} />  Temporarily disabled */}
  </>
);

function AsociarModal({ titulo, subtitulo, lado, cargarLibres, asociar, onClose, onSaved, opcionLabel, vacioMsg }: {
  titulo: string; subtitulo: string; lado: "Debe" | "Haber";
  cargarLibres: () => Promise<{ data: { id: number; label: string }[] }>;
  asociar: (movimientoId: number) => Promise<unknown>;
  onClose: () => void; onSaved: () => void;
  opcionLabel?: string; vacioMsg?: string;
}) {
  const [libres, setLibres] = useState<{ id: number; label: string }[]>([]);
  const [sel, setSel] = useState<string>("");
  const [saving, setSaving] = useState(false);
  useEffect(() => { cargarLibres().then((r) => setLibres(r.data)); }, [cargarLibres]);
  const guardar = async () => {
    if (!sel) return;
    setSaving(true);
    try { await asociar(Number(sel)); onSaved(); }
    catch (e) { alert(`No se pudo asociar: ${e instanceof Error ? e.message : ""}`); }
    finally { setSaving(false); }
  };
  return (
    <Modal title={titulo} subtitle={subtitulo} onClose={onClose} closeOnBackdrop={false} size="sm"
      footer={
        <ModalButton variant="primary" onClick={guardar} disabled={saving || !sel}>
          <IconoGuardar cargando={saving}>Asociar</IconoGuardar>
        </ModalButton>
      }
    >
      <ModalBody>
        {libres.length === 0
          ? <p className="text-[12px] text-[#7C3AED] italic">{vacioMsg ?? `No hay apuntes del ${lado} libres. Sube el extracto en la pestaña Debe/Haber.`}</p>
          : <select value={sel} onChange={(e) => setSel(e.target.value)} className={MODAL_INPUT}>
              <option value="">{opcionLabel ?? `— Elige un apunte del ${lado} —`}</option>
              {libres.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
            </select>}
      </ModalBody>
    </Modal>
  );
}

const TIPOS_MOV = [["", "Todos"], ["debe", "Debe (gastos)"], ["haber", "Haber (ingresos)"]];

// Deep-link desde INICIO: /gestoria/facturacion?tab=debehaber&mov=<id> aísla ese apunte
// en el buscador (que ya filtra por id), para no dejar al usuario buscándolo entre miles.
function movDeepLink(): string | null {
  if (typeof window === "undefined") return null;
  const m = new URLSearchParams(window.location.search).get("mov");
  return m && /^\d+$/.test(m) ? m : null;
}

export function DebeHaber({ tabs, activeTab, onChange }: { tabs: { id: string; label: string }[]; activeTab: string; onChange: (id: string) => void }) {
  const { puedeEditarGestoria } = usePermisos();
  const [rows, setRows] = useState<Movimiento[]>([]);
  const [tipo, setTipo] = useState("");
  const [anyo, setAnyo] = useState("");
  const [movFoco, setMovFoco] = useState<string | null>(null);
  const [busca, setBusca] = useState("");
  // Deep-link desde INICIO: ?tab=debehaber&mov=<id> aísla ese apunte en el buscador
  // (que ya filtra por id), para no dejar al usuario buscándolo entre miles.
  useEffect(() => {
    const mov = movDeepLink();
    if (mov) { setBusca(mov); setMovFoco(mov); }
  }, []);
  const [cargando, setCargando] = useState(false);
  const [cuadrando, setCuadrando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [nuevo, setNuevo] = useState(false);
  const [extractos, setExtractos] = useState<Extracto[]>([]);
  const [verExtractos, setVerExtractos] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const cargar = useCallback(() => {
    gestoriaService.movimientos(tipo || undefined, anyo ? Number(anyo) : undefined).then((r) => setRows(r.data));
  }, [tipo, anyo]);
  const cargarExtractos = useCallback(() => {
    gestoriaService.listarExtractos().then((r) => setExtractos(r.extractos)).catch(() => setExtractos([]));
  }, []);
  useEffect(() => { cargarExtractos(); }, [cargarExtractos]);
  // Con deep-link (?mov=<id>) el filtro es por id EXACTO; si el usuario edita el buscador, vuelve al modo texto.
  const mostrados = (movFoco && busca === movFoco)
    ? rows.filter((m) => String(m.id) === movFoco)
    : rows.filter((m) => coincide(busca, m.id, m.conceptoBanco, m.fechaOperacion, m.importe, m.gastoId, m.asociado?.proveedor, m.asociado?.numero));
  useEffect(() => { cargar(); }, [cargar]);
  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setCargando(true); setMsg(null);
    try {
      const r = await gestoriaService.importarBancoXlsx(file);
      setMsg(`Importados ${r.importados} · omitidos ${r.omitidos} · descartados ${r.descartadas}`);
      cargar();
      cargarExtractos();   // el fichero queda archivado para la asesoría
    } catch (err) {
      setMsg(`Error: ${err instanceof Error ? err.message : "no se pudo importar"}`);
    } finally { setCargando(false); }
  };
  const cuadrarBanco = async () => {
    setCuadrando(true); setMsg(null);
    try {
      const p = await gestoriaService.cuadrarBanco(false);   // previsualiza
      const gen = p.generadas.alquiler + p.generadas.parking + p.generadas.colaborador + p.generadas.renting;
      const con = p.contabilizadas.impuesto + p.contabilizadas.retencion + p.contabilizadas.ss + p.contabilizadas.seguro;
      if (gen + con === 0) { setMsg(`Banco cuadrado: nada nuevo que generar (${p.revision} a revisar).`); return; }
      const ok = window.confirm(
        `Conciliación:\n\n· ${p.generadas.alquiler} alquiler · ${p.generadas.parking} parking · ${p.generadas.renting} renting · ${p.generadas.colaborador} autofacturas de colaboradores\n` +
        `· ${con} impuestos/SS/seguros a contabilizar\n· ${p.revision} quedan en revisión\n\n¿Generar y conciliar ahora?`);
      if (!ok) { setMsg(`${gen} a generar · ${con} a contabilizar · ${p.revision} a revisar. Sin ejecutar.`); return; }
      const r = await gestoriaService.cuadrarBanco(true);    // ejecuta
      setMsg(`Banco cuadrado: +${r.generadas.alquiler + r.generadas.parking + r.generadas.colaborador + r.generadas.renting} generadas · ` +
        `+${r.contabilizadas.impuesto + r.contabilizadas.retencion + r.contabilizadas.ss + r.contabilizadas.seguro} contabilizadas · ` +
        `${r.conciliadas_existentes} casadas · ${r.requiere_datos} piden dato · ${r.revision} a revisar`);
      cargar();
    } catch (e) { setMsg(`Error: ${e instanceof Error ? e.message : ""}`); }
    finally { setCuadrando(false); }
  };
  const borrarApunte = async (m: Movimiento) => {
    if (!confirm(`¿Borrar el apunte de ${fmtFecha(m.fechaOperacion)} · ${eur(Math.abs(m.importe))}? Esta acción no se puede deshacer.`)) return;
    try { await gestoriaService.borrarMovimiento(m.id); cargar(); }
    catch (e) { alert(`No se pudo borrar: ${e instanceof Error ? e.message : ""}`); }
  };
  return (<>
    {/* Barra del buscador integrada al FINAL de la línea de pestañas (ahorra una fila) */}
    <AreaTabs tabs={tabs} activeTab={activeTab} onChange={onChange} className="pt-2"
      right={
        <div className="flex items-center gap-2">
          <span className="text-[12px] text-[#7f8c8d] whitespace-nowrap shrink-0"><b className="text-[#1500A0]">{mostrados.length}</b> apunte{mostrados.length === 1 ? "" : "s"}</span>
          {movFoco && busca === movFoco && (
            <button onClick={() => { setMovFoco(null); setBusca(""); }}
              className="text-[11px] font-semibold text-[#065AED] hover:underline shrink-0 whitespace-nowrap">
              Mostrando solo el apunte #{movFoco} — ver todos
            </button>
          )}
          {msg && <span className="text-[11px] text-[#555] max-w-[160px] truncate shrink-0" title={msg}>{msg}</span>}
          <Buscador value={busca} onChange={(v) => { if (movFoco) setMovFoco(null); setBusca(v); }} placeholder="Buscar nº, concepto, importe…" />
          <select value={tipo} onChange={(e) => setTipo(e.target.value)} className="border border-[#e5e7eb] rounded-sm px-2 py-1 text-[11px]">
            {TIPOS_MOV.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <select value={anyo} onChange={(e) => setAnyo(e.target.value)} className="border border-[#e5e7eb] rounded-sm px-2 py-1 text-[11px]">
            {ANYOS_GASTOS.map((y) => <option key={y} value={y}>{y || "Todos los años"}</option>)}
          </select>
          {/* EL MISMO fichero que Envío manda a la asesoría (bancos_{año}.csv). */}
          <BtnCSV onClick={() => gestoriaService.descargarSeccionCsv("bancos", Number(anyo) || new Date().getFullYear())
            .then(() => setMsg(null)).catch((e) => setMsg(`Error: ${e instanceof Error ? e.message : ""}`))} />
          {/* Ficheros de extracto TAL CUAL se subieron: soporte documental para la asesoría. */}
          <button onClick={() => setVerExtractos((v) => !v)}
            title="Extractos originales subidos (para la asesoría)"
            className={`inline-flex items-center gap-1.5 shrink-0 whitespace-nowrap rounded-sm border px-2.5 py-1.5 text-[12px] font-semibold ${verExtractos ? "border-[#1500A0] bg-[#1500A0] text-white" : "border-[#9ca3af] text-[#1500A0] hover:bg-[#E6EDFF]"}`}>
            <FileText className="h-3.5 w-3.5" />
            Extractos{extractos.length ? ` (${extractos.length})` : ""}
          </button>
          {puedeEditarGestoria && <>
          <button onClick={cuadrarBanco} disabled={cuadrando} title="Conciliación: casar facturas y generar los recurrentes (alquiler, parking, colaboradores, impuestos)"
            className="inline-flex items-center gap-1.5 shrink-0 whitespace-nowrap rounded-sm border border-[#065AED] px-2.5 py-1.5 text-[12px] font-semibold text-[#065AED] hover:bg-[#065AED]/5 disabled:opacity-60">
            {cuadrando ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle className="h-3.5 w-3.5" />}
            {cuadrando ? "Conciliando…" : "Conciliación"}
          </button>
          <input ref={fileRef} type="file" accept=".pdf,.xlsx,.xls,.csv,.txt" onChange={onFile} className="hidden" />
          <button onClick={() => fileRef.current?.click()} disabled={cargando} title="Subir extracto bancario (PDF, XLSX, XLS o CSV)"
            className="inline-flex items-center gap-1.5 shrink-0 whitespace-nowrap rounded-sm border border-[#065AED] px-2.5 py-1.5 text-[12px] font-semibold text-[#065AED] hover:bg-[#065AED]/5 disabled:opacity-60">
            {cargando ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />}
            {cargando ? "Importando…" : "Subir"}
          </button>
          <button onClick={() => setNuevo(true)} title="Nuevo apunte"
            className="inline-flex items-center gap-1.5 shrink-0 whitespace-nowrap rounded-sm bg-[#065AED] px-2.5 py-1.5 text-[12px] font-semibold text-white hover:bg-[#054AC2]">
            <Plus className="h-3.5 w-3.5" /> Nuevo
          </button>
          </>}
        </div>
      } />
    {/* Extractos originales archivados: lo que la asesoría descarga como soporte. */}
    {verExtractos && (
      <div className="mx-3 mt-2 rounded-sm border border-[#e5e7eb] bg-white shadow-sm">
        <div className="px-3 py-2 border-b border-[#e5e7eb] text-[11px] font-semibold uppercase tracking-wide text-[#1500A0]">
          Extractos subidos — fichero original
        </div>
        {extractos.length === 0
          ? <div className="px-3 py-4 text-[12px] text-gray-400 italic">
              Aún no hay extractos archivados. Los ficheros que subas a partir de ahora quedarán aquí para descargar.
            </div>
          : <table className="w-full text-[12px]">
              <thead><tr className="text-left text-[#7f8c8d]">
                <th className="py-1.5 px-3 font-semibold">Fichero</th>
                <th className="py-1.5 px-3 font-semibold">Subido</th>
                <th className="py-1.5 px-3 font-semibold">Por</th>
                <th className="py-1.5 px-3 font-semibold text-right">Apuntes</th>
                <th className="py-1.5 px-3 font-semibold text-right">Tamaño</th>
                <th className="py-1.5 px-3" />
              </tr></thead>
              <tbody>
                {extractos.map((x) => (
                  <tr key={x.id} className="border-t border-[#f0f3f7] even:bg-[#FFFFFF] hover:bg-[#E6EDFF]">
                    <td className="py-1.5 px-3"><span className="inline-flex items-center gap-1.5"><FileText className="h-3.5 w-3.5 text-[#1ca0d1]" />{x.nombre}</span></td>
                    <td className="py-1.5 px-3">{fmtFecha(x.fecha)}</td>
                    <td className="py-1.5 px-3">{x.subidoPor}</td>
                    <td className="py-1.5 px-3 text-right">{x.importados} nuevos · {x.omitidos} ya estaban</td>
                    <td className="py-1.5 px-3 text-right">{Math.max(1, Math.round(x.tamano / 1024))} KB</td>
                    <td className="py-1.5 px-3 text-right">
                      <button onClick={() => gestoriaService.descargarExtracto(x.id, x.nombre)
                        .catch((e) => setMsg(`Error: ${e instanceof Error ? e.message : ""}`))}
                        className="inline-flex items-center gap-1 text-[#1ca0d1] hover:text-[#065AED] font-semibold">
                        <Download className="h-3.5 w-3.5" /> Descargar
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>}
      </div>
    )}
    <Wrap>
    <Tbl head={<tr><Th>Nº</Th><Th>Fecha</Th><Th>Concepto</Th><Th r>Debe</Th><Th r>Haber</Th><Th>Asociado</Th><Th></Th></tr>}>
      {mostrados.length === 0 ? <tr><td colSpan={7} className="text-center py-8 text-gray-400 italic">{busca ? "Sin apuntes que coincidan con la búsqueda." : "Sin apuntes. Sube el extracto (PDF, XLSX o CSV) o crea uno manual."}</td></tr>
        : mostrados.map((m) => {
          // Debe sin factura ni pago encontrados: se destaca en rojo para que salte a la vista.
          const sinAsociar = m.importe < 0 && !m.asociado && !m.gastoId && !m.pagoId;
          return <tr key={m.id} className="border-b border-[#f0f3f7] even:bg-[#FFFFFF] hover:bg-[#E6EDFF]">
          <td className={`py-1.5 px-3 font-mono ${sinAsociar ? "text-[#C026D3]" : "text-slate-400"}`}>{m.id}</td>
          <Td cls={sinAsociar ? "text-[#C026D3]" : undefined}>{fmtFecha(m.fechaOperacion)}</Td>
          <td className={`py-1.5 px-3 ${sinAsociar ? "text-[#C026D3]" : "text-slate-600"}`} onClick={(e) => e.stopPropagation()}>
            <ConceptoCell m={m} puedeEditar={puedeEditarGestoria} onSaved={cargar} />
          </td>
          <td className="py-1.5 px-3 text-right font-semibold text-[#C026D3]">{m.importe < 0 ? eur(Math.abs(m.importe)) : ""}</td>
          <td className="py-1.5 px-3 text-right font-semibold text-[#065AED]">{m.importe >= 0 ? eur(m.importe) : ""}</td>
          <td className="py-1.5 px-3"><AsociadoCell m={m} puedeEditar={puedeEditarGestoria} onSaved={cargar} /></td>
          <td className="py-1.5 px-3 text-right" onClick={(e) => e.stopPropagation()}>
            {puedeEditarGestoria && (
              <button onClick={() => borrarApunte(m)} title="Borrar apunte"
                      className="text-slate-400 hover:text-[#C026D3]"><Trash2 className="w-3.5 h-3.5" /></button>
            )}
          </td>
        </tr>;
        })}
    </Tbl>
    {nuevo && <NuevoApunteModal onClose={() => setNuevo(false)} onSaved={() => { setNuevo(false); cargar(); }} />}
  </Wrap>
  </>);
}

/** Concepto del apunte. El rótulo que la clínica escribe al ordenar una transferencia se
 * equivoca a veces (dos pagos seguidos como "Producción Dic" cuando el 2º era enero). Aquí
 * se corrige SIN tocar el extracto: el literal del banco se conserva y se enseña debajo. */
function ConceptoCell({ m, puedeEditar, onSaved }: { m: Movimiento; puedeEditar: boolean; onSaved: () => void }) {
  const [editando, setEditando] = useState(false);
  const [texto, setTexto] = useState(m.conceptoBanco);
  const [guardando, setGuardando] = useState(false);
  const guardar = async (valor: string | null) => {
    setGuardando(true);
    try { await gestoriaService.corregirConcepto(m.id, valor); setEditando(false); onSaved(); }
    finally { setGuardando(false); }
  };
  if (editando) {
    return <div className="flex items-center gap-1">
      <input autoFocus value={texto} onChange={(e) => setTexto(e.target.value)}
             onKeyDown={(e) => { if (e.key === "Enter") guardar(texto); if (e.key === "Escape") setEditando(false); }}
             className="flex-1 min-w-[240px] border border-[#1ca0d1] rounded px-1.5 py-0.5 text-[12px]" />
      <button disabled={guardando} onClick={() => guardar(texto)}
              className="text-[10px] font-semibold text-[#1ca0d1] hover:text-[#065AED]">guardar</button>
      {m.conceptoOriginal && (
        <button disabled={guardando} onClick={() => guardar(null)} title="Volver a lo que dice el extracto"
                className="text-[10px] text-slate-400 hover:text-[#C026D3]">deshacer</button>
      )}
    </div>;
  }
  return <div className="flex flex-col leading-tight">
    <span className="inline-flex items-center gap-1">
      {m.conceptoBanco}
      {puedeEditar && (
        <button onClick={() => { setTexto(m.conceptoBanco); setEditando(true); }} title="Corregir el concepto"
                className="text-slate-300 hover:text-[#1ca0d1]"><Pencil className="w-3 h-3" /></button>
      )}
    </span>
    {m.conceptoOriginal && (
      <span className="text-[10px] text-slate-400 italic" title="Texto literal del extracto bancario">
        extracto: {m.conceptoOriginal}
      </span>
    )}
  </div>;
}

/** Columna "Asociado" de Debe/Haber: muestra la FACTURA REAL (proveedor + nº) y enlaza a
 * su PDF. Antes solo ponía "Factura #123" — un id interno que no dice nada ni lleva a nada. */
function AsociadoCell({ m, puedeEditar, onSaved }: { m: Movimiento; puedeEditar: boolean; onSaved: () => void }) {
  const [conciliarManual, setConciliarManual] = useState(false);
  const a = m.asociado;
  const desasociar = (gastoId: number) =>
    gestoriaService.desasociarGasto(gastoId).then(onSaved).catch((e) => alert(`No se pudo desasociar: ${e instanceof Error ? e.message : ""}`));
  // Pago unificado: una sola transferencia liquidó varias facturas. Se listan todas,
  // cada una con su enlace, para que la gestoría vea de qué se compone el importe.
  if (a?.tipo === "factura" && a.unificado) {
    return <div className="flex flex-col gap-0.5">
      <span className="inline-flex items-center gap-1 text-[10px] font-semibold uppercase text-[#065AED]"
            title={`Un solo pago de ${eur(Math.abs(m.importe))} que liquida ${a.unificado.length} facturas`}>
        <Layers className="w-3 h-3 shrink-0" />Pago unificado · {a.unificado.length} facturas
      </span>
      {a.unificado.map((f) => (
        <span key={f.id} className="text-[11px] leading-tight inline-flex items-center gap-1">
          {f.tienePdf
            ? <a href={pdfHref(`/gestoria/gastos/${f.id}/pdf`)} target="_blank" rel="noopener noreferrer"
                 className="text-[#1ca0d1] hover:text-[#065AED] font-semibold">
                {f.numero ?? `#${f.id}`}
              </a>
            : <span className="text-[#065AED] font-semibold">{f.numero ?? `#${f.id}`}</span>}
          <span className="text-slate-500"> · {eur(f.total)}</span>
          {puedeEditar && (
            <button onClick={() => desasociar(f.id)} title="Desasociar (revertir conciliación)"
                    className="text-slate-400 hover:text-[#C026D3]"><X className="w-3 h-3" /></button>
          )}
        </span>
      ))}
      {a.totalUnificado !== undefined && Math.abs(a.totalUnificado - Math.abs(m.importe)) >= 0.01 && (
        <span className="text-[10px] text-[#7C3AED]"
              title="Las facturas asociadas no suman el importe del apunte">
          sin asignar {eur(Math.abs(m.importe) - a.totalUnificado)}
        </span>
      )}
    </div>;
  }
  if (a?.tipo === "factura") {
    const etiqueta = [a.proveedor, a.numero && `nº ${a.numero}`].filter(Boolean).join(" · ");
    const titulo = `Factura ${a.numero ?? `#${a.id}`}${a.proveedor ? ` de ${a.proveedor}` : ""}`
      + `${a.fecha ? ` (${fmtFecha(a.fecha)})` : ""} · ${eur(a.total)}`;
    return <span className="inline-flex items-center gap-1">
      {a.tienePdf
        ? <a href={pdfHref(`/gestoria/gastos/${a.id}/pdf`)} target="_blank" rel="noopener noreferrer"
             title={`${titulo} — abrir PDF`}
             className="inline-flex items-center gap-1 text-[11px] text-[#1ca0d1] hover:text-[#065AED] font-semibold">
            <FileText className="w-3.5 h-3.5 shrink-0" />{etiqueta || `Factura #${a.id}`}
          </a>
        : <span className="text-[11px] text-[#065AED]" title={`${titulo} — sin PDF archivado`}>
            {etiqueta || `Factura #${a.id}`}
          </span>}
      {puedeEditar && (
        <button onClick={() => desasociar(a.id)} title="Desasociar (revertir conciliación)"
                className="text-slate-400 hover:text-[#C026D3]"><X className="w-3 h-3" /></button>
      )}
    </span>;
  }
  if (a?.tipo === "pago") {
    return <span className="text-[11px] text-[#065AED]" title={`Pago de paciente · ${eur(a.total)}`}>
      Pago de paciente{a.fecha ? ` (${fmtFecha(a.fecha)})` : ""}
    </span>;
  }
  // Conciliado contra algo que ya no existe (factura borrada): avisar, no mentir.
  if (m.gastoId || m.pagoId) {
    return <span className="text-[11px] text-[#7C3AED]" title="El documento asociado ya no existe">
      Asociado #{m.gastoId ?? m.pagoId} (no encontrado)
    </span>;
  }
  if (m.importe >= 0) {
    return <span className="text-[11px] text-slate-400" title="Entrada (cobro): un Haber no es una factura">— ingreso</span>;
  }
  if (!puedeEditar) {
    return <span className="text-[11px] text-[#C026D3]">— sin asociar</span>;
  }
  return <>
    <button onClick={() => setConciliarManual(true)}
            className="text-[11px] text-[#C026D3] hover:text-[#A21CAF] font-semibold underline">
      Conciliar manualmente
    </button>
    {conciliarManual && (
      <AsociarModal titulo="Conciliar manualmente" lado="Debe"
        subtitulo={`Apunte: ${fmtFecha(m.fechaOperacion)} · ${(m.conceptoBanco || "").slice(0, 60)} · ${eur(Math.abs(m.importe))}`}
        opcionLabel="— Elige una factura —"
        vacioMsg="No hay facturas sin asociar disponibles."
        cargarLibres={gestoriaService.gastosLibres}
        asociar={(gid) => gestoriaService.asociarGasto(gid, m.id)}
        onClose={() => setConciliarManual(false)}
        onSaved={() => { setConciliarManual(false); onSaved(); }} />
    )}
  </>;
}

function NuevoApunteModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [tipo, setTipo] = useState<"debe" | "haber">("debe");
  const [fecha, setFecha] = useState("");
  const [concepto, setConcepto] = useState("");
  const [importe, setImporte] = useState("");
  const [saving, setSaving] = useState(false);
  const guardar = async () => {
    const imp = Math.abs(parseFloat(importe) || 0);
    if (!fecha || !concepto.trim() || !imp) { alert("Completa fecha, concepto e importe."); return; }
    setSaving(true);
    try {
      await gestoriaService.crearMovimiento({
        fecha_operacion: fecha, concepto_banco: concepto.trim(),
        importe: tipo === "debe" ? -imp : imp,
      });
      onSaved();
    } catch (e) { alert(`No se pudo crear: ${e instanceof Error ? e.message : ""}`); }
    finally { setSaving(false); }
  };
  return (
    <Modal title="Nuevo apunte bancario" onClose={onClose} closeOnBackdrop={false} size="sm"
      footer={
        <ModalButton variant="primary" onClick={guardar} disabled={saving}>
          <IconoGuardar cargando={saving}>Crear apunte</IconoGuardar>
        </ModalButton>
      }
    >
      <ModalTabs
        tabs={[{ id: "debe", label: "Debe (gasto)" }, { id: "haber", label: "Haber (ingreso)" }]}
        activeTab={tipo}
        onChange={(id) => setTipo(id as "debe" | "haber")}
      />
      <ModalBody>
        <div className="flex flex-col gap-3">
          <label className="flex flex-col gap-1"><span className="text-[10px] uppercase text-[#1ca0d1] font-semibold">Fecha</span>
            <input type="date" value={fecha} onChange={(e) => setFecha(e.target.value)} className={MODAL_INPUT} /></label>
          <label className="flex flex-col gap-1"><span className="text-[10px] uppercase text-[#1ca0d1] font-semibold">Concepto</span>
            <input value={concepto} onChange={(e) => setConcepto(e.target.value)} className={MODAL_INPUT} /></label>
          <label className="flex flex-col gap-1"><span className="text-[10px] uppercase text-[#1ca0d1] font-semibold">Importe €</span>
            <input type="number" step="0.01" value={importe} onChange={(e) => setImporte(e.target.value)} className={MODAL_INPUT} /></label>
        </div>
      </ModalBody>
    </Modal>
  );
}

export function Modelos() {
  // Deep-link desde INICIO: ?modelo=303&periodo=1T&ejercicio=2026 resalta esa fila.
  const foco = (() => {
    if (typeof window === "undefined") return null;
    const q = new URLSearchParams(window.location.search);
    const m = q.get("modelo");
    return m ? { modelo: m, periodo: q.get("periodo") || "", ejercicio: q.get("ejercicio") || "" } : null;
  })();
  const [anyo, setAnyo] = useState(foco?.ejercicio ? Number(foco.ejercicio) : Y);
  const [rows, setRows] = useState<Vencimiento[]>([]);
  const [gen, setGen] = useState<string | null>(null);
  const focoRef = useRef<HTMLTableRowElement | null>(null);
  const cargar = useCallback(() => { gestoriaService.calendarioTributario(anyo).then((r) => setRows(r.data)); }, [anyo]);
  useEffect(() => { cargar(); }, [cargar]);
  useEffect(() => {
    if (foco && rows.length && focoRef.current) {
      focoRef.current.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }, [rows]); // eslint-disable-line react-hooks/exhaustive-deps
  const generar = async (v: Vencimiento) => {
    setGen(`${v.modelo}-${v.periodo}`);
    try { await gestoriaService.generarModelo(v.modelo, v.periodo, anyo); cargar(); }
    catch (e) { alert(`No se pudo generar: ${e instanceof Error ? e.message : ""}`); }
    finally { setGen(null); }
  };
  const badge = (estado: string) => estado === "presentado" ? "bg-[#FFFFFF] text-[#073D8D]"
    : estado === "vencido" ? "bg-[#FFFFFF] text-[#C026D3]" : "bg-[#FFFFFF] text-[#6D28D9]";
  return (<Wrap>
    <div className="flex justify-end">
      <select value={anyo} onChange={(e) => setAnyo(Number(e.target.value))} className="border border-[#e5e7eb] rounded-sm px-2 py-1 text-[11px] self-start">{YEARS.map((y) => <option key={y}>{y}</option>)}</select></div>
    <Tbl head={<tr><Th>Modelo</Th><Th>Concepto</Th><Th>Periodo</Th><Th>Fecha límite</Th><Th r>Cuota</Th><Th>Estado</Th><Th>Acción</Th></tr>}>
      {rows.map((v) => {
        const esFoco = !!foco && String(v.modelo) === foco.modelo && (v.periodo || "") === foco.periodo;
        return <tr key={`${v.modelo}-${v.periodo}`} ref={esFoco ? focoRef : undefined}
          className={`border-b border-[#f0f3f7] ${esFoco ? "bg-[#FFFFFF] ring-2 ring-[#A78BFA]" : "even:bg-[#FFFFFF] hover:bg-[#E6EDFF]"}`}>
        <Td><b className="text-[#065AED]">{v.modelo}</b></Td><Td>{v.descripcion}</Td><Td>{v.periodo}</Td><Td>{fmtFecha(v.fechaLimite)}</Td>
        <Td r>{v.cuota != null ? eur(v.cuota) : "—"}</Td>
        <td className="py-1.5 px-3"><span className={`px-1.5 py-0.5 rounded-sm text-[10px] uppercase ${badge(v.estado)}`}>{v.estado}</span></td>
        <td className="py-1.5 px-3">
          <button onClick={() => generar(v)} disabled={gen === `${v.modelo}-${v.periodo}`}
            className="inline-flex items-center gap-1 text-[11px] text-[#1ca0d1] hover:text-[#065AED] font-semibold disabled:opacity-50">
            {gen === `${v.modelo}-${v.periodo}` ? <Loader2 className="w-3 h-3 animate-spin" /> : <FileText className="w-3 h-3" />}
            {v.id ? "regenerar" : "generar"}
          </button></td>
      </tr>;
      })}
    </Tbl>
  </Wrap>);
}

export function Pagos() {
  const [rows, setRows] = useState<PagoPaciente[]>([]);
  const [formas, setFormas] = useState<string[]>([]);
  const [anyo, setAnyo] = useState("");
  const [forma, setForma] = useState("");
  const [mes, setMes] = useState("");   // filtros de mes y día (cliente: filtran lo ya cargado del año/forma)
  const [dia, setDia] = useState("");
  const [busca, setBusca] = useState("");
  const [asociando, setAsociando] = useState<PagoPaciente | null>(null);
  const { puedeEditarGestoria } = usePermisos();
  const [conciliando, setConciliando] = useState(false);
  const [tjMsg, setTjMsg] = useState<string | null>(null);
  const cargar = useCallback(() => {
    gestoriaService.pagosPacientes(anyo ? Number(anyo) : undefined, forma || undefined)
      .then((r) => { setRows(r.data); setFormas(r.formas); });
  }, [anyo, forma]);
  const conciliarTarjetas = async () => {
    setConciliando(true); setTjMsg(null);
    try {
      const p = await gestoriaService.conciliarTarjetas(false);   // previsualiza
      const falta = p.huecos.reduce((s, h) => s + h.falta, 0);
      const ok = window.confirm(
        `Conciliación de tarjeta (${p.liquidaciones} liquidaciones):\n\n` +
        `· ${p.conciliadas} cuadran con su lote de pagos (comisión ${eur(p.comision_total)})\n` +
        `· ${p.huecos.length} liquidaciones sin pagos suficientes → faltan ${eur(falta)} por registrar\n` +
        `· ${p.sin_cuadre} quedan para revisar a mano\n\nMarcar pagos como liquidados y señalar los huecos?`);
      if (!ok) { setTjMsg(`Previsualización: ${p.conciliadas} cuadran · ${p.huecos.length} huecos (${eur(falta)}). Sin ejecutar.`); return; }
      const r = await gestoriaService.conciliarTarjetas(true);    // ejecuta
      const faltaR = r.huecos.reduce((s, h) => s + h.falta, 0);
      setTjMsg(`Tarjetas conciliadas: ${r.conciliadas}/${r.liquidaciones} · ${r.pagos_marcados} pagos liquidados · ${r.huecos.length} huecos (faltan ${eur(faltaR)} por registrar).`);
      cargar();
    } catch (e) { setTjMsg(`Error: ${e instanceof Error ? e.message : ""}`); }
    finally { setConciliando(false); }
  };
  useEffect(() => { cargar(); }, [cargar]);
  // Lo que se MUESTRA (tras el filtro de mes) y la suma neta de esos pagos (la devolución resta).
  const mostrados = rows.filter((p) =>
    (!mes || (p.fecha || "").slice(5, 7) === mes) && (!dia || (p.fecha || "").slice(8, 10) === dia)
    && coincide(busca, p.nombre, p.apellidos, p.formaPago, p.fecha));
  const suma = mostrados.reduce((s, p) => s + (p.importe || 0), 0);
  const conciliados = mostrados.filter((p) => p.movimientoId || p.liquidado).length;
  const dev = asociando?.esDevolucion ?? false;  // devolución → se concilia con el Debe (salida)
  return (<Wrap>
    <div className="flex items-center justify-between">
      <span className="text-[12px] text-[#7f8c8d]"><b className="text-[#1500A0]">{mostrados.length}</b> pago{mostrados.length === 1 ? "" : "s"} · Suma <b className="text-[#1500A0]">{eur(suma)}</b>
        {conciliados > 0 && <span className="ml-2 text-[#0F8C7D]">· {conciliados} conciliado{conciliados === 1 ? "" : "s"}</span>}
        {tjMsg && <span className="ml-2 text-[#555]">{tjMsg}</span>}</span>
      <div className="flex gap-2">
        {puedeEditarGestoria && <button onClick={conciliarTarjetas} disabled={conciliando} title="Casar las liquidaciones del TPV con los pagos con tarjeta y señalar los cobros que faltan por registrar"
          className="inline-flex items-center gap-2 rounded-sm border border-[#065AED] px-3 py-1 text-[11px] font-semibold text-[#065AED] hover:bg-[#065AED]/5 disabled:opacity-60">
          {conciliando ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle className="h-3.5 w-3.5" />}
          {conciliando ? "Conciliando…" : "Conciliar tarjetas"}
        </button>}
        <Buscador value={busca} onChange={setBusca} placeholder="Buscar paciente…" />
        <select value={anyo} onChange={(e) => setAnyo(e.target.value)} className="border border-[#e5e7eb] rounded-sm px-2 py-1 text-[11px]">
          {ANYOS_GASTOS.map((y) => <option key={y} value={y}>{y || "Todos los años"}</option>)}
        </select>
        <select value={mes} onChange={(e) => setMes(e.target.value)} className="border border-[#e5e7eb] rounded-sm px-2 py-1 text-[11px]">
          <option value="">Todos los meses</option>
          {MESES.map((m, i) => <option key={m} value={String(i + 1).padStart(2, "0")}>{m}</option>)}
        </select>
        <select value={dia} onChange={(e) => setDia(e.target.value)} className="border border-[#e5e7eb] rounded-sm px-2 py-1 text-[11px]">
          <option value="">Todos los días</option>
          {Array.from({ length: 31 }, (_, i) => String(i + 1).padStart(2, "0")).map((d) => <option key={d} value={d}>{d}</option>)}
        </select>
        <select value={forma} onChange={(e) => setForma(e.target.value)} className="border border-[#e5e7eb] rounded-sm px-2 py-1 text-[11px]">
          <option value="">Todas las formas</option>
          {formas.map((f) => <option key={f} value={f}>{f}</option>)}
        </select>
      </div>
    </div>
    <Tbl head={<tr><Th>Fecha</Th><Th>Nombre</Th><Th>Apellidos</Th><Th>Forma de pago</Th><Th r>Importe</Th><Th>Apunte banco</Th></tr>}>
      {mostrados.length === 0 ? <tr><td colSpan={6} className="text-center py-8 text-gray-400 italic">Sin pagos de pacientes en este filtro.</td></tr>
        : mostrados.map((p) => <tr key={p.id} className="border-b border-[#f0f3f7] even:bg-[#FFFFFF] hover:bg-[#E6EDFF]">
          <Td>{fmtFecha(p.fecha)}</Td><Td>{p.nombre ?? "—"}</Td><Td>{p.apellidos ?? "—"}</Td>
          <Td>{p.formaPago ?? "—"}{p.esDevolucion && <span className="ml-1.5 text-[9px] uppercase tracking-wide text-[#C026D3] font-semibold">devolución</span>}</Td>
          <td className={`py-1.5 px-3 text-right tabular-nums ${p.esDevolucion ? "text-[#C026D3] font-semibold" : ""}`}>{eur(p.importe)}</td>
          <td className="py-1.5 px-3">{p.movimientoId
            ? <span className="inline-flex items-center gap-1.5 text-[10px] text-[#065AED]">{p.movimientoConcepto}
                <button onClick={() => gestoriaService.desasociarPago(p.id).then(cargar)} title="Desasociar" className="text-slate-400 hover:text-[#C026D3]"><X className="w-3 h-3" /></button></span>
            : p.liquidacionId
            ? <span className="inline-flex items-center gap-1 text-[10px] text-[#0F8C7D]" title="Cobro con tarjeta conciliado con su liquidación de TPV"><CheckCircle className="w-3 h-3" /> {p.liquidacionConcepto}</span>
            : p.liquidado
            ? <span className="inline-flex items-center gap-1 text-[10px] text-[#0F8C7D]" title="Marcado como liquidado"><CheckCircle className="w-3 h-3" /> Liquidado</span>
            : <button onClick={() => setAsociando(p)} className="text-[10px] text-[#1ca0d1] hover:text-[#065AED] font-semibold underline">asociar apunte</button>}</td>
        </tr>)}
    </Tbl>
    {asociando && <AsociarModal titulo={`Asociar apunte (${dev ? "Debe" : "Haber"})`} lado={dev ? "Debe" : "Haber"}
      subtitulo={`${dev ? "Devolución" : "Pago"}: ${asociando.paciente} · ${eur(asociando.importe)}`}
      cargarLibres={dev ? gestoriaService.movimientosDebeLibres : gestoriaService.movimientosHaberLibres}
      asociar={(mid) => gestoriaService.asociarPago(asociando.id, mid)}
      onClose={() => setAsociando(null)} onSaved={() => { setAsociando(null); cargar(); }} />}
  </Wrap>);
}

const TABLAS = [["facturas", "Facturas emitidas"], ["gastos", "Gastos"], ["bancos", "Movimientos bancarios"], ["modelos", "Modelos fiscales"], ["produccion", "Producción doctores"]];
const ordinal = (d: number) => `día ${d}`;
export function Envio() {
  const [sel, setSel] = useState<Record<string, boolean>>({ gastos: true, bancos: true });
  const [destino, setDestino] = useState("");
  const [otroEmail, setOtroEmail] = useState("");   // destinatario alternativo (solo envío manual)
  const [cfg, setCfg] = useState<{ nombreAsesoria: string | null; smtpListo: boolean } | null>(null);
  const [res, setRes] = useState<{ ok: boolean; error?: string } | null>(null);
  const [busy, setBusy] = useState(false);
  // Programación del envío automático mensual.
  const [autoOn, setAutoOn] = useState(false);
  const [dia, setDia] = useState(15);
  const [ultimo, setUltimo] = useState<string | null>(null);
  const [savingAuto, setSavingAuto] = useState(false);
  const [autoMsg, setAutoMsg] = useState<string | null>(null);
  useEffect(() => { gestoriaService.envioConfig().then((r) => {
    setCfg({ nombreAsesoria: r.nombreAsesoria, smtpListo: r.smtpListo }); if (r.destino) setDestino(r.destino);
    setAutoOn(r.auto.activo); setDia(r.auto.dia); setUltimo(r.auto.ultimoEnvio);
    if (r.auto.tablas?.length) setSel(Object.fromEntries(r.auto.tablas.map((t) => [t, true])));
  }); }, []);
  // Destino efectivo del envío manual: el email alternativo si está relleno; si no, el de la asesoría.
  const destinoManual = otroEmail.trim() || destino;
  const enviar = async () => { setBusy(true); setRes(null); const r = await gestoriaService.envio(Object.keys(sel).filter((k) => sel[k]), Y, destinoManual || undefined); setRes(r); setBusy(false); };
  const guardarAuto = async (activo: boolean) => {
    setSavingAuto(true); setAutoMsg(null);
    try {
      const r = await gestoriaService.guardarEnvioAuto(activo, dia, Object.keys(sel).filter((k) => sel[k]));
      setAutoOn(r.activo); setDia(r.dia);
      setAutoMsg(r.activo ? `Programado: cada ${ordinal(r.dia)} del mes → ${destino || "la asesoría"}.` : "Envío automático desactivado.");
    } catch (e) { setAutoMsg(`Error: ${e instanceof Error ? e.message : ""}`); }
    finally { setSavingAuto(false); }
  };
  return (<Wrap><div className="border border-[#e5e7eb] rounded-sm bg-white max-w-lg">
    <div className="bg-[#065AED] text-white px-4 py-2.5 text-[12px] font-semibold uppercase tracking-wider flex items-center gap-2"><Send className="w-4 h-4" /> Envío a gestoría</div>
    <div className="p-4 flex flex-col gap-3">
      <label className="flex flex-col gap-0.5"><span className="text-[10px] uppercase text-[#1ca0d1] font-semibold">Email de la asesoría</span>
        <input value={destino} onChange={(e) => setDestino(e.target.value)} placeholder="asesoria@ejemplo.com" className="border border-[#e5e7eb] rounded-sm px-2 py-1 text-[12px]" /></label>
      <label className="flex flex-col gap-0.5"><span className="text-[10px] uppercase text-[#1ca0d1] font-semibold">Otro destinatario (opcional)</span>
        <input value={otroEmail} onChange={(e) => setOtroEmail(e.target.value)} placeholder="otro@ejemplo.com" className="border border-[#e5e7eb] rounded-sm px-2 py-1 text-[12px]" />
        {otroEmail.trim() && <span className="text-[10px] text-slate-500">El envío manual irá a esta dirección (el automático sigue yendo a la asesoría).</span>}</label>
      <p className="text-[12px] text-slate-500">Datos a enviar{cfg?.smtpListo ? "" : " (SMTP sin configurar)"}:</p>
      {TABLAS.map(([id, label]) => <label key={id} className="flex items-center gap-2 text-[12px] text-[#333] cursor-pointer"><input type="checkbox" checked={!!sel[id]} onChange={(e) => setSel({ ...sel, [id]: e.target.checked })} /> {label}</label>)}
      <button onClick={enviar} disabled={busy || !destinoManual} className="inline-flex items-center justify-center gap-2 bg-[#065AED] text-white text-[12px] font-semibold uppercase px-4 py-2 rounded-sm hover:bg-[#01498f] disabled:opacity-50">{busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />} Enviar ahora</button>
      {res && <div className={`text-[11px] px-2 py-1.5 rounded-sm flex items-center gap-2 ${res.ok ? "bg-[#FFFFFF] text-[#073D8D]" : "bg-[#FFFFFF] text-[#C026D3]"}`}><CheckCircle className="w-4 h-4" /> {res.ok ? `Enviado a ${destinoManual}` : res.error}</div>}

      {/* Envío automático mensual */}
      <div className="mt-1 pt-3 border-t border-[#eef2f7] flex flex-col gap-2">
        <label className="flex items-center gap-2 text-[12px] font-semibold text-[#065AED] cursor-pointer">
          <input type="checkbox" checked={autoOn} onChange={(e) => guardarAuto(e.target.checked)} disabled={savingAuto} />
          Envío automático mensual
        </label>
        <div className="flex items-center gap-2 text-[12px] text-[#333]">
          <span>Enviar el</span>
          <select value={dia} onChange={(e) => setDia(Number(e.target.value))} className="border border-[#e5e7eb] rounded-sm px-2 py-1 text-[12px]">
            {Array.from({ length: 28 }, (_, i) => i + 1).map((d) => <option key={d} value={d}>{ordinal(d)}</option>)}
          </select>
          <span>de cada mes</span>
          <button onClick={() => guardarAuto(true)} disabled={savingAuto || !cfg?.smtpListo}
            className="ml-auto inline-flex items-center gap-1.5 rounded-sm border border-[#065AED] px-2.5 py-1 text-[11px] font-semibold text-[#065AED] hover:bg-[#065AED]/5 disabled:opacity-50">
            {savingAuto ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle className="w-3.5 h-3.5" />} Guardar programación
          </button>
        </div>
        {ultimo && <p className="text-[10px] text-slate-400">Último envío automático: {ultimo}</p>}
        {autoMsg && <p className="text-[11px] text-[#0F8C7D]">{autoMsg}</p>}
        {!cfg?.smtpListo && <p className="text-[11px] text-[#7C3AED]">Configura el SMTP (Config → Centro → Email saliente) para poder programarlo.</p>}
      </div>
    </div>
  </div></Wrap>);
}
