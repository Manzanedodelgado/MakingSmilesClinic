"use client";
import { Mail, Inbox, PlugZap, Save, HardDrive, FolderTree, Server, RefreshCw } from "lucide-react";
/**
 * Config → Conectores. Editores de la clínica hacia fuera, todos sobre `integraciones`
 * (fuente de la verdad; credenciales nunca en .env). Cada editor lee de GET /configuracion/centro
 * y guarda con PUT /configuracion/centro/integracion — que REEMPLAZA el JSON entero del tipo, así
 * que donde hay credenciales que no se editan (tokens OAuth de Drive) se cargan y se conservan por
 * merge, no se pisan. Mail (SMTP+IMAP) se reubica aquí desde Clínica → Centro sin cambiar su cableado.
 */
import { useEffect, useState } from "react";
import { api } from "@/shared/lib/api";
import { ClinicalCard, SectionHeader, ClinicalButton, INPUT, LABEL, TEXTAREA } from "@/shared/components";
import { errMsg } from "@/shared/lib/errores";

type Dict = Record<string, unknown>;
type Integ = { tipo: string; nombre?: string; config: Dict };
type CentroData = { integraciones: Integ[] };
const S = (v: unknown) => (v == null ? "" : String(v));
function useFlash() {
  const [msg, setMsg] = useState<{ t: string; e?: boolean }>({ t: "" });
  const flash = (t: string, e = false) => { setMsg({ t, e }); setTimeout(() => setMsg({ t: "" }), 3000); };
  const Toast = () => msg.t ? (
    <div className={`fixed top-14 right-6 z-50 px-4 py-2.5 rounded-sm text-[12px] font-semibold shadow-lg ${msg.e ? "bg-[#C026D3] text-white" : "bg-[#2DD9C3] text-[#1500A0]"}`}>{msg.t}</div>
  ) : null;
  return { flash, Toast };
}
async function cargarIntegracion(tipo: string): Promise<Dict> {
  const x = await api.get<CentroData>("/configuracion/centro");
  return { ...(x.integraciones.find((i) => i.tipo === tipo)?.config || {}) };
}
function Field({ label, value, onChange, ph, secret }: { label: string; value: string; onChange: (v: string) => void; ph?: string; secret?: boolean }) {
  return (
    <div>
      <label className={LABEL}>{label}</label>
      <input type={secret ? "password" : "text"} value={value} placeholder={ph} onChange={(e) => onChange(e.target.value)} className={INPUT} />
    </div>
  );
}

/* ───────────────────────────── MAIL (SMTP saliente + Gmail IMAP) ───────────────────────────── */
export function ConectorMail() {
  const { flash, Toast } = useFlash();
  const [smtp, setSmtp] = useState<Dict>({});
  const [imap, setImap] = useState<Dict>({});
  const [imapTest, setImapTest] = useState<{ ok: boolean; msg: string } | null>(null);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);

  async function load() {
    setSmtp(await cargarIntegracion("email_saliente"));
    // IMAP: fuente real GmailIngestService (mismas claves que gmail_imap.py), no el genérico.
    try { const im = await api.get<{ activo: boolean; config: Dict }>("/gestoria/email-imap/config"); setImap({ ...im.config, activo: im.activo }); }
    catch { /* sin permiso de Gestoría: deja la tarjeta vacía, no rompe el resto */ }
  }
  useEffect(() => { load(); }, []);

  async function probarImap() {
    setTesting(true); setImapTest(null);
    try { const r = await api.post<{ ok: boolean; error?: string; cuenta?: string }>("/gestoria/email-imap/test", {});
      setImapTest({ ok: r.ok, msg: r.ok ? `Conexión OK · ${r.cuenta}` : (r.error || "Fallo de conexión") }); }
    catch (e) { setImapTest({ ok: false, msg: errMsg(e) }); }
    finally { setTesting(false); }
  }
  async function guardar() {
    setSaving(true);
    try {
      await api.put("/configuracion/centro/integracion", { tipo: "email_saliente", nombre: "Email saliente", config: smtp });
      // IMAP: PUT dedicado (merge campo a campo). El genérico borraría la credencial real.
      const imapBody: Dict = {};
      if (imap.usuario) imapBody.usuario = imap.usuario;
      if (imap.host) imapBody.host = imap.host;
      if (imap.port) imapBody.port = Number(imap.port);
      if (imap.carpeta) imapBody.carpeta = imap.carpeta;
      if (imap.password) imapBody.password = imap.password;
      if (Object.keys(imapBody).length) await api.put("/gestoria/email-imap/config", imapBody);
      flash("Configuración de correo guardada ✓");
      load();
    } catch (e) { flash(errMsg(e), true); } finally { setSaving(false); }
  }

  return (
    <div className="flex-1 flex flex-col gap-2.5">
      <Toast />
      <div className="grid grid-cols-2 gap-2.5 items-start">
        <ClinicalCard className="!p-3">
          <SectionHeader title="Email saliente (SMTP)" icon={Mail} className="!mb-2 !pb-1.5" />
          <div className="grid grid-cols-2 gap-2">
            <Field label="Remitente" ph="Clínica Rubio" value={S(smtp.remitente)} onChange={(v) => setSmtp({ ...smtp, remitente: v })} />
            <Field label="Dirección" ph="noreply@…" value={S(smtp.direccion)} onChange={(v) => setSmtp({ ...smtp, direccion: v })} />
            <Field label="Responder a" ph="info@…" value={S(smtp.responder_a)} onChange={(v) => setSmtp({ ...smtp, responder_a: v })} />
            <Field label="SMTP host" ph="smtp.gmail.com" value={S(smtp.smtp_host)} onChange={(v) => setSmtp({ ...smtp, smtp_host: v })} />
            <Field label="Puerto" ph="587" value={S(smtp.puerto)} onChange={(v) => setSmtp({ ...smtp, puerto: v })} />
            <Field label="Usuario" ph="noreply@…" value={S(smtp.usuario)} onChange={(v) => setSmtp({ ...smtp, usuario: v })} />
            <div className="col-span-2"><Field label="Password" secret ph="••••" value={S(smtp.password)} onChange={(v) => setSmtp({ ...smtp, password: v })} /></div>
          </div>
        </ClinicalCard>

        <ClinicalCard className="!p-3">
          <SectionHeader title="Gmail IMAP — Facturas" icon={Inbox} className="!mb-2 !pb-1.5"
            action={<ClinicalButton variant="accent" icon={PlugZap} size="sm" onClick={probarImap} disabled={testing}>{testing ? "Probando…" : "Probar conexión"}</ClinicalButton>} />
          <div className="grid grid-cols-2 gap-2">
            <Field label="Email Gmail (usuario)" ph="clinica@gmail.com" value={S(imap.usuario)} onChange={(v) => setImap({ ...imap, usuario: v })} />
            <Field label="App Password" secret ph={imap.usuario ? "•••••••• (en blanco = no cambiar)" : "xxxx xxxx"} value={S(imap.password)} onChange={(v) => setImap({ ...imap, password: v })} />
            <Field label="Servidor IMAP" ph="imap.gmail.com" value={S(imap.host)} onChange={(v) => setImap({ ...imap, host: v })} />
            <Field label="Puerto IMAP" ph="993" value={S(imap.port)} onChange={(v) => setImap({ ...imap, port: v })} />
            <div className="col-span-2"><Field label="Carpeta a procesar" ph="Facturas" value={S(imap.carpeta)} onChange={(v) => setImap({ ...imap, carpeta: v })} /></div>
          </div>
          {imapTest && <p className={`mt-1.5 text-[11px] font-semibold ${imapTest.ok ? "text-[#0F8C7D]" : "text-[#C026D3]"}`}>{imapTest.ok ? "✓ " : "✗ "}{imapTest.msg}</p>}
        </ClinicalCard>
      </div>
      <div className="flex justify-end">
        <ClinicalButton variant="save" icon={Save} onClick={guardar} disabled={saving}>{saving ? "Guardando…" : "Guardar cambios"}</ClinicalButton>
      </div>
    </div>
  );
}

/* ───────────────────────────── DRIVE (Google Drive — credenciales + carpetas) ───────────────────────────── */
export function ConectorDrive() {
  const { flash, Toast } = useFlash();
  const [cfg, setCfg] = useState<Dict>({});   // config COMPLETA (no se pisan otras claves al guardar)
  const [saJson, setSaJson] = useState("");   // JSON NUEVO de cuenta de servicio → se convierte a sa_b64
  const [saving, setSaving] = useState(false);
  const carpetas = (cfg.carpetas as Dict) || {};
  const setCarpeta = (k: string, v: string) => setCfg((c) => ({ ...c, carpetas: { ...((c.carpetas as Dict) || {}), [k]: v } }));
  const set = (k: string, v: string) => setCfg((c) => ({ ...c, [k]: v }));
  const tieneToken = !!(cfg.sa_b64 || (cfg.refresh_token && cfg.client_id));
  const puedeLeer = tieneToken || !!cfg.api_key;

  useEffect(() => { cargarIntegracion("google_drive").then(setCfg); }, []);

  async function guardar() {
    setSaving(true);
    try {
      const base: Dict = { ...cfg };
      if (saJson.trim()) {                       // convierte el JSON pegado a base64 (sa_b64)
        try { base.sa_b64 = btoa(unescape(encodeURIComponent(saJson.trim()))); }
        catch { flash("El JSON de la cuenta de servicio no es válido", true); setSaving(false); return; }
      }
      await api.put("/configuracion/centro/integracion", { tipo: "google_drive", nombre: "Google Drive", config: base });
      setCfg(base); setSaJson("");
      flash("Google Drive guardado ✓");
    } catch (e) { flash(errMsg(e), true); } finally { setSaving(false); }
  }

  return (
    <div className="flex-1 flex flex-col gap-2.5">
      <Toast />
      {/* Estado + carpetas */}
      <ClinicalCard>
        <SectionHeader title="Google Drive" icon={HardDrive}
          action={<span className={`text-[11px] font-semibold px-2 py-0.5 rounded-sm ${tieneToken ? "bg-[#FFFFFF] text-[#0F8C7D]" : puedeLeer ? "bg-[#FFFFFF] text-[#6D28D9]" : "bg-[#FFFFFF] text-[#64748b]"}`}>{tieneToken ? "Conectado (lectura + escritura)" : puedeLeer ? "Solo lectura (API key)" : "Sin conectar"}</span>} />
        <p className="text-[11px] text-[#7f8c8d] mb-3">Fotos y radiografías de la ficha se sirven por proxy desde Drive. Fija las carpetas raíz y las credenciales para conectar.</p>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Carpeta PACIENTES (ID)" ph="1AbC…" value={S(carpetas.pacientes)} onChange={(v) => setCarpeta("pacientes", v)} />
          <Field label="Carpeta FACTURAS (ID)" ph="1XyZ…" value={S(carpetas.facturas)} onChange={(v) => setCarpeta("facturas", v)} />
        </div>
        <div className="flex items-center gap-1.5 mt-3 text-[11px] text-[#7f8c8d]">
          <FolderTree className="w-3.5 h-3.5 text-[#1ca0d1]" />
          Estructura esperada: PACIENTES/&#123;nº historia — APELLIDOS, Nombre&#125;/&#123;Imágenes, RX&#125;
        </div>
      </ClinicalCard>

      {/* Credencial recomendada: cuenta de servicio */}
      <ClinicalCard>
        <SectionHeader title="Conexión · Cuenta de servicio (recomendado)" icon={HardDrive}
          action={cfg.sa_b64 ? <span className="text-[11px] font-semibold px-2 py-0.5 rounded-sm bg-[#FFFFFF] text-[#0F8C7D]">Configurada</span> : undefined} />
        <p className="text-[11px] text-[#7f8c8d] mb-2">Pega el JSON de la cuenta de servicio de Google Cloud (con Drive habilitado y la carpeta compartida con su email). Es lo más estable: no caduca como el OAuth. {cfg.sa_b64 ? "Ya hay una configurada; pega un JSON nuevo solo si quieres reemplazarla." : ""}</p>
        <textarea rows={4} spellCheck={false} className={`${TEXTAREA} font-mono text-[11px]`} placeholder={'{ "type": "service_account", "client_email": "...", "private_key": "..." }'} value={saJson} onChange={(e) => setSaJson(e.target.value)} />
      </ClinicalCard>

      {/* Alternativa: OAuth */}
      <ClinicalCard>
        <SectionHeader title="Conexión · OAuth (alternativa)" icon={HardDrive} />
        <div className="grid grid-cols-2 gap-3">
          <Field label="Client ID" value={S(cfg.client_id)} onChange={(v) => set("client_id", v)} />
          <Field label="Client Secret" secret value={S(cfg.client_secret)} onChange={(v) => set("client_secret", v)} />
          <div className="col-span-2"><Field label="Refresh token" secret value={S(cfg.refresh_token)} onChange={(v) => set("refresh_token", v)} /></div>
        </div>
      </ClinicalCard>

      {/* Solo lectura: API key */}
      <ClinicalCard>
        <SectionHeader title="Conexión · API key (solo lectura)" icon={HardDrive} />
        <p className="text-[11px] text-[#7f8c8d] mb-2">Para leer carpetas compartidas por enlace, sin escritura.</p>
        <Field label="API key" secret value={S(cfg.api_key)} onChange={(v) => set("api_key", v)} />
      </ClinicalCard>

      <div className="flex justify-end">
        <ClinicalButton variant="save" icon={Save} onClick={guardar} disabled={saving}>{saving ? "Guardando…" : "Guardar"}</ClinicalButton>
      </div>
    </div>
  );
}

/* ───────────────────────────── RADIOGRAFÍAS (Orthanc / PACS) ───────────────────────────── */
export function ConectorRadiografias() {
  const { flash, Toast } = useFlash();
  const [cfg, setCfg] = useState<Dict>({});
  const [saving, setSaving] = useState(false);
  useEffect(() => { cargarIntegracion("orthanc").then(setCfg); }, []);

  async function guardar() {
    setSaving(true);
    try { await api.put("/configuracion/centro/integracion", { tipo: "orthanc", nombre: "Orthanc (PACS)", config: cfg });
      flash("Servidor de radiografías guardado ✓"); }
    catch (e) { flash(errMsg(e), true); } finally { setSaving(false); }
  }
  return (
    <div className="flex-1 flex flex-col gap-2.5">
      <Toast />
      <ClinicalCard>
        <SectionHeader title="Servidor de radiografías (Orthanc / PACS)" icon={Server}
          action={<span className={`text-[11px] font-semibold px-2 py-0.5 rounded-sm ${cfg.url ? "bg-[#FFFFFF] text-[#0F8C7D]" : "bg-[#FFFFFF] text-[#64748b]"}`}>{cfg.url ? "Configurado" : "Sin configurar"}</span>} />
        <p className="text-[11px] text-[#7f8c8d] mb-3">Servidor DICOM que alimenta las Panorámicas de la ficha (cruce por <code className="font-mono">PatientID == nº historia</code>).</p>
        <div className="grid grid-cols-2 gap-3">
          <Field label="URL Orthanc" ph="http://localhost:8042" value={S(cfg.url)} onChange={(v) => setCfg({ ...cfg, url: v })} />
          <Field label="Campo PatientID" ph="num_historia" value={S(cfg.patient_id_field)} onChange={(v) => setCfg({ ...cfg, patient_id_field: v })} />
          <Field label="Usuario" value={S(cfg.username)} onChange={(v) => setCfg({ ...cfg, username: v })} />
          <Field label="Contraseña" secret value={S(cfg.password)} onChange={(v) => setCfg({ ...cfg, password: v })} />
        </div>
        <div className="flex justify-end mt-3">
          <ClinicalButton variant="save" icon={Save} onClick={guardar} disabled={saving}>{saving ? "Guardando…" : "Guardar"}</ClinicalButton>
        </div>
      </ClinicalCard>
    </div>
  );
}

/* ───────────────────────────── SERVIDOR (la máquina que aloja TODA la app) ───────────────────────────── */
// NO es el PACS de radiografías (eso es "Radiografías"). Es el servidor donde viven web + backend + BD.
// Config en integraciones tipo="servidor": dirección, acceso remoto (SSH/Tailscale) y a qué backend apunta.
export function ConectorServidor() {
  const { flash, Toast } = useFlash();
  const [cfg, setCfg] = useState<Dict>({});
  const [saving, setSaving] = useState(false);
  const [salud, setSalud] = useState<"?" | "ok" | "ko">("?");
  const set = (k: string, v: string) => setCfg((c) => ({ ...c, [k]: v }));

  const comprobar = () => {
    setSalud("?");
    api.get("/auth/me").then(() => setSalud("ok")).catch(() => setSalud("ko"));
  };
  useEffect(() => { cargarIntegracion("servidor").then(setCfg); comprobar(); }, []);

  async function guardar() {
    setSaving(true);
    try { await api.put("/configuracion/centro/integracion", { tipo: "servidor", nombre: "Servidor (host de la app)", config: cfg });
      flash("Servidor guardado ✓"); }
    catch (e) { flash(errMsg(e), true); } finally { setSaving(false); }
  }

  return (
    <div className="flex-1 flex flex-col gap-2.5">
      <Toast />
      {/* Estado */}
      <ClinicalCard>
        <SectionHeader title="La máquina que aloja la app" icon={Server}
          action={<ClinicalButton variant="secondary" icon={RefreshCw} onClick={comprobar}>Comprobar</ClinicalButton>} />
        <p className="text-[11px] text-[#7f8c8d] mb-3">El servidor donde vive TODA la app (web, backend y base de datos). No confundir con el de radiografías.</p>
        <div className="grid grid-cols-2 gap-x-10 gap-y-1.5">
          <Row label="Aplicación">{salud === "?" ? <span className="text-[12px] text-slate-400">Comprobando…</span> : <Badge ok={salud === "ok"} />}</Row>
          <Row label="Dirección"><span className="font-mono">{S(cfg.direccion) || "—"}</span></Row>
        </div>
      </ClinicalCard>

      {/* Acceso remoto */}
      <ClinicalCard>
        <SectionHeader title="Acceso remoto (administración)" icon={Server} />
        <p className="text-[11px] text-[#7f8c8d] mb-3">Cómo entrar a la máquina para administrarla. La app no lo usa; queda registrado aquí para tenerlo a mano.</p>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Dirección / IP" ph="192.168.1.x  ·  o host público" value={S(cfg.direccion)} onChange={(v) => set("direccion", v)} />
          <Field label="IP Tailscale" ph="100.x.x.x" value={S(cfg.tailscale)} onChange={(v) => set("tailscale", v)} />
          <Field label="Usuario SSH" ph="jmd" value={S(cfg.ssh_usuario)} onChange={(v) => set("ssh_usuario", v)} />
          <Field label="Puerto SSH" ph="22" value={S(cfg.ssh_puerto)} onChange={(v) => set("ssh_puerto", v)} />
        </div>
      </ClinicalCard>

      {/* A qué máquina apunta la app */}
      <ClinicalCard>
        <SectionHeader title="A qué máquina apunta la app" icon={Server} />
        <p className="text-[11px] text-[#7f8c8d] mb-3">Dirección del backend (API) que usa la app. Si migras la app a otra máquina, cámbiala aquí; <b>surte efecto tras reiniciar/desplegar</b> (no es un cambio en caliente).</p>
        <Field label="Backend (API)" ph="http://localhost:8000" value={S(cfg.backend_origin)} onChange={(v) => set("backend_origin", v)} />
      </ClinicalCard>

      <div className="flex justify-end">
        <ClinicalButton variant="save" icon={Save} onClick={guardar} disabled={saving}>{saving ? "Guardando…" : "Guardar"}</ClinicalButton>
      </div>
    </div>
  );
}
function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between border-b border-[#f0f2f5] py-1">
      <span className={LABEL}>{label}</span>
      <span className="text-[12px] text-[#1500A0]">{children}</span>
    </div>
  );
}
function Badge({ ok }: { ok: boolean }) {
  return <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-sm ${ok ? "bg-[#FFFFFF] text-[#0F8C7D]" : "bg-[#FFFFFF] text-[#A21CAF]"}`}>{ok ? "OK" : "No"}</span>;
}
