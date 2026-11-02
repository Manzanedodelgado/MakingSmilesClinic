"use client";
/**
 * Estados de cita — tarjeta de Config · Clínica · Agenda, con los tokens de esa página
 * (título 13px/500 #0f172a, cabecera 10px/500 #475569 con línea #94a3b8, celdas 11px
 * #1e293b, casilla #81C3E0). Sin botón Guardar, como el resto de Agenda: cada cambio
 * se guarda al momento (color/activo al cambiar, nombre/orden al salir del campo).
 * Datos: GET /configuracion/centro → estados_cita; PUT /configuracion/centro/estado/{id}.
 */
import { useEffect, useState } from "react";
import { api } from "@/shared/lib/api";

type EstadoCita = { id: number; codigo: string; nombre: string; color?: string | null; orden?: number | null; activo: boolean };

const COLS = "grid grid-cols-[44px_1fr_60px_50px] gap-x-3";
const CELDA = "w-full border border-[#e5e7eb] rounded-md outline-none bg-white text-[11px] text-[#1e293b] px-2 py-0.5 focus:border-[#1BA4E9]";

function Check({ on, onClick, label }: { on: boolean; onClick: () => void; label: string }) {
  return (
    <span role="checkbox" aria-checked={on} aria-label={label} tabIndex={0} onClick={onClick}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onClick(); } }}
      className="inline-flex w-[18px] h-[18px] rounded items-center justify-center cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-[#1BA4E9]"
      style={{ background: on ? "#81C3E0" : "#FFFFFF" }}>
      {on && <svg width="11" height="9" viewBox="0 0 11 9"><path d="M1 4.5L4 7.5L10 1" stroke="white" strokeWidth="1.6" fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>}
    </span>
  );
}

export default function EstadosCita() {
  const [estados, setEstados] = useState<EstadoCita[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get<{ estados_cita: EstadoCita[] }>("/configuracion/centro")
      .then((d) => setEstados([...d.estados_cita].sort((a, b) => (a.orden ?? 0) - (b.orden ?? 0))))
      .catch(() => setError("No se pudieron cargar los estados."));
  }, []);

  function editar(id: number, patch: Partial<EstadoCita>) {
    setEstados((prev) => prev && prev.map((e) => (e.id === id ? { ...e, ...patch } : e)));
  }
  async function guardar(e: EstadoCita) {
    setError("");
    try { await api.put(`/configuracion/centro/estado/${e.id}`, { codigo: e.codigo, nombre: e.nombre, color: e.color, orden: e.orden, activo: e.activo }); }
    catch { setError(`No se pudo guardar "${e.nombre}".`); }
  }
  const cambiar = (e: EstadoCita, patch: Partial<EstadoCita>) => { editar(e.id, patch); guardar({ ...e, ...patch }); };

  return (
    <div className="bg-white rounded-md shadow-sm p-4">
      <div className="text-[13px] font-medium text-[#0f172a] mb-2">Estados de cita</div>
      <div className={`${COLS} text-[10px] font-medium text-[#475569] border-b border-[#94a3b8] pb-1 max-w-[520px]`}>
        <div>Color</div><div>Nombre</div><div>Orden</div><div>Activo</div>
      </div>
      {estados?.map((e) => (
        <div key={e.id} className={`${COLS} items-center py-1 border-b border-[#f1f5f9] max-w-[520px]`}>
          <input type="color" aria-label={`Color de ${e.nombre}`} value={e.color || "#94a3b8"}
            onChange={(ev) => editar(e.id, { color: ev.target.value })} onBlur={() => guardar(e)}
            className="w-6 h-6 rounded border border-[#e5e7eb] cursor-pointer bg-white p-0" />
          <input aria-label={`Nombre de ${e.codigo}`} className={CELDA} value={e.nombre}
            onChange={(ev) => editar(e.id, { nombre: ev.target.value })} onBlur={() => guardar(e)} />
          <input type="number" aria-label={`Orden de ${e.nombre}`} className={`${CELDA} tabular-nums`} value={e.orden ?? ""}
            onChange={(ev) => editar(e.id, { orden: ev.target.value ? Number(ev.target.value) : null })} onBlur={() => guardar(e)} />
          <Check on={e.activo} label={`${e.nombre} activo`} onClick={() => cambiar(e, { activo: !e.activo })} />
        </div>
      ))}
      {estados?.length === 0 && <div className="text-[11px] text-[#94a3b8] py-2">Sin estados configurados.</div>}
      {!estados && !error && <div className="text-[11px] text-[#94a3b8] py-2">Cargando…</div>}
      {error && <div className="text-[11px] text-[#C026D3] mt-2">{error}</div>}
    </div>
  );
}
