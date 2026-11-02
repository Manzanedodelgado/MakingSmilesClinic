"use client";
/**
 * FILIACIÓN — ficha administrativa + anamnesis del paciente. Solo BBDD nueva.
 * Campos core → PUT /pacientes/{id}; campos extra → PUT /pacientes/{id}/extra (bolsa);
 * RGPD → boolean core; tarifas → /tarifas; anamnesis → /anamnesis (catálogo en CONFIG).
 * Estética = config-styles + componentes Clinical* (fuente única, cero estilos ad-hoc).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, Activity, Camera, FileText, FolderSearch, Phone, Shield, User, Wallet } from "lucide-react";
import { ClinicalCard, SectionHeader } from "@/shared/components";
import { patientService } from "../services/patientService";
import type { AnamnesisCatalogo, Filiacion as TFiliacion } from "../types/patient";
import { CampoEdit } from "./CampoEdit";
import { Anamnesis } from "./Anamnesis";

const RGPD: { key: keyof TFiliacion; label: string }[] = [
  { key: "acepta_lopd", label: "Tratamiento datos (RGPD)" },
  { key: "acepta_whatsapp", label: "SMS / WhatsApp" },
  { key: "acepta_info", label: "Info comercial" },
  { key: "acepta_bots", label: "Asistentes / Bots" },
];

export function Filiacion({ patientId }: { patientId: number }) {
  const [fil, setFil] = useState<TFiliacion | null>(null);
  const [cat, setCat] = useState<AnamnesisCatalogo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [savingAnam, setSavingAnam] = useState(false);

  const cargar = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [f, c] = await Promise.all([patientService.filiacion(patientId), patientService.anamnesisCatalogo()]);
      setFil(f); setCat(c);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo cargar la filiación");
    } finally { setLoading(false); }
  }, [patientId]);

  useEffect(() => { cargar(); }, [cargar]);

  // Avisa a la barra superior (PatientTopBar) para que recargue la cabecera al instante.
  const notify = () => window.dispatchEvent(new CustomEvent("ms:patient-updated"));

  const saveCore = (campo: string, parse?: (v: string) => unknown) => async (v: string) => {
    await patientService.actualizar(patientId, { [campo]: parse ? parse(v) : v || null });
    setFil((p) => (p ? { ...p, [campo]: parse ? parse(v) : v } : p));
    notify();
  };
  // Facturación → tabla clientes · Seguro → tabla paciente_seguros (cada uno a su sitio).
  const saveFacturacion = (campo: string) => async (v: string) => {
    await patientService.setFacturacion(patientId, { [campo]: v });
    setFil((p) => (p ? { ...p, facturacion: { ...p.facturacion, [campo]: v } } : p));
  };
  const saveSeguro = (campo: string) => async (v: string) => {
    await patientService.setSeguro(patientId, { [campo]: v });
    setFil((p) => (p ? { ...p, seguro: { ...p.seguro, [campo]: v } } : p));
  };
  async function toggleRGPD(key: keyof TFiliacion) {
    if (!fil) return;
    const next = !fil[key];
    setFil({ ...fil, [key]: next });
    await patientService.actualizar(patientId, { [key]: next }).catch(() => setFil((p) => (p ? { ...p, [key]: !next } : p)));
  }
  async function toggleTarifa(id: number) {
    if (!fil) return;
    const cur = fil.tarifas.asignadas;
    const next = cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id];
    setFil({ ...fil, tarifas: { ...fil.tarifas, asignadas: next } });
    const r = await patientService.setTarifas(patientId, next).catch(() => null);
    if (r) setFil((p) => (p ? { ...p, tarifas: r } : p));
    notify();
  }
  // Foto de perfil: proxy autenticado (?v= como cache-bust tras subir/quitar, la URL no cambia).
  const [fotoVer, setFotoVer] = useState(0);
  const [fotoSubiendo, setFotoSubiendo] = useState(false);
  const [fotoError, setFotoError] = useState<string | null>(null);
  const [fotoMenu, setFotoMenu] = useState(false);
  const fotoInputRef = useRef<HTMLInputElement>(null);

  async function subirFoto(file: File) {
    setFotoSubiendo(true); setFotoError(null);
    try {
      await patientService.subirFoto(patientId, file);
      setFil((p) => (p ? { ...p, tiene_foto: true } : p));
      setFotoVer((v) => v + 1);
    } catch (e) {
      setFotoError(e instanceof Error ? e.message.replace(/^POST.*?→ \d+ /, "") : "No se pudo subir la foto");
    } finally { setFotoSubiendo(false); }
  }
  async function fotoDesdeDrive() {
    setFotoMenu(false); setFotoSubiendo(true); setFotoError(null);
    try {
      await patientService.fotoDesdeDrive(patientId);
      setFil((p) => (p ? { ...p, tiene_foto: true } : p));
      setFotoVer((v) => v + 1);
    } catch (e) {
      setFotoError(e instanceof Error ? e.message.replace(/^POST.*?→ \d+ /, "") : "No se encontró CARA.JPEG en Drive");
    } finally { setFotoSubiendo(false); }
  }
  async function quitarFoto() {
    if (!window.confirm("¿Quitar la foto del paciente?")) return;
    try {
      await patientService.borrarFoto(patientId);
      setFil((p) => (p ? { ...p, tiene_foto: false } : p));
      setFotoVer((v) => v + 1);
      setFotoError(null);
    } catch (e) {
      setFotoError(e instanceof Error ? e.message.replace(/^DELETE.*?→ \d+ /, "") : "No se pudo quitar la foto");
    }
  }

  async function toggleAnamnesis(item: string) {
    if (!fil) return;
    const next = fil.anamnesis.includes(item) ? fil.anamnesis.filter((x) => x !== item) : [...fil.anamnesis, item];
    setFil({ ...fil, anamnesis: next });
    setSavingAnam(true);
    const r = await patientService.setAnamnesis(patientId, next).catch(() => null);
    if (r) setFil((p) => (p ? { ...p, anamnesis: r.anamnesis } : p));
    setSavingAnam(false);
  }

  if (loading) return <p className="text-[12px] text-slate-400 p-4">Cargando filiación…</p>;
  if (error) return <p className="text-[12px] text-[#C026D3] p-4">{error}</p>;
  if (!fil) return null;

  return (
    <div className="h-full pl-2 pr-4 pt-2 pb-4 flex flex-col gap-1.5 overflow-hidden text-[12px] w-full">
      {/* Identificación + Contacto: contenido equivalente (6 campos cada una) → 50/50, mismo alto. */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-1.5 items-stretch">
        <ClinicalCard compact className="!rounded-md">
          <SectionHeader title="Identificación" customIcon={<User className="w-3.5 h-3.5 text-[#1500A0]" />} />
          <div className="flex gap-2">
            <div className="relative shrink-0 flex flex-col items-center gap-1">
              <button type="button" onClick={() => setFotoMenu((v) => !v)} title="Cambiar foto"
                className="relative w-16 h-16 rounded-md overflow-hidden border border-[#e5e7eb] bg-[#FFFFFF] flex items-center justify-center hover:border-[#1ca0d1] transition-colors">
                {fil.tiene_foto ? (
                  <img key={fotoVer} src={`${patientService.fotoUrl(patientId)}?v=${fotoVer}`} alt="" className="w-full h-full object-cover" />
                ) : (
                  <User className="w-6 h-6 text-slate-300" />
                )}
                {fotoSubiendo && (
                  <span className="absolute inset-0 bg-white/70 flex items-center justify-center">
                    <Loader2 className="w-4 h-4 animate-spin text-[#1ca0d1]" />
                  </span>
                )}
              </button>
              {fotoMenu && (
                <>
                  <div className="fixed inset-0 z-10" onClick={() => setFotoMenu(false)} />
                  <div className="absolute top-[68px] left-0 z-20 w-40 bg-white border border-[#e5e7eb] rounded-md shadow-lg overflow-hidden">
                    <button type="button" onClick={() => { setFotoMenu(false); fotoInputRef.current?.click(); }}
                      className="w-full flex items-center gap-2 px-2.5 py-2 text-[11px] text-left hover:bg-[#E6EDFF] uppercase">
                      <Camera className="w-3.5 h-3.5 text-[#1ca0d1]" /> Hacer foto
                    </button>
                    <button type="button" onClick={fotoDesdeDrive}
                      className="w-full flex items-center gap-2 px-2.5 py-2 text-[11px] text-left hover:bg-[#E6EDFF] uppercase border-t border-[#f0f2f5]">
                      <FolderSearch className="w-3.5 h-3.5 text-[#1ca0d1]" /> Buscar en Drive
                    </button>
                  </div>
                </>
              )}
              <input ref={fotoInputRef} type="file" accept="image/png,image/jpeg,image/webp" capture="user" className="hidden"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) subirFoto(f); e.target.value = ""; }} />
              {fil.tiene_foto && (
                <button type="button" onClick={quitarFoto} className="text-[10px] text-[#C026D3] hover:underline uppercase">Quitar</button>
              )}
              {fotoError && <p className="text-[9px] text-[#C026D3] text-center leading-tight max-w-[80px]">{fotoError}</p>}
            </div>
            <div className="flex flex-wrap gap-2 flex-1 min-w-0">
              <div className="flex-1 min-w-[150px] max-w-[200px]"><CampoEdit label="Nombre" value={fil.nombre ?? ""} onSave={saveCore("nombre")} /></div>
              <div className="flex-1 min-w-[150px] max-w-[200px]"><CampoEdit label="Apellidos" value={fil.apellidos ?? ""} onSave={saveCore("apellidos")} /></div>
              <div className="w-32"><CampoEdit label="NIF / DNI" value={fil.nif ?? ""} onSave={saveCore("nif")} /></div>
              <div className="w-36"><CampoEdit label="Fecha nac." type="date" value={fil.fecha_nacimiento ?? ""} onSave={saveCore("fecha_nacimiento")} /></div>
              <div className="w-24"><CampoEdit label="Nº Historia" value={fil.num_historia ?? ""} onSave={async () => {}} readOnly /></div>
            </div>
          </div>
        </ClinicalCard>
        <ClinicalCard compact className="!rounded-md">
          <SectionHeader title="Contacto" customIcon={<Phone className="w-3.5 h-3.5 text-[#1500A0]" />} />
          <div className="flex flex-wrap gap-2">
            <div className="w-32"><CampoEdit label="Móvil" value={fil.telefono_movil ?? ""} onSave={saveCore("telefono_movil")} /></div>
            <div className="w-32"><CampoEdit label="Fijo" value={fil.telefono_fijo ?? ""} onSave={saveCore("telefono_fijo")} /></div>
            <div className="w-32"><CampoEdit label="Trabajo" value={fil.telefono_fijo2 ?? ""} onSave={saveCore("telefono_fijo2")} /></div>
            <div className="flex-1 min-w-[160px] max-w-[320px]"><CampoEdit label="Email" type="email" value={fil.email ?? ""} onSave={saveCore("email")} /></div>
            <div className="flex-[2] min-w-[220px] max-w-[420px]"><CampoEdit label="Dirección" value={fil.direccion ?? ""} onSave={saveCore("direccion")} /></div>
            <div className="w-20"><CampoEdit label="C.P." value={fil.cp ?? ""} onSave={saveCore("cp")} /></div>
          </div>
        </ClinicalCard>
      </div>

      {/* Consentimientos + Tarifa: ambas ligeras (checkboxes/pills), pero RGPD necesita más ancho
          para 4 etiquetas legibles — 3fr/2fr en vez de 50/50, mismo alto que RGPD. */}
      <div className="grid grid-cols-1 lg:grid-cols-[3fr_2fr] gap-1.5 items-stretch">
        <ClinicalCard compact className="!rounded-md">
          <SectionHeader title="Consentimientos RGPD" customIcon={<Shield className="w-3.5 h-3.5 text-[#1500A0]" />} />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {RGPD.map((c) => {
              const on = Boolean(fil[c.key]);
              return (
                <button key={c.key} onClick={() => toggleRGPD(c.key)}
                  className={`flex items-center gap-2 px-2.5 py-1.5 rounded-sm border text-left text-[12px] transition-colors ${on ? "bg-[#FFFFFF] border-[#7dd3fc]" : "bg-white border-[#e5e7eb] hover:bg-[#E6EDFF]"}`}>
                  <span className={`w-3.5 h-3.5 rounded-sm border-2 flex items-center justify-center shrink-0 ${on ? "bg-[#3388FF] border-[#3388FF]" : "border-[#cbd5e1]"}`}>
                    {on && <span className="w-1.5 h-1.5 bg-white rounded-full" />}
                  </span>
                  <span className="text-slate-600 uppercase">{c.label}</span>
                </button>
              );
            })}
          </div>
        </ClinicalCard>
        <ClinicalCard compact className="!rounded-md">
          <SectionHeader title="Tarifa aplicada" customIcon={<FileText className="w-3.5 h-3.5 text-[#1500A0]" />} />
          <div className="flex flex-wrap gap-2">
            {fil.tarifas.catalogo.map((t) => {
              const on = fil.tarifas.asignadas.includes(t.id);
              return (
                <button key={t.id} onClick={() => toggleTarifa(t.id)}
                  className={`px-2.5 py-1 rounded-sm text-[11px] uppercase tracking-wide border transition-colors ${on ? "bg-[#3388FF] text-white border-[#3388FF]" : "bg-white text-slate-600 border-[#e5e7eb] hover:bg-[#E6EDFF]"}`}>
                  {t.nombre}
                </button>
              );
            })}
            {fil.tarifas.catalogo.length === 0 && <span className="text-[12px] text-slate-400 italic uppercase">Sin tarifas en el centro</span>}
          </div>
        </ClinicalCard>
      </div>

      {/* Seguro y Responsable: contenido parejo (3 campos cortos cada una) → 50/50 con items-start. */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-1.5 items-start">
        <ClinicalCard compact className="!rounded-md">
          <SectionHeader title="Seguro / Mutua" customIcon={<Shield className="w-3.5 h-3.5 text-[#1500A0]" />} />
          <div className="flex flex-wrap gap-2">
            <div className="flex-1 min-w-[140px] max-w-[320px]"><CampoEdit label="Aseguradora" value={fil.seguro?.aseguradora ?? ""} onSave={saveSeguro("aseguradora")} /></div>
            <div className="w-28"><CampoEdit label="Nº Póliza" value={fil.seguro?.num_poliza ?? ""} onSave={saveSeguro("num_poliza")} /></div>
            <div className="w-32"><CampoEdit label="Nº Seg. Social" value={fil.seguro?.num_ss ?? ""} onSave={saveSeguro("num_ss")} /></div>
          </div>
        </ClinicalCard>
        <ClinicalCard compact className="!rounded-md">
          <SectionHeader title="Responsable / Tutor legal" customIcon={<User className="w-3.5 h-3.5 text-[#1500A0]" />} />
          <div className="flex flex-wrap gap-2">
            <div className="flex-1 min-w-[140px] max-w-[320px]"><CampoEdit label="Nombre" value={fil.responsable_nombre ?? ""} onSave={saveCore("responsable_nombre")} /></div>
            <div className="w-28"><CampoEdit label="NIF" value={fil.responsable_nif ?? ""} onSave={saveCore("responsable_nif")} /></div>
            <div className="w-32"><CampoEdit label="Parentesco" value={fil.responsable_parentesco ?? ""} onSave={saveCore("responsable_parentesco")} /></div>
          </div>
        </ClinicalCard>
      </div>

      {/* Facturación + Notas internas */}
      <ClinicalCard compact className="!rounded-md">
        <SectionHeader title="Facturación" customIcon={<Wallet className="w-3.5 h-3.5 text-[#1500A0]" />} />
        <div className="flex flex-wrap gap-2">
          <div className="flex-[2] min-w-[300px] max-w-[520px]"><CampoEdit label="Razón social" value={fil.facturacion?.razon_social ?? ""} onSave={saveFacturacion("razon_social")} /></div>
          <div className="w-36"><CampoEdit label="NIF / CIF" value={fil.facturacion?.nif ?? ""} onSave={saveFacturacion("nif")} /></div>
          <div className="w-40"><CampoEdit label="Forma de pago" value={fil.facturacion?.forma_pago ?? ""} onSave={saveFacturacion("forma_pago")} /></div>
          <div className="flex-[3] min-w-[260px] max-w-[480px]"><CampoEdit label="Dirección" value={fil.facturacion?.direccion ?? ""} onSave={saveFacturacion("direccion")} /></div>
          <div className="flex-[2] min-w-[220px] max-w-[320px]"><CampoEdit label="IBAN" value={fil.facturacion?.iban ?? ""} onSave={saveFacturacion("iban")} /></div>
          <div className="flex-1 min-w-[180px] max-w-[320px]"><CampoEdit label="Titular cuenta" value={fil.facturacion?.titular_cuenta ?? ""} onSave={saveFacturacion("titular_cuenta")} /></div>
          <div className="w-20"><CampoEdit label="Descuento %" type="number" value={fil.descuento != null ? String(fil.descuento) : ""} onSave={saveCore("descuento", (v) => (v ? Number(v) : null))} /></div>
        </div>
      </ClinicalCard>

      {/* Datos médicos (separada de Facturación) */}
      <ClinicalCard compact className="!rounded-md">
        <SectionHeader title="Datos médicos" customIcon={<Activity className="w-3.5 h-3.5 text-[#1500A0]" />} />
        <div className="flex flex-wrap gap-2">
          <div className="w-28"><CampoEdit label="Grupo sanguíneo" value={fil.grupo_sanguineo ?? ""} onSave={saveCore("grupo_sanguineo")} /></div>
          <div className="w-20"><CampoEdit label="Peso (kg)" type="number" value={fil.peso != null ? String(fil.peso) : ""} onSave={saveCore("peso", (v) => (v ? Number(v) : null))} /></div>
          <div className="w-20"><CampoEdit label="Altura (cm)" type="number" value={fil.altura != null ? String(fil.altura) : ""} onSave={saveCore("altura", (v) => (v ? Number(v) : null))} /></div>
          <div className="flex-1 min-w-[180px] max-w-[320px]"><CampoEdit label="Médico cabecera" value={fil.medico_cabecera ?? ""} onSave={saveCore("medico_cabecera")} /></div>
          <div className="w-36"><CampoEdit label="Tel. médico" value={fil.tel_medico ?? ""} onSave={saveCore("tel_medico")} /></div>
          <div className="flex-1 min-w-[160px] max-w-[300px]"><CampoEdit label="Especialista" value={fil.especialista ?? ""} onSave={saveCore("especialista")} /></div>
        </div>
      </ClinicalCard>

      {/* Notas internas — antes de Anamnesis */}
      <ClinicalCard compact className="!rounded-md">
        <CampoEdit label="Notas internas (uso interno)" value={fil.notas ?? ""} onSave={saveCore("notas")} placeholder="Observaciones…" />
      </ClinicalCard>

      {/* Anamnesis — única sección con altura flexible: absorbe el espacio que sobra y solo
          ella scrollea por dentro si hace falta, para que la página NUNCA tenga scroll propio
          sea cual sea el alto real de la ventana (con barra de direcciones, pestañas, etc.). */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        {cat && <Anamnesis catalogo={cat} marcados={fil.anamnesis} onToggle={toggleAnamnesis} guardando={savingAnam} />}
      </div>
    </div>
  );
}
