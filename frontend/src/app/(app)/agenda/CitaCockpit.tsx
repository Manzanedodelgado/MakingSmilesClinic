"use client";
/**
 * Panel-cockpit que se despliega DENTRO de la rejilla de la agenda al pulsar la flecha ▾ de una
 * cita (empujando las de debajo). 3 zonas enchufadas a lo que ya existe.
 */
import { useEffect, useState } from "react";
import {
  Image as ImageIcon, ClipboardList, Mic, MessageCircle,
  ShieldCheck, Pill, Calculator, Printer, Send, CalendarClock,
  Mail, Wallet, ChevronDown, ChevronUp,
} from "lucide-react";
import { api } from "@/shared/lib/api";
import { Modal, ModalBody } from "@/shared/components";
import { patientService } from "@/features/patients/services/patientService";
import { imprimirPresupuesto, enviarPresupuestoWhatsApp } from "@/features/patients/lib/presupuestoDoc";
import OdontogramaOverlay, { type PiezaMarcada } from "@/features/patients/components/odontograma/OdontogramaOverlay";
import { construirOdontogramaClinico } from "@/features/patients/components/odontograma/odontogramaData";
import { EscuchaActiva } from "@/features/patients/components/EscuchaActiva";
import { Escucha } from "@/features/patients/components/Escucha";
import { Multimedia } from "@/features/patients/components/Multimedia";

const eur = (n: number) => new Intl.NumberFormat("es-ES", { style: "currency", currency: "EUR" }).format(n || 0);
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Any = any;

export function CitaCockpit({ pid, telefono, nombre, doctorId }: { pid: number | null; telefono: string | null; nombre: string; doctorId: number | null }) {
  if (!pid) return <div className="px-4 py-6 text-[12px] text-[#7C3AED]">Esta cita no tiene ficha de paciente asociada.</div>;
  return <Cockpit pid={pid} telefono={telefono} nombre={nombre} doctorId={doctorId} />;
}

function Cockpit({ pid, telefono, nombre, doctorId }: { pid: number; telefono: string | null; nombre: string; doctorId: number | null }) {
  const [modal, setModal] = useState<null | "panoramica" | "actos" | "escucha" | "recetas" | "whatsapp">(null);
  const [presu, setPresu] = useState<Any>(null);
  const [recetas, setRecetas] = useState<Any[]>([]);
  const [actos, setActos] = useState<Any[]>([]);
  const [previstos, setPrevistos] = useState<Any[]>([]);
  const [multimedia, setMultimedia] = useState<Any>(null);
  const [odoPiezas, setOdoPiezas] = useState<PiezaMarcada[]>([]);   // O1 (ficha) para la imagen
  const [edad, setEdad] = useState<number | null>(null);
  const [consent, setConsent] = useState<Any[]>([]);
  const [wapp, setWapp] = useState<Any[]>([]);
  const [borrador, setBorrador] = useState("");
  const [waMsg, setWaMsg] = useState("");

  useEffect(() => {
    patientService.presupuestos(pid).then(setPresu).catch(() => {});
    patientService.recetas(pid).then((r) => setRecetas(r.recetas || [])).catch(() => {});
    patientService.actos(pid).then((r: Any) => setActos(r.actos || [])).catch(() => {});
    patientService.previstos(pid).then((r: Any) => setPrevistos((r.presupuestos || []).flatMap((g: Any) => g.previstos || []))).catch(() => {});
    patientService.multimedia(pid).then(setMultimedia).catch(() => {});
    patientService.odontograma(pid).then((d: Any) => setOdoPiezas(construirOdontogramaClinico(d.teeth || [], d.realizados || [], { soloInicial: true }))).catch(() => {});
    patientService.cabecera(pid).then((c: Any) => setEdad(c.edad ?? null)).catch(() => {});
    patientService.consentListar(pid).then((r) => setConsent(r || [])).catch(() => {});
    const norm = (s: string) => (s || "").replace(/\D/g, "").slice(-9);   // últimos 9 dígitos (como match_paciente)
    api.get<{ data: Any[] }>("/comunicacion/conversaciones").then((r) => {
      const conv = (r.data || [])
        .filter((x) => x.pacienteId === pid || (telefono && norm(x.telefono) === norm(telefono)))
        .sort((a, b) => String(b.ultimoMensajeAt || "").localeCompare(String(a.ultimoMensajeAt || "")))[0];
      if (conv) api.get<{ data: Any[] }>(`/comunicacion/conversaciones/${conv.id}/mensajes`)
        .then((m) => setWapp(m.data || [])).catch(() => {});
    }).catch(() => {});
  }, [pid, telefono]);

  const refrescarActos = () => patientService.actos(pid).then((r: Any) => setActos(r.actos || [])).catch(() => {});
  const enviarBorrador = async () => {
    if (!telefono || !borrador.trim()) { setWaMsg("Sin teléfono o mensaje"); return; }
    try { await api.post("/comunicacion/whatsapp/enviar", { telefono, texto: borrador }); setWaMsg("Enviado ✓"); }
    catch { setWaMsg("Error al enviar"); }
  };

  const presus = presu?.presupuestos || [];
  const RE_PANO = /PANORAM|ORTOPANT|CBCT|TAC|RADIO/i;
  const rx: Any[] = multimedia?.radiografias || [];
  const pano = rx.find((r) => RE_PANO.test(r.name)) || rx[0] || null;
  const consFirmados = consent.filter((c) => c.estado === "firmado");
  const vigente = (c: Any) => { const d = new Date(c.fecha); return Number.isFinite(d.getTime()) && (Date.now() - d.getTime()) < 90 * 864e5; };

  return (
    <div className="p-3 flex flex-col gap-2 bg-[#FFFFFF]">
      {/* Tarjeta del paciente + Previas (GesdenOne 7.09.42) */}
      <TarjetaPaciente pid={pid} nombre={nombre} />
      <PreviasPaciente pid={pid} />
      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)_minmax(0,1fr)] gap-3 bg-transparent items-start">
      {/* IZQUIERDA — HISTORIAL */}
      <div className="flex flex-col gap-2 min-w-0">
        <Zona>Historial</Zona>
        {/* Miniatura de la ÚLTIMA panorámica (arriba) → emergente */}
        <button onClick={() => setModal("panoramica")} title="Ver panorámica" className="relative block w-full rounded-md overflow-hidden border border-[#e5e7eb] bg-[#0b1220] aspect-[16/10]">
          {pano ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={patientService.multimediaUrl(pid, pano.id, true)} alt="Última panorámica" className="w-full h-full object-contain" />
          ) : <div className="w-full h-full flex items-center justify-center text-[11px] text-slate-400"><ImageIcon className="w-5 h-5 mr-1" /> Sin panorámica</div>}
          <span className="absolute bottom-1 left-1 text-[9px] font-semibold uppercase tracking-wide text-white bg-black/50 px-1.5 py-0.5 rounded-sm">Última panorámica{pano?.fecha ? ` · ${pano.fecha}` : ""}</span>
        </button>
        {/* 5 últimos tratamientos realizados */}
        <Seccion titulo="Últimos realizados" icon={ClipboardList}>
          {actos.length === 0 ? <Vacio /> : actos.slice(0, 5).map((a: Any) => (
            <Fila key={a.id}><span className="truncate">{a.tratamiento}</span><span className="text-[#7f8c8d] shrink-0">{a.fecha}</span></Fila>
          ))}
          {actos.length > 5 && <button onClick={() => setModal("actos")} className="text-[10px] text-[#1ca0d1] hover:underline mt-1">ver todos ({actos.length})</button>}
        </Seccion>
        {/* Previstos (fondo coral) */}
        <div className="border rounded-md" style={{ borderColor: "#C4B5FD", background: "#FFFFFF" }}>
          <div className="flex items-center gap-1.5 px-2.5 py-1.5 border-b" style={{ borderColor: "#DDD6FE" }}>
            <CalendarClock className="w-3.5 h-3.5" style={{ color: "#7C3AED" }} />
            <span className="text-[10px] font-semibold uppercase tracking-wide" style={{ color: "#6D28D9" }}>Previstos ({previstos.length})</span>
          </div>
          <div className="p-2 max-h-36 overflow-y-auto">
            {previstos.length === 0 ? <p className="text-[11px] italic" style={{ color: "#A78BFA" }}>—</p> : previstos.slice(0, 8).map((p: Any) => (
              <div key={p.id} className="flex items-center justify-between gap-2 text-[11px] py-0.5" style={{ color: "#374151" }}>
                <span className="truncate">{p.tratamiento}{p.pieza ? ` · ${p.pieza}` : ""}{p.etiqueta ? ` (${p.etiqueta})` : ""}</span>
                <span className="shrink-0 font-semibold">{eur(p.importe)}</span>
              </div>
            ))}
          </div>
        </div>
        {/* Iconos: recetas y WhatsApp → abren su historial */}
        <div className="grid grid-cols-2 gap-2">
          <Btn icon={Pill} onClick={() => setModal("recetas")}>Recetas ({recetas.length})</Btn>
          <Btn icon={MessageCircle} onClick={() => setModal("whatsapp")}>WhatsApp</Btn>
        </div>
      </div>

      {/* CENTRO — EVALUACIÓN */}
      <div className="flex flex-col gap-2 min-w-0">
        <Zona>Evaluación</Zona>
        <div className="border border-[#e5e7eb] rounded-md bg-white overflow-hidden p-2">
          <OdontogramaOverlay modo="view" piezasMarcadas={odoPiezas} onPiezaClick={() => {}} piezaActiva={null} imgClassName="w-full h-auto object-contain max-h-[300px]" edad={edad} />
        </div>
        {/* Escucha: mismo componente que el modal, en modo inline. El mensaje va al borrador de la derecha. */}
        <div className="border border-[#e5e7eb] rounded-md bg-white p-2.5">
          <Escucha patientId={pid} telefono={telefono} variant="inline" doctorId={doctorId} onMensaje={setBorrador} onGuardado={refrescarActos} />
        </div>
      </div>

      {/* DERECHA — ACCIONES */}
      <div className="flex flex-col gap-2 min-w-0">
        <Zona>Acciones</Zona>
        <button onClick={() => setModal("escucha")} className="flex items-center justify-center gap-1.5 text-[13px] font-bold text-[#1500A0] bg-[#2DD9C3] hover:brightness-105 rounded-md px-3 py-2.5 shadow-sm"><Mic className="w-4 h-4" /> Escucha</button>
        <Seccion titulo="Presupuestos generados" icon={Calculator}>
          {presus.length === 0 ? <Vacio /> : presus.slice(0, 6).map((p: Any) => (
            <div key={p.id} className="flex items-center gap-2 text-[11px] py-0.5">
              <span className="truncate flex-1">#{p.num} · {eur(p.total)}</span>
              <a href={`/pacientes/${pid}/presupuestos`} title="Ver / editar" className="text-[#1ca0d1] hover:underline shrink-0">ver</a>
              <button title="Imprimir" onClick={() => imprimirPresupuesto(pid, p.id, "").catch(() => {})} className="shrink-0 text-[#1500A0] hover:opacity-70"><Printer className="w-3.5 h-3.5" /></button>
              <button title="Enviar por WhatsApp" onClick={() => enviarPresupuestoWhatsApp(pid, p.id, "").then(() => setWaMsg("Presupuesto enviado ✓")).catch(() => setWaMsg("Error al enviar"))} className="shrink-0 text-[#20BEAB] hover:opacity-70"><Send className="w-3.5 h-3.5" /></button>
            </div>
          ))}
        </Seccion>
        <Seccion titulo="Recetas" icon={Pill}>
          {recetas.length === 0 ? <Vacio /> : recetas.slice(0, 5).map((r: Any) => (<Fila key={r.id}><span className="truncate">{r.medicamento || "Receta"}</span></Fila>))}
        </Seccion>
        <Seccion titulo="Mensaje WhatsApp (borrador)" icon={MessageCircle}>
          <textarea value={borrador} onChange={(e) => setBorrador(e.target.value)} rows={3} placeholder="Recomendaciones para el paciente…"
            className="w-full border border-[#e5e7eb] rounded-sm text-[12px] px-2 py-1 outline-none focus:border-[#1ca0d1] resize-none" />
          <div className="flex items-center gap-2 mt-1">
            <button onClick={enviarBorrador} disabled={!telefono} className="text-[11px] font-semibold text-white bg-[#1ca0d1] hover:brightness-110 rounded-sm px-2.5 py-1 disabled:opacity-40">Enviar</button>
            {waMsg && <span className={`text-[11px] ${waMsg.includes("✓") ? "text-[#0F8C7D]" : "text-[#C026D3]"}`}>{waMsg}</span>}
          </div>
        </Seccion>
        <Seccion titulo="Consentimientos" icon={ShieldCheck}>
          <div className="text-[11px] mb-1"><b className="text-[#0F8C7D]">{consFirmados.length}</b> firmado(s) · validez 3 meses</div>
          {consent.length === 0 ? <Vacio /> : consent.slice(0, 6).map((c: Any) => {
            const firm = c.estado === "firmado"; const vig = firm && vigente(c);
            return (
              <div key={c.id} className="flex items-center gap-1.5 text-[11px] py-0.5">
                <span className="truncate flex-1">{c.tipo}</span>
                {!firm ? <span className="text-[#7C3AED] shrink-0">pendiente</span> : vig ? <span className="text-[#0F8C7D] shrink-0">vigente</span> : <span className="text-[#C026D3] shrink-0">caducado</span>}
              </div>
            );
          })}
        </Seccion>
      </div>
      </div>

      {modal === "panoramica" && <ModalBox titulo="Multimedia · Panorámicas" onClose={() => setModal(null)}><Multimedia patientId={pid} /></ModalBox>}
      {modal === "actos" && (
        <ModalBox titulo={`Tratamientos realizados · ${nombre}`} onClose={() => setModal(null)}>
          <table className="w-full text-[12px]">
            <thead className="text-[10px] uppercase text-[#7f8c8d] border-b border-[#e5e7eb]"><tr><th className="text-left py-1 px-2">Fecha</th><th className="text-left px-2">Tratamiento</th><th className="text-left px-2">Pieza</th><th className="text-right px-2">Importe</th></tr></thead>
            <tbody>{actos.map((a: Any) => (<tr key={a.id} className="border-b border-[#f0f2f5]"><td className="py-1 px-2 text-[#7f8c8d]">{a.fecha}</td><td className="px-2">{a.tratamiento}</td><td className="px-2 text-[#7f8c8d]">{a.piezas || "—"}</td><td className="px-2 text-right text-[#1500A0]">{eur(a.importe)}</td></tr>))}</tbody>
          </table>
          {actos.length === 0 && <p className="text-center text-slate-400 italic py-4 text-[12px]">Sin tratamientos realizados.</p>}
        </ModalBox>
      )}
      {modal === "recetas" && (
        <ModalBox titulo={`Recetas · ${nombre}`} onClose={() => setModal(null)}>
          {recetas.length === 0 ? <p className="text-center text-slate-400 italic py-4 text-[12px]">Sin recetas.</p> : (
            <table className="w-full text-[12px]">
              <thead className="text-[10px] uppercase text-[#7f8c8d] border-b border-[#e5e7eb]"><tr><th className="text-left py-1 px-2">Fecha</th><th className="text-left px-2">Medicamento</th><th className="text-left px-2">Posología</th><th className="text-left px-2">Doctor</th></tr></thead>
              <tbody>{recetas.map((r: Any) => (<tr key={r.id} className="border-b border-[#f0f2f5]"><td className="py-1 px-2 text-[#7f8c8d]">{r.fecha}</td><td className="px-2">{r.medicamento}</td><td className="px-2 text-[#7f8c8d]">{r.posologia || "—"}</td><td className="px-2 text-[#7f8c8d]">{r.doctor || "—"}</td></tr>))}</tbody>
            </table>
          )}
        </ModalBox>
      )}
      {modal === "whatsapp" && (
        <ModalBox titulo={`WhatsApp · ${nombre}`} onClose={() => setModal(null)}>
          {wapp.length === 0 ? <p className="text-center text-slate-400 italic py-4 text-[12px]">Sin conversación reciente.</p> : (
            <div className="flex flex-col gap-1.5">
              {wapp.map((m: Any) => (<div key={m.id} className={`text-[12px] px-2.5 py-1.5 rounded-md max-w-[80%] ${m.direccion === "saliente" || m.direccion === "out" ? "bg-[#FFFFFF] self-end" : "bg-[#FFFFFF] self-start"}`}>{m.cuerpo || m.mediaTipo || "—"}</div>))}
            </div>
          )}
          {telefono && <a href={`/comunicacion?tel=${encodeURIComponent(telefono)}`} className="inline-block mt-3 text-[12px] text-[#1ca0d1] hover:underline">Abrir conversación completa →</a>}
        </ModalBox>
      )}
      {modal === "escucha" && <EscuchaActiva patientId={pid} onClose={() => setModal(null)} />}
    </div>
  );
}

function Seccion({ titulo, icon: Icon, children }: { titulo: string; icon?: React.ElementType; children: React.ReactNode }) {
  return (
    <div className="border border-[#e5e7eb] rounded-md bg-white">
      <div className="flex items-center gap-1.5 px-2.5 py-1.5 border-b border-[#f0f2f5]">
        {Icon && <Icon className="w-3.5 h-3.5 text-[#1ca0d1]" />}
        <span className="text-[10px] font-semibold uppercase tracking-wide text-[#1500A0]">{titulo}</span>
      </div>
      <div className="p-2 max-h-40 overflow-y-auto">{children}</div>
    </div>
  );
}
function Btn({ icon: Icon, onClick, children }: { icon: React.ElementType; onClick: () => void; children: React.ReactNode }) {
  return (
    <button onClick={onClick} className="flex items-center gap-2 text-[12px] font-semibold text-[#1500A0] bg-white border border-[#e5e7eb] hover:border-[#1ca0d1] rounded-md px-3 py-2 text-left">
      <Icon className="w-4 h-4 text-[#1ca0d1] shrink-0" /><span className="truncate">{children}</span>
    </button>
  );
}
const Zona = ({ children }: { children: React.ReactNode }) => (
  <div className="text-[11px] font-bold uppercase tracking-widest text-[#1500A0] border-b-2 border-[#2DD9C3] pb-1 mb-0.5">{children}</div>
);
const Vacio = ({ texto }: { texto?: string }) => <p className="text-[11px] text-slate-400 italic">{texto || "—"}</p>;
function Fila({ children }: { children: React.ReactNode }) {
  return <div className="flex items-center justify-between gap-2 text-[11px] text-[#333] py-0.5">{children}</div>;
}
function ModalBox({ titulo, onClose, children }: { titulo: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <Modal title={<span className="uppercase">{titulo}</span>} onClose={onClose} size="lg">
      <ModalBody>{children}</ModalBody>
    </Modal>
  );
}

// ── Tarjeta del paciente (GesdenOne 7.09.42): NHC + contacto + tarifa + consentimientos/canales ──
function TarjetaPaciente({ pid, nombre }: { pid: number; nombre: string }) {
  const [cab, setCab] = useState<Any>(null);
  const [fili, setFili] = useState<Any>(null);
  useEffect(() => {
    patientService.cabecera(pid).then(setCab).catch(() => {});
    patientService.filiacion(pid).then(setFili).catch(() => {});
  }, [pid]);
  const chips: { etiqueta: string; on: boolean }[] = [
    { etiqueta: "GDPR", on: !!fili?.acepta_lopd },
    { etiqueta: "Info", on: !!fili?.acepta_info },
    { etiqueta: "WhatsApp", on: !!fili?.acepta_whatsapp },
    { etiqueta: "Bots", on: !!fili?.acepta_bots },
  ];
  const telMov = (fili?.telefono_movil || "").trim();
  const telFij = (fili?.telefono_fijo || "").trim();
  return (
    <div className="bg-white border border-[#e5e7eb] rounded-md shadow-sm">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-[#f0f2f5] min-w-0">
        <ShieldCheck className="w-4 h-4 text-[#1ca0d1] shrink-0" />
        <span className="text-[13px] font-bold text-[#1500A0] truncate">{nombre}</span>
        {cab?.num_historia && <span className="text-[10px] font-semibold text-white bg-[#1ca0d1] px-1.5 py-0.5 rounded-sm shrink-0">NHC {cab.num_historia}</span>}
        <div className="ml-auto flex items-center gap-3 min-w-0">
          {fili && <span className="text-[11px] text-[#374151] shrink-0 tabular-nums">{[telFij, telMov].filter(Boolean).join(" · ") || "sin teléfono"}</span>}
          {fili?.email && <span className="hidden md:flex items-center gap-1 text-[11px] text-[#374151] min-w-0"><Mail className="w-3.5 h-3.5 text-[#1ca0d1] shrink-0" /><span className="truncate">{fili.email}</span></span>}
          {cab?.tarifa && <span className="hidden xl:flex items-center gap-1 text-[11px] text-[#374151] shrink-0"><Wallet className="w-3.5 h-3.5 text-[#1ca0d1]" />{cab.tarifa}</span>}
        </div>
      </div>
      <div className="px-3 py-1.5 flex flex-wrap items-center gap-1.5">
        {chips.map((c) => (
          <span key={c.etiqueta} className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-sm text-[10px] font-semibold ${c.on ? "bg-[#20BEAB]/15 text-[#0F8C7D] border border-[#20BEAB]/40" : "bg-white text-slate-400 border border-slate-200"}`}>
            {c.on ? "✓" : "✕"} {c.etiqueta}
          </span>
        ))}
      </div>
    </div>
  );
}

// ── Previas del paciente (GesdenOne 7.09.42): Anterior / Hoy / Siguientes con citas-card ──
type CitaPrev = { id: number; fecha: string; hora: string; duracion_min: number; tipo_nombre: string | null; estado_nombre: string | null; estado_color?: string | null; estado_id?: number | null; colaborador_id: number | null; gabinete_id?: number | null; paciente_id?: number | null };
function PreviasPaciente({ pid }: { pid: number }) {
  const [abierto, setAbierto] = useState(false);
  const [tab, setTab] = useState<"Anterior" | "Hoy" | "Siguientes">("Anterior");
  const [citas, setCitas] = useState<CitaPrev[] | null>(null);
  const [nombres, setNombres] = useState<{ doctores: Map<number, string>; gabs: Map<number, string> }>({ doctores: new Map(), gabs: new Map() });
  const ymdLocal = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  const toggle = () => {
    const next = !abierto; setAbierto(next);
    if (next && citas === null) {
      const hoy = new Date();
      Promise.allSettled([
        api.get<{ citas: CitaPrev[] }>(`/agenda/citas?desde=${ymdLocal(new Date(hoy.getFullYear() - 2, hoy.getMonth(), hoy.getDate()))}&hasta=${ymdLocal(new Date(hoy.getTime() + 210 * 864e5))}`),
        api.get<Any>("/agenda/referencias"),
      ]).then(([citasR, refR]) => {
        const en2a = citasR.status === "fulfilled" ? citasR.value.citas : [];
        setCitas(en2a.filter((c) => c.paciente_id === pid));
        if (refR.status === "fulfilled") {
          const r = refR.value;
          setNombres({
            doctores: new Map((r.colaboradores || []).map((c: Any) => [c.id, c.nombre])),
            gabs: new Map((r.gabinetes || []).map((g: Any) => [g.id, g.nombre])),
          });
        }
      });
    }
  };
  const hoyYMD = ymdLocal(new Date());
  const previas = (citas || []).filter((c) => c.fecha && c.fecha < hoyYMD).sort((a, b) => (b.fecha + b.hora).localeCompare(a.fecha + a.hora));
  const deHoy = (citas || []).filter((c) => c.fecha === hoyYMD).sort((a, b) => a.hora.localeCompare(b.hora));
  const siguientes = (citas || []).filter((c) => c.fecha && c.fecha > hoyYMD).sort((a, b) => (a.fecha + a.hora).localeCompare(b.fecha + b.hora));
  const porTab = tab === "Anterior" ? previas : tab === "Hoy" ? deHoy : siguientes;
  return (
    <div className="bg-white border border-[#e5e7eb] rounded-md shadow-sm">
      <div className="flex items-center gap-2 px-3 py-1.5 border-b border-[#f0f2f5] cursor-pointer select-none" onClick={toggle} aria-expanded={abierto}>
        <CalendarClock className="w-3.5 h-3.5 text-[#1ca0d1] shrink-0" />
        <span className="text-[10px] font-semibold uppercase tracking-wide text-[#1500A0]">Citas del paciente</span>
        <span className="text-[10px] text-[#7f8c8d]">· Anterior {previas.length} · Hoy {deHoy.length} · Siguientes {siguientes.length}</span>
        {abierto ? <ChevronUp className="w-3.5 h-3.5 text-[#1ca0d1] ml-auto" /> : <ChevronDown className="w-3.5 h-3.5 text-[#1ca0d1] ml-auto" />}
      </div>
      {abierto && (
        <div className="p-2">
          <div className="flex items-center gap-1 mb-1.5">
            {(["Anterior", "Hoy", "Siguientes"] as const).map((t) => (
              <button key={t} onClick={() => setTab(t)} className={`px-2.5 py-1 text-[11px] font-semibold rounded-sm ${tab === t ? "bg-[#1ca0d1] text-white" : "text-[#374151] hover:bg-[#E6EDFF]"}`}>{t}</button>
            ))}
          </div>
          {citas === null ? <Vacio texto="cargando…" /> : porTab.length === 0 ? <Vacio /> : (
            <div className="flex flex-col gap-1.5 max-h-56 overflow-y-auto pr-1">
              {porTab.map((c) => (
                <div key={c.id} className="border border-[#f0f2f5] rounded-md bg-white hover:bg-[#E6EDFF] px-2.5 py-1.5">
                  <div className="flex items-center gap-1.5 text-[12px]">
                    <span className="tabular-nums font-semibold text-[#1500A0]">{(c.fecha || "").split("-").reverse().join("/")} · {c.hora}</span>
                    <span className="text-[12px] font-semibold text-[#374151] truncate">{c.tipo_nombre || "Cita"}</span>
                    <span className="ml-auto shrink-0 inline-flex items-center gap-1 px-1.5 py-0.5 rounded-sm text-[10px] font-semibold"
                      style={{ background: /anul/i.test(c.estado_nombre || "") ? "#F7E5FB" : `${c.estado_color || "#1ca0d1"}22`, color: /anul/i.test(c.estado_nombre || "") ? "#C026D3" : (c.estado_color || "#013B82") }}>
                      {c.estado_nombre || "—"}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 text-[11px] text-[#7f8c8d] mt-0.5">
                    <span>{c.duracion_min || 30} min</span>
                    {c.colaborador_id && nombres.doctores.has(c.colaborador_id) ? <span>· {nombres.doctores.get(c.colaborador_id)}</span> : null}
                    {c.gabinete_id && nombres.gabs.has(c.gabinete_id) ? <span>· Box {nombres.gabs.get(c.gabinete_id)}</span> : null}
                    {/anul/i.test(c.estado_nombre || "") && <span className="line-through">anulada</span>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
