"use client";
import { Users, Plus, Save, ToggleLeft, ToggleRight, RotateCcw, CalendarClock, X } from "lucide-react";
/**
 * Config · Clínica · Personal — gestión de usuarios de la app (tabla `usuarios`
 * + rol vía `user_center_roles`). Master-detail con estética idéntica al .37,
 * pero usando el modelo de roles nuevo (no flags de permiso planos).
 */
import { useEffect, useState } from "react";
import { api } from "@/shared/lib/api";
import { ClinicalCard, SectionHeader, ClinicalButton, INPUT, LABEL, SELECT, EMPTY, Modal, ModalBody, ModalButton, MODAL_INPUT } from "@/shared/components";
import { type EstadoFiltro } from "../../_components/ListFilter";
import { errMsg } from "@/shared/lib/errores";
import { NivelPicker, nivelDeArea, conNivel, type Nivel, type TabDef } from "../../_components/NivelPicker";
import { PestanasArea } from "../../_components/PestanasArea";

const TIPOS = ["DOCTOR", "HIGIENISTA", "ADMINISTRADOR", "COORDINADOR", "RECEPCION", "AUXILIAR"];

type Rol = { id: number; nombre: string; permisos: string[] };
// Permisos agrupados por ÁREA con nivel Ver/Editar (+ accesos sueltos que no son ver/editar).
type PermArea = { key: string; nombre: string; ver?: string; editar?: string; tabs?: TabDef[] };
type PermExtra = { codigo: string; nombre: string };
type Periodo = {
  id: number; orden: number; codigo: string; staff_tipo?: string | null; tipo_contrato?: string | null;
  fecha_alta?: string | null; fecha_baja?: string | null; abierto: boolean; colaborador_id?: number | null;
};
type Persona = {
  id: number; nombre: string; apellidos?: string | null; nif?: string | null; email?: string | null;
  username?: string | null; telefono?: string | null; color?: string | null;
  staff_tipo?: string | null; tipo_contrato?: string | null;
  fecha_alta?: string | null; fecha_baja?: string | null; activo: boolean; periodo_codigo?: string | null;
  periodos?: Periodo[];
  tiene_login: boolean; rol_id?: number | null; rol_nombre?: string | null; colaborador_id?: number | null;
  permisos?: string[];   // permisos EFECTIVOS: (rol − límites) ∪ directos
  permisos_rol?: string[];        // techo que da su rol
  permisos_directos?: string[];   // concesiones heredadas, fuera del rol
};
const CONTRATOS = ["Autónomo", "Reg. General"];
type Draft = Partial<Persona> & { password?: string };

function Toggle({ on, onClick }: { on: boolean; onClick: () => void }) {
  return (
    <div onClick={onClick} className="cursor-pointer">
      {on ? <ToggleRight className="w-5 h-5 text-[#2DD9C3]" /> : <ToggleLeft className="w-5 h-5 text-slate-300" />}
    </div>
  );
}
// Selector segmentado del nivel de acceso a un área: Sin acceso · Ver · Editar.
export default function PersonalPage() {
  const [lista, setLista] = useState<Persona[]>([]);
  const [roles, setRoles] = useState<Rol[]>([]);
  const [permAreas, setPermAreas] = useState<PermArea[]>([]);
  const [permExtras, setPermExtras] = useState<PermExtra[]>([]);
  const [sel, setSel] = useState<Draft | null>(null);
  const [estado, setEstado] = useState<EstadoFiltro>("activos");
  const [msg, setMsg] = useState<{ t: string; e?: boolean }>({ t: "" });
  const [reactOpen, setReactOpen] = useState(false);
  const flash = (t: string, e = false) => { setMsg({ t, e }); setTimeout(() => setMsg({ t: "" }), 3000); };

  const filtrada = lista.filter((u) => {
    if (estado === "activos" && !u.activo) return false;
    if (estado === "inactivos" && u.activo) return false;
    return true;
  });

  async function load() {
    const x = await api.get<{ personal: Persona[]; roles: Rol[]; permiso_areas: PermArea[]; permiso_extras: PermExtra[] }>("/configuracion/personal");
    setLista(x.personal); setRoles(x.roles); setPermAreas(x.permiso_areas ?? []); setPermExtras(x.permiso_extras ?? []);
  }
  useEffect(() => { load(); }, []);

  const nuevo = () => setSel({ nombre: "", staff_tipo: "DOCTOR", color: "#1500A0", rol_id: roles[0]?.id, permisos: roles[0]?.permisos ?? [] });
  // Nivel actual del área (editar implica ver). Cambiar el nivel reescribe solo los códigos
  // de ESA área, dejando intactos el resto (y los no gestionables, que el backend respeta).
  const nivelArea = (a: PermArea, permisos: string[]): Nivel => nivelDeArea(a, permisos);
  const setNivelArea = (a: PermArea, nivel: Nivel) => setSel((p) => ({ ...(p as Draft), permisos: conNivel(a, p?.permisos ?? [], nivel, techo(p as Draft)) }));
  const setTabs = (permisos: string[]) => setSel((p) => ({ ...(p as Draft), permisos }));
  const toggleExtra = (codigo: string) => setSel((p) => {
    const cur = p?.permisos ?? [];
    return { ...(p as Draft), permisos: cur.includes(codigo) ? cur.filter((k) => k !== codigo) : [...cur, codigo] };
  });
  // Techo = lo que da el rol + las concesiones directas heredadas. Si el rol no define permisos
  // no hay techo (modo anterior: se marcan libremente).
  const permisosDeRol = (rolId?: number | null) => roles.find((r) => r.id === rolId)?.permisos ?? [];
  const techo = (p: Draft | null): string[] | null => {
    const R = permisosDeRol(p?.rol_id);
    return R.length ? [...new Set([...R, ...(p?.permisos_directos ?? [])])] : null;
  };
  const maxArea = (a: PermArea): Nivel => { const t = techo(sel); return t ? nivelDeArea(a, t) : "editar"; };
  const cambiarRol = (rolId: number | null) => setSel((p) => {
    const R = permisosDeRol(rolId);
    const permisos = R.length ? [...new Set([...R, ...(p?.permisos_directos ?? [])])] : (p?.permisos ?? []);
    return { ...(p as Draft), rol_id: rolId, permisos };
  });
  const s = (k: keyof Draft, v: unknown) => setSel((p) => ({ ...(p as Draft), [k]: v }));

  async function guardar() {
    if (!sel?.nombre?.trim()) { flash("El nombre es obligatorio", true); return; }
    try {
      // `activo` no se envía: lo deriva el backend de fecha_baja.
      const body = {
        nombre: sel.nombre, apellidos: sel.apellidos ?? null, nif: sel.nif ?? null, email: sel.email ?? null,
        username: sel.username ?? null, telefono: sel.telefono ?? null, color: sel.color ?? null,
        staff_tipo: sel.staff_tipo ?? null, tipo_contrato: sel.tipo_contrato ?? null,
        fecha_alta: sel.fecha_alta || null, fecha_baja: sel.fecha_baja || null,
        rol_id: sel.rol_id ?? null,
        permisos: sel.permisos ?? [],   // áreas habilitadas (el nuevo "Permisos")
        ...(sel.password ? { password: sel.password } : {}),
      };
      if (sel.id) await api.put(`/configuracion/personal/${sel.id}`, body);
      else await api.post("/configuracion/personal", body);
      flash("Perfil guardado ✓"); setSel(null); load();
    } catch (e) { flash(errMsg(e), true); }
  }

  // On-off de la ficha = colaborador sí/no (crea/quita el vínculo en BD al instante).
  async function toggleColaborador() {
    if (!sel?.id) { flash("Guarda primero la persona para marcarla como colaborador", true); return; }
    const next = sel.colaborador_id == null;
    try {
      const dto = await api.put<Persona>(`/configuracion/personal/${sel.id}/colaborador`, { colaborador: next });
      setSel((p) => ({ ...(p as Draft), colaborador_id: dto.colaborador_id }));
      flash(next ? "Marcado como colaborador ✓" : "Ya no es colaborador ✓");
      load();
    } catch (e) { flash(errMsg(e), true); }
  }

  // Abre una nueva etapa para una persona inactiva.
  async function reactivar(payload: { modo: "mismos" | "diferentes"; fecha_alta: string; staff_tipo?: string; tipo_contrato?: string }) {
    if (!sel?.id) return;
    try {
      const dto = await api.post<Persona>(`/configuracion/personal/${sel.id}/reactivar`, payload);
      setSel({ ...dto }); setReactOpen(false);
      flash(`Reactivado · etapa ${dto.periodo_codigo} ✓`); load();
    } catch (e) { flash(errMsg(e), true); }
  }

  return (
    <div className="min-h-full -m-5 p-5" style={{ background: "#E5DDD5" }}>
      {msg.t && (
        <div className={`fixed top-14 right-6 z-50 px-4 py-2.5 rounded-sm text-[12px] font-semibold shadow-lg ${msg.e ? "bg-[#C026D3] text-white" : "bg-[#2DD9C3] text-[#1500A0]"}`}>{msg.t}</div>
      )}
      {/* Selector desplegable */}
      <div className="flex items-center gap-2 mb-2.5 flex-wrap">
        <Users className="w-4 h-4 text-[#1500A0] shrink-0" />
        <select value={sel?.id ?? ""} onChange={(e) => { const id = Number(e.target.value); setSel(id ? { ...(lista.find((u) => u.id === id) as Persona) } : null); }} className={`${SELECT} max-w-xs`}>
          <option value="">— Selecciona una persona —</option>
          {filtrada.map((u) => <option key={u.id} value={u.id}>{u.nombre} {u.apellidos ?? ""}{u.activo ? "" : " · baja"}</option>)}
        </select>
        <select value={estado} onChange={(e) => setEstado(e.target.value as EstadoFiltro)} className={`${SELECT} max-w-[130px]`}>
          <option value="activos">Activos</option>
          <option value="inactivos">Bajas</option>
          <option value="todos">Todos</option>
        </select>
        <span className="text-[11px] text-[#7f8c8d]">{filtrada.length} {filtrada.length === 1 ? "persona" : "personas"}</span>
        <div className="ml-auto"><ClinicalButton variant="nuevo" icon={Plus} size="sm" onClick={nuevo}>Nuevo</ClinicalButton></div>
      </div>

      {/* Ficha */}
      {!sel ? (
        <ClinicalCard className="!rounded-md"><div className="py-12 text-center"><span className={EMPTY}>Selecciona una persona en el desplegable o crea una nueva</span></div></ClinicalCard>
      ) : (
        <ClinicalCard className="!rounded-md">
              <SectionHeader
                title={sel.nombre || "Nuevo usuario"}
                customIcon={<Users className="w-3.5 h-3.5 text-[#1500A0]" />}
                action={
                  <div className="flex items-center gap-2">
                    {sel.id && !sel.activo && (
                      <button onClick={() => setReactOpen(true)}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-sm text-[12px] font-bold text-white bg-[#1500A0] hover:bg-[#012c61] transition-colors">
                        <RotateCcw className="w-3.5 h-3.5" /> Reactivar
                      </button>
                    )}
                    {sel.activo && (
                      <>
                        <span className="text-[10px] uppercase tracking-wide text-[#7f8c8d] font-semibold">Colaborador</span>
                        <Toggle on={sel.colaborador_id != null} onClick={toggleColaborador} />
                      </>
                    )}
                    <ClinicalButton variant="secondary" size="sm" onClick={() => setSel(null)}>Cancelar</ClinicalButton>
                    <ClinicalButton variant="save" icon={Save} size="sm" onClick={guardar}>Guardar</ClinicalButton>
                  </div>
                }
              />
              <div className="grid grid-cols-4 gap-3">
                <div><label className={LABEL}>Nombre</label><input value={sel.nombre || ""} onChange={(e) => s("nombre", e.target.value)} className={`${INPUT} !rounded-md uppercase placeholder:normal-case`} /></div>
                <div><label className={LABEL}>Apellidos</label><input value={sel.apellidos || ""} onChange={(e) => s("apellidos", e.target.value)} className={`${INPUT} !rounded-md uppercase placeholder:normal-case`} /></div>
                <div><label className={LABEL}>NIF</label><input value={sel.nif || ""} onChange={(e) => s("nif", e.target.value)} className={`${INPUT} !rounded-md uppercase placeholder:normal-case`} /></div>
                <div>
                  <label className={LABEL}>Color</label>
                  <div className="flex items-center gap-2">
                    <div className="w-7 h-7 rounded-sm border border-[#e5e7eb] overflow-hidden relative">
                      <input type="color" value={sel.color || "#1500A0"} onChange={(e) => s("color", e.target.value)} className="absolute -top-1 -left-1 w-10 h-10 cursor-pointer" />
                    </div>
                    <span className="text-[10px] font-mono text-[#7f8c8d]">{sel.color}</span>
                  </div>
                </div>
              </div>
              <div className="grid grid-cols-4 gap-3 mt-3">
                <div><label className={LABEL}>Email</label><input type="email" value={sel.email || ""} onChange={(e) => s("email", e.target.value)} className={`${INPUT} !rounded-md lowercase placeholder:normal-case`} /></div>
                <div><label className={LABEL}>Teléfono</label><input value={sel.telefono || ""} onChange={(e) => s("telefono", e.target.value)} className={`${INPUT} !rounded-md uppercase placeholder:normal-case`} /></div>
                <div><label className={LABEL}>Usuario</label><input value={sel.username || ""} onChange={(e) => s("username", e.target.value)} className={`${INPUT} !rounded-md uppercase placeholder:normal-case`} /></div>
                <div><label className={LABEL}>Contraseña</label><input type="password" placeholder={sel.tiene_login ? "•••• (sin cambios)" : "nueva"} value={sel.password || ""} onChange={(e) => s("password", e.target.value)} className={`${INPUT} !rounded-md uppercase placeholder:normal-case`} /></div>
              </div>
              <div className="mt-4 mb-1 flex items-center gap-2">
                <CalendarClock className="w-3.5 h-3.5 text-[#1500A0]" />
                <span className="text-[11px] font-semibold text-[#1500A0] uppercase tracking-wide">
                  Etapa vigente{sel.periodo_codigo ? ` · ${sel.periodo_codigo}` : ""}
                </span>
              </div>
              <div className="grid grid-cols-4 gap-3">
                <div>
                  <label className={LABEL}>Tipo</label>
                  <select value={sel.staff_tipo || ""} onChange={(e) => s("staff_tipo", e.target.value)} className={SELECT}>
                    {!TIPOS.includes(sel.staff_tipo || "") && sel.staff_tipo && <option value={sel.staff_tipo}>{sel.staff_tipo}</option>}
                    {TIPOS.map((t) => <option key={t} value={t}>{t}</option>)}
                  </select>
                </div>
                <div>
                  <label className={LABEL}>Tipo de contrato</label>
                  <select value={sel.tipo_contrato || ""} onChange={(e) => s("tipo_contrato", e.target.value)} className={SELECT}>
                    <option value="">—</option>
                    {!CONTRATOS.includes(sel.tipo_contrato || "") && sel.tipo_contrato && <option value={sel.tipo_contrato}>{sel.tipo_contrato}</option>}
                    {CONTRATOS.map((t) => <option key={t} value={t}>{t}</option>)}
                  </select>
                </div>
                <div><label className={LABEL}>Fecha alta</label><input type="date" value={sel.fecha_alta || ""} onChange={(e) => s("fecha_alta", e.target.value)} className={`${INPUT} !rounded-md uppercase placeholder:normal-case`} /></div>
                <div>
                  <label className={LABEL}>Fecha baja</label>
                  <input type="date" value={sel.fecha_baja || ""} onChange={(e) => s("fecha_baja", e.target.value)} className={`${INPUT} !rounded-md uppercase placeholder:normal-case`} />
                  <span className="text-[10px] text-[#7f8c8d] mt-0.5 block">Con fecha de baja cumplida → inactivo</span>
                </div>
              </div>
              <div className="mt-4">
                <div className="mb-3 max-w-[320px]">
                  <label className={LABEL}>Rol</label>
                  <select value={sel.rol_id ?? ""} onChange={(e) => cambiarRol(e.target.value ? Number(e.target.value) : null)} className={SELECT}>
                    {sel.rol_id == null && <option value="">— sin rol —</option>}
                    {roles.map((x) => <option key={x.id} value={x.id}>{x.nombre}</option>)}
                  </select>
                  <span className="text-[10px] text-[#7f8c8d] mt-0.5 block">Los roles y sus permisos se editan en Config › Clínica › Centro.</span>
                </div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className={LABEL}>Permisos — qué puede hacer en cada área</label>
                  <span className="text-[10px] text-[#7f8c8d]">{techo(sel) ? "Puedes quitar permisos; no ampliar más allá del rol" : "«Editar» incluye «Ver»"}</span>
                </div>
                <div className="border border-[#e5e7eb] rounded-md divide-y divide-[#f0f2f5] overflow-hidden">
                  {permAreas.map((a) => {
                    const nivel = nivelArea(a, sel.permisos ?? []);
                    return (
                      <div key={a.key}>
                        <div className="flex items-center justify-between px-3 py-2 bg-white">
                          <span className="text-[12.5px] font-semibold text-[#1e293b]">{a.nombre}</span>
                          <NivelPicker nivel={nivel} soloVer={!a.editar} max={maxArea(a)} onChange={(n) => setNivelArea(a, n)} />
                        </div>
                        {a.tabs?.length && nivel !== "none" ? (
                          <PestanasArea tabs={a.tabs} permisos={sel.permisos ?? []} techo={techo(sel)} onChange={setTabs} />
                        ) : null}
                      </div>
                    );
                  })}
                  {permAreas.length === 0 && <div className="px-3 py-2 text-[11px] text-slate-400 italic bg-white">Sin áreas configuradas</div>}
                </div>
                {permExtras.length > 0 && (
                  <div className="mt-2.5">
                    <span className="text-[10px] font-semibold text-[#7f8c8d] uppercase tracking-wide">Accesos especiales</span>
                    <div className="flex flex-wrap gap-2 mt-1">
                      {permExtras.map((x) => {
                        const on = (sel.permisos ?? []).includes(x.codigo);
                        const t = techo(sel);
                        const fuera = !!t && !t.includes(x.codigo);
                        return (
                          <button key={x.codigo} type="button" disabled={fuera} title={fuera ? "Su rol no incluye este acceso" : undefined} onClick={() => toggleExtra(x.codigo)}
                            className={`px-3 py-1.5 rounded-sm border text-[12px] font-semibold transition-colors ${fuera ? "bg-white text-[#cbd5e1] border-[#e5e7eb] cursor-not-allowed line-through" : on
                              ? "bg-[#1ca0d1] text-white border-[#1ca0d1]"
                              : "bg-white text-[#64748b] border-[#e5e7eb] hover:border-[#1ca0d1]"}`}>{x.nombre}</button>
                        );
                      })}
                    </div>
                  </div>
                )}
                {sel.colaborador_id != null && (
                  <span className="inline-block mt-2.5 text-[11px] text-[#1ca0d1] bg-[#FFFFFF] border border-[#7dd3fc] rounded-sm px-3 py-1.5 font-semibold">
                    Colaborador #{sel.colaborador_id} · el detalle económico se edita en Colaboradores
                  </span>
                )}
              </div>

              {/* Historial de etapas (periodos) */}
              {sel.periodos && sel.periodos.length > 0 && (
                <div className="mt-4">
                  <div className="flex items-center gap-2 mb-1.5">
                    <CalendarClock className="w-3.5 h-3.5 text-[#1500A0]" />
                    <span className="text-[11px] font-semibold text-[#1500A0] uppercase tracking-wide">Etapas</span>
                  </div>
                  <div className="border border-[#e5e7eb] rounded-sm divide-y divide-[#eef1f6]">
                    {sel.periodos.map((p) => (
                      <div key={p.id} className="flex items-center gap-3 px-3 py-2 text-[12px]">
                        <span className="font-mono font-bold text-[#1500A0] w-12 shrink-0">{p.codigo}</span>
                        <span className="text-[#33415c] w-44 shrink-0">
                          {p.fecha_alta || "—"} → {p.fecha_baja || "abierta"}
                        </span>
                        <span className="text-[#7f8c8d] uppercase text-[10px] w-24 shrink-0">{p.staff_tipo || "—"}</span>
                        <span className="text-[#7f8c8d] text-[11px] flex-1 truncate">{p.tipo_contrato || ""}</span>
                        {p.colaborador_id != null && <Chip>colab</Chip>}
                        <Badge ok={p.abierto}>{p.abierto ? "Abierta" : "Cerrada"}</Badge>
                      </div>
                    ))}
                  </div>
                </div>
              )}
        </ClinicalCard>
      )}
      {reactOpen && sel?.id && <ReactivarModal onClose={() => setReactOpen(false)} onConfirm={reactivar} />}
    </div>
  );
}

function ReactivarModal({ onClose, onConfirm }: {
  onClose: () => void;
  onConfirm: (p: { modo: "mismos" | "diferentes"; fecha_alta: string; staff_tipo?: string; tipo_contrato?: string }) => void;
}) {
  const [modo, setModo] = useState<"mismos" | "diferentes">("mismos");
  const [fecha, setFecha] = useState("");
  const [tipo, setTipo] = useState("DOCTOR");
  const [contrato, setContrato] = useState("");
  return (
    <Modal
      title="Reactivar — nueva etapa"
      onClose={onClose}
      size="md"
      closeOnBackdrop={false}
      footer={
        <>
          <ModalButton variant="magenta" icon={X} onClick={onClose}>Cancelar</ModalButton>
          <ModalButton
            variant="primary"
            icon={RotateCcw}
            onClick={() => { if (!fecha) return; onConfirm(modo === "mismos" ? { modo, fecha_alta: fecha } : { modo, fecha_alta: fecha, staff_tipo: tipo, tipo_contrato: contrato || undefined }); }}
            disabled={!fecha}
          >
            Reactivar
          </ModalButton>
        </>
      }
    >
      <ModalBody>
        <div className="flex flex-col gap-2 mb-2.5">
          <label className={`flex items-start gap-2 p-2.5 rounded-sm border cursor-pointer ${modo === "mismos" ? "border-[#21A2E5] bg-[#FFFFFF]" : "border-[#BFE4F7]"}`}>
            <input type="radio" checked={modo === "mismos"} onChange={() => setModo("mismos")} className="mt-0.5 accent-[#1500A0]" />
            <span className="text-[12px]"><b>Mismos datos + nueva fecha.</b> Copia tipo, contrato y colaborador de la última etapa.</span>
          </label>
          <label className={`flex items-start gap-2 p-2.5 rounded-sm border cursor-pointer ${modo === "diferentes" ? "border-[#21A2E5] bg-[#FFFFFF]" : "border-[#BFE4F7]"}`}>
            <input type="radio" checked={modo === "diferentes"} onChange={() => setModo("diferentes")} className="mt-0.5 accent-[#1500A0]" />
            <span className="text-[12px]"><b>Datos diferentes.</b> Nueva etapa con otro tipo/contrato (sin colaborador).</span>
          </label>
        </div>
        <div className="grid grid-cols-3 gap-3">
          <div><label className={LABEL}>Fecha de alta</label><input type="date" value={fecha} onChange={(e) => setFecha(e.target.value)} className={MODAL_INPUT} /></div>
          {modo === "diferentes" && (
            <>
              <div>
                <label className={LABEL}>Tipo</label>
                <select value={tipo} onChange={(e) => setTipo(e.target.value)} className={MODAL_INPUT}>
                  {TIPOS.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
              <div>
                <label className={LABEL}>Contrato</label>
                <select value={contrato} onChange={(e) => setContrato(e.target.value)} className={MODAL_INPUT}>
                  <option value="">—</option>
                  {CONTRATOS.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
            </>
          )}
        </div>
      </ModalBody>
    </Modal>
  );
}

function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span className="text-[8px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded-full bg-[#FFFFFF] text-[#0369a1] border border-[#7dd3fc]">
      {children}
    </span>
  );
}

function Badge({ ok, children }: { ok: boolean; children: React.ReactNode }) {
  return (
    <span className={`text-[9px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full border ${ok ? "bg-[#FFFFFF] border-[#9FE6DB] text-[#0F8C7D]" : "bg-white border-slate-200 text-slate-400"}`}>
      {children}
    </span>
  );
}
