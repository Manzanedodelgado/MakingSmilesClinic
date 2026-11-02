"use client";
import { useEffect, useRef, useState } from "react";
import { Loader2, X, Check, UserPlus, User, Phone, Shield, Activity } from "lucide-react";
import { Modal, ModalBody, ModalButton, MODAL_INPUT } from "@/shared/components";
import { patientService, type NuevoPacienteBody } from "../services/patientService";

/**
 * Alta de paciente = campos de FILIACIÓN (columnas directas). Lo abre el botón "Nuevo +"
 * de la barra superior. El Nº de historia NO es editable: lo asigna el backend de forma
 * incremental y se muestra al crear. Los bloques relacionales (tarifas, seguro, facturación,
 * anamnesis) se completan luego en la ficha. Al crear, dispara el puente a Romexis.
 */
type Estado = NuevoPacienteBody & Record<string, string | number | boolean | null | undefined>;

const RGPD: { key: keyof NuevoPacienteBody; label: string }[] = [
  { key: "acepta_lopd", label: "Tratamiento datos (RGPD)" },
  { key: "acepta_whatsapp", label: "SMS / WhatsApp" },
  { key: "acepta_info", label: "Info comercial" },
  { key: "acepta_bots", label: "Asistentes / Bots" },
];

const IN = `${MODAL_INPUT} disabled:bg-white`;
const LBL = "flex flex-col gap-1 text-[11px] text-slate-500";

// Definidos FUERA del componente: si estuvieran dentro, cada tecla remonta el input y pierde el foco.
function Campo({ label, value, onChange, disabled, type = "text", ph, className }: {
  label: string; value: string; onChange: (v: string) => void; disabled: boolean;
  type?: string; ph?: string; className?: string;
}) {
  return (
    <label className={`${LBL} ${className ?? ""}`}>{label}
      <input type={type} inputMode={type === "tel" ? "tel" : undefined} value={value} placeholder={ph}
        onChange={(e) => onChange(e.target.value)} disabled={disabled} className={IN} /></label>
  );
}

function Seccion({ icon: Icon, titulo, children }: { icon: typeof User; titulo: string; children: React.ReactNode }) {
  return (
    <div className="border border-[#BFE4F7] rounded-lg overflow-hidden">
      <div className="flex items-center gap-2 px-3 py-1.5 bg-[#21A2E5] text-white text-[12px] font-semibold">
        <span className="w-[18px] h-[18px] rounded-full border border-white/80 grid place-items-center shrink-0">
          <Icon className="w-3 h-3" strokeWidth={2.5} />
        </span>
        {titulo}
      </div>
      <div className="p-3 grid grid-cols-2 gap-2.5">{children}</div>
    </div>
  );
}

export function NuevoPacienteModal({ onCerrar, onCreado }: { onCerrar: () => void; onCreado: (id: number) => void }) {
  const [f, setF] = useState<Estado>({ nombre: "", apellidos: "" });
  const [guardando, setGuardando] = useState(false);
  const [creado, setCreado] = useState<{ id: number; numHistoria: string } | null>(null);
  // Si se cierra el modal durante los 950 ms de confirmación, no navegar a la ficha.
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (timerRef.current) clearTimeout(timerRef.current); }, []);
  const cerrar = () => { if (timerRef.current) clearTimeout(timerRef.current); onCerrar(); };
  const [error, setError] = useState<string | null>(null);

  const set = (k: keyof NuevoPacienteBody, v: string | boolean) => setF((p) => ({ ...p, [k]: v }));
  const txt = (k: keyof NuevoPacienteBody) => String(f[k] ?? "");
  const bloqueado = !!creado || guardando;

  const guardar = async () => {
    if (!txt("nombre").trim() || !txt("apellidos").trim()) { setError("Nombre y apellidos son obligatorios"); return; }
    setGuardando(true); setError(null);
    try {
      // Nº de historia lo asigna el backend (incremental): no se envía.
      const body: NuevoPacienteBody = {
        ...f,
        nombre: txt("nombre").trim(), apellidos: txt("apellidos").trim(),
        fecha_nacimiento: txt("fecha_nacimiento") || null,
        descuento: txt("descuento") ? Number(txt("descuento")) : null,
        peso: txt("peso") ? Number(txt("peso")) : null,
        altura: txt("altura") ? Number(txt("altura")) : null,
      };
      const r = await patientService.crearPaciente(body);
      setCreado({ id: r.id, numHistoria: r.num_historia });
      timerRef.current = setTimeout(() => onCreado(r.id), 950);   // muestra el nº asignado y abre la ficha
    } catch (e) {
      setError(e instanceof Error ? e.message.slice(0, 180) : "No se pudo crear");
      setGuardando(false);
    }
  };

  return (
    <Modal
      title="Nuevo paciente · Filiación"
      onClose={cerrar}
      size="lg"
      zIndex={120}
      closeOnBackdrop
      footer={
        <>
          <ModalButton variant="magenta" icon={X} onClick={cerrar}>Cancelar</ModalButton>
          <ModalButton variant="primary" icon={UserPlus} onClick={guardar} disabled={bloqueado}>
            {guardando && <Loader2 className="w-4 h-4 animate-spin" />} Crear paciente
          </ModalButton>
        </>
      }
    >
      <ModalBody className="flex flex-col gap-3">
          <Seccion icon={User} titulo="Identificación">
            <Campo label="Nombre" value={txt("nombre")} onChange={(v) => set("nombre", v)} disabled={bloqueado} />
            <Campo label="Apellidos" value={txt("apellidos")} onChange={(v) => set("apellidos", v)} disabled={bloqueado} />
            <Campo label="NIF / DNI" value={txt("nif")} onChange={(v) => set("nif", v)} disabled={bloqueado} />
            <Campo label="Fecha nacimiento" type="date" value={txt("fecha_nacimiento")} onChange={(v) => set("fecha_nacimiento", v)} disabled={bloqueado} />
            <label className={LBL}>Nº historia <span className="text-slate-400">· automático</span>
              <input value={creado?.numHistoria ?? ""} readOnly placeholder="Automático"
                className="w-full text-sm border border-[#BFE4F7] bg-white text-slate-500 rounded-md px-2 py-1.5 cursor-default" /></label>
            <Campo label="Descuento %" type="number" value={txt("descuento")} onChange={(v) => set("descuento", v)} disabled={bloqueado} />
          </Seccion>

          <Seccion icon={Phone} titulo="Contacto">
            <Campo label="Móvil · WhatsApp / citas" type="tel" ph="6XX XXX XXX" value={txt("telefono_movil")} onChange={(v) => set("telefono_movil", v)} disabled={bloqueado} />
            <Campo label="Fijo" type="tel" value={txt("telefono_fijo")} onChange={(v) => set("telefono_fijo", v)} disabled={bloqueado} />
            <Campo label="Trabajo" type="tel" value={txt("telefono_fijo2")} onChange={(v) => set("telefono_fijo2", v)} disabled={bloqueado} />
            <Campo label="Email" type="email" value={txt("email")} onChange={(v) => set("email", v)} disabled={bloqueado} />
            <Campo label="Dirección" value={txt("direccion")} onChange={(v) => set("direccion", v)} disabled={bloqueado} />
            <Campo label="C.P." value={txt("cp")} onChange={(v) => set("cp", v)} disabled={bloqueado} />
          </Seccion>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Seccion icon={User} titulo="Responsable / Tutor">
              <Campo label="Nombre" value={txt("responsable_nombre")} onChange={(v) => set("responsable_nombre", v)} disabled={bloqueado} />
              <Campo label="NIF" value={txt("responsable_nif")} onChange={(v) => set("responsable_nif", v)} disabled={bloqueado} />
              <Campo label="Parentesco" className="col-span-2" value={txt("responsable_parentesco")} onChange={(v) => set("responsable_parentesco", v)} disabled={bloqueado} />
            </Seccion>
            <Seccion icon={Activity} titulo="Datos médicos">
              <Campo label="Grupo sanguíneo" value={txt("grupo_sanguineo")} onChange={(v) => set("grupo_sanguineo", v)} disabled={bloqueado} />
              <Campo label="Médico cabecera" value={txt("medico_cabecera")} onChange={(v) => set("medico_cabecera", v)} disabled={bloqueado} />
              <Campo label="Peso (kg)" type="number" value={txt("peso")} onChange={(v) => set("peso", v)} disabled={bloqueado} />
              <Campo label="Altura (cm)" type="number" value={txt("altura")} onChange={(v) => set("altura", v)} disabled={bloqueado} />
            </Seccion>
          </div>

          <div className="border border-[#BFE4F7] rounded-lg overflow-hidden">
            <div className="flex items-center gap-2 px-3 py-1.5 bg-[#21A2E5] text-white text-[12px] font-semibold">
              <span className="w-[18px] h-[18px] rounded-full border border-white/80 grid place-items-center shrink-0">
                <Shield className="w-3 h-3" strokeWidth={2.5} />
              </span>
              Consentimientos RGPD
            </div>
            <div className="p-3 grid grid-cols-2 gap-2">
              {RGPD.map((c) => {
                const on = Boolean(f[c.key]);
                return (
                  <button key={String(c.key)} type="button" disabled={bloqueado} onClick={() => set(c.key, !on)}
                    className={`flex items-center gap-2 px-2.5 py-1.5 rounded-sm border text-left text-[12px] transition-colors ${on ? "bg-[#FFFFFF] border-[#7dd3fc]" : "bg-white border-slate-200 hover:bg-[#E6EDFF]"}`}>
                    <span className={`w-3.5 h-3.5 rounded-sm border-2 flex items-center justify-center shrink-0 ${on ? "bg-[#3388FF] border-[#3388FF]" : "border-slate-300"}`}>
                      {on && <span className="w-1.5 h-1.5 bg-white rounded-full" />}
                    </span>
                    <span className="text-slate-600">{c.label}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {error && <div className="text-xs text-[#8B1A96] bg-[#FFFFFF] border border-[#C026D3] rounded-md px-2 py-1.5">{error}</div>}
          {creado ? (
            <div className="text-xs text-[#0F8C7D] bg-[#FFFFFF] border border-[#20BEAB] rounded-md px-2 py-1.5 flex items-center gap-1.5">
              <Check className="w-3.5 h-3.5" /> Paciente creado con Nº historia <b>{creado.numHistoria}</b>. Abriendo ficha…
            </div>
          ) : (
            <p className="text-[11px] text-slate-400">
              El Nº de historia se asigna automáticamente y se crea también en Romexis. Tarifas, seguro/mutua,
              facturación y anamnesis se completan en la ficha tras el alta.
            </p>
          )}

      </ModalBody>
    </Modal>
  );
}
