"use client";
/**
 * Config · IA&apos;s · Canales — WhatsApp (Evolution API) + Voicebot SIP.
 * CONFIG PURA: credenciales y ajustes sobre `integraciones` (reutiliza los
 * endpoints existentes GET /configuracion/centro y PUT .../integracion). La
 * vinculación en vivo (QR/ping Evolution) y SIP real van en una 2ª fase.
 */
import { useEffect, useState } from "react";
import { Check, MessageCircle, Phone, QrCode, KeyRound, ShieldCheck, Save, Activity, RefreshCw, Send, Unlink } from "lucide-react";
import { api } from "@/shared/lib/api";
import { ClinicalCard, SectionHeader, ClinicalButton, INPUT, LABEL } from "@/shared/components";
import { errMsg } from "@/shared/lib/errores";

type Dict = Record<string, unknown>;
type Integ = { tipo: string; nombre?: string; config: Dict };
type CentroData = { integraciones: Integ[] };
const S = (v: unknown) => (v == null ? "" : String(v));

export function CanalesIA({ solo }: { solo?: "whatsapp" | "voicebot" } = {}) {
  const [canal, setCanal] = useState<"whatsapp" | "voicebot">(solo ?? "whatsapp");
  const [wa, setWa] = useState<Dict>({});
  const [sip, setSip] = useState<Dict>({});
  const [estado, setEstado] = useState<{ evolution: boolean; conectado: boolean; estado: string | null; numero?: string | null; perfil?: string | null } | null>(null);
  const [revinculando, setRevinculando] = useState(false);
  const [vbHealth, setVbHealth] = useState<{ sip_configurado: boolean; canal_activo: boolean } | null>(null);
  const [qr, setQr] = useState<string | null>(null);
  const [testPhone, setTestPhone] = useState("");
  const [testMsg, setTestMsg] = useState("Mensaje de prueba de MakingSmiles ✅");
  const [enviando, setEnviando] = useState(false);
  const [msg, setMsg] = useState<{ t: string; e?: boolean }>({ t: "" });
  const flash = (t: string, e = false) => { setMsg({ t, e }); setTimeout(() => setMsg({ t: "" }), 3000); };

  async function load() {
    const x = await api.get<CentroData>("/configuracion/centro");
    setWa({ ...(x.integraciones.find((i) => i.tipo === "whatsapp")?.config || {}) });
    setSip({ ...(x.integraciones.find((i) => i.tipo === "voicebot_sip")?.config || {}) });
  }
  const cargarEstado = () =>
    api.get<{ evolution: boolean; conectado: boolean; estado: string | null; numero?: string | null; perfil?: string | null }>("/comunicacion/whatsapp/estado")
      .then(setEstado).catch(() => setEstado(null));
  useEffect(() => {
    load();
    cargarEstado();
    api.get<{ sip_configurado: boolean; canal_activo: boolean }>("/comunicacion/voicebot/health")
      .then(setVbHealth).catch(() => setVbHealth(null));
  }, []);

  async function guardar(tipo: string, nombre: string, config: Dict) {
    try { await api.put("/configuracion/centro/integracion", { tipo, nombre, config }); flash("Guardado ✓"); load(); }
    catch (e) { flash(errMsg(e), true); }
  }
  async function obtenerQr() {
    try { const r = await api.get<{ qrcode: string | null }>("/comunicacion/whatsapp/qr"); setQr(r.qrcode); if (!r.qrcode) flash("Instancia ya vinculada o sin QR"); }
    catch (e) { flash(errMsg(e), true); }
  }
  // Re-vincular OTRO teléfono: cierra la sesión actual (logout) y saca un QR nuevo. Al
  // escanearlo, el número queda enlazado y el webhook se reasegura solo. El historial NO
  // se importa: WhatsApp multidispositivo solo sincroniza una ventana reciente (límite de WhatsApp).
  async function revincular() {
    if (revinculando) return;
    if (estado?.conectado && !window.confirm(
      "Se cerrará la sesión de WhatsApp actual para enlazar otro teléfono. El historial antiguo no se importa. ¿Continuar?")) return;
    setRevinculando(true);
    try {
      if (estado?.conectado) {
        const r = await api.post<{ ok: boolean; error?: string }>("/comunicacion/whatsapp/desvincular", {});
        if (!r.ok) throw new Error(r.error || "No se pudo desvincular");
      }
      await new Promise((res) => setTimeout(res, 800));   // deja a Baileys cerrar la sesión
      await obtenerQr();
      cargarEstado();
      flash("Escanea el QR con el nuevo teléfono");
    } catch (e) { flash(errMsg(e), true); }
    finally { setRevinculando(false); }
  }
  async function enviarPrueba() {
    if (!testPhone.trim() || !testMsg.trim() || enviando) return;
    setEnviando(true);
    try { await api.post("/comunicacion/whatsapp/enviar", { telefono: testPhone.trim(), texto: testMsg.trim() }); flash("Mensaje enviado ✓"); }
    catch (e) { flash(errMsg(e), true); }
    finally { setEnviando(false); }
  }

  return (
    <div className="flex-1">
      {msg.t && (
        <div className={`fixed top-14 right-6 z-50 px-4 py-2.5 rounded-sm text-[12px] font-semibold shadow-lg ${msg.e ? "bg-[#C026D3] text-white" : "bg-[#2DD9C3] text-[#1500A0]"}`}>{msg.t}</div>
      )}

      {/* selector de canal — oculto si el canal viene fijado desde fuera */}
      {!solo && (
        <div className="flex items-center gap-0 border-b border-[#e5e7eb] mb-4">
          {([["whatsapp", "WhatsApp", MessageCircle], ["voicebot", "Voicebot SIP", Phone]] as const).map(([id, label, Icon]) => (
            <button
              key={id}
              onClick={() => setCanal(id)}
              className={`flex items-center gap-1.5 px-3 py-2 text-[12px] font-semibold uppercase tracking-wider border-b-2 transition-colors ${
                canal === id ? "text-[#1500A0] border-[#1ca0d1]" : "text-[#7f8c8d] border-transparent hover:text-[#1500A0]"
              }`}
            >
              <Icon className="w-3.5 h-3.5" /> {label}
            </button>
          ))}
        </div>
      )}

      {canal === "whatsapp" ? (
        <div className="grid grid-cols-2 gap-2.5">
          {/* Estado de la conexión */}
          <ClinicalCard className="col-span-2">
            <SectionHeader title="Estado" icon={Activity}
              action={<ClinicalButton variant="secondary" icon={RefreshCw} onClick={cargarEstado}>Actualizar</ClinicalButton>} />
            <div className="grid grid-cols-2 gap-x-10 gap-y-1.5">
              <StatusRow label="Conexión">
                <span className={`text-[12px] font-semibold ${estado?.conectado ? "text-[#0F8C7D]" : "text-[#6D28D9]"}`}>{estado?.conectado ? "Conectado" : "Desconectado"}</span>
              </StatusRow>
              <StatusRow label="WhatsApp">{estado ? (estado.estado === "open" ? "Vinculado" : estado.estado === "connecting" ? "Esperando QR" : estado.estado || "—") : "—"}</StatusRow>
              <StatusRow label="Número conectado"><span className="font-mono">{estado?.numero || "—"}</span>{estado?.perfil ? <span className="text-[#7f8c8d]"> · {estado.perfil}</span> : null}</StatusRow>
              <StatusRow label="Instancia"><span className="font-mono">{S(wa.instancia) || "—"}</span></StatusRow>
              <StatusRow label="Evolution"><EstadoBadge ok={!!estado?.evolution} /></StatusRow>
            </div>
          </ClinicalCard>

          {/* Vincular WhatsApp */}
          <ClinicalCard className="col-span-2">
            <SectionHeader title="Vincular WhatsApp" icon={QrCode}
              action={<span className={`text-[11px] font-semibold px-2 py-0.5 rounded-sm ${estado?.conectado ? "bg-[#FFFFFF] text-[#0F8C7D]" : estado?.evolution ? "bg-[#FFFFFF] text-[#6D28D9]" : "bg-[#FFFFFF] text-[#64748b]"}`}>
                {estado?.conectado ? "Conectado" : estado?.evolution ? (estado.estado || "Sin vincular") : "No configurado"}
              </span>} />
            <div className="flex items-start gap-4">
              <div className="flex flex-col gap-2">
                <ClinicalButton variant="accent" icon={QrCode} disabled={!estado?.evolution} onClick={obtenerQr}>Obtener QR</ClinicalButton>
                <ClinicalButton variant="secondary" icon={Unlink} disabled={!estado?.evolution || revinculando}
                  onClick={revincular}>{revinculando ? "Procesando…" : estado?.conectado ? "Cambiar de teléfono" : "Vincular otro teléfono"}</ClinicalButton>
                <p className="text-[11px] text-[#7f8c8d] leading-relaxed max-w-[280px]">
                  Guarda primero las credenciales. Pulsa «Obtener QR» y escanéalo desde WhatsApp &gt; Dispositivos vinculados.
                  Para enlazar <b>otro número</b>, usa «Cambiar de teléfono»: cierra la sesión actual y genera un QR nuevo.
                  El historial antiguo no se importa (límite de WhatsApp).
                </p>
              </div>
              {qr && (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={qr.startsWith("data:") ? qr : `data:image/png;base64,${qr}`} alt="QR WhatsApp" className="h-44 w-44 border border-[#e5e7eb] rounded-sm" />
              )}
            </div>
          </ClinicalCard>

          {/* Credenciales Evolution */}
          <ClinicalCard className="col-span-2">
            <SectionHeader title="Credenciales Evolution API" icon={KeyRound} />
            <div className="grid grid-cols-3 gap-3">
              <Field label="Instancia" ph="chatwoot_link" value={S(wa.instancia)} onChange={(v) => setWa({ ...wa, instancia: v })} />
              <Field label="API Key" secret value={S(wa.api_key)} onChange={(v) => setWa({ ...wa, api_key: v })} />
              <Field label="Webhook HMAC" secret value={S(wa.webhook_hmac || wa.webhook_secret)} onChange={(v) => setWa({ ...wa, webhook_hmac: v })} />
              <Field label="URL API" ph="http://evolution-api:8080" value={S(wa.url_api)} onChange={(v) => setWa({ ...wa, url_api: v })} />
            </div>
            <div className="flex justify-end mt-3">
              <ClinicalButton variant="save" icon={Save} onClick={() => guardar("whatsapp", "WhatsApp (Evolution)", wa)}>Guardar</ClinicalButton>
            </div>
          </ClinicalCard>

          {/* Envío de prueba */}
          <ClinicalCard className="col-span-2">
            <SectionHeader title="Envío de prueba" icon={Send} />
            <div className="grid grid-cols-[200px_1fr_auto] gap-3 items-end">
              <div>
                <label className={LABEL}>Teléfono</label>
                <input type="tel" value={testPhone} onChange={(e) => setTestPhone(e.target.value)} placeholder="+34 600 123 456" className={INPUT} />
              </div>
              <div>
                <label className={LABEL}>Mensaje</label>
                <input type="text" value={testMsg} onChange={(e) => setTestMsg(e.target.value)} className={INPUT} />
              </div>
              <ClinicalButton variant="accent" icon={Send} disabled={enviando || !estado?.conectado || !testPhone.trim() || !testMsg.trim()} onClick={enviarPrueba}>Enviar</ClinicalButton>
            </div>
            <p className="text-[11px] text-[#7f8c8d] mt-2">
              Envía un WhatsApp real desde la clínica para verificar la conexión de extremo a extremo.
              {estado?.conectado ? "" : " Requiere WhatsApp vinculado."}
            </p>
          </ClinicalCard>

          {/* Webhooks y seguridad */}
          <ClinicalCard className="col-span-2">
            <SectionHeader title="Webhooks y seguridad" icon={ShieldCheck} />
            <div className="grid grid-cols-2 gap-2.5">
              <div className="flex flex-col gap-2">
                <Webhook titulo="Evolution → Backend (configurar en Evolution)" ruta="/comunicacion/webhook/{centro_id}?token={webhook_hmac}" />
                <p className="text-[11px] text-[#7f8c8d] leading-relaxed">Sustituye <code className="font-mono">{"{centro_id}"}</code> por el ID del centro y <code className="font-mono">{"{webhook_hmac}"}</code> por el secreto de arriba.</p>
              </div>
              <div className="flex flex-col gap-1.5 justify-center">
                <Garantia>Token de webhook validado (timing-safe)</Garantia>
                <Garantia>Credenciales solo en backend</Garantia>
                <Garantia>Mensajes auditados</Garantia>
              </div>
            </div>
          </ClinicalCard>
        </div>
      ) : (
        <ClinicalCard>
          <SectionHeader title="Voicebot SIP" icon={Phone}
            action={<span className={`text-[11px] font-semibold px-2 py-0.5 rounded-sm ${vbHealth?.canal_activo && vbHealth?.sip_configurado ? "bg-[#FFFFFF] text-[#0F8C7D]" : vbHealth?.sip_configurado ? "bg-[#FFFFFF] text-[#6D28D9]" : "bg-[#FFFFFF] text-[#64748b]"}`}>
              {vbHealth?.canal_activo && vbHealth?.sip_configurado ? "Activo" : vbHealth?.sip_configurado ? "Configurado (canal off)" : "Sin configurar"}
            </span>} />
          <p className="text-[11px] text-[#7f8c8d] mb-3">El canal de voz reutiliza el agente Alex. Actívalo en los chips de arriba (barra de IA&apos;s). La telefonía (Asterisk/SIP) se conecta a los endpoints <code className="font-mono">/comunicacion/voicebot/*</code>.</p>
          <div className="grid grid-cols-3 gap-3">
            <Field label="Servidor SIP" ph="sip.proveedor.com" value={S(sip.host)} onChange={(v) => setSip({ ...sip, host: v })} />
            <Field label="Puerto" ph="5060" value={S(sip.puerto)} onChange={(v) => setSip({ ...sip, puerto: v })} />
            <Field label="Número (DID)" ph="+34..." value={S(sip.did)} onChange={(v) => setSip({ ...sip, did: v })} />
            <Field label="Usuario" value={S(sip.usuario)} onChange={(v) => setSip({ ...sip, usuario: v })} />
            <Field label="Contraseña" secret value={S(sip.password)} onChange={(v) => setSip({ ...sip, password: v })} />
            <Field label="Dominio" ph="proveedor.com" value={S(sip.dominio)} onChange={(v) => setSip({ ...sip, dominio: v })} />
          </div>
          <div className="flex justify-end mt-3">
            <ClinicalButton variant="save" icon={Save} onClick={() => guardar("voicebot_sip", "Voicebot SIP", sip)}>Guardar</ClinicalButton>
          </div>
        </ClinicalCard>
      )}
    </div>
  );
}

function Field({ label, value, onChange, ph, secret }: { label: string; value: string; onChange: (v: string) => void; ph?: string; secret?: boolean }) {
  return (
    <div>
      <label className={LABEL}>{label}</label>
      <input type={secret ? "password" : "text"} value={value} placeholder={ph} onChange={(e) => onChange(e.target.value)} className={INPUT} />
    </div>
  );
}
function StatusRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between border-b border-[#f0f2f5] py-1">
      <span className={LABEL}>{label}</span>
      <span className="text-[12px] text-[#1500A0]">{children}</span>
    </div>
  );
}
function EstadoBadge({ ok }: { ok: boolean }) {
  return (
    <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-sm ${ok ? "bg-[#FFFFFF] text-[#0F8C7D]" : "bg-[#FFFFFF] text-[#A21CAF]"}`}>{ok ? "OK" : "No"}</span>
  );
}
function Webhook({ titulo, ruta }: { titulo: string; ruta: string }) {
  return (
    <div className="bg-[#FFFFFF] border border-[#e5e7eb] rounded-sm px-3 py-2">
      <div className="text-[11px] text-[#1ca0d1] uppercase tracking-wide font-semibold mb-0.5">{titulo}</div>
      <code className="text-[11px] text-[#1500A0] font-mono break-all">{ruta}</code>
    </div>
  );
}
function Garantia({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2 text-[12px] text-[#0F8C7D]">
      <Check className="w-4 h-4 text-[#2DD9C3]" /> {children}
    </div>
  );
}
