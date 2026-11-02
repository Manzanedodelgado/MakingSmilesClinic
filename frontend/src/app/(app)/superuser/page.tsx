"use client";
/**
 * SUPERUSER — panel del supercreador. Acceso exclusivo (permiso `superuser`; el backend lo exige).
 * Centros (editor/gestor/creador/monitorizador multi-tenant) + Aura (su casa: PIN de escritura,
 * estado, capacidades y el espejo de Centinela que ella vigila) + Centinela + Explorador de BD (solo lectura).
 */
import { useCallback, useEffect, useState } from "react";
import { X, ArrowLeft, Check, ChevronRight, Shield, Database, Table2, Search, Play, RefreshCw, Building2, Plus, Link2, Users, HeartPulse, Landmark, Key, AlertTriangle, AlertCircle, Power, PowerOff, Pause, Package } from "lucide-react";
import { api, API_BASE } from "@/shared/lib/api";
import { ClinicalCard, SectionHeader, ClinicalButton, AreaTabs, ImgPicker, GeoCascada, INPUT, Modal, ModalBody, ModalButton, MODAL_INPUT } from "@/shared/components";
import { errMsg } from "@/shared/lib/errores";
import { AuraPanel } from "@/features/superuser/AuraPanel";
import { CentinelaPanel } from "@/features/superuser/CentinelaPanel";

type Tabla = { nombre: string; filas: number; bytes: number };
type Col = { nombre: string; tipo: string; nullable: boolean; longitud: number | null };
type RowsResp = { tabla: string; total: number; page: number; limit: number; columnas: string[]; filas: Record<string, unknown>[] };
type QueryResp = { columnas: string[]; filas: Record<string, unknown>[]; n: number; cap: number };

const LIMIT = 50;
const cell = (v: unknown) => (v === null || v === undefined ? "" : typeof v === "object" ? JSON.stringify(v) : String(v));


export default function SuperUserPage() {
  const [seccion, setSeccion] = useState<"centros" | "aura" | "centinela" | "apariencia" | "bd">("centros");
  const [tablas, setTablas] = useState<Tabla[]>([]);
  const [filtroTabla, setFiltroTabla] = useState("");
  const [modo, setModo] = useState<"tablas" | "sql">("tablas");

  // explorador de tabla
  const [sel, setSel] = useState<string | null>(null);
  const [schema, setSchema] = useState<Col[]>([]);
  const [rows, setRows] = useState<RowsResp | null>(null);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [verSchema, setVerSchema] = useState(false);

  // runner SQL
  const [sql, setSql] = useState("SELECT * FROM pacientes LIMIT 20");
  const [sqlRes, setSqlRes] = useState<QueryResp | null>(null);
  const [sqlErr, setSqlErr] = useState("");
  const [cargando, setCargando] = useState(false);

  useEffect(() => {
    api.get<{ tablas: Tabla[] }>("/superuser/db/tables").then((d) => setTablas(d.tablas)).catch(() => {});
  }, []);

  const cargarTabla = useCallback(async (tabla: string, pg: number, q: string) => {
    setCargando(true);
    try {
      const [sc, rw] = await Promise.all([
        api.get<{ columnas: Col[] }>(`/superuser/db/tables/${tabla}/schema`),
        api.get<RowsResp>(`/superuser/db/tables/${tabla}/rows?page=${pg}&limit=${LIMIT}&search=${encodeURIComponent(q)}`),
      ]);
      setSchema(sc.columnas); setRows(rw);
    } catch { /* noop */ } finally { setCargando(false); }
  }, []);

  const abrir = (t: string) => { setSel(t); setModo("tablas"); setPage(1); setSearch(""); setVerSchema(false); cargarTabla(t, 1, ""); };
  const buscar = () => { setPage(1); if (sel) cargarTabla(sel, 1, search); };
  const irPagina = (pg: number) => { setPage(pg); if (sel) cargarTabla(sel, pg, search); };

  async function correrSQL() {
    setCargando(true); setSqlErr(""); setSqlRes(null);
    try { setSqlRes(await api.post<QueryResp>("/superuser/db/query", { sql })); }
    catch (e) { setSqlErr(e instanceof Error ? e.message.replace(/.*\{.*"detail":\s*"?|"?\}.*/g, "") : "Error"); }
    finally { setCargando(false); }
  }

  const tablasFiltradas = tablas.filter((t) => t.nombre.includes(filtroTabla.toLowerCase()));
  const totalPags = rows ? Math.max(1, Math.ceil(rows.total / LIMIT)) : 1;

  return (
    <div className="flex flex-col h-full min-h-0">
      <AreaTabs
        tabs={[{ id: "centros", label: "Centros" }, { id: "aura", label: "Aura" }, { id: "centinela", label: "Centinela" }, { id: "apariencia", label: "Apariencia" }, { id: "bd", label: "Base de datos" }]}
        activeTab={seccion} onChange={(id) => setSeccion(id as typeof seccion)} />
      <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-4">

      {seccion === "centros" && <CentrosPanel />}
      {seccion === "aura" && <AuraPanel onVerCentinela={() => setSeccion("centinela")} />}
      {seccion === "centinela" && <CentinelaPanel />}
      {seccion === "apariencia" && <AparienciaPanel />}

      {seccion === "bd" && (
      <ClinicalCard>
        <SectionHeader title="Explorador de base de datos" icon={Database}
          action={
            <div className="flex gap-1">
              <ClinicalButton variant={modo === "tablas" ? "primary" : "ghost"} size="sm" icon={Table2} onClick={() => setModo("tablas")}>Tablas</ClinicalButton>
              <ClinicalButton variant={modo === "sql" ? "primary" : "ghost"} size="sm" icon={Play} onClick={() => setModo("sql")}>SQL</ClinicalButton>
            </div>
          } />

        {modo === "sql" ? (
          <div className="space-y-2">
            <textarea value={sql} onChange={(e) => setSql(e.target.value)} spellCheck={false}
              className="w-full h-28 border border-[#e5e7eb] rounded-sm p-2 font-mono text-[12px] outline-none focus:border-[#1ca0d1]"
              placeholder="SELECT … (solo lectura)" />
            <div className="flex items-center gap-2">
              <ClinicalButton variant="accent" size="sm" icon={Play} disabled={cargando} onClick={correrSQL}>Ejecutar</ClinicalButton>
              {sqlErr && <span className="text-[12px] text-[#C026D3]">{sqlErr}</span>}
              {sqlRes && <span className="text-[11px] text-[#7f8c8d]">{sqlRes.n} fila(s){sqlRes.n >= sqlRes.cap ? ` (cap ${sqlRes.cap})` : ""}</span>}
            </div>
            {sqlRes && <Grid columnas={sqlRes.columnas} filas={sqlRes.filas} />}
          </div>
        ) : (
          <div className="grid grid-cols-[260px_1fr] gap-3 min-h-0">
            {/* Lista de tablas */}
            <div className="border border-[#e5e7eb] rounded-sm flex flex-col min-h-0 max-h-[60vh]">
              <div className="p-2 border-b border-[#e5e7eb]">
                <input value={filtroTabla} onChange={(e) => setFiltroTabla(e.target.value)} placeholder={`Filtrar ${tablas.length} tablas…`} className={INPUT} />
              </div>
              <div className="overflow-y-auto divide-y divide-[#f0f2f5]">
                {tablasFiltradas.map((t) => (
                  <button key={t.nombre} onClick={() => abrir(t.nombre)}
                    className={`w-full flex items-center justify-between px-2 py-1.5 text-left text-[12px] hover:bg-[#E6EDFF] ${sel === t.nombre ? "bg-[#FFFFFF] text-[#1500A0] font-semibold" : "text-[#333333]"}`}>
                    <span className="truncate">{t.nombre}</span>
                    <span className="text-[10px] text-slate-400 tabular-nums shrink-0 ml-2">{t.filas.toLocaleString("es-ES")}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Detalle de la tabla */}
            <div className="min-w-0">
              {!sel ? (
                <div className="text-[12px] text-slate-400 italic p-6 text-center">Elige una tabla a la izquierda.</div>
              ) : (
                <div className="space-y-2 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-[13px] font-semibold text-[#1500A0]">{sel}</span>
                    <span className="text-[11px] text-[#7f8c8d]">{rows?.total?.toLocaleString("es-ES")} filas</span>
                    <button onClick={() => setVerSchema((v) => !v)} className="text-[11px] text-[#1ca0d1] hover:underline">{verSchema ? "ocultar" : "ver"} esquema ({schema.length} cols)</button>
                    <div className="flex-1" />
                    <div className="relative">
                      <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
                      <input value={search} onChange={(e) => setSearch(e.target.value)} onKeyDown={(e) => e.key === "Enter" && buscar()}
                        placeholder="Buscar…" className="border border-[#e5e7eb] rounded-sm pl-7 pr-6 py-1 text-[12px] outline-none focus:border-[#1ca0d1]" />
                      {search && (
                        <button type="button" onClick={() => setSearch("")} className="absolute right-1.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-[#C026D3]">
                          <X className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                    <ClinicalButton variant="secondary" size="sm" icon={RefreshCw} onClick={buscar}>Buscar</ClinicalButton>
                  </div>

                  {verSchema && (
                    <div className="flex flex-wrap gap-1">
                      {schema.map((c) => (
                        <span key={c.nombre} className="text-[10px] bg-[#FFFFFF] border border-[#e5e7eb] rounded-sm px-1.5 py-0.5 text-[#33415c]">
                          {c.nombre} <span className="text-slate-400">{c.tipo}</span>
                        </span>
                      ))}
                    </div>
                  )}

                  {rows && <Grid columnas={rows.columnas} filas={rows.filas} />}

                  <div className="flex items-center justify-end gap-2 text-[12px]">
                    <ClinicalButton variant="ghost" size="sm" disabled={page <= 1 || cargando} onClick={() => irPagina(page - 1)}>‹ Anterior</ClinicalButton>
                    <span className="text-[#7f8c8d]">{page} / {totalPags}</span>
                    <ClinicalButton variant="ghost" size="sm" disabled={page >= totalPags || cargando} onClick={() => irPagina(page + 1)}>Siguiente ›</ClinicalButton>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </ClinicalCard>
      )}
      </div>
    </div>
  );
}

// ── Centros (tenants): dashboard + lista + ficha completa ───────────────────
type Centro = { id: number; nombre: string; codigo: string | null; estado: string; plan: string | null; modulos_activos: string[] };
type Modulo = { id: string; label: string; fijo?: boolean; pack?: string };
const ESTADO_UI: Record<string, { txt: string; dot: string; cls: string }> = {
  activo: { txt: "Activo", dot: "bg-[#20BEAB]", cls: "bg-[#FFFFFF] text-[#0F8C7D] border-[#9FE6DB]" },
  suspendido: { txt: "Suspendido", dot: "bg-[#7C3AED]", cls: "bg-[#FFFFFF] text-[#6D28D9] border-[#C4B5FD]" },
  inactivo: { txt: "Inactivo", dot: "bg-[#94a3b8]", cls: "bg-[#FFFFFF] text-[#64748b] border-[#cbd5e1]" },
};

function CentrosPanel() {
  const [centros, setCentros] = useState<Centro[]>([]);
  const [modulos, setModulos] = useState<Modulo[]>([]);
  const [planes, setPlanes] = useState<Record<string, string[]>>({});
  const [modalOpen, setModalOpen] = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [form, setForm] = useState({
    nombre: "", admin_nombre: "", admin_email: "", plan: "lite",
    asociado_a_centro_id: "" as string | number, comparte_personal: false,
    comparte_razon_social: false, comparte_pacientes: false,
  });
  const [creando, setCreando] = useState(false);
  const [error, setError] = useState("");
  // Credenciales del admin recién creado — se muestran UNA vez, no se pueden recuperar después.
  const [creado, setCreado] = useState<{ admin_email: string; password_temporal: string; personal_compartido: number } | null>(null);
  // "Sin centros registrados" y "no se pudo cargar la lista" NO son lo mismo — un fallo de
  // red (p.ej. el backend reiniciando, sin par A/B como el frontend) se veía IDÉNTICO a que
  // de verdad no hubiera ningún centro, porque el catch original se tragaba el error dejando
  // `centros` en su [] inicial. Un `undefined` en `cargaError` = todavía sin resolver la
  // primera carga (no mostrar ningún mensaje mientras tanto).
  const [cargaError, setCargaError] = useState<string | null | undefined>(undefined);

  const load = useCallback(() => {
    api.get<{ centros: Centro[]; modulos: Modulo[]; planes: Record<string, string[]> }>("/superuser/centros")
      .then((d) => { setCentros(d.centros); setModulos(d.modulos); setPlanes(d.planes); setCargaError(null); })
      .catch((e) => { setCargaError(e instanceof Error ? e.message : "No se pudo conectar con el servidor"); });
  }, []);
  useEffect(() => { load(); }, [load]);

  async function crear() {
    if (!form.nombre.trim() || !form.admin_nombre.trim() || !form.admin_email.trim()) {
      setError("Nombre del centro, nombre y email del administrador son obligatorios"); return;
    }
    setCreando(true); setError("");
    try {
      const r = await api.post<{ id: number; admin_email: string; password_temporal: string; personal_compartido: number }>("/superuser/centros", {
        nombre: form.nombre.trim(), admin_nombre: form.admin_nombre.trim(),
        admin_email: form.admin_email.trim(), plan: form.plan,
        asociado_a_centro_id: form.asociado_a_centro_id ? Number(form.asociado_a_centro_id) : null,
        comparte_personal: form.comparte_personal, comparte_razon_social: form.comparte_razon_social,
        comparte_pacientes: form.comparte_pacientes,
      });
      setModalOpen(false);
      setForm({ nombre: "", admin_nombre: "", admin_email: "", plan: "lite",
               asociado_a_centro_id: "", comparte_personal: false, comparte_razon_social: false, comparte_pacientes: false });
      setCreado({ admin_email: r.admin_email, password_temporal: r.password_temporal, personal_compartido: r.personal_compartido });
      load();
    } catch (e) { setError(errMsg(e)); }
    finally { setCreando(false); }
  }

  const selected = centros.find((c) => c.id === selectedId);

  if (selected) {
    return (
      <CentroDetalle centro={selected} centros={centros} modulos={modulos} planes={planes}
        onBack={() => setSelectedId(null)} onCambio={load} />
    );
  }

  return (
    <div className="space-y-3">
      {creado && (
        <div className="p-3 rounded-sm border border-[#9FE6DB] bg-[#FFFFFF] text-[12px]">
          <p className="font-semibold text-[#0F8C7D] mb-1">Centro creado. Guarda estas credenciales — la contraseña no se puede volver a ver:</p>
          <p className="text-[#0F8C7D]">Email: <b>{creado.admin_email}</b> · Contraseña temporal: <code className="bg-white px-1.5 py-0.5 rounded-sm border border-[#9FE6DB]">{creado.password_temporal}</code></p>
          {creado.personal_compartido > 0 && <p className="text-[#0F8C7D] mt-1">+ {creado.personal_compartido} persona(s) del centro asociado recibieron acceso aquí también.</p>}
          <button onClick={() => setCreado(null)} className="text-[11px] text-[#0F8C7D] underline mt-1">Entendido</button>
        </div>
      )}

      <ClinicalCard noPadding>
        <SectionHeader variant="dark" title={`Centros (${centros.length})`} icon={Building2}
          action={<ClinicalButton variant="primary" size="sm" icon={Plus} onClick={() => { setError(""); setModalOpen(true); }}>Nuevo centro</ClinicalButton>} />

        {cargaError === undefined ? (
          <div className="p-8 text-center">
            <p className="text-[12px] font-semibold text-[#7f8c8d]">Cargando…</p>
          </div>
        ) : cargaError ? (
          <div className="p-8 text-center">
            <Building2 className="w-8 h-8 text-[#C026D3] mx-auto mb-2" />
            <p className="text-[12px] font-semibold text-[#C026D3]">No se pudo cargar la lista de centros</p>
            <p className="text-[11px] text-[#7f8c8d] mt-0.5">{cargaError} — puede ser que el backend esté reiniciando.</p>
            <ClinicalButton variant="secondary" size="sm" onClick={load} className="mt-2">Reintentar</ClinicalButton>
          </div>
        ) : centros.length > 0 ? (
          <div className="divide-y divide-[#e5e7eb]">
            {centros.map((c) => {
              const cf = ESTADO_UI[c.estado] ?? ESTADO_UI.inactivo;
              return (
                <button key={c.id} onClick={() => setSelectedId(c.id)}
                  className="w-full flex items-center justify-between px-4 py-3 text-left transition-colors hover:bg-[#E6EDFF]">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className={`w-2.5 h-2.5 rounded-full shrink-0 ${cf.dot}`} />
                    <div className="min-w-0">
                      <div className="text-[13px] font-semibold text-[#1500A0] truncate">{c.nombre}</div>
                      <div className="text-[11px] text-[#7f8c8d]">
                        {c.codigo && <span>{c.codigo} · </span>}
                        {c.plan ? c.plan[0].toUpperCase() + c.plan.slice(1) : "Personalizado"} · {(c.modulos_activos ?? []).length} módulos
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    <span className={`text-[10px] font-semibold border rounded-sm px-1.5 py-0.5 ${cf.cls}`}>{cf.txt}</span>
                    <ChevronRight className="w-4 h-4 text-[#cbd5e1]" />
                  </div>
                </button>
              );
            })}
          </div>
        ) : (
          <div className="p-8 text-center">
            <Building2 className="w-8 h-8 text-[#e5e7eb] mx-auto mb-2" />
            <p className="text-[12px] font-semibold text-[#7f8c8d]">Sin centros registrados</p>
            <p className="text-[11px] text-[#7f8c8d] mt-0.5">Crea el primero con &quot;Nuevo centro&quot;.</p>
          </div>
        )}
      </ClinicalCard>

      {modalOpen && (
        <Modal
          title={<span className="flex items-center gap-2"><Building2 className="w-4 h-4" />Nuevo centro</span>}
          onClose={() => setModalOpen(false)}
          size="sm"
          closeOnBackdrop={false}
          footer={
            <>
              <ModalButton variant="magenta" icon={X} onClick={() => setModalOpen(false)} disabled={creando}>Cancelar</ModalButton>
              <ModalButton variant="primary" icon={Check} onClick={crear} disabled={creando}>{creando ? "Creando…" : "Crear centro"}</ModalButton>
            </>
          }
        >
          <ModalBody>
            <div className="flex flex-col gap-2.5">
              <div>
                <label className="block text-[10px] font-semibold text-[#1ca0d1] uppercase tracking-wide mb-1">Nombre del centro</label>
                <input autoFocus value={form.nombre} onChange={(e) => setForm({ ...form, nombre: e.target.value })} className={MODAL_INPUT} placeholder="Clínica Ejemplo" />
              </div>
              <div>
                <label className="block text-[10px] font-semibold text-[#1ca0d1] uppercase tracking-wide mb-1">Nombre del administrador</label>
                <input value={form.admin_nombre} onChange={(e) => setForm({ ...form, admin_nombre: e.target.value })} className={MODAL_INPUT} placeholder="Nombre y apellidos" />
              </div>
              <div>
                <label className="block text-[10px] font-semibold text-[#1ca0d1] uppercase tracking-wide mb-1">Email del administrador</label>
                <input type="email" value={form.admin_email} onChange={(e) => setForm({ ...form, admin_email: e.target.value })} className={MODAL_INPUT} placeholder="admin@clinica.com" />
              </div>
              <div>
                <label className="block text-[10px] font-semibold text-[#1ca0d1] uppercase tracking-wide mb-1">Plan</label>
                <select value={form.plan} onChange={(e) => setForm({ ...form, plan: e.target.value })} className={MODAL_INPUT}>
                  {Object.keys(planes).length ? Object.keys(planes).map((p) => <option key={p} value={p}>{p[0].toUpperCase() + p.slice(1)}</option>) : <option value="lite">Lite</option>}
                </select>
              </div>
              <div className="border-t border-[#BFE4F7] pt-2.5">
                <label className="block text-[10px] font-semibold text-[#1ca0d1] uppercase tracking-wide mb-1">Centro independiente o asociado a otro</label>
                <select value={form.asociado_a_centro_id}
                  onChange={(e) => setForm({ ...form, asociado_a_centro_id: e.target.value,
                    ...(e.target.value ? {} : { comparte_personal: false, comparte_razon_social: false, comparte_pacientes: false }) })}
                  className={MODAL_INPUT}>
                  <option value="">— Independiente —</option>
                  {centros.map((c) => <option key={c.id} value={c.id}>Asociado a: {c.nombre}</option>)}
                </select>
                {form.asociado_a_centro_id && (
                  <div className="flex flex-col gap-1 mt-1.5 pl-1">
                    <label className="flex items-center gap-1.5 text-[12px] text-[#333] cursor-pointer">
                      <input type="checkbox" checked={form.comparte_personal} onChange={(e) => setForm({ ...form, comparte_personal: e.target.checked })} />
                      Comparte personal (el equipo ya existente tendrá acceso aquí también)
                    </label>
                    <label className="flex items-center gap-1.5 text-[12px] text-[#333] cursor-pointer">
                      <input type="checkbox" checked={form.comparte_razon_social} onChange={(e) => setForm({ ...form, comparte_razon_social: e.target.checked })} />
                      Comparte razón social (factura con la del centro asociado)
                    </label>
                    <label className="flex items-center gap-1.5 text-[12px] text-[#333] cursor-pointer">
                      <input type="checkbox" checked={form.comparte_pacientes} onChange={(e) => setForm({ ...form, comparte_pacientes: e.target.checked })} />
                      Comparte pacientes <span className="text-[10px] text-[#6D28D9]">(guardado, aún no aplicado — pendiente)</span>
                    </label>
                  </div>
                )}
              </div>
              {error && <p className="text-[11px] font-semibold text-[#C026D3] bg-[#FFFFFF] border border-[#C026D3] rounded-md px-2 py-1.5">{error}</p>}
            </div>
          </ModalBody>
        </Modal>
      )}
    </div>
  );
}

// ── Ficha completa de un centro: editor real, plan, asociación, personal, salud ──
type Ficha = {
  centro: Centro & { direccion: string | null; cp: string | null; poblacion: string | null; provincia: string | null;
    telefono: string | null; telefono_movil: string | null; email: string | null; web: string | null;
    instagram: string | null; num_gabinetes: number | null; razon_social_compartida_id: number | null };
  razon_social: { id: number; nombre: string; cif: string | null; centro_id: number; compartida_de_centro_id?: number } | null;
  asociacion: { asociado_a_centro_id: number; asociado_a_nombre: string | null; comparte_personal: boolean;
    comparte_razon_social: boolean; comparte_pacientes: boolean } | null;
  personal: { usuario_id: number; nombre: string; email: string; rol: string }[];
  salud: { nivel_servicio: "ok" | "degraded" | "critical"; alertas: { tipo: "error" | "warning"; titulo: string; descripcion: string }[];
    integraciones: { tipo: string; nombre: string | null; activo: boolean }[]; pacientes: number; citas: number; ultima_cita: string | null };
};
const NIVEL_UI: Record<string, { txt: string; cls: string; dot: string }> = {
  ok: { txt: "Todo en orden", cls: "text-[#0F8C7D]", dot: "bg-[#20BEAB]" },
  degraded: { txt: "Requiere atención", cls: "text-[#6D28D9]", dot: "bg-[#7C3AED]" },
  critical: { txt: "Crítico", cls: "text-[#A21CAF]", dot: "bg-[#C026D3]" },
};
const PLAN_COLOR: Record<string, { border: string; bg: string; dot: string; txt: string }> = {
  lite: { border: "border-[#1ca0d1]", bg: "bg-[#FFFFFF]", dot: "bg-[#1ca0d1]", txt: "text-[#1ca0d1]" },
  connect: { border: "border-[#3388FF]", bg: "bg-[#FFFFFF]", dot: "bg-[#3388FF]", txt: "text-[#3388FF]" },
  improve: { border: "border-[#1500A0]", bg: "bg-[#FFFFFF]", dot: "bg-[#1500A0]", txt: "text-[#1500A0]" },
};
const PLAN_COLOR_FALLBACK = { border: "border-[#7f8c8d]", bg: "bg-[#FFFFFF]", dot: "bg-[#7f8c8d]", txt: "text-[#7f8c8d]" };

function CentroDetalle({ centro, centros, modulos, planes, onBack, onCambio }: {
  centro: Centro; centros: Centro[]; modulos: Modulo[]; planes: Record<string, string[]>;
  onBack: () => void; onCambio: () => void;
}) {
  const centroId = centro.id;
  const [f, setF] = useState<Ficha | null>(null);
  const [datos, setDatos] = useState<Record<string, string>>({});
  // Razón social y CIF: solo aquí se editan (Config → Centro los muestra bloqueados).
  const [rs, setRs] = useState({ nombre: "", cif: "" });
  const [asoc, setAsoc] = useState({ asociado_a_centro_id: "" as string | number, comparte_personal: false, comparte_razon_social: false, comparte_pacientes: false });
  const [nuevoEmail, setNuevoEmail] = useState("");
  const [nuevoNombre, setNuevoNombre] = useState("");
  const [nuevaPersonaCreada, setNuevaPersonaCreada] = useState<{ email: string; password_temporal: string } | null>(null);
  const [credencialReset, setCredencialReset] = useState<{ email: string; password_temporal: string } | null>(null);
  const [editandoEmailDe, setEditandoEmailDe] = useState<number | null>(null);
  const [emailEnEdicion, setEmailEnEdicion] = useState("");
  const [msg, setMsg] = useState("");
  const [guardando, setGuardando] = useState(false);
  const flash = (t: string) => { setMsg(t); setTimeout(() => setMsg(""), 3000); };

  const cargar = useCallback(() => {
    api.get<Ficha>(`/superuser/centros/${centroId}`).then((d) => {
      setF(d);
      setDatos({ nombre: d.centro.nombre || "", codigo: d.centro.codigo || "", direccion: d.centro.direccion || "",
        cp: d.centro.cp || "", poblacion: d.centro.poblacion || "", provincia: d.centro.provincia || "",
        telefono: d.centro.telefono || "", telefono_movil: d.centro.telefono_movil || "", email: d.centro.email || "",
        web: d.centro.web || "", instagram: d.centro.instagram || "" });
      setRs({ nombre: d.razon_social?.nombre || "", cif: d.razon_social?.cif || "" });
      setAsoc(d.asociacion ? { asociado_a_centro_id: d.asociacion.asociado_a_centro_id, comparte_personal: d.asociacion.comparte_personal,
        comparte_razon_social: d.asociacion.comparte_razon_social, comparte_pacientes: d.asociacion.comparte_pacientes }
        : { asociado_a_centro_id: "", comparte_personal: false, comparte_razon_social: false, comparte_pacientes: false });
    }).catch(() => {});
  }, [centroId]);
  useEffect(() => { cargar(); }, [cargar]);
  // Salud del centro: auto-refresco mientras la ficha esté abierta, como el Centinela.
  useEffect(() => {
    const id = setInterval(cargar, 20_000);
    return () => clearInterval(id);
  }, [cargar]);

  async function guardarDatos() {
    setGuardando(true);
    const rsPropia = f?.razon_social && !f.razon_social.compartida_de_centro_id;
    try { await api.put(`/superuser/centros/${centroId}`, rsPropia ? { ...datos, razon_social: rs } : datos); flash("Datos guardados ✓"); cargar(); onCambio(); }
    catch (e) { flash(errMsg(e)); } finally { setGuardando(false); }
  }
  async function guardarAsociacion() {
    setGuardando(true);
    try {
      await api.put(`/superuser/centros/${centroId}/asociacion`, {
        ...asoc, asociado_a_centro_id: asoc.asociado_a_centro_id ? Number(asoc.asociado_a_centro_id) : null,
      });
      flash("Asociación guardada ✓"); cargar(); onCambio();
    } catch (e) { flash(errMsg(e)); } finally { setGuardando(false); }
  }
  async function anadirPersonal() {
    if (!nuevoEmail.trim()) return;
    try {
      const r = await api.post<{ usuario_id: number; nombre: string; email: string; password_temporal: string | null }>(
        `/superuser/centros/${centroId}/personal`, { email: nuevoEmail.trim(), nombre: nuevoNombre.trim() || undefined });
      setNuevoEmail(""); setNuevoNombre("");
      if (r.password_temporal) setNuevaPersonaCreada({ email: r.email, password_temporal: r.password_temporal });
      flash(r.password_temporal ? "Persona creada y añadida ✓" : "Persona añadida ✓");
      cargar();
    } catch (e) { flash(errMsg(e)); }
  }
  async function quitarPersonal(usuarioId: number) {
    try { await api.del(`/superuser/centros/${centroId}/personal/${usuarioId}`); flash("Acceso quitado ✓"); cargar(); }
    catch (e) { flash(errMsg(e)); }
  }
  async function resetPassword(usuarioId: number) {
    if (!confirm("¿Generar una contraseña temporal nueva para esta persona? La actual dejará de servir.")) return;
    try {
      const r = await api.post<{ email: string; password_temporal: string }>(`/superuser/centros/${centroId}/personal/${usuarioId}/reset-password`, {});
      setCredencialReset({ email: r.email, password_temporal: r.password_temporal });
      flash("Contraseña reseteada ✓");
    } catch (e) { flash(errMsg(e)); }
  }
  async function guardarEmail(usuarioId: number) {
    if (!emailEnEdicion.includes("@")) return;
    try {
      await api.put(`/superuser/centros/${centroId}/personal/${usuarioId}/email`, { email: emailEnEdicion.trim() });
      setEditandoEmailDe(null); flash("Email actualizado ✓"); cargar();
    } catch (e) { flash(errMsg(e)); }
  }
  async function setEstado(estado: string) { await api.patch(`/superuser/centros/${centroId}/estado`, { estado }); cargar(); onCambio(); }
  async function setPlan(plan: string) {
    await api.put(`/superuser/centros/${centroId}`, { plan });
    await api.patch(`/superuser/centros/${centroId}/modulos`, { modulos: planes[plan] ?? [] });
    cargar(); onCambio();
  }

  if (!f) return <div className="text-[12px] text-slate-400 italic p-6 text-center">Cargando ficha…</div>;
  const otrosCentros = centros.filter((x) => x.id !== centroId);
  const cf = ESTADO_UI[f.centro.estado] ?? ESTADO_UI.inactivo;
  const F = "border border-[#e5e7eb] rounded-sm px-2 py-1 text-[12px] outline-none focus:border-[#1ca0d1] w-full";
  const L = "block text-[10px] font-semibold text-[#1ca0d1] uppercase tracking-wide mb-0.5";
  const planActual = f.centro.plan ?? "";

  return (
    <div className="space-y-3">
      {/* Header: volver, estado, acciones */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2.5">
          <ClinicalButton variant="ghost" size="sm" icon={ArrowLeft} onClick={onBack}>Volver</ClinicalButton>
          <div className={`w-3 h-3 rounded-full ${cf.dot}`} />
          <h2 className="text-[14px] font-semibold text-[#1500A0]">{f.centro.nombre}</h2>
          <span className={`text-[10px] font-semibold border rounded-sm px-1.5 py-0.5 ${cf.cls}`}>{cf.txt}</span>
        </div>
        <div className="flex items-center gap-1.5">
          {f.centro.estado !== "activo" && <ClinicalButton variant="primary" size="sm" icon={Power} onClick={() => setEstado("activo")}>Activar</ClinicalButton>}
          {f.centro.estado === "activo" && <ClinicalButton variant="secondary" size="sm" icon={Pause} onClick={() => setEstado("suspendido")}>Suspender</ClinicalButton>}
          {f.centro.estado !== "inactivo" && <ClinicalButton variant="ghost" size="sm" icon={PowerOff} onClick={() => setEstado("inactivo")}>Desactivar</ClinicalButton>}
        </div>
      </div>

      {msg && <div className="text-[11px] font-semibold text-[#0F8C7D]">{msg}</div>}

      <div className="grid grid-cols-1 lg:grid-cols-[1.3fr_1fr] gap-3 items-start">
        {/* Columna izquierda: Datos + Razón social + Plan */}
        <div className="flex flex-col gap-3">
          <ClinicalCard>
            <SectionHeader title="Datos del centro" icon={Building2} />
            <div className="grid grid-cols-2 gap-2">
              {(["nombre", "codigo", "direccion"] as const).map((k) => (
                <div key={k}><label className={L}>{k.replace("_", " ")}</label>
                  <input value={datos[k] ?? ""} onChange={(e) => setDatos({ ...datos, [k]: e.target.value })} className={F} /></div>
              ))}
            </div>
            <div className="flex flex-wrap gap-2 mt-2">
              <GeoCascada
                provincia={datos.provincia ?? ""}
                poblacion={datos.poblacion ?? ""}
                cp={datos.cp ?? ""}
                onChange={(g) => setDatos({ ...datos, provincia: g.provincia, poblacion: g.poblacion, cp: g.cp })}
                wPais="w-32" wProvincia="w-32" wCiudad="w-40" wCp="w-24"
              />
            </div>
            <div className="grid grid-cols-2 gap-2 mt-2">
              {(["telefono", "telefono_movil", "email", "web", "instagram"] as const).map((k) => (
                <div key={k}><label className={L}>{k.replace("_", " ")}</label>
                  <input value={datos[k] ?? ""} onChange={(e) => setDatos({ ...datos, [k]: e.target.value })} className={F} /></div>
              ))}
            </div>
            <ClinicalButton variant="save" size="sm" onClick={guardarDatos} disabled={guardando} className="mt-2.5">Guardar datos</ClinicalButton>

            <div className="mt-3 pt-3 border-t border-[#eef1f6]">
              <SectionHeader title="Razón social (facturación)" icon={Landmark} />
              {f.razon_social && !f.razon_social.compartida_de_centro_id ? (
                <div className="grid grid-cols-[2fr_1fr] gap-2">
                  <div><label className={L}>razón social</label>
                    <input value={rs.nombre} onChange={(e) => setRs({ ...rs, nombre: e.target.value })} className={F} /></div>
                  <div><label className={L}>cif</label>
                    <input value={rs.cif} onChange={(e) => setRs({ ...rs, cif: e.target.value.toUpperCase() })} className={F} /></div>
                  <p className="col-span-2 text-[11px] text-slate-500">Se guarda con «Guardar datos». En Config → Centro aparece bloqueada.</p>
                </div>
              ) : f.razon_social ? (
                <p className="text-[13px] text-[#333]">
                  <b className="text-[#1500A0]">{f.razon_social.nombre}</b> {f.razon_social.cif ? `· ${f.razon_social.cif}` : ""}
                  <span className="ml-1.5 text-[10px] font-semibold text-[#6D28D9] bg-[#FFFFFF] border border-[#C4B5FD] rounded-sm px-1.5 py-0.5">compartida</span>
                  <span className="block text-[11px] text-slate-500 mt-1">Se edita desde el centro que la comparte.</span>
                </p>
              ) : <p className="text-[12px] text-slate-400 italic">Sin razón social</p>}
            </div>
          </ClinicalCard>

          <ClinicalCard>
            <SectionHeader title="Plan contratado" icon={Package}
              action={<span className="text-[10px] font-semibold text-[#7f8c8d]">{(f.centro.modulos_activos ?? []).length} módulos activos</span>} />
            <div className="grid grid-cols-3 gap-2">
              {Object.keys(planes).map((p) => {
                const on = planActual === p;
                const col = PLAN_COLOR[p] ?? PLAN_COLOR_FALLBACK;
                const mods = (planes[p] ?? []).map((mid) => modulos.find((m) => m.id === mid)?.label ?? mid);
                return (
                  <button key={p} onClick={() => setPlan(p)}
                    className={`relative p-3 border-2 rounded-sm text-left transition-all ${on ? `${col.border} ${col.bg}` : "border-[#e5e7eb] bg-white hover:bg-[#E6EDFF]"}`}>
                    {on && <Check className={`w-3.5 h-3.5 absolute top-2 right-2 ${col.txt}`} />}
                    <div className="flex items-center gap-1.5 mb-1.5">
                      <div className={`w-2.5 h-2.5 rounded-full ${on ? col.dot : "bg-[#FFFFFF]"}`} />
                      <span className={`text-[12px] font-semibold uppercase ${on ? col.txt : "text-[#7f8c8d]"}`}>{p}</span>
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {mods.map((m) => (
                        <span key={m} className={`text-[9px] font-semibold uppercase px-1 py-0.5 rounded-sm ${on ? "bg-white/60" : "bg-[#FFFFFF]"} ${on ? col.txt : "text-[#7f8c8d]"}`}>{m}</span>
                      ))}
                    </div>
                  </button>
                );
              })}
            </div>
          </ClinicalCard>
        </div>

        {/* Columna derecha: Asociación, Personal, Salud */}
        <div className="flex flex-col gap-3">
          <ClinicalCard>
            <SectionHeader title="Asociación con otro centro" icon={Link2} />
            <select value={asoc.asociado_a_centro_id} onChange={(e) => setAsoc({ ...asoc, asociado_a_centro_id: e.target.value })} className={F}>
              <option value="">— Independiente —</option>
              {otrosCentros.map((oc) => <option key={oc.id} value={oc.id}>Asociado a: {oc.nombre}</option>)}
            </select>
            {asoc.asociado_a_centro_id ? (
              <div className="flex flex-col gap-1 mt-2">
                <label className="flex items-center gap-1.5 text-[12px] cursor-pointer">
                  <input type="checkbox" checked={asoc.comparte_personal} onChange={(e) => setAsoc({ ...asoc, comparte_personal: e.target.checked })} /> Comparte personal
                </label>
                <label className="flex items-center gap-1.5 text-[12px] cursor-pointer">
                  <input type="checkbox" checked={asoc.comparte_razon_social} onChange={(e) => setAsoc({ ...asoc, comparte_razon_social: e.target.checked })} /> Comparte razón social
                </label>
                <label className="flex items-center gap-1.5 text-[12px] cursor-pointer">
                  <input type="checkbox" checked={asoc.comparte_pacientes} onChange={(e) => setAsoc({ ...asoc, comparte_pacientes: e.target.checked })} /> Comparte pacientes <span className="text-[10px] text-[#6D28D9]">(pendiente)</span>
                </label>
              </div>
            ) : (
              <p className="text-[11px] text-slate-400 italic mt-1.5">Centro independiente — no comparte nada con otro centro.</p>
            )}
            <ClinicalButton variant="save" size="sm" onClick={guardarAsociacion} disabled={guardando} className="mt-2.5">Guardar asociación</ClinicalButton>
          </ClinicalCard>

          <ClinicalCard>
            <SectionHeader title={`Personal con acceso (${f.personal.length})`} icon={Users} />
            <div className="flex flex-col gap-0.5 mb-2 max-h-48 overflow-y-auto">
              {f.personal.map((p) => (
                <div key={p.usuario_id} className="flex items-center gap-2 text-[12px] py-1 border-b border-[#f0f2f5] last:border-0">
                  <span className="flex-1 min-w-0 truncate">{p.nombre}{" "}
                    {editandoEmailDe === p.usuario_id ? (
                      <span className="inline-flex items-center gap-1">
                        <input autoFocus value={emailEnEdicion} onChange={(e) => setEmailEnEdicion(e.target.value)}
                          onKeyDown={(e) => e.key === "Enter" && guardarEmail(p.usuario_id)}
                          className="border border-[#1ca0d1] rounded-sm px-1 py-0.5 text-[11px] w-40" />
                        <button onClick={() => guardarEmail(p.usuario_id)} className="text-[#0F8C7D] font-semibold">✓</button>
                        <button onClick={() => setEditandoEmailDe(null)} className="text-[#7f8c8d]">✕</button>
                      </span>
                    ) : (
                      <span className="text-[#7f8c8d] cursor-pointer hover:underline" title="Editar email"
                        onClick={() => { setEditandoEmailDe(p.usuario_id); setEmailEnEdicion(p.email); }}>· {p.email}</span>
                    )}
                  </span>
                  <span className="text-[10px] text-[#1ca0d1] shrink-0">{p.rol}</span>
                  <button onClick={() => resetPassword(p.usuario_id)} title="Resetear contraseña" className="text-[#7f8c8d] shrink-0 hover:bg-[#E6EDFF] hover:text-[#1500A0] rounded-sm p-0.5"><Key className="w-3.5 h-3.5" /></button>
                  <button onClick={() => quitarPersonal(p.usuario_id)} title="Quitar acceso" className="text-[#C026D3] shrink-0 hover:bg-[#E6EDFF] rounded-sm p-0.5"><X className="w-3.5 h-3.5" /></button>
                </div>
              ))}
              {f.personal.length === 0 && <p className="text-[11px] text-slate-400 italic py-1">Nadie tiene acceso todavía.</p>}
            </div>
            {nuevaPersonaCreada && (
              <div className="mb-2 text-[11px] bg-[#FFFFFF] border border-[#C4B5FD] rounded-sm px-2 py-1.5 text-[#4C1D95]">
                Persona nueva creada: <b>{nuevaPersonaCreada.email}</b> · contraseña temporal:{" "}
                <b className="font-mono">{nuevaPersonaCreada.password_temporal}</b> — guárdala, no se volverá a mostrar.
                <button onClick={() => setNuevaPersonaCreada(null)} className="ml-1.5 text-[#6D28D9] underline">cerrar</button>
              </div>
            )}
            {credencialReset && (
              <div className="mb-2 text-[11px] bg-[#FFFFFF] border border-[#C4B5FD] rounded-sm px-2 py-1.5 text-[#4C1D95]">
                Contraseña reseteada para <b>{credencialReset.email}</b>: {" "}
                <b className="font-mono">{credencialReset.password_temporal}</b> — guárdala, no se volverá a mostrar.
                <button onClick={() => setCredencialReset(null)} className="ml-1.5 text-[#6D28D9] underline">cerrar</button>
              </div>
            )}
            <div className="flex flex-col gap-1">
              <div className="flex gap-1.5">
                <input value={nuevoEmail} onChange={(e) => setNuevoEmail(e.target.value)} placeholder="email (existente o de una persona nueva)" className={F} />
                <ClinicalButton variant="accent" size="sm" icon={Plus} onClick={anadirPersonal}>Añadir</ClinicalButton>
              </div>
              <input value={nuevoNombre} onChange={(e) => setNuevoNombre(e.target.value)} placeholder="nombre (solo si es una persona nueva)" className={F} />
            </div>
          </ClinicalCard>

          <ClinicalCard>
            <SectionHeader title="Salud del centro" icon={HeartPulse}
              action={<ClinicalButton variant="ghost" size="sm" icon={RefreshCw} onClick={cargar}>Actualizar</ClinicalButton>} />
            <div className="flex items-center gap-2 mb-2">
              <span className={`w-2.5 h-2.5 rounded-full ${NIVEL_UI[f.salud.nivel_servicio]?.dot ?? "bg-slate-300"}`} />
              <span className={`text-[12px] font-semibold ${NIVEL_UI[f.salud.nivel_servicio]?.cls ?? ""}`}>{NIVEL_UI[f.salud.nivel_servicio]?.txt ?? f.salud.nivel_servicio}</span>
            </div>
            <p className="text-[13px] text-[#333] mb-1.5">
              <b>{f.salud.pacientes.toLocaleString("es-ES")}</b> pacientes · <b>{f.salud.citas.toLocaleString("es-ES")}</b> citas
              {f.salud.ultima_cita ? <span className="text-[#7f8c8d]"> · última {f.salud.ultima_cita}</span> : null}
            </p>
            {f.salud.alertas.length > 0 && (
              <div className="flex flex-col gap-1 mb-2">
                {f.salud.alertas.map((a, i) => (
                  <div key={i} className={`flex items-start gap-1.5 px-2 py-1.5 rounded-sm border-l-2 ${a.tipo === "error" ? "bg-[#FFFFFF] border-l-[#C026D3]" : "bg-[#FFFFFF] border-l-[#7C3AED]"}`}>
                    {a.tipo === "error" ? <AlertCircle className="w-3 h-3 text-[#C026D3] mt-0.5 shrink-0" /> : <AlertTriangle className="w-3 h-3 text-[#7C3AED] mt-0.5 shrink-0" />}
                    <div className="min-w-0">
                      <div className="text-[11px] font-semibold text-[#333]">{a.titulo}</div>
                      <div className="text-[10px] text-[#7f8c8d]">{a.descripcion}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
            <div className="flex flex-wrap gap-1.5">
              {f.salud.integraciones.length === 0 && <span className="text-[11px] text-slate-400 italic">Sin integraciones configuradas</span>}
              {f.salud.integraciones.map((i) => (
                <span key={i.tipo} className={`px-2 py-0.5 rounded-sm text-[10px] font-semibold border ${i.activo ? "bg-[#FFFFFF] text-[#0F8C7D] border-[#9FE6DB]" : "bg-[#FFFFFF] text-[#64748b] border-[#cbd5e1]"}`}>
                  {i.nombre || i.tipo}
                </span>
              ))}
            </div>
          </ClinicalCard>
        </div>
      </div>
    </div>
  );
}

function AparienciaPanel() {
  type Apariencia = { favicon_url?: string; logo_url?: string; icono_url?: string };
  const [ap, setAp] = useState<Apariencia>({});
  const [cargando, setCargando] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  const load = useCallback(() => {
    setCargando(true);
    api.get<Apariencia>("/superuser/apariencia").then(setAp).catch(() => {}).finally(() => setCargando(false));
  }, []);
  useEffect(() => { load(); }, [load]);

  function flash(t: string) { setMsg(t); setTimeout(() => setMsg(""), 2500); }
  const img = (u?: string) => (u ? `${API_BASE}${u}` : "");

  async function subir(campo: keyof Apariencia, f?: File) {
    if (!f) return;
    try {
      const { url } = await api.upload("/uploads", f);
      setAp((prev) => ({ ...prev, [campo]: url }));
      flash("Imagen subida ✓ — pulsa Guardar para publicarla");
    } catch (e) { flash(errMsg(e)); }
  }

  async function guardar() {
    setSaving(true);
    try {
      await api.put("/superuser/apariencia", ap);
      flash("Apariencia guardada ✓");
    } catch (e) { flash(errMsg(e)); }
    finally { setSaving(false); }
  }

  if (cargando) return <div className="p-4 text-[12px] text-[#7f8c8d]">Cargando…</div>;

  return (
    <div className="p-4 max-w-2xl">
      <SectionHeader title="Apariencia de la web" icon={Package} />
      <p className="text-[11px] text-[#7f8c8d] mb-3">
        Favicon, logo e icono a nivel de PLATAFORMA (no de un centro concreto). El favicon se
        sirve incluso sin haber iniciado sesión (login, recuperar contraseña).
      </p>
      <div className="grid grid-cols-3 gap-3">
        <ImgPicker label="Favicon (pestaña navegador)" url={img(ap.favicon_url)}
          onPick={(f) => subir("favicon_url", f)} onClear={() => setAp((p) => ({ ...p, favicon_url: "" }))} />
        <ImgPicker label="Logo" url={img(ap.logo_url)}
          onPick={(f) => subir("logo_url", f)} onClear={() => setAp((p) => ({ ...p, logo_url: "" }))} />
        <ImgPicker label="Icono" url={img(ap.icono_url)}
          onPick={(f) => subir("icono_url", f)} onClear={() => setAp((p) => ({ ...p, icono_url: "" }))} />
      </div>
      <div className="flex items-center gap-3 mt-3">
        <ClinicalButton onClick={guardar} disabled={saving}>{saving ? "Guardando…" : "Guardar"}</ClinicalButton>
        {msg && <span className="text-[11px] text-[#1ca0d1]">{msg}</span>}
      </div>
    </div>
  );
}

function Grid({ columnas, filas }: { columnas: string[]; filas: Record<string, unknown>[] }) {
  if (!filas.length) return <div className="text-[12px] text-slate-400 italic py-4 text-center">Sin filas.</div>;
  return (
    <div className="overflow-auto border border-[#e5e7eb] rounded-sm max-h-[55vh]">
      <table className="text-[11px] border-collapse w-full">
        <thead className="sticky top-0 bg-[#FFFFFF]">
          <tr>{columnas.map((c) => <th key={c} className="text-left font-semibold text-[#1500A0] px-2 py-1 border-b border-[#e5e7eb] whitespace-nowrap">{c}</th>)}</tr>
        </thead>
        <tbody>
          {filas.map((f, i) => (
            <tr key={i} className="hover:bg-[#E6EDFF]">
              {columnas.map((c) => <td key={c} className="px-2 py-1 border-b border-[#f0f2f5] text-[#333333] max-w-[280px] truncate" title={cell(f[c])}>{cell(f[c])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
