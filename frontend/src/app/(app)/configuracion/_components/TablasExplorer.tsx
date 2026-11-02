"use client";
import { useEffect, useRef, useState } from "react";
import { X, Check } from "lucide-react";
import { api, API_BASE } from "@/shared/lib/api";
import { Modal, ModalBody, ModalButton } from "@/shared/components";

type Tabla = { nombre: string; filas: number };
type Col = { nombre: string; tipo: string };
type Row = Record<string, unknown>;
type Datos = { nombre: string; pk: string[]; columnas: Col[]; filas: Row[]; total: number; limit: number; offset: number };

const LIMIT = 50;
const celda = (v: unknown) => (v === null || v === undefined ? "—" : typeof v === "object" ? JSON.stringify(v) : String(v));

export function TablasExplorer() {
  const [tablas, setTablas] = useState<Tabla[]>([]);
  const [busca, setBusca] = useState("");
  const [sel, setSel] = useState("");
  const [datos, setDatos] = useState<Datos | null>(null);
  const [offset, setOffset] = useState(0);
  const [cargando, setCargando] = useState(false);
  const [msg, setMsg] = useState<{ t: string; err?: boolean }>({ t: "" });
  const [edit, setEdit] = useState<Row | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const flash = (t: string, err = false) => { setMsg({ t, err }); setTimeout(() => setMsg({ t: "" }), 3500); };
  const cargarTablas = () => api.get<{ tablas: Tabla[] }>("/configuracion/admin/tablas").then((d) => setTablas(d.tablas)).catch(() => {});
  useEffect(() => { cargarTablas(); }, []);

  function cargarDatos() {
    if (!sel) return;
    setCargando(true);
    api.get<Datos>(`/configuracion/admin/tabla/${sel}?limit=${LIMIT}&offset=${offset}`)
      .then(setDatos).catch(() => setDatos(null)).finally(() => setCargando(false));
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { cargarDatos(); }, [sel, offset]);

  const lista = tablas.filter((t) => t.nombre.includes(busca.toLowerCase()));
  const pk = datos?.pk?.length === 1 ? datos.pk[0] : null;

  async function exportar() {
    try {
      const res = await fetch(`${API_BASE}/configuracion/admin/tabla/${sel}/export`, { credentials: "include" });
      if (!res.ok) throw new Error();
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a"); a.href = url; a.download = `${sel}.csv`; a.click(); URL.revokeObjectURL(url);
    } catch { flash("No se pudo exportar", true); }
  }

  async function importar(file: File) {
    const fd = new FormData(); fd.append("file", file);
    try {
      const res = await fetch(`${API_BASE}/configuracion/admin/tabla/${sel}/import`, { method: "POST", body: fd, credentials: "include" });
      const d = await res.json();
      if (!res.ok) throw new Error(d.detail || "Error");
      flash(`${d.insertadas} filas importadas ✓`); cargarDatos(); cargarTablas();
    } catch (e) { flash(e instanceof Error ? e.message : "Error al importar", true); }
  }

  async function guardarEdicion(cambios: Row) {
    if (!pk || !edit) return;
    try {
      await api.put(`/configuracion/admin/tabla/${sel}/fila`, { pk_valor: edit[pk], cambios });
      setEdit(null); flash("Fila actualizada ✓"); cargarDatos();
    } catch (e) {
      flash(e instanceof Error ? e.message.replace(/.*→\s*\d+\s*/, "") : "Error", true);
    }
  }

  return (
    <div className="flex gap-2.5 h-[calc(100vh-200px)]">
      {msg.t && <div className="fixed top-14 right-6 z-50 px-4 py-2.5 rounded-sm font-semibold text-[12px] shadow-lg"
        style={{ background: msg.err ? "#C026D3" : "#2DD9C3", color: msg.err ? "#fff" : "#1500A0" }}>{msg.t}</div>}

      {/* lista de tablas */}
      <aside className="w-56 shrink-0 bg-white border border-[#e5e7eb] rounded-sm flex flex-col">
        <div className="p-2.5 border-b border-[#e5e7eb] relative">
          <input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar tabla…"
            className="w-full h-8 px-2 pr-7 text-[12px] border border-[#e5e7eb] rounded-sm outline-none focus:border-[#1ca0d1]" />
          {busca && (
            <button type="button" onClick={() => setBusca("")} className="absolute right-3.5 top-1/2 -translate-y-1/2 text-[#9ca3af] hover:text-[#C026D3]">
              <X className="w-3.5 h-3.5" />
            </button>
          )}
          <div className="text-[11px] text-[#9aa7c2] mt-1.5">{lista.length} tablas</div>
        </div>
        <div className="overflow-y-auto flex-1">
          {lista.map((t) => (
            <button key={t.nombre} onClick={() => { setSel(t.nombre); setOffset(0); }}
              className={`w-full flex items-center justify-between px-2.5 py-1.5 text-left text-[12px] border-b border-[#f4f6f9] ${sel === t.nombre ? "bg-[#FFFFFF] text-[#1500A0] font-semibold" : "hover:bg-[#E6EDFF] text-[#33415c]"}`}>
              <span className="truncate">{t.nombre}</span>
              <span className="text-[11px] text-[#9aa7c2] ml-2 shrink-0">{t.filas.toLocaleString()}</span>
            </button>
          ))}
        </div>
      </aside>

      {/* datos */}
      <section className="flex-1 min-w-0 bg-white border border-[#e5e7eb] rounded-sm flex flex-col">
        {!sel ? (
          <div className="flex-1 grid place-items-center text-[#9aa7c2] text-[12px]">Selecciona una tabla para ver sus datos.</div>
        ) : (
          <>
            <div className="p-2.5 border-b border-[#e5e7eb] flex items-center gap-2.5 flex-wrap">
              <b className="text-[#1500A0] text-[13px]">{sel}</b>
              <span className="text-[12px] text-[#9aa7c2]">{datos ? `${datos.total.toLocaleString()} filas · ${datos.columnas.length} cols` : "…"}</span>
              <div className="ml-auto flex items-center gap-2 text-[12px]">
                <button onClick={exportar} className="px-2.5 py-1 border border-[#e5e7eb] rounded hover:bg-[#E6EDFF]">⬇ Exportar CSV</button>
                <button onClick={() => fileRef.current?.click()} className="px-2.5 py-1 border border-[#e5e7eb] rounded hover:bg-[#E6EDFF]">⬆ Subir CSV</button>
                <input ref={fileRef} type="file" accept=".csv" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) importar(f); e.target.value = ""; }} />
                <span className="w-px h-5 bg-[#FFFFFF]" />
                <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - LIMIT))} className="px-2 py-1 border border-[#e5e7eb] rounded disabled:opacity-40">←</button>
                <span className="text-[#7f8c8d]">{datos ? `${datos.total ? offset + 1 : 0}–${Math.min(offset + LIMIT, datos.total)}` : ""}</span>
                <button disabled={!datos || offset + LIMIT >= datos.total} onClick={() => setOffset(offset + LIMIT)} className="px-2 py-1 border border-[#e5e7eb] rounded disabled:opacity-40">→</button>
              </div>
            </div>
            <div className="overflow-auto flex-1">
              {cargando ? <div className="p-4 text-[#9aa7c2] text-[12px]">Cargando…</div> : datos && (
                <table className="text-[12px] border-collapse w-full">
                  <thead className="sticky top-0 bg-[#FFFFFF]">
                    <tr>
                      {pk && <th className="px-2 py-2 border-b border-[#e5e7eb] w-8" />}
                      {datos.columnas.map((c) => (
                        <th key={c.nombre} className="text-left px-3 py-2 border-b border-[#e5e7eb] whitespace-nowrap text-[#1500A0] font-semibold">
                          {c.nombre}<span className="block text-[9px] text-[#9aa7c2] font-normal">{c.tipo}</span>
                        </th>))}
                    </tr>
                  </thead>
                  <tbody>
                    {datos.filas.map((f, i) => (
                      <tr key={i} className="hover:bg-[#E6EDFF]">
                        {pk && <td className="px-2 py-1.5 border-b border-[#f4f6f9] text-center">
                          <button onClick={() => setEdit(f)} title="Editar" className="text-[#1ca0d1] hover:text-[#1500A0]">✎</button></td>}
                        {datos.columnas.map((c) => (
                          <td key={c.nombre} className="px-3 py-1.5 border-b border-[#f4f6f9] whitespace-nowrap max-w-[280px] truncate" title={celda(f[c.nombre])}>{celda(f[c.nombre])}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
            {!pk && datos && <div className="px-3 py-1.5 text-[11px] text-[#9aa7c2] border-t border-[#eef1f6]">Edición por fila no disponible (la tabla no tiene clave primaria simple).</div>}
          </>
        )}
      </section>

      {edit && pk && datos && (
        <EditModal row={edit} columnas={datos.columnas} pk={pk} onClose={() => setEdit(null)} onSave={guardarEdicion} />
      )}
    </div>
  );
}

function EditModal({ row, columnas, pk, onClose, onSave }: { row: Row; columnas: Col[]; pk: string; onClose: () => void; onSave: (c: Row) => void }) {
  const [vals, setVals] = useState<Record<string, string>>(() =>
    Object.fromEntries(columnas.map((c) => [c.nombre, row[c.nombre] == null ? "" : (typeof row[c.nombre] === "object" ? JSON.stringify(row[c.nombre]) : String(row[c.nombre]))])));
  function save() {
    const cambios: Row = {};
    for (const c of columnas) {
      if (c.nombre === pk) continue;
      const orig = row[c.nombre] == null ? "" : (typeof row[c.nombre] === "object" ? JSON.stringify(row[c.nombre]) : String(row[c.nombre]));
      if (vals[c.nombre] !== orig) cambios[c.nombre] = vals[c.nombre];
    }
    if (Object.keys(cambios).length === 0) { onClose(); return; }
    onSave(cambios);
  }
  return (
    <Modal
      title={`Editar fila · ${pk}=${String(row[pk])}`}
      onClose={onClose}
      size="lg"
      closeOnBackdrop={false}
      footer={
        <>
          <ModalButton variant="magenta" icon={X} onClick={onClose}>Cancelar</ModalButton>
          <ModalButton variant="primary" icon={Check} onClick={save}>Guardar</ModalButton>
        </>
      }
    >
      <ModalBody>
        <div className="grid grid-cols-2 gap-2.5">
          {columnas.map((c) => {
            const ro = c.nombre === pk || c.nombre === "created_at";
            return (
              <label key={c.nombre} className="flex flex-col gap-1">
                <span className="text-[10px] uppercase tracking-wide text-[#1ca0d1] font-semibold">{c.nombre} <span className="text-[#9aa7c2] normal-case">{c.tipo}</span></span>
                <input disabled={ro} value={vals[c.nombre]} onChange={(e) => setVals({ ...vals, [c.nombre]: e.target.value })}
                  className={`h-8 px-2 text-[12px] border rounded-md outline-none ${ro ? "bg-[#FFFFFF] text-[#9aa7c2]" : "border-[#BFE4F7] focus:border-[#21A2E5] focus:ring-2 focus:ring-[#21A2E5]/20"}`} />
              </label>
            );
          })}
        </div>
      </ModalBody>
    </Modal>
  );
}
