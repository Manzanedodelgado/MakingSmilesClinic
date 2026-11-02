"use client";
/**
 * INICIO — unión de Agenda del día y Pacientes.
 * Camino: 1 cabecera (cita+paciente) → 2 previa → 3 consulta → 4 documentos+cobro.
 * Sin monedas ni clay: tarjetas sobrias del sistema (ClinicalCard/Button).
 */
import { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  CalendarDays, FileText, Pill, FileSignature, ClipboardList,
  MessageCircle, Wrench, Ear, Mic, Square, Sparkles, Stethoscope,
  FolderOpen, Wallet, ChevronDown,
} from "lucide-react";
import { api } from "@/shared/lib/api";
import { ClinicalButton } from "@/shared/components/ClinicalButton";
import { ClinicalCard } from "@/shared/components/ClinicalCard";
import { SectionHeader } from "@/shared/components/SectionHeader";
import { patientService, type EscuchaExtraido } from "@/features/patients/services/patientService";
import type { Cita, Ref } from "@/features/agenda/components/CitaModal";
import { imprimirPresupuesto } from "@/features/patients/lib/presupuestoDoc";
import { errMsg } from "@/shared/lib/errores";

const eur = (n: number) => n.toLocaleString("es-ES", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";
const fch = (s: string | null) => s ? new Date(s.length === 10 ? `${s}T00:00:00` : s).toLocaleDateString("es-ES", { day: "2-digit", month: "2-digit", year: "numeric" }) : "—";
const ymdH = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const haceMasDeUnMes = (s: string | null) => {
  if (!s) return true;
  const f = new Date(s.length === 10 ? `${s}T00:00:00` : s).getTime();
  return Date.now() - f > 31 * 24 * 3600 * 1000;
};
// Citas "en espera": todo lo que no está cerrado ni anulado.
const CERRADA = /finaliz|fall|anul|cancel/i;

type Msg = { t: string; e?: boolean } | null;
function correr<T>(p: Promise<T>, ok: (r: T) => void, flash: (t: string, e?: boolean) => void, okMsg: (r: T) => string) {
  p.then((r) => { ok(r); flash(okMsg(r)); }).catch((e) => flash(errMsg(e), true));
}

// Banda tintada por tipo de caja (gracia sobria del render).
const BANDA: Record<string, string> = {
  hist: "bg-[#FFFFFF] text-[#1500A0] border-[#c7d2fe]",
  img: "bg-[#FFFFFF] text-[#0f6f92] border-[#b3e3f5]",
  pres: "bg-[#FFFFFF] text-[#6D28D9] border-[#C4B5FD]",
  rec: "bg-[#FFFFFF] text-[#4a3fa3] border-[#d3cffb]",
  wa: "bg-[#FFFFFF] text-[#0b7364] border-[#a9e8da]",
  cob: "bg-[#FFFFFF] text-[#1500A0] border-[#c7d2fe]",
};
function Banda({ tono, children }: { tono: string; children: React.ReactNode }) {
  return <div className={`-m-3 mb-2 px-3 py-2 text-[11px] uppercase border-b rounded-t-sm ${BANDA[tono]}`}>{children}</div>;
}

export default function InicioPage() {
  return <Suspense fallback={null}><Inicio /></Suspense>;
}

function Inicio() {
  const router = useRouter();
  const sp = useSearchParams();
  const [fecha, setFecha] = useState(() => sp.get("fecha") || ymdH(new Date()));
  const [refs, setRefs] = useState<Ref | null>(null);
  const [agendaId, setAgendaId] = useState<number | null>(null);
  const [citas, setCitas] = useState<Cita[] | null>(null);
  const [citaId, setCitaId] = useState<number | null>(() => Number(sp.get("cita")) || null);
  const [msg, setMsg] = useState<Msg>(null);
  const [marcado, setMarcado] = useState<{ tratamiento: string; precio: number | null } | null>(null);
  const flash = useCallback((t: string, e = false) => { setMsg({ t, e }); }, []);

  useEffect(() => {
    api.get<Ref>("/agenda/referencias").then((r) => {
      setRefs(r);
      setAgendaId((p) => p ?? r.agendas?.[0]?.id ?? null);
    }).catch((e) => flash(errMsg(e), true));
  }, [flash]);
  const cargar = useCallback(() => {
    if (!agendaId) return;
    api.get<{ citas: Cita[] }>(`/agenda/citas?fecha=${fecha}&agenda_id=${agendaId}`)
      .then((r) => setCitas([...r.citas]
        .filter((c) => !CERRADA.test(c.estado_nombre ?? ""))
        .sort((a, b) => a.hora.localeCompare(b.hora))))
      .catch((e) => { setCitas([]); flash(errMsg(e), true); });
  }, [fecha, agendaId, flash]);
  useEffect(() => { setCitas(null); cargar(); }, [cargar]);
  useEffect(() => { setMarcado(null); }, [citaId]);

  const cita = citas?.find((c) => c.id === citaId) ?? null;
  const elegir = (c: Cita) => {
    setCitaId(c.id);
    const q = new URLSearchParams(sp.toString());
    q.set("fecha", fecha); q.set("cita", String(c.id));
    router.replace(`/inicio?${q}`, { scroll: false });
  };

  return (
    <div className="flex flex-col xl:flex-row h-full min-h-0 gap-2 p-2 overflow-y-auto xl:overflow-hidden bg-[#E5DDD5]">
      <aside className="shrink-0 xl:w-[300px] flex flex-col gap-2 xl:min-h-0 xl:overflow-y-auto">
        {msg && <p role="status" className={`rounded px-2 py-1 text-[12px] font-medium ${msg.e ? "bg-[#FFFFFF] text-[#5B21B6]" : "bg-white text-[#0E6B5E]"}`}>{msg.t}</p>}
        <ClinicalCard>
          <SectionHeader title="En espera · hoy" icon={CalendarDays} />
          <div className="flex flex-col sm:flex-row xl:flex-col gap-1.5 mb-2">
            <input type="date" value={fecha} onChange={(e) => e.target.value && setFecha(e.target.value)} className="rounded border border-[#e5e7eb] text-[12px] px-2 py-1" aria-label="Fecha" />
            <select value={agendaId ?? ""} onChange={(e) => setAgendaId(Number(e.target.value))} className="rounded border border-[#e5e7eb] text-[12px] px-2 py-1" aria-label="Agenda">
              {(refs?.agendas ?? []).map((a) => <option key={a.id} value={a.id}>{a.nombre}</option>)}
            </select>
          </div>
          {citas == null ? <p className="text-[12px] text-slate-400">Cargando…</p> : citas.length === 0 ? <p className="text-[12px] text-slate-400">Sin citas en espera.</p> : (
            <ul className="flex flex-col gap-1.5">
              {citas.map((c) => (
                <li key={c.id}>
                  <button onClick={() => elegir(c)} className={`w-full text-left rounded border px-2.5 py-1.5 transition ${c.id === citaId ? "border-[#1500A0] bg-[#FFFFFF]" : "border-[#eef2f7] bg-[#FFFFFF] hover:bg-white"}`}>
                    <span className="text-[15px] tabular-nums text-[#1A2290]">{c.hora}</span>
                    <span className="text-[12px] text-slate-600"> · {`${c.nombre} ${c.apellidos}`.trim() || "Sin paciente"}</span>
                    <span className="block text-[11px] text-slate-400">{c.estado_nombre ?? ""}{c.tipo_nombre ? ` · ${c.tipo_nombre}` : ""}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </ClinicalCard>
      </aside>

      <div className="flex-1 min-w-0 xl:min-h-0 xl:overflow-y-auto flex flex-col gap-2.5">
        {!cita ? (
          <ClinicalCard className="flex items-center justify-center min-h-[200px]">
            <p className="text-[12px] text-slate-400">Elige una cita en espera para gestionarla.</p>
          </ClinicalCard>
        ) : (
          <Camino key={cita.id} cita={cita} refs={refs} onCambio={cargar} flash={flash} router={router} marcado={marcado} setMarcado={setMarcado} />
        )}
      </div>
    </div>
  );
}

function Camino({ cita, refs, onCambio, flash, router, marcado, setMarcado }: {
  cita: Cita; refs: Ref | null; onCambio: () => void; flash: (t: string, e?: boolean) => void;
  router: ReturnType<typeof useRouter>; marcado: { tratamiento: string; precio: number | null } | null;
  setMarcado: (m: { tratamiento: string; precio: number | null } | null) => void;
}) {
  const pid = cita.paciente_id;
  return (
    <div className="flex flex-col gap-2.5">
      <Cabecera cita={cita} refs={refs} onCambio={onCambio} flash={flash} router={router} />
      {pid && (
        <>
          <Previa pid={pid} telefono={cita.telefono} flash={flash} router={router} onMarcar={setMarcado} />
          <Consulta pid={pid} flash={flash} marcado={marcado} setMarcado={setMarcado} />
          <Documentos pid={pid} telefono={cita.telefono} flash={flash} onHecho={onCambio} />
        </>
      )}
    </div>
  );
}

/* ── 1. CABECERA ─────────────────────────────────────────── */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function Cabecera({ cita, refs, onCambio, flash, router }: { cita: Cita; refs: Ref | null; onCambio: () => void; flash: (t: string, e?: boolean) => void; router: ReturnType<typeof useRouter> }) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [pac, setPac] = useState<any | null>(null);
  const [alertas, setAlertas] = useState<{ texto: string }[]>([]);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [consent, setConsent] = useState<any[]>([]);
  useEffect(() => {
    if (!cita.paciente_id) return;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    patientService.cabecera(cita.paciente_id).then((p: any) => setPac(p)).catch(() => setPac(null));
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    patientService.alertas(cita.paciente_id).then((a: any) => setAlertas((a.alertas || []).filter((x: any) => x.activo))).catch(() => setAlertas([]));
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    patientService.consentListar(cita.paciente_id).then((r: any) => setConsent((r || []).filter((c: any) => c.estado === "firmado" && !haceMasDeUnMes(c.fecha)))).catch(() => setConsent([]));
  }, [cita.paciente_id]);
  const nombre = `${cita.nombre} ${cita.apellidos}`.trim() || "Cita sin paciente";
  const iniciales = nombre.split(/\s+/).slice(0, 2).map((w) => w[0]?.toUpperCase() ?? "").join("") || "–";
  const num = pac?.num_historia ?? cita.num_historia;
  const cambiarEstado = (v: string) => {
    if (!v) return;
    correr(api.put(`/agenda/citas/${cita.id}/estado`, { estado_id: Number(v) }), () => onCambio(), flash, () => "Estado actualizado");
  };
  return (
    <ClinicalCard>
      <div className="flex items-center gap-3.5">
        <span aria-hidden className="grid place-items-center rounded-xl bg-[#1500A0] text-white text-[22px] shrink-0" style={{ width: 76, height: 76 }}>{iniciales}</span>
        <div className="flex-1 min-w-0 h-[76px] flex flex-col justify-center gap-1.5">
          <p className="text-[17px] leading-6 text-[#333] truncate"><span className="text-[#1500A0]">{num ?? ""}</span>{num ? " · " : ""}{nombre}</p>
          <p className="text-[12px] text-slate-500 tabular-nums">
            {pac?.edad != null ? `${pac.edad} años · ` : ""}{(pac?.telefono_movil ?? cita.telefono) || ""}
          </p>
        </div>
        <div className="flex flex-col items-end gap-2 shrink-0">
          <select value={String(cita.estado_id ?? "")} onChange={(e) => cambiarEstado(e.target.value)} className="text-[12px] px-2 py-1.5 rounded-md bg-[#ccfbf1] text-[#0b7364] border border-[#99f6e4]" aria-label="Estado de la cita">
            <option value="">Estado…</option>
            {(refs?.estados ?? []).map((e) => <option key={e.id} value={e.id}>{e.nombre}</option>)}
          </select>
          {consent.map((c) => <span key={c.id} className="text-[11px] text-[#0b7364]">✓ Consent. {String(c.tipo).replace(/_/g, " ")} {fch(c.fecha)}</span>)}
        </div>
      </div>
      <div className="flex mt-3 text-[12px] leading-[18px]">
        <span className="w-[22px] text-center text-[#FF007F] shrink-0">●</span>
        <span className="text-[#FF007F]">{alertas.length ? alertas.map((a) => a.texto).join(" · ") : "Sin alertas activas"}</span>
      </div>
      <div className="flex mt-1.5 text-[12px] leading-[18px] text-slate-500">
        <span className="w-[22px] text-center text-[#1500A0] shrink-0">●</span>
        <span>{cita.tipo_nombre || "Sin tipo"} · {cita.duracion_min} min{cita.notas ? "" : ""}</span>
      </div>
      <div className="flex items-center mt-1.5 text-[12px] leading-[18px] text-slate-600">
        <span className="w-[22px] text-center shrink-0">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#0f9d85" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" /></svg>
        </span>
        <span className="flex-1">{cita.notas || "Sin comentarios de recepción"}</span>
        {cita.paciente_id ? <ClinicalButton variant="nuevo" onClick={() => router.push(`/pacientes/${cita.paciente_id}/ficha`)}>Ficha</ClinicalButton> : null}
      </div>
    </ClinicalCard>
  );
}

/* ── 2. PREVIA ───────────────────────────────────────────── */
function Previa({ pid, telefono, flash, router, onMarcar }: {
  pid: number; telefono: string | null; flash: (t: string, e?: boolean) => void;
  router: ReturnType<typeof useRouter>; onMarcar: (m: { tratamiento: string; precio: number | null } | null) => void;
}) {
  type CitaPac = { id: number; fecha: string | null; hora: string; estado: string; tipo: string | null };
  const [citasPac, setCitasPac] = useState<CitaPac[] | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [actos, setActos] = useState<any[] | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [previstos, setPrevistos] = useState<any[]>([]);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [presus, setPresus] = useState<any[] | null>(null);
  const [anamnesis, setAnamnesis] = useState<string[] | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [media, setMedia] = useState<any | null>(null);
  const [abierto, setAbierto] = useState<"pres" | "prev" | null>("prev");
  useEffect(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    api.get<{ citas: { permitido: boolean; pasadas?: CitaPac[] } }>(`/inicio/paciente/${pid}`)
      .then((r) => setCitasPac(r.citas.permitido ? (r.citas.pasadas || []) : [])).catch(() => setCitasPac([]));
    patientService.actos(pid).then((r: unknown) => setActos((r as { actos?: unknown[] }).actos || [])).catch((e) => { setActos([]); flash(errMsg(e), true); });
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    patientService.previstos(pid).then((r: any) => setPrevistos((r.presupuestos || []).flatMap((g: any) => g.previstos || []))).catch(() => setPrevistos([]));
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    patientService.presupuestos(pid).then((r: any) => setPresus((r.presupuestos || []).filter((p: any) => !["Anulado", "Cancelado", "Finalizado", "Aceptado"].includes(p.estado)))).catch(() => setPresus([]));
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    patientService.filiacion(pid).then((f: any) => setAnamnesis(f.anamnesis || [])).catch(() => setAnamnesis([]));
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    patientService.multimedia(pid).then((m: any) => setMedia(m)).catch(() => setMedia(null));
  }, [pid, flash]);
  const esPrimera = (actos?.length ?? -1) === 0 && (citasPac?.length ?? -1) === 0;
  const imgs = media ? [...(media.radiografias || []), ...(media.fotos || [])] : [];
  return (
    <div className="flex flex-col gap-2.5">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 items-start">
        <ClinicalCard className="!p-0 !overflow-hidden">
          <div className="px-3 py-2 text-[11px] uppercase bg-[#FFFFFF] text-[#1500A0] border-b border-[#c7d2fe]">Historial ⟷ scroll</div>
          <div className="p-3">
            {actos == null ? <p className="text-[12px] text-slate-400">Cargando…</p> : actos.length === 0 ? <p className="text-[12px] text-slate-400">Sin historial.</p> : (
              <div className="max-h-[150px] overflow-y-auto border border-[#eef2f7] rounded px-2.5">
                <table className="w-full text-[12px] text-slate-600 border-collapse" style={{ fontVariantNumeric: "tabular-nums" }}>
                  <tbody>
                    {actos.map((a: { id: number; tratamiento: string; fecha?: string | null; importe: number }) => (
                      <tr key={a.id} className="border-b border-[#f1f5f9] last:border-0">
                        <td className="py-1.5 pr-2 w-16 text-[#0f6f92] whitespace-nowrap">{fch(a.fecha ?? null)}</td>
                        <td className="py-1.5">{a.tratamiento}</td>
                        <td className="py-1.5 text-right">{eur(a.importe)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </ClinicalCard>
        <ClinicalCard className="!p-0 !overflow-hidden">
          <div className="px-3 py-2 text-[11px] uppercase bg-[#FFFFFF] text-[#0f6f92] border-b border-[#b3e3f5]">Imágenes y radiografías</div>
          <div className="p-3">
            {!media ? <p className="text-[12px] text-slate-400">Cargando…</p> : imgs.length === 0 ? <p className="text-[12px] text-slate-400">Ninguna.</p> : (
              <>
                <div className="flex gap-2">
                  {imgs.slice(0, 4).map((img: { id: string; name: string }) => (
                    // eslint-disable-next-line @next/next/no-img-element
                    <button key={img.id} title={img.name} onClick={() => window.open(patientService.multimediaUrl(pid, img.id), "_blank")}
                      className="w-[76px] h-[76px] overflow-hidden rounded-lg bg-[#14213D] border border-[#E5E7EB] hover:-translate-y-0.5 transition-transform">
                      <img src={patientService.multimediaUrl(pid, img.id, true)} alt={img.name} loading="lazy" className="h-full w-full object-cover" />
                    </button>
                  ))}
                </div>
                <button onClick={() => router.push(`/pacientes/${pid}/radiologia`)} className="text-[11px] text-slate-500 underline mt-1.5">Ver todas</button>
              </>
            )}
          </div>
        </ClinicalCard>
      </div>
      <ClinicalCard className="!py-2">
        <button onClick={() => setAbierto(abierto === "pres" ? null : "pres")} className="w-full flex justify-between text-[12px] text-[#333]">
          <span>▸ Presupuestos pendientes de aceptar ({presus?.length ?? "…"})</span>
          <span className="tabular-nums">{presus ? eur(presus.reduce((s: number, p: { total: number }) => s + p.total, 0)) : ""}</span>
        </button>
        {abierto === "pres" && presus && (
          <ul className="mt-1.5 flex flex-col">
            {presus.length === 0 ? <li className="text-[12px] text-slate-400">Ninguno.</li> : presus.map((p: { id: number; titulo: string | null; num: number | null; total: number }) => (
              <li key={p.id} className="flex items-baseline gap-2 py-1 border-t border-[#f1f5f9] text-[12px]">
                <span className="flex-1 truncate text-slate-600">{p.titulo || `Presupuesto ${p.num ?? ""}`}</span>
                <span className="tabular-nums">{eur(p.total)}</span>
                <ClinicalButton variant="secondary" onClick={() => imprimirPresupuesto(pid, p.id).catch((e) => flash(errMsg(e), true))}>PDF</ClinicalButton>
              </li>
            ))}
          </ul>
        )}
      </ClinicalCard>
      <ClinicalCard className="!py-2">
        <button onClick={() => setAbierto(abierto === "prev" ? null : "prev")} className="w-full flex justify-between text-[12px] text-[#333]">
          <span>▾ Tratamientos pendientes ({previstos.length})</span><span />
        </button>
        {abierto === "prev" && (
          <table className="w-full text-[12px] text-slate-600 border-collapse mt-1">
            <tbody>
              {previstos.length === 0 ? <tr><td className="text-slate-400">Nada pendiente.</td></tr> : previstos.slice(0, 8).map((p: { tratamiento: string; pieza?: string | null; precio?: number | null }, i: number) => (
                <tr key={i} className="border-t border-[#f1f5f9]">
                  <td className="py-1.5 pr-2 w-[22px]">☐</td>
                  <td className="py-1.5">{p.tratamiento}{p.pieza ? ` · ${p.pieza}` : ""}</td>
                  <td className="py-1.5 text-right tabular-nums">{p.precio != null ? eur(p.precio) : ""}</td>
                  <td className="py-1.5 w-[130px] text-right"><ClinicalButton variant="secondary" onClick={() => onMarcar({ tratamiento: p.tratamiento, precio: p.precio ?? null })}>A realizar hoy</ClinicalButton></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </ClinicalCard>
      {esPrimera && (
        <ClinicalCard className="!border-[#7C3AED] !bg-[#FFFFFF]">
          <SectionHeader title="Solo primera visita" icon={ClipboardList} />
          <p className="text-[12px] text-slate-600">RX de hoy lista · Anamnesis: {(anamnesis && anamnesis.length ? anamnesis.join(" · ") : "sin registrar")} · <button className="underline" onClick={() => router.push(`/pacientes/${pid}/ficha`)}>ver completa</button></p>
          {telefono ? <ClinicalButton variant="secondary" onClick={() => router.push(`/comunicacion?tel=${encodeURIComponent(telefono)}`)}>Abrir chat</ClinicalButton> : null}
        </ClinicalCard>
      )}
    </div>
  );
}

/* ── 3. CONSULTA ─────────────────────────────────────────── */
function Consulta({ pid, flash, marcado, setMarcado }: {
  pid: number; flash: (t: string, e?: boolean) => void;
  marcado: { tratamiento: string; precio: number | null } | null;
  setMarcado: (m: { tratamiento: string; precio: number | null } | null) => void;
}) {
  const [caso, setCaso] = useState<"A" | "B">("A");
  const [colab, setColab] = useState("");
  const [colabs, setColabs] = useState<{ id: number; nombre: string }[]>([]);
  const [hecho, setHecho] = useState("");
  const [nota, setNota] = useState("");
  useEffect(() => {
    api.get<Ref>("/agenda/referencias").then((r) => setColabs(r.colaboradores || [])).catch(() => {});
  }, []);
  useEffect(() => { if (marcado) { setCaso("A"); setHecho(marcado.tratamiento); } }, [marcado]);
  const registrar = () => {
    if (!colab) { flash("Elige el profesional que lo ha realizado", true); return; }
    if (!hecho.trim()) { flash("Describe lo realizado", true); return; }
    correr(patientService.consultaCerrar(pid, { nota: nota || null, tratamientos: [{ texto: hecho.trim(), pieza: null, precio: null }] }),
      () => { setMarcado(null); }, flash, () => "Tratamiento registrado");
  };
  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex rounded-md overflow-hidden border border-[#e5e7eb] text-[11px]">
        <button onClick={() => setCaso("A")} className={`flex-1 px-2.5 py-2 text-left ${caso === "A" ? "bg-[#1500A0] text-white" : "bg-[#FFFFFF] text-slate-500"}`}>Caso A — tratamiento citado, sin dictar</button>
        <button onClick={() => setCaso("B")} className={`flex-1 px-2.5 py-2 text-left ${caso === "B" ? "bg-[#1500A0] text-white" : "bg-[#FFFFFF] text-slate-500"}`}>Caso B — 1ª visita / revisión, con escucha</button>
      </div>
      {caso === "A" && (
        <ClinicalCard className="!border-l-4 !border-l-[#1500A0]">
          <SectionHeader title={marcado ? `A realizar hoy: ${marcado.tratamiento}${marcado.precio != null ? ` · ${eur(marcado.precio)}` : ""}` : "Nada marcado de previstos"} icon={Wrench} />
          <div className="flex gap-1.5">
            <ClinicalButton variant="primary" onClick={registrar}>Confirmar y realizar</ClinicalButton>
            {marcado && <ClinicalButton variant="secondary" onClick={() => setMarcado(null)}>Cambiar</ClinicalButton>}
          </div>
          <label className="flex flex-col mt-2"><span className="text-[10px] uppercase text-slate-500 mb-0.5">Profesional</span>
            <select value={colab} onChange={(e) => setColab(e.target.value)} className="rounded border border-[#e5e7eb] text-[12px] px-2 py-1">
              <option value="">Elegir…</option>{colabs.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}
            </select></label>
          <label className="flex flex-col mt-2"><span className="text-[10px] uppercase text-slate-500 mb-0.5">Lo realizado</span>
            <textarea rows={2} value={hecho} onChange={(e) => setHecho(e.target.value)} className="rounded border border-[#e5e7eb] text-[12px] p-2" placeholder="Ej.: endodoncia en el 36" /></label>
          <label className="flex flex-col mt-2"><span className="text-[10px] uppercase text-slate-500 mb-0.5">Nota (opcional)</span>
            <textarea rows={2} value={nota} onChange={(e) => setNota(e.target.value)} className="rounded border border-[#e5e7eb] text-[12px] p-2" /></label>
        </ClinicalCard>
      )}
      {caso === "B" && <EscuchaPanel pid={pid} flash={flash} />}
    </div>
  );
}

function EscuchaPanel({ pid, flash }: { pid: number; flash: (t: string, e?: boolean) => void }) {
  const [texto, setTexto] = useState("");
  const [oyendo, setOyendo] = useState(false);
  const [pensando, setPensando] = useState(false);
  const [res, setRes] = useState<EscuchaExtraido | null>(null);
  useEffect(() => () => { setOyendo(false); }, [pid]);
  const dictar = () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) { flash("Este navegador no admite dictado: usa Chrome o escribe la nota", true); return; }
    if (oyendo) { setOyendo(false); return; }
    const r = new SR();
    r.lang = "es-ES"; r.continuous = true; r.interimResults = false;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    r.onresult = (e: any) => {
      let t = "";
      for (let i = e.resultIndex; i < e.results.length; i++) if (e.results[i].isFinal) t += e.results[i][0].transcript;
      if (t) setTexto((x) => `${x}${x && !x.endsWith(" ") ? " " : ""}${t.trim()}`);
    };
    r.onend = () => setOyendo(false);
    try { r.start(); setOyendo(true); } catch { setOyendo(false); }
  };
  const preparar = () => {
    if (!texto.trim()) return;
    setPensando(true);
    patientService.consultaEscucha(pid, texto.trim())
      .then((r) => { setRes(r); flash("Borradores preparados: revísalos abajo"); })
      .catch((e) => flash(errMsg(e), true))
      .finally(() => setPensando(false));
  };
  return (
    <div className="flex flex-col gap-2.5">
      <ClinicalCard>
        <SectionHeader title="Lo hablado" icon={Ear} action={
          <ClinicalButton variant="secondary" icon={oyendo ? Square : Mic} onClick={dictar}>{oyendo ? "Detener" : "Dictar"}</ClinicalButton>
        } />
        <textarea value={texto} onChange={(e) => setTexto(e.target.value)} rows={4} className="w-full rounded border border-[#e5e7eb] text-[12px] p-2"
          placeholder="Ej.: refiere dolor al frío en el 36. Caries distal profunda." />
        <div className="mt-2 flex justify-end">
          <ClinicalButton variant="primary" icon={Sparkles} onClick={preparar} disabled={pensando || !texto.trim()}>{pensando ? "Preparando…" : "Preparar borradores"}</ClinicalButton>
        </div>
      </ClinicalCard>
      {res && <Borradores pid={pid} res={res} flash={flash} />}
    </div>
  );
}

function Borradores({ pid, res, flash }: { pid: number; res: EscuchaExtraido; flash: (t: string, e?: boolean) => void }) {
  const [diag, setDiag] = useState(res.soap.analisis);
  const [plan, setPlan] = useState(res.soap.plan);
  const [lineas, setLineas] = useState(res.presupuesto);
  const [receta, setReceta] = useState(res.receta);
  const [mensaje, setMensaje] = useState(res.mensaje);
  const [ultimoPre, setUltimoPre] = useState<{ id: number; num: number } | null>(null);
  useEffect(() => {
    setDiag(res.soap.analisis); setPlan(res.soap.plan);
    setLineas(res.presupuesto); setReceta(res.receta); setMensaje(res.mensaje);
  }, [res]);
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 items-start">
      <ClinicalCard>
        <SectionHeader title="Nota clínica" icon={Stethoscope} action={<ClinicalButton variant="save" onClick={() =>
          correr(patientService.guardarSoap(pid, { ...res.soap, analisis: diag, plan }), () => {}, flash, () => "Nota guardada en la ficha")}>Guardar</ClinicalButton>} />
        <p className="text-[11px] uppercase text-slate-500">Subjetivo</p><p className="text-[12px] text-slate-600 mb-2">{res.soap.subjetivo || "—"}</p>
        <p className="text-[11px] uppercase text-slate-500">Objetivo</p><p className="text-[12px] text-slate-600 mb-2">{res.soap.objetivo || "—"}</p>
        <label className="flex flex-col mb-2"><span className="text-[10px] uppercase text-slate-500 mb-0.5">Diagnóstico</span>
          <textarea rows={2} value={diag} onChange={(e) => setDiag(e.target.value)} className="rounded border border-[#e5e7eb] text-[12px] p-2" /></label>
        <label className="flex flex-col"><span className="text-[10px] uppercase text-slate-500 mb-0.5">Plan</span>
          <textarea rows={2} value={plan} onChange={(e) => setPlan(e.target.value)} className="rounded border border-[#e5e7eb] text-[12px] p-2" /></label>
      </ClinicalCard>
      <ClinicalCard>
        <SectionHeader title="Presupuesto" icon={FileText} action={<ClinicalButton variant="primary" onClick={() => {
          const validas = lineas.filter((l) => l.tratamiento_id);
          if (!validas.length) { flash("No hay líneas del catálogo", true); return; }
          correr(patientService.crearPresupuesto(pid, {
            titulo: "Presupuesto de consulta",
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            lineas: validas.map((l) => ({ tratamiento_id: l.tratamiento_id!, pieza: l.pieza || null, cantidad: l.cantidad || 1, precio: l.precio })) } as any),
          (p) => setUltimoPre({ id: p.id, num: p.num }), flash, (p) => `Presupuesto nº ${p.num} creado`);
        }}>Crear</ClinicalButton>} />
        {ultimoPre && <div className="flex items-center gap-2 mb-2"><span className="text-[12px] text-[#0E6B5E]">Presupuesto nº {ultimoPre.num} creado</span>
          <ClinicalButton variant="secondary" onClick={() => imprimirPresupuesto(pid, ultimoPre.id).catch((e) => flash(errMsg(e), true))}>Ver PDF</ClinicalButton></div>}
        {lineas.length === 0 ? <p className="text-[12px] text-slate-400">Sin líneas.</p> : (
          <table className="w-full text-[12px] border-collapse">
            <tbody>{lineas.map((l, i) => (
              <tr key={i} className="border-b border-[#f1f5f9] last:border-0">
                <td className="py-1.5">{l.tratamiento}{!l.tratamiento_id && <span className="block text-[11px] text-[#6D28D9]">No está en el catálogo: no se incluirá</span>}</td>
                <td className="py-1.5 w-16"><input value={l.pieza ?? ""} onChange={(e) => setLineas(lineas.map((x, j) => j === i ? { ...x, pieza: e.target.value || null } : x))}
                  className="w-full rounded border border-[#e5e7eb] text-[12px] px-1.5 py-1 text-center" aria-label="Pieza" placeholder="Pieza" /></td>
                <td className="py-1.5 w-24"><input type="number" min={0} step="0.01" value={l.precio}
                  onChange={(e) => setLineas(lineas.map((x, j) => j === i ? { ...x, precio: Number(e.target.value) } : x))}
                  className="w-full rounded border border-[#e5e7eb] text-[12px] px-1.5 py-1 text-right tabular-nums" aria-label="Precio" /></td>
              </tr>))}</tbody>
          </table>)}
      </ClinicalCard>
      {receta.length > 0 && (
        <ClinicalCard>
          <SectionHeader title="Receta" icon={Pill} action={<ClinicalButton variant="save" onClick={() => {
            const meds = receta.filter((m) => m.medicamento.trim());
            if (!meds.length) return;
            correr(patientService.guardarReceta(pid, meds, { diagnostico: diag || undefined }), () => {}, flash, () => "Receta emitida");
          }}>Firmar receta</ClinicalButton>} />
          <ul className="flex flex-col gap-1.5">
            {receta.map((m, i) => (
              <li key={i} className="grid grid-cols-2 gap-1.5">
                <input value={m.medicamento} onChange={(e) => setReceta(receta.map((x, j) => j === i ? { ...x, medicamento: e.target.value } : x))} className="rounded border border-[#e5e7eb] text-[12px] px-2 py-1" aria-label="Medicamento" />
                <input value={m.posologia || ""} onChange={(e) => setReceta(receta.map((x, j) => j === i ? { ...x, posologia: e.target.value } : x))} className="rounded border border-[#e5e7eb] text-[12px] px-2 py-1" aria-label="Posología" />
              </li>))}
          </ul>
        </ClinicalCard>
      )}
      {mensaje.trim() && (
        <ClinicalCard>
          <SectionHeader title="Mensaje al paciente" icon={MessageCircle} action={<ClinicalButton variant="secondary" onClick={() => {
            const tel = res.telefono;
            if (!tel) { flash("El paciente no tiene móvil", true); return; }
            correr(api.post("/comunicacion/whatsapp/enviar", { telefono: tel, texto: mensaje }), () => {}, flash, () => `Enviado a ${tel}`);
          }}>Enviar por WhatsApp</ClinicalButton>} />
          <textarea rows={4} value={mensaje} onChange={(e) => setMensaje(e.target.value)} className="w-full rounded border border-[#e5e7eb] text-[12px] p-2" />
        </ClinicalCard>
      )}
    </div>
  );
}

/* ── 4. DOCUMENTOS + COBRO ───────────────────────────────── */
function Documentos({ pid, telefono, flash, onHecho }: {
  pid: number; telefono: string | null; flash: (t: string, e?: boolean) => void; onHecho: () => void;
}) {
  return (
    <div className="flex flex-col gap-2.5">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 items-start">
        <PresupuestoMini pid={pid} flash={flash} />
        <RecetaMini pid={pid} flash={flash} />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 items-start">
        <WhatsMini telefono={telefono} flash={flash} />
        <CobroMini pid={pid} flash={flash} onHecho={onHecho} />
      </div>
      <ConsentRow pid={pid} flash={flash} />
    </div>
  );
}

function PresupuestoMini({ pid, flash }: { pid: number; flash: (t: string, e?: boolean) => void }) {
  const [q, setQ] = useState("");
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [res, setRes] = useState<any[]>([]);
  const [lineas, setLineas] = useState<{ tratamiento_id: number; tratamiento: string; pieza: string | null; precio: number }[]>([]);
  const [ultimo, setUltimo] = useState<{ id: number; num: number } | null>(null);
  useEffect(() => {
    if (q.trim().length < 2) { setRes([]); return; }
    const t = setTimeout(() => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      patientService.catalogoTratamientos(pid, q.trim()).then((r: any) => setRes(r.tratamientos || [])).catch(() => setRes([]));
    }, 300);
    return () => clearTimeout(t);
  }, [q, pid]);
  const crear = () => {
    if (!lineas.length) { flash("Añade al menos una línea del catálogo", true); return; }
    correr(patientService.crearPresupuesto(pid, {
      titulo: "Presupuesto de consulta",
      lineas: lineas.map((l) => ({ tratamiento_id: l.tratamiento_id, pieza: l.pieza, cantidad: 1, precio: l.precio })),
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any), (p) => { setUltimo({ id: p.id, num: p.num }); setLineas([]); }, flash, (p) => `Presupuesto nº ${p.num} creado`);
  };
  return (
    <ClinicalCard>
      <div className="px-3 py-2 -m-3 mb-2 text-[11px] uppercase bg-[#FFFFFF] text-[#6D28D9] border-b border-[#C4B5FD] rounded-t-sm">Presupuesto</div>
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar tratamiento…" className="w-full rounded border border-[#e5e7eb] text-[12px] px-2 py-1.5 mb-1.5" aria-label="Buscar tratamiento" />
      {res.length > 0 && (
        <ul className="border border-[#eef2f7] rounded mb-1.5 max-h-[120px] overflow-y-auto">
          {res.slice(0, 8).map((t) => (
            <li key={t.id}><button className="w-full text-left px-2 py-1 text-[12px] hover:bg-[#E6EDFF] flex justify-between gap-2"
              onClick={() => { setLineas([...lineas, { tratamiento_id: t.id, tratamiento: t.nombre, pieza: null, precio: t.precio }]); setQ(""); setRes([]); }}>
              <span className="truncate text-slate-600">{t.nombre}</span><span className="tabular-nums text-slate-400">{eur(t.precio)}</span>
            </button></li>))}
        </ul>)}
      {lineas.length > 0 && (
        <table className="w-full text-[12px] border-collapse mb-1.5">
          <tbody>{lineas.map((l, i) => (
            <tr key={i} className="border-b border-[#f1f5f9] last:border-0">
              <td className="py-1.5 text-slate-600">{l.tratamiento}</td>
              <td className="py-1.5 w-16"><input value={l.pieza ?? ""} onChange={(e) => setLineas(lineas.map((x, j) => j === i ? { ...x, pieza: e.target.value || null } : x))}
                className="w-full rounded border border-[#e5e7eb] text-[12px] px-1 py-1 text-center" placeholder="Pieza" aria-label="Pieza" /></td>
              <td className="py-1.5 w-24"><input type="number" min={0} step="0.01" value={l.precio}
                onChange={(e) => setLineas(lineas.map((x, j) => j === i ? { ...x, precio: Number(e.target.value) } : x))}
                className="w-full rounded border border-[#e5e7eb] text-[12px] px-1 py-1 text-right tabular-nums" aria-label="Precio" /></td>
              <td className="py-1.5 w-8 text-right"><button onClick={() => setLineas(lineas.filter((_, j) => j !== i))} className="text-slate-400 hover:text-[#C026D3]" aria-label="Quitar">✕</button></td>
            </tr>))}</tbody>
        </table>)}
      {ultimo && <div className="flex items-center gap-2 mb-1.5"><span className="text-[12px] text-[#0E6B5E]">Nº {ultimo.num} creado</span>
        <ClinicalButton variant="secondary" onClick={() => imprimirPresupuesto(pid, ultimo.id).catch((e) => flash(errMsg(e), true))}>Ver PDF</ClinicalButton></div>}
      <div className="flex gap-1.5"><ClinicalButton variant="primary" onClick={crear}>Crear</ClinicalButton></div>
    </ClinicalCard>
  );
}

function RecetaMini({ pid, flash }: { pid: number; flash: (t: string, e?: boolean) => void }) {
  const [meds, setMeds] = useState([{ medicamento: "", posologia: "" }]);
  const [diag, setDiag] = useState("");
  const firmar = () => {
    const validos = meds.filter((m) => m.medicamento.trim()).map((m) => ({ medicamento: m.medicamento.trim(), posologia: m.posologia || undefined }));
    if (!validos.length) { flash("Escribe al menos un medicamento", true); return; }
    correr(patientService.guardarReceta(pid, validos, { diagnostico: diag || undefined }), () => setMeds([{ medicamento: "", posologia: "" }]), flash, () => "Receta emitida");
  };
  return (
    <ClinicalCard>
      <div className="px-3 py-2 -m-3 mb-2 text-[11px] uppercase bg-[#FFFFFF] text-[#4a3fa3] border-b border-[#d3cffb] rounded-t-sm">Receta</div>
      <ul className="flex flex-col gap-1.5 mb-1.5">
        {meds.map((m, i) => (
          <li key={i} className="grid grid-cols-[1fr_1fr_auto] gap-1.5">
            <input value={m.medicamento} onChange={(e) => setMeds(meds.map((x, j) => j === i ? { ...x, medicamento: e.target.value } : x))} placeholder="Medicamento" className="rounded border border-[#e5e7eb] text-[12px] px-2 py-1.5" aria-label="Medicamento" />
            <input value={m.posologia} onChange={(e) => setMeds(meds.map((x, j) => j === i ? { ...x, posologia: e.target.value } : x))} placeholder="Posología" className="rounded border border-[#e5e7eb] text-[12px] px-2 py-1.5" aria-label="Posología" />
            <button onClick={() => setMeds(meds.filter((_, j) => j !== i))} className="text-slate-400 hover:text-[#C026D3] px-1" aria-label="Quitar">✕</button>
          </li>))}
      </ul>
      <div className="flex gap-1.5 mb-1.5">
        <ClinicalButton variant="secondary" onClick={() => setMeds([...meds, { medicamento: "", posologia: "" }])}>+ Línea</ClinicalButton>
      </div>
      <input value={diag} onChange={(e) => setDiag(e.target.value)} placeholder="Diagnóstico (opcional)" className="w-full rounded border border-[#e5e7eb] text-[12px] px-2 py-1.5 mb-2" aria-label="Diagnóstico" />
      <ClinicalButton variant="save" onClick={firmar}>Firmar receta</ClinicalButton>
    </ClinicalCard>
  );
}

function WhatsMini({ telefono, flash }: { telefono: string | null; flash: (t: string, e?: boolean) => void }) {
  const [texto, setTexto] = useState("");
  const enviar = () => {
    if (!telefono) { flash("La cita no tiene teléfono", true); return; }
    if (!texto.trim()) { flash("Escribe el mensaje", true); return; }
    correr(api.post("/comunicacion/whatsapp/enviar", { telefono, texto: texto.trim() }), () => setTexto(""), flash, () => `Enviado a ${telefono}`);
  };
  return (
    <ClinicalCard>
      <div className="px-3 py-2 -m-3 mb-2 text-[11px] uppercase bg-[#FFFFFF] text-[#0b7364] border-b border-[#a9e8da] rounded-t-sm">WhatsApp (directo)</div>
      <textarea rows={3} value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="Recomendaciones, recordatorio…" className="w-full rounded border border-[#e5e7eb] text-[12px] p-2" />
      <div className="mt-2"><ClinicalButton variant="primary" onClick={enviar}>Enviar{telefono ? ` a ${telefono}` : ""}</ClinicalButton></div>
    </ClinicalCard>
  );
}

function CobroMini({ pid, flash, onHecho }: { pid: number; flash: (t: string, e?: boolean) => void; onHecho: () => void }) {
  type Linea = { key: string; concepto: string; importe: number; deuda_id?: number; acto_id?: number };
  const [lineas, setLineas] = useState<Linea[] | null>(null);
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [formas, setFormas] = useState<{ id: number; nombre: string }[]>([]);
  const [formaId, setFormaId] = useState<number | null>(null);
  const cargar = useCallback(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    api.get<any>(`/inicio/paciente/${pid}/caja`).then((r) => {
      const ls: Linea[] = [
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        ...((r.actos || []).map((a: any) => ({ key: `a${a.acto_id}`, concepto: a.concepto, importe: a.importe, acto_id: a.acto_id }))),
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        ...((r.deudas || []).map((d: any) => ({ key: `d${d.deuda_id}`, concepto: d.concepto || `Deuda ${d.deuda_id}`, importe: d.pendiente, deuda_id: d.deuda_id }))),
      ];
      setLineas(ls);
      setFormas(r.formas || []);
      setFormaId((p) => p ?? r.formas?.[0]?.id ?? null);
      setSel(new Set(ls.map((l) => l.key)));
    }).catch((e) => { setLineas([]); flash(errMsg(e), true); });
  }, [pid, flash]);
  useEffect(() => { cargar(); }, [cargar]);
  const total = (lineas || []).filter((l) => sel.has(l.key)).reduce((s, l) => s + l.importe, 0);
  const cobrar = () => {
    const aps = (lineas || []).filter((l) => sel.has(l.key)).map((l) => ({ importe: l.importe, deuda_id: l.deuda_id ?? null, acto_id: l.acto_id ?? null }));
    if (!aps.length) { flash("Marca al menos una línea", true); return; }
    const forma = formas.find((f) => f.id === formaId);
    if (!forma) { flash("Elige la forma de pago", true); return; }
    correr(api.post(`/inicio/paciente/${pid}/cobro`, { forma_pago_id: forma.id, aplicaciones: aps }), () => { cargar(); onHecho(); }, flash, () => `Cobro de ${eur(total)} en ${forma.nombre.toLowerCase()}`);
  };
  return (
    <ClinicalCard>
      <div className="px-3 py-2 -m-3 mb-2 text-[11px] uppercase bg-[#FFFFFF] text-[#1500A0] border-b border-[#c7d2fe] rounded-t-sm">Cobro</div>
      {lineas == null ? <p className="text-[12px] text-slate-400">Cargando…</p> : lineas.length === 0 ? <p className="text-[12px] text-slate-400">Sin pendiente.</p> : (
        <table className="w-full text-[12px] border-collapse mb-2">
          <tbody>{lineas.map((l) => (
            <tr key={l.key} className="border-b border-[#f1f5f9] last:border-0">
              <td className="py-1.5 pr-2 w-[22px]"><input type="checkbox" checked={sel.has(l.key)} onChange={() => setSel((p) => {
                const n = new Set(p); if (n.has(l.key)) n.delete(l.key); else n.add(l.key); return n;
              })} aria-label={l.concepto} /></td>
              <td className="py-1.5 text-slate-600">{l.concepto}</td>
              <td className="py-1.5 text-right tabular-nums">{eur(l.importe)}</td>
            </tr>))}</tbody>
        </table>)}
      <div className="flex gap-1.5 flex-wrap mb-2">
        {formas.map((f) => (
          <button key={f.id} onClick={() => setFormaId(f.id)} className={`text-[11px] px-3 py-1.5 rounded border ${formaId === f.id ? "bg-[#1500A0] text-white border-[#1500A0]" : "bg-white border-[#e5e7eb] text-slate-600"}`}>{f.nombre}</button>
        ))}
      </div>
      <ClinicalButton variant="primary" onClick={cobrar}>Cobrar {eur(total)}</ClinicalButton>
    </ClinicalCard>
  );
}

function ConsentRow({ pid, flash }: { pid: number; flash: (t: string, e?: boolean) => void }) {
  const [plantillas, setPlantillas] = useState<{ key: string; label: string }[]>([]);
  const [tpl, setTpl] = useState("");
  const [colab, setColab] = useState("");
  const [colabs, setColabs] = useState<{ id: number; nombre: string }[]>([]);
  useEffect(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    patientService.consentPlantillas().then((r: any) => { setPlantillas(r.plantillas || []); setTpl(r.plantillas?.[0]?.key || ""); }).catch(() => {});
    api.get<Ref>("/agenda/referencias").then((r) => setColabs(r.colaboradores || [])).catch(() => {});
  }, []);
  return (
    <ClinicalCard>
      <SectionHeader title="Consentimiento" icon={FileSignature} action={<ClinicalButton variant="secondary" onClick={() => {
        if (!tpl) { flash("Elige plantilla", true); return; }
        correr(patientService.consentGenerar({ paciente_id: pid, plantilla: tpl, colaborador_id: colab ? Number(colab) : null }),
          () => {}, flash, () => "Consentimiento generado");
      }}>Generar</ClinicalButton>} />
      <div className="flex gap-1.5">
        <select value={tpl} onChange={(e) => setTpl(e.target.value)} className="flex-1 rounded border border-[#e5e7eb] text-[12px] px-2 py-1.5" aria-label="Plantilla">
          {plantillas.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
        </select>
        <select value={colab} onChange={(e) => setColab(e.target.value)} className="rounded border border-[#e5e7eb] text-[12px] px-2 py-1.5" aria-label="Profesional">
          <option value="">Profesional…</option>{colabs.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}
        </select>
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        <ClinicalButton variant="ghost" icon={Wallet} onClick={() => flash("La caja vive en Documentos › Cobro")}>Ver caja</ClinicalButton>
        <ClinicalButton variant="ghost" icon={FolderOpen} onClick={() => window.open(`/pacientes/${pid}/ficha`, "_self")}>Ver documentos en ficha</ClinicalButton>
        <ClinicalButton variant="ghost" icon={ChevronDown} onClick={() => flash("Próxima cita: créala desde Agenda")}>Próxima cita en Agenda</ClinicalButton>
      </div>
    </ClinicalCard>
  );
}
