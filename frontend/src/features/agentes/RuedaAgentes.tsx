"use client";
import { useEffect, useState } from "react";
import { ArrowLeft, Users, Cog, Target, Wallet2, MessageSquareText, Sliders, ListChecks, Radio, Clock, ScrollText, KeyRound } from "lucide-react";
import { api } from "@/shared/lib/api";
import { ClinicalCard, SectionHeader, ClinicalButton, INPUT, LABEL, TEXTAREA, SELECT, DESC, EMPTY } from "@/shared/components";

type Ficha = { id: string; nombre: string; titular: string; parcela: string; modelo: string; capacidades: Record<string, string>; limites?: string[]; permisos?: string[] };
type Estado = { id: string; activa: boolean; operativa: boolean; modelo: string; baseUrl: string | null };
type Dict = Record<string, unknown>;
type PermisoCatalogo = { codigo: string; descripcion: string | null };

type AgenteDb = { id: number; audiencia: string; modo_activacion: string; programacion: { cron?: string; interval_seg?: number } | null };
type Capacidad = { clave: string; descripcion: string };
type CanalAjuste = { longitud_max: number | null; usa_emojis: boolean | null; ritmo: string | null };

// Canal por defecto según a quién habla el agente (Sección 7 de la spec).
const CANAL_POR_AUDIENCIA: Record<string, string> = {
  paciente: "whatsapp", staff: "chat_interno", superuser: "superuser", facturacion: "chat_interno", sistema: "sistema",
};

// Colores tomados de la paleta corporativa (navy/cyan/brand/accent), más un quinto tono
// ámbar solo para Centinela (vigilancia/alerta, no conversa) — nunca verdes ni rojos, y
// ningún color fuera de la identidad de marca. Es el único acento de color de toda la
// pantalla: el resto sigue al pie de la letra el sistema de Config (ClinicalCard/SectionHeader).
const PETALO: Record<string, { color: string; oscuro: string; icono: typeof Users }> = {
  alex: { color: "#1ca0d1", oscuro: "#0f6f92", icono: MessageSquareText },
  victor: { color: "#013b82", oscuro: "#012a5e", icono: Users },
  aura: { color: "#1500A0", oscuro: "#0f0075", icono: Cog },
  gestor: { color: "#2DD9C3", oscuro: "#189985", icono: Wallet2 },
  centinela: { color: "#7C3AED", oscuro: "#5B21B6", icono: Target },
};
// Aura y Centinela NO salen aquí: de momento solo viven en SuperUser (la ficha de Aura se
// edita con <AuraConfig /> dentro de SuperUser → Aura; Centinela tiene su propia pestaña).
const ORDEN = ["alex", "victor", "gestor"];
// Centinela no viene de /agentes (fuera del catálogo del backend a propósito, ver
// domain/config/agentes.py): sin este nombre de repuesto, el id crudo salía en minúsculas.
const NOMBRE_RESPUESTO: Record<string, string> = { centinela: "Centinela" };
// Centinela no tiene ficha en /agentes: mismo hecho que ya describe su panel de detalle
// (no es conversacional, vive en SuperUser), no una frase nueva inventada aquí.
const PARCELA_RESPUESTO: Record<string, string> = {
  centinela: "Vigilancia continua del sistema: procesos, copias de seguridad y alertas. No conversa con nadie.",
};

// Agrupación real por audiencia (Sección 1 de la spec) — no es decoración, es a quién
// habla cada agente. Mismo orden que ORDEN.
const GRUPO: Record<string, string> = {
  alex: "Habla con los pacientes",
  victor: "Habla con el equipo",
  gestor: "Habla con facturación",
  aura: "Solo lo ve SuperUser",
  centinela: "Vigila el sistema, no conversa",
};

const CONVERSACIONALES: Record<string, { endpointChat: string; claveConfig: string; sistemaConfig: string; tieneVoz?: boolean }> = {
  alex: { endpointChat: "/comunicacion/agente/chat", claveConfig: "agente.alex", sistemaConfig: "ia", tieneVoz: true },
  victor: { endpointChat: "/agentes/victor/chat", claveConfig: "agente.victor", sistemaConfig: "ia" },
  aura: { endpointChat: "/agentes/aura/chat", claveConfig: "aura.config", sistemaConfig: "aura" },
  gestor: { endpointChat: "/agentes/gestor/chat", claveConfig: "gestor.config", sistemaConfig: "gestor" },
};

// Insignia de estado — mismo patrón que EstadoBadge en CanalesIA.tsx (verde/ámbar/gris,
// nunca el color del agente: el estado tiene un significado universal en toda la app).
function InsigniaEstado({ estado }: { estado?: Estado }) {
  const texto = estado?.operativa ? "Operativo" : estado?.activa ? "Encendido" : "Apagado";
  const clases = estado?.operativa
    ? "bg-[#FFFFFF] text-[#0F8C7D]"
    : estado?.activa
    ? "bg-[#FFFFFF] text-[#6D28D9]"
    : "bg-[#FFFFFF] text-[#64748b]";
  return <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-sm shrink-0 ${clases}`}>{texto}</span>;
}

export function RuedaAgentes() {
  const [fichas, setFichas] = useState<Record<string, Ficha>>({});
  const [estados, setEstados] = useState<Record<string, Estado>>({});
  const [activo, setActivo] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      api.get<{ agentes: Ficha[] }>("/agentes").then((r) => r.agentes),
      api.get<{ agentes: Estado[] }>("/agentes/estado/todos").then((r) => r.agentes),
    ]).then(([cat, est]) => {
      setFichas(Object.fromEntries(cat.map((f) => [f.id, f])));
      setEstados(Object.fromEntries(est.map((e) => [e.id, e])));
    });
  }, []);

  if (activo) {
    return <DetalleAgente id={activo} ficha={fichas[activo]} estado={estados[activo]} onCerrar={() => setActivo(null)} />;
  }

  return (
    <div className="flex-1 flex flex-col gap-2.5">
      <p className={DESC}>Cada agente tiene su propio modelo, personalidad, límites, capacidades y permisos. Pulsa uno para configurarlo.</p>
      {ORDEN.map((id) => {
        const pet = PETALO[id];
        const f = fichas[id];
        const e = estados[id];
        const Icono = pet.icono;
        const nombre = f?.nombre ?? NOMBRE_RESPUESTO[id] ?? id;
        return (
          <button key={id} onClick={() => setActivo(id)}
            className="text-left w-full bg-white border border-[#e5e7eb] rounded-sm shadow-sm p-3 hover:border-[#1ca0d1] transition-colors">
            <SectionHeader
              title={nombre}
              customIcon={<Icono className="w-3.5 h-3.5" style={{ color: pet.color }} />}
              action={
                <div className="flex items-center gap-2.5">
                  <span className="text-[10.5px] text-slate-400">{GRUPO[id]}</span>
                  <InsigniaEstado estado={e} />
                </div>
              }
              className="!mb-1.5 !pb-1.5"
            />
            <p className={DESC}>{f?.parcela ?? PARCELA_RESPUESTO[id] ?? ""}</p>
          </button>
        );
      })}
    </div>
  );
}

// Ficha de Aura (límites, capacidades, permisos, modelo, chat) para SuperUser → Aura.
export function AuraConfig({ tituloCapacidades }: { tituloCapacidades?: string }) {
  const [ficha, setFicha] = useState<Ficha | undefined>();
  const [estado, setEstado] = useState<Estado | undefined>();
  useEffect(() => {
    api.get<{ agentes: Ficha[] }>("/agentes").then((r) => setFicha(r.agentes.find((a) => a.id === "aura")));
    api.get<{ agentes: Estado[] }>("/agentes/estado/todos").then((r) => setEstado(r.agentes.find((a) => a.id === "aura")));
  }, []);
  if (!ficha || !estado) return <p className={EMPTY}>Cargando la ficha de Aura…</p>;
  return <DetalleAgente id="aura" ficha={ficha} estado={estado} tituloCapacidades={tituloCapacidades} />;
}

function DetalleAgente({ id, ficha, estado, onCerrar, tituloCapacidades }: { id: string; ficha?: Ficha; estado?: Estado; onCerrar?: () => void; tituloCapacidades?: string }) {
  const pet = PETALO[id];
  // Centinela no tiene ficha en /agentes (fuera del catálogo a propósito): panel propio,
  // sin depender de datos que nunca van a llegar de esa API.
  if (id === "centinela") {
    const Icono = pet.icono;
    return (
      <div className="flex-1 flex flex-col gap-2.5">
        <ClinicalCard>
          <div className="flex items-center gap-2 mb-1.5 pb-1.5 border-b border-[#e5e7eb]">
            <button onClick={onCerrar} className="text-slate-400 hover:text-[#1500A0] transition-colors" aria-label="Volver"><ArrowLeft className="w-4 h-4" /></button>
            <div className="w-6 h-6 rounded-full overflow-hidden bg-white flex items-center justify-center p-0.5">
              <Icono className="w-3.5 h-3.5" style={{ color: pet.color }} />
            </div>
            <div>
              <h2 className="text-[12px] font-semibold text-[#1500A0] uppercase tracking-wide leading-tight">{NOMBRE_RESPUESTO.centinela}</h2>
              <p className="text-[10.5px] text-slate-400 leading-tight">{GRUPO.centinela}</p>
            </div>
          </div>
          <p className={`${DESC} mb-3`}>{PARCELA_RESPUESTO.centinela}</p>
          <a href="/superuser"><ClinicalButton variant="secondary">Ir a SuperUser → Centinela</ClinicalButton></a>
        </ClinicalCard>
      </div>
    );
  }
  const conv = CONVERSACIONALES[id];
  const [ajustes, setAjustes] = useState<Dict>({});
  const [turnos, setTurnos] = useState<{ propio: boolean; texto: string; corregido?: boolean }[]>([]);
  const [entrada, setEntrada] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [aviso, setAviso] = useState("");
  const [estadoLocal, setEstadoLocal] = useState(estado);
  const [corrigiendo, setCorrigiendo] = useState<number | null>(null);
  const [textoCorreccion, setTextoCorreccion] = useState("");

  const [dbAgente, setDbAgente] = useState<AgenteDb | null>(null);
  const [catalogo, setCatalogo] = useState<Capacidad[]>([]);
  const [capsActivas, setCapsActivas] = useState<string[]>([]);
  const [canal, setCanal] = useState<CanalAjuste>({ longitud_max: null, usa_emojis: null, ritmo: null });
  const [guardandoAvanzado, setGuardandoAvanzado] = useState("");

  // Límites editables y permisos de la app (los dos huecos de esta pantalla): sembrados
  // desde la ficha del catálogo y pisados por lo que tenga GUARDADO la config del centro.
  const [limites, setLimites] = useState<string[]>(ficha?.limites ?? []);
  const [permisosApp, setPermisosApp] = useState<string[]>(ficha?.permisos ?? []);
  const [nuevoLimite, setNuevoLimite] = useState("");
  const [catalogoPermisos, setCatalogoPermisos] = useState<PermisoCatalogo[]>([]);

  useEffect(() => {
    if (!conv) return;
    api.get<{ valores: Record<string, unknown> }>(`/config?sistema=${conv.sistemaConfig}`)
      .then((cfg) => {
        const base = (cfg.valores?.[conv.claveConfig] as Dict) || {};
        setAjustes(base);
        if (Array.isArray(base.limites_texto)) setLimites(base.limites_texto as string[]);
        const req = (base.permisos as Dict | undefined)?.requiere;
        if (Array.isArray(req)) setPermisosApp(req as string[]);
      })
      .catch(() => {});
  }, [id, conv]);

  useEffect(() => {
    if (!conv) return;
    api.get<{ permisos: PermisoCatalogo[] }>("/agentes/permisos/catalogo")
      .then((r) => setCatalogoPermisos(r.permisos))
      .catch(() => setCatalogoPermisos([]));
  }, [id, conv]);

  // Filas de las casillas: el catálogo COMPLETO de permisos de la app (se puede conceder
  // cualquiera); si la API fallara, al menos la lista por defecto del agente sin textos.
  const filasPermisos: PermisoCatalogo[] = catalogoPermisos.length > 0
    ? catalogoPermisos
    : (ficha?.permisos ?? []).map((codigo) => ({ codigo, descripcion: null }));

  useEffect(() => {
    if (!conv) return;
    (async () => {
      let lista = (await api.get<{ agentes: (AgenteDb & { config_key: string })[] }>("/agentes/db")).agentes;
      let propio = lista.find((a) => a.config_key === conv.claveConfig);
      if (!propio) {
        await api.post("/agentes/db/migrar-base", {});
        lista = (await api.get<{ agentes: (AgenteDb & { config_key: string })[] }>("/agentes/db")).agentes;
        propio = lista.find((a) => a.config_key === conv.claveConfig);
      }
      if (!propio) return;
      setDbAgente(propio);
      const [cat, det] = await Promise.all([
        api.get<{ capacidades: Capacidad[] }>("/agentes/db/capacidades/catalogo"),
        api.get<{ activas: string[] }>(`/agentes/db/${propio.id}`),
      ]);
      setCatalogo(cat.capacidades);
      setCapsActivas(det.activas);
      const canalId = CANAL_POR_AUDIENCIA[propio.audiencia] || "chat_interno";
      api.get<{ ajuste: CanalAjuste | null }>(`/agentes/db/${propio.id}/canal/${canalId}`)
        .then((r) => r.ajuste && setCanal(r.ajuste));
    })();
  }, [id, conv]);

  const persona = (ajustes.persona as Dict) || {};
  const setPersona = (k: string, v: unknown) => setAjustes((a) => ({ ...a, persona: { ...((a.persona as Dict) || {}), [k]: v } }));

  async function toggleAgente() {
    const r = await api.patch<{ ok: boolean; estado: Estado }>(`/agentes/${id}/config`, { activa: !estadoLocal?.activa });
    if (r.ok) setEstadoLocal(r.estado);
  }
  async function guardar() {
    if (!conv) return;
    setGuardando(true);
    try {
      const cur = await api.get<{ valores: Record<string, unknown> }>(`/config?sistema=${conv.sistemaConfig}`);
      const base = (cur.valores?.[conv.claveConfig] as Dict) || {};
      await api.put("/config", { clave: conv.claveConfig, valor: { ...base, persona }, sistema: conv.sistemaConfig });
      setAviso("Guardado ✓"); setTimeout(() => setAviso(""), 2200);
    } finally { setGuardando(false); }
  }
  async function enviar() {
    if (!conv?.endpointChat) return;
    const texto = entrada.trim();
    if (!texto || enviando) return;
    const historial = turnos.map((t) => ({ role: t.propio ? "user" : "assistant", content: t.texto }));
    setTurnos((t) => [...t, { propio: true, texto }]); setEntrada(""); setEnviando(true);
    try {
      const r = await api.post<{ ok: boolean; respuesta?: string }>(conv.endpointChat, { agente: id, texto, historial });
      setTurnos((t) => [...t, { propio: false, texto: r.ok ? (r.respuesta || "") : "No disponible ahora mismo." }]);
    } catch { setTurnos((t) => [...t, { propio: false, texto: "Error de conexión." }]); }
    finally { setEnviando(false); }
  }
  async function enviarCorreccion(indiceRespuesta: number) {
    const correccion = textoCorreccion.trim();
    if (!correccion) return;
    const previa = turnos[indiceRespuesta - 1];
    const propuesta = turnos[indiceRespuesta];
    await api.post("/comunicacion/agente/chat/corregir", {
      agente: id, entrada: previa?.texto ?? "", propuesta: propuesta.texto, correccion,
    });
    setTurnos((t) => t.map((x, i) => (i === indiceRespuesta ? { ...x, corregido: true } : x)));
    setCorrigiendo(null); setTextoCorreccion("");
  }
  function toggleCapacidad(clave: string) {
    setCapsActivas((c) => (c.includes(clave) ? c.filter((k) => k !== clave) : [...c, clave]));
  }
  async function guardarCapacidades() {
    if (!dbAgente) return;
    setGuardandoAvanzado("capacidades");
    try {
      await api.post(`/agentes/db/${dbAgente.id}/capacidades`, { claves: capsActivas });
      setAviso("Guardado ✓"); setTimeout(() => setAviso(""), 2200);
    } finally { setGuardandoAvanzado(""); }
  }
  async function guardarCanal() {
    if (!dbAgente) return;
    setGuardandoAvanzado("canal");
    try {
      const canalId = CANAL_POR_AUDIENCIA[dbAgente.audiencia] || "chat_interno";
      await api.post(`/agentes/db/${dbAgente.id}/canal/${canalId}`, canal);
      setAviso("Guardado ✓"); setTimeout(() => setAviso(""), 2200);
    } finally { setGuardandoAvanzado(""); }
  }
  async function guardarProgramacion(modo: string, programacion: Dict | null) {
    if (!dbAgente) return;
    const r = await api.patch<AgenteDb>(`/agentes/db/${dbAgente.id}`, { modo_activacion: modo, programacion });
    setDbAgente(r);
    setAviso("Guardado ✓"); setTimeout(() => setAviso(""), 2200);
  }
  function añadirLimite() {
    const t = nuevoLimite.trim();
    if (!t) return;
    setLimites((xs) => [...xs, t]);
    setNuevoLimite("");
  }
  async function guardarLimites() {
    setGuardandoAvanzado("limites");
    try {
      const r = await api.patch<{ ok: boolean; motivo?: string }>(`/agentes/${id}/config`,
        { limites_texto: limites.map((x) => x.trim()).filter(Boolean) });
      setAviso(r.ok ? "Guardado ✓" : (r.motivo || "No se pudo guardar"));
      setTimeout(() => setAviso(""), r.ok ? 2200 : 4500);
    } finally { setGuardandoAvanzado(""); }
  }
  function togglePermisoApp(codigo: string) {
    setPermisosApp((p) => (p.includes(codigo) ? p.filter((x) => x !== codigo) : [...p, codigo]));
  }
  async function guardarPermisosApp() {
    setGuardandoAvanzado("permisos");
    try {
      const r = await api.patch<{ ok: boolean; motivo?: string }>(`/agentes/${id}/config`,
        { permisos_requiere: permisosApp });
      setAviso(r.ok ? "Guardado ✓" : (r.motivo || "No se pudo guardar"));
      setTimeout(() => setAviso(""), r.ok ? 2200 : 4500);
    } finally { setGuardandoAvanzado(""); }
  }

  if (!ficha) return null;
  const Icono = pet.icono;
  const entrenamientoReal = conv?.endpointChat === "/comunicacion/agente/chat";

  return (
    <div className="flex-1 flex flex-col gap-2.5">
      {aviso && <div className="fixed top-14 right-6 z-50 bg-[#2DD9C3] text-[#1500A0] text-[12px] font-semibold px-4 py-2.5 rounded-sm shadow-lg">{aviso}</div>}

      <ClinicalCard>
        <div className="flex items-center justify-between mb-1.5 pb-1.5 border-b border-[#e5e7eb]">
          <div className="flex items-center gap-2">
            {onCerrar && <button onClick={onCerrar} className="text-slate-400 hover:text-[#1500A0] transition-colors" aria-label="Volver"><ArrowLeft className="w-4 h-4" /></button>}
            <div className="w-6 h-6 rounded-full overflow-hidden bg-white flex items-center justify-center p-0.5">
              <Icono className="w-3.5 h-3.5" style={{ color: pet.color }} />
            </div>
            <div>
              <h2 className="text-[12px] font-semibold text-[#1500A0] uppercase tracking-wide leading-tight">{ficha.nombre}</h2>
              <p className="text-[10.5px] text-slate-400 leading-tight">{GRUPO[id]}</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <InsigniaEstado estado={estadoLocal} />
            <button onClick={toggleAgente} className={`w-9 h-5 rounded-full relative transition-colors ${estadoLocal?.activa ? "" : "bg-slate-200"}`}
              style={estadoLocal?.activa ? { background: pet.color } : {}}>
              <span className="absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all shadow-sm" style={{ left: estadoLocal?.activa ? 18 : 2 }} />
            </button>
          </div>
        </div>
        <p className={`${DESC} mb-2`}>{ficha.parcela}</p>
        <div className="flex gap-8 pt-2 border-t border-[#f0f2f5]">
          <div>
            <span className={LABEL}>Modelo</span>
            <span className="text-[12px] text-[#1500A0]">{estadoLocal?.modelo ?? ficha.modelo}</span>
          </div>
          <div>
            <span className={LABEL}>Conexión</span>
            <span className="text-[12px] text-[#1500A0]">{estadoLocal?.baseUrl || <span className="text-slate-400">Sin conexión activa</span>}</span>
          </div>
        </div>
      </ClinicalCard>

      {conv && (
        <div className={`grid grid-cols-1 ${conv.endpointChat ? "md:grid-cols-2" : ""} gap-2.5`}>
          {conv.endpointChat && (
            <ClinicalCard>
              <SectionHeader title={entrenamientoReal ? "Chat de entrenamiento" : "Chat de prueba"} icon={MessageSquareText} />
              <div className="h-52 overflow-y-auto bg-[#FFFFFF] border border-[#e5e7eb] rounded-sm p-2.5 mb-2.5 flex flex-col gap-2">
                {turnos.length === 0 && !enviando && (
                  <p className={`${EMPTY} m-auto`}>Escribe algo para probar a {ficha.nombre}.</p>
                )}
                {turnos.map((t, i) => (
                  <div key={i} className={`max-w-[85%] ${t.propio ? "self-end" : "self-start"}`}>
                    <div className={`text-[12px] leading-snug px-3 py-2 rounded-sm ${t.propio ? "bg-white border border-[#e5e7eb]" : "text-white"}`}
                      style={t.propio ? {} : { background: pet.color }}>{t.texto}</div>
                    {entrenamientoReal && !t.propio && (
                      t.corregido ? (
                        <p className="text-[10px] text-slate-400 mt-0.5">Corrección guardada ✓</p>
                      ) : corrigiendo === i ? (
                        <div className="mt-1 flex gap-1.5">
                          <input className={INPUT} value={textoCorreccion} onChange={(e) => setTextoCorreccion(e.target.value)}
                            placeholder="¿Cómo debería haber respondido?" />
                          <ClinicalButton variant="save" onClick={() => enviarCorreccion(i)} disabled={!textoCorreccion.trim()}>Guardar</ClinicalButton>
                        </div>
                      ) : (
                        <button onClick={() => { setCorrigiendo(i); setTextoCorreccion(""); }}
                          className="text-[10px] text-slate-400 hover:text-[#1500A0] mt-0.5 underline">Corregir</button>
                      )
                    )}
                  </div>
                ))}
                {enviando && <p className={`${EMPTY} self-start`}>…</p>}
              </div>
              <div className="flex gap-2">
                <input className={INPUT} value={entrada} onChange={(e) => setEntrada(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && enviar()} placeholder="Mensaje de prueba" />
                <ClinicalButton onClick={enviar} disabled={enviando || !entrada.trim()}>Enviar</ClinicalButton>
              </div>
            </ClinicalCard>
          )}
          <ClinicalCard>
            <SectionHeader title="Personalidad" icon={Sliders} />
            <div className="grid grid-cols-3 gap-2.5 mb-2.5">
              {(["cercania", "proactividad", "formalidad"] as const).map((campo) => (
                <div key={campo} className="col-span-1">
                  <label className={LABEL}>{campo[0].toUpperCase() + campo.slice(1)} · {Number(persona[campo] ?? 3)}</label>
                  <input type="range" min={0} max={5} value={Number(persona[campo] ?? 3)}
                    onChange={(e) => setPersona(campo, Number(e.target.value))} className="w-full" style={{ accentColor: pet.color }} />
                </div>
              ))}
            </div>
            <label className={LABEL}>Tono / instrucciones</label>
            <textarea className={TEXTAREA} rows={2} value={String(persona.tono ?? "")} onChange={(e) => setPersona("tono", e.target.value)} />
            <div className="grid grid-cols-2 gap-2.5 my-2.5">
              <div><label className={LABEL}>Bienvenida</label>
                <input className={INPUT} value={String(persona.bienvenida ?? "")} onChange={(e) => setPersona("bienvenida", e.target.value)} /></div>
              <div><label className={LABEL}>Despedida</label>
                <input className={INPUT} value={String(persona.despedida ?? "")} onChange={(e) => setPersona("despedida", e.target.value)} /></div>
            </div>
            <ClinicalButton variant="save" onClick={guardar} disabled={guardando}>{guardando ? "Guardando…" : "Guardar"}</ClinicalButton>
          </ClinicalCard>
        </div>
      )}

      {conv && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
          <ClinicalCard>
            <SectionHeader title="Límites" icon={ScrollText} />
            <p className={`${DESC} mb-2.5`}>
              Lo que {ficha.nombre} nunca puede hacer. Entra en su prompt tal cual y manda sobre lo que pida cualquiera en la conversación.
            </p>
            <div className="flex flex-col gap-1.5 mb-2.5 max-h-56 overflow-y-auto">
              {limites.map((l, i) => (
                <div key={i} className="flex gap-1.5">
                  <input className={INPUT} value={l}
                    onChange={(e) => setLimites((xs) => xs.map((x, j) => (j === i ? e.target.value : x)))} />
                  <button onClick={() => setLimites((xs) => xs.filter((_, j) => j !== i))}
                    aria-label="Quitar límite"
                    className="shrink-0 w-7 border border-[#e5e7eb] rounded-sm text-slate-400 hover:text-[#1500A0] hover:border-[#1ca0d1] transition-colors">×</button>
                </div>
              ))}
              {limites.length === 0 && <p className={EMPTY}>Sin límites configurados: solo aplicaría el prompt base.</p>}
            </div>
            <div className="flex gap-2">
              <input className={INPUT} value={nuevoLimite} onChange={(e) => setNuevoLimite(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && añadirLimite()} placeholder="Añadir un límite…" />
              <ClinicalButton variant="nuevo" onClick={añadirLimite} disabled={!nuevoLimite.trim()}>Añadir</ClinicalButton>
            </div>
            <div className="mt-2.5">
              <ClinicalButton variant="save" onClick={guardarLimites} disabled={guardandoAvanzado === "limites"}>
                {guardandoAvanzado === "limites" ? "Guardando…" : "Guardar"}
              </ClinicalButton>
            </div>
          </ClinicalCard>

          <ClinicalCard>
            <SectionHeader title="Permisos de la app" icon={KeyRound} />
            <p className={`${DESC} mb-2.5`}>
              Casillas de permisos que la app concede a {ficha.nombre}. Sin su permiso, las herramientas que lo exigen quedan cortadas de verdad (no se ofrecen ni se ejecutan).
            </p>
            <div className="flex flex-col gap-1.5 mb-2.5 max-h-56 overflow-y-auto">
              {filasPermisos.map((p) => (
                <label key={p.codigo} className="flex items-start gap-2 text-[12px] text-slate-700 cursor-pointer">
                  <input type="checkbox" className="mt-0.5" checked={permisosApp.includes(p.codigo)}
                    onChange={() => togglePermisoApp(p.codigo)} style={{ accentColor: pet.color }} />
                  <span><span className="font-medium">{p.codigo}</span>{p.descripcion ? ` — ${p.descripcion}` : ""}</span>
                </label>
              ))}
              {filasPermisos.length === 0 && <p className={EMPTY}>Sin catálogo de permisos todavía.</p>}
            </div>
            <ClinicalButton variant="save" onClick={guardarPermisosApp} disabled={guardandoAvanzado === "permisos"}>
              {guardandoAvanzado === "permisos" ? "Guardando…" : "Guardar"}
            </ClinicalButton>
          </ClinicalCard>
        </div>
      )}

      {id === "aura" && (
        <p className="text-[11px] text-[#7f8c8d]">
          El PIN de escritura de Aura no se fija en esta ficha: se fija en la tarjeta <b>PIN de escritura</b>, arriba —
          solo el dueño del sistema lo cambia, y desde ahí ella también se mira en Centinela.
        </p>
      )}

      {dbAgente && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
          <ClinicalCard>
            <SectionHeader title={tituloCapacidades ?? "Capacidades"} icon={ListChecks} />
            {catalogo.length === 0 ? (
              <p className={EMPTY}>Sin capacidades en el catálogo todavía.</p>
            ) : (
              <div className="flex flex-col gap-1.5 max-h-52 overflow-y-auto mb-2.5">
                {catalogo.map((c) => (
                  <label key={c.clave} className="flex items-start gap-2 text-[12px] text-slate-700 cursor-pointer">
                    <input type="checkbox" className="mt-0.5" checked={capsActivas.includes(c.clave)}
                      onChange={() => toggleCapacidad(c.clave)} style={{ accentColor: pet.color }} />
                    <span>{c.descripcion}</span>
                  </label>
                ))}
              </div>
            )}
            <ClinicalButton variant="save" onClick={guardarCapacidades} disabled={guardandoAvanzado === "capacidades"}>
              {guardandoAvanzado === "capacidades" ? "Guardando…" : "Guardar"}
            </ClinicalButton>
          </ClinicalCard>

          <ClinicalCard>
            <SectionHeader title={`Canal · ${CANAL_POR_AUDIENCIA[dbAgente.audiencia] || "chat_interno"}`} icon={Radio} />
            <div className="grid grid-cols-2 gap-2.5 mb-2.5">
              <div><label className={LABEL}>Longitud máxima (caracteres)</label>
                <input type="number" className={INPUT} value={canal.longitud_max ?? ""}
                  onChange={(e) => setCanal((c) => ({ ...c, longitud_max: e.target.value ? Number(e.target.value) : null }))} /></div>
              <div>
                <label className={LABEL}>Emojis</label>
                <select className={SELECT} value={canal.usa_emojis === null ? "" : canal.usa_emojis ? "si" : "no"}
                  onChange={(e) => setCanal((c) => ({ ...c, usa_emojis: e.target.value === "" ? null : e.target.value === "si" }))}>
                  <option value="">Sin preferencia</option>
                  <option value="si">Con moderación</option>
                  <option value="no">Nunca</option>
                </select>
              </div>
            </div>
            <label className={LABEL}>Ritmo de respuesta</label>
            <input className={INPUT} value={canal.ritmo ?? ""} onChange={(e) => setCanal((c) => ({ ...c, ritmo: e.target.value || null }))}
              placeholder="Ej. Respuestas cortas y directas." />
            <div className="mt-2.5">
              <ClinicalButton variant="save" onClick={guardarCanal} disabled={guardandoAvanzado === "canal"}>
                {guardandoAvanzado === "canal" ? "Guardando…" : "Guardar"}
              </ClinicalButton>
            </div>
          </ClinicalCard>

          <PanelProgramacion dbAgente={dbAgente} onGuardar={guardarProgramacion} />
        </div>
      )}
    </div>
  );
}

function PanelProgramacion({ dbAgente, onGuardar }: {
  dbAgente: AgenteDb;
  onGuardar: (modo: string, programacion: Dict | null) => void;
}) {
  const [modo, setModo] = useState(dbAgente.modo_activacion);
  const [cron, setCron] = useState(dbAgente.programacion?.cron ?? "");

  return (
    <ClinicalCard>
      <SectionHeader title="Programación" icon={Clock} />
      <label className={LABEL}>Modo de activación</label>
      <select className={SELECT} value={modo} onChange={(e) => setModo(e.target.value)}>
        <option value="manual">Solo manual (lo dispara una persona)</option>
        <option value="programado">Solo programado</option>
        <option value="ambos">Manual y programado</option>
      </select>
      {(modo === "programado" || modo === "ambos") && (
        <div className="mt-2.5">
          <label className={LABEL}>Expresión cron (ej. &quot;0 9 * * 1&quot; = lunes 9:00)</label>
          <input className={INPUT} value={cron} onChange={(e) => setCron(e.target.value)} placeholder="0 9 * * 1" />
        </div>
      )}
      <div className="mt-2.5">
        <ClinicalButton variant="save" onClick={() => onGuardar(modo, (modo === "manual") ? null : (cron.trim() ? { cron: cron.trim() } : null))}>
          Guardar
        </ClinicalButton>
      </div>
    </ClinicalCard>
  );
}
