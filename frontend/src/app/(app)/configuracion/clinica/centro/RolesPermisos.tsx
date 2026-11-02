"use client";
/**
 * Config · Clínica · Centro · ROLES y PERMISOS.
 * Un rol agrupa permisos por área (Sin acceso · Ver · Editar). El rol marca el techo de lo que
 * puede hacer una persona; en Config › Personal se le pueden quitar permisos concretos a cada
 * persona, nunca darle más de lo que su rol incluye.
 */
import { useCallback, useEffect, useState } from "react";
import { Plus, Save, ShieldCheck, Trash2 } from "lucide-react";
import { api } from "@/shared/lib/api";
import { errMsg } from "@/shared/lib/errores";
import { NivelPicker, nivelDeArea, conNivel, type TabDef } from "../../_components/NivelPicker";
import { PestanasArea } from "../../_components/PestanasArea";

type Area = { key: string; nombre: string; ver?: string; editar?: string; tabs?: TabDef[] };
type Extra = { codigo: string; nombre: string };
type Rol = { id: number; nombre: string; descripcion?: string | null; permisos: string[]; usuarios: number; sistema: boolean };
type Borrador = { id?: number; nombre: string; descripcion: string; permisos: string[] };

export function RolesPermisos() {
  const [roles, setRoles] = useState<Rol[]>([]);
  const [areas, setAreas] = useState<Area[]>([]);
  const [extras, setExtras] = useState<Extra[]>([]);
  const [sel, setSel] = useState<Borrador | null>(null);
  const [msg, setMsg] = useState<{ t: string; e?: boolean }>({ t: "" });
  const [confirmarBorrado, setConfirmarBorrado] = useState(false);
  const flash = (t: string, e = false) => { setMsg({ t, e }); setTimeout(() => setMsg({ t: "" }), 3500); };

  const cargar = useCallback(async () => {
    const x = await api.get<{ roles: Rol[]; permiso_areas: Area[]; permiso_extras: Extra[] }>("/configuracion/roles");
    setRoles(x.roles); setAreas(x.permiso_areas ?? []); setExtras(x.permiso_extras ?? []);
  }, []);
  useEffect(() => { cargar().catch((e) => flash(errMsg(e), true)); }, [cargar]);

  const elegir = (r: Rol) => { setConfirmarBorrado(false); setSel({ id: r.id, nombre: r.nombre, descripcion: r.descripcion ?? "", permisos: r.permisos }); };
  const nuevo = () => { setConfirmarBorrado(false); setSel({ nombre: "", descripcion: "", permisos: [] }); };
  const actual = sel?.id != null ? roles.find((r) => r.id === sel.id) : undefined;

  async function guardar() {
    if (!sel?.nombre.trim()) { flash("El nombre del rol es obligatorio", true); return; }
    const body = { nombre: sel.nombre.trim(), descripcion: sel.descripcion.trim() || null, permisos: sel.permisos };
    try {
      const r = sel.id != null
        ? await api.put<Rol>(`/configuracion/roles/${sel.id}`, body)
        : await api.post<Rol>("/configuracion/roles", body);
      await cargar(); elegir(r); flash("Rol guardado ✓");
    } catch (e) { flash(errMsg(e), true); }
  }
  async function borrar() {
    if (sel?.id == null) return;
    try { await api.delete(`/configuracion/roles/${sel.id}`); setSel(null); setConfirmarBorrado(false); await cargar(); flash("Rol eliminado ✓"); }
    catch (e) { setConfirmarBorrado(false); flash(errMsg(e), true); }
  }
  const toggleExtra = (c: string) => setSel((p) => p && ({ ...p, permisos: p.permisos.includes(c) ? p.permisos.filter((k) => k !== c) : [...p.permisos, c] }));

  return (
    <section className="mt-6 bg-white border border-[#e5e7eb] rounded-md shadow-sm" aria-label="Roles y permisos">
      <header className="flex items-center gap-2 px-4 h-11 border-b border-[#e5e7eb]">
        <ShieldCheck className="w-4 h-4 text-[#1500A0]" />
        <h2 className="text-[13px] font-semibold uppercase tracking-wide text-[#1500A0]">Roles y permisos</h2>
        <span className="text-[11px] text-[#7f8c8d]">El rol marca el máximo; en Personal se le pueden quitar permisos a cada persona.</span>
        {msg.t && <span className={`ml-auto text-[12px] font-semibold ${msg.e ? "text-[#C026D3]" : "text-[#0F8C7D]"}`}>{msg.t}</span>}
      </header>
      <div className="grid grid-cols-[240px_1fr] min-h-[260px]">
        <div className="border-r border-[#e5e7eb] p-2 flex flex-col gap-1">
          {roles.map((r) => (
            <button key={r.id} type="button" onClick={() => elegir(r)}
              className={`text-left px-3 py-2 rounded-sm border text-[12.5px] ${sel?.id === r.id ? "bg-[#e6edff] border-[#1500A0] text-[#1500A0] font-semibold" : "bg-white border-[#e5e7eb] text-[#1e293b] hover:border-[#1ca0d1]"}`}>
              <span className="block truncate">{r.nombre}</span>
              <span className="block text-[10.5px] text-[#7f8c8d] font-normal">{r.usuarios} persona{r.usuarios === 1 ? "" : "s"}{r.sistema ? " · sistema" : ""}</span>
            </button>
          ))}
          <button type="button" onClick={nuevo}
            className="mt-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-sm border border-dashed border-[#1ca0d1] text-[12px] font-semibold text-[#1ca0d1] hover:bg-[#E6EDFF]">
            <Plus className="w-3.5 h-3.5" /> Nuevo rol
          </button>
        </div>
        <div className="p-4">
          {!sel ? (
            <p className="text-[12px] italic text-[#94a3b8]">Elige un rol para ver y editar sus permisos, o crea uno nuevo.</p>
          ) : (
            <div className="flex flex-col gap-3">
              <div className="grid grid-cols-2 gap-3">
                <label className="text-[11px] font-semibold text-[#1ca0d1] uppercase tracking-wide">Nombre
                  <input value={sel.nombre} disabled={actual?.sistema} onChange={(e) => setSel({ ...sel, nombre: e.target.value })}
                    className="mt-1 w-full h-[30px] px-2 border border-[#ccc] rounded-[4px] text-[12px] normal-case font-normal text-[#333] disabled:bg-[#FFFFFF] focus:border-[#005BB5] outline-none" />
                </label>
                <label className="text-[11px] font-semibold text-[#1ca0d1] uppercase tracking-wide">Descripción
                  <input value={sel.descripcion} onChange={(e) => setSel({ ...sel, descripcion: e.target.value })}
                    className="mt-1 w-full h-[30px] px-2 border border-[#ccc] rounded-[4px] text-[12px] normal-case font-normal text-[#333] focus:border-[#005BB5] outline-none" />
                </label>
              </div>
              {actual && actual.usuarios > 0 && (
                <p className="text-[11.5px] text-[#7C3AED] bg-[#FFFFFF] border border-[#C4B5FD] rounded-sm px-3 py-1.5">
                  {actual.usuarios} persona{actual.usuarios === 1 ? "" : "s"} usa{actual.usuarios === 1 ? "" : "n"} este rol: lo que cambies aquí les afecta (salvo lo que ya se les haya quitado en Personal).
                </p>
              )}
              <div className="border border-[#e5e7eb] rounded-md divide-y divide-[#f0f2f5] overflow-hidden">
                {areas.map((a) => (
                  <div key={a.key}>
                    <div className="flex items-center justify-between px-3 py-2 bg-white">
                      <span className="text-[12.5px] font-semibold text-[#1e293b]">{a.nombre}</span>
                      <NivelPicker nivel={nivelDeArea(a, sel.permisos)} soloVer={!a.editar}
                        onChange={(n) => setSel({ ...sel, permisos: conNivel(a, sel.permisos, n) })} />
                    </div>
                    {a.tabs?.length && nivelDeArea(a, sel.permisos) !== "none" ? (
                      <PestanasArea tabs={a.tabs} permisos={sel.permisos}
                        onChange={(permisos) => setSel({ ...sel, permisos })} />
                    ) : null}
                  </div>
                ))}
              </div>
              {extras.length > 0 && (
                <div>
                  <span className="text-[10px] font-semibold text-[#7f8c8d] uppercase tracking-wide">Accesos especiales</span>
                  <div className="flex flex-wrap gap-2 mt-1">
                    {extras.map((x) => {
                      const on = sel.permisos.includes(x.codigo);
                      return (
                        <button key={x.codigo} type="button" onClick={() => toggleExtra(x.codigo)}
                          className={`px-3 py-1.5 rounded-sm border text-[12px] font-semibold ${on ? "bg-[#1ca0d1] text-white border-[#1ca0d1]" : "bg-white text-[#64748b] border-[#e5e7eb] hover:border-[#1ca0d1]"}`}>{x.nombre}</button>
                      );
                    })}
                  </div>
                </div>
              )}
              <div className="flex items-center gap-2 pt-1">
                {sel.id != null && !actual?.sistema && (confirmarBorrado ? (
                  <>
                    <span className="text-[12px] text-[#C026D3] font-semibold">¿Eliminar «{sel.nombre}»?</span>
                    <button type="button" onClick={borrar} className="px-3 py-1.5 rounded-sm bg-[#C026D3] text-white text-[12px] font-semibold">Sí, eliminar</button>
                    <button type="button" onClick={() => setConfirmarBorrado(false)} className="px-3 py-1.5 rounded-sm border border-[#e5e7eb] text-[12px]">No</button>
                  </>
                ) : (
                  <button type="button" onClick={() => setConfirmarBorrado(true)} className="flex items-center gap-1.5 px-3 py-1.5 rounded-sm border border-[#e5e7eb] text-[12px] text-[#C026D3] hover:border-[#C026D3]">
                    <Trash2 className="w-3.5 h-3.5" /> Eliminar rol
                  </button>
                ))}
                <button type="button" onClick={guardar} className="ml-auto flex items-center gap-1.5 px-4 py-1.5 rounded-sm bg-[#1500A0] text-white text-[12px] font-semibold hover:brightness-110">
                  <Save className="w-3.5 h-3.5" /> Guardar rol
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
