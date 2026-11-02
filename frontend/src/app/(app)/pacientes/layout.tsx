"use client";
/**
 * Layout del área Pacientes: barra superior del PACIENTE (réplica del .37) sobre /pacientes/**.
 * El paciente vive en el store global (patientSession) → sigue "cargado" aunque cambies de
 * sección. Aquí solo: sincronizo URL→store, pinto la barra y enrouto la "X" por el guard de
 * cambios sin guardar.
 */
import { useCallback, useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { PatientTopBar } from "@/features/patients/components/PatientTopBar";
import { patientService } from "@/features/patients/services/patientService";
import { patientSession, usePatientSession } from "@/features/patients/store/patientSession";

export default function PacientesLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { cab } = usePatientSession();
  const id = pathname.match(/^\/pacientes\/(\d+)/)?.[1] ?? null;

  // URL con paciente → lo dejo abierto en el store y cargo su cabecera.
  const cargar = useCallback(async () => {
    if (!id) return;
    const nid = Number(id);
    const prev = patientSession.snapshot();
    patientSession.open(nid, prev.openId === nid ? prev.cab : null);
    try { patientSession.setCab(await patientService.cabecera(nid)); } catch { /* deja cab previa */ }
  }, [id]);
  useEffect(() => { cargar(); }, [cargar]);

  // La barra se refresca cuando un cambio del paciente emite 'ms:patient-updated'.
  useEffect(() => {
    const h = () => cargar();
    window.addEventListener("ms:patient-updated", h);
    return () => window.removeEventListener("ms:patient-updated", h);
  }, [cargar]);

  // Cerrar paciente: pasa por el guard (si hay cambios sin guardar pregunta) → vacía y sale.
  const cerrar = () => patientSession.requestClose(() => { patientSession.clear(); router.push("/pacientes"); });

  return (
    <div className="flex flex-col h-full min-h-0">
      <PatientTopBar cab={cab} onClose={cerrar} />
      <div className="flex-1 min-h-0 min-w-0 overflow-hidden">{children}</div>
    </div>
  );
}
