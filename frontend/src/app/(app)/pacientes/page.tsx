"use client";
import { Users, AlertTriangle } from "lucide-react";
import { useState, useEffect, useCallback } from "react";
import { patientService, type RomexisSyncItem } from "@/features/patients/services/patientService";

export default function PacientesPage() {
  const [conflictos, setConflictos] = useState<RomexisSyncItem[]>([]);

  const cargarConflictos = useCallback(() => {
    patientService.romexisConflictos().then((r) => setConflictos(r.sync)).catch(() => setConflictos([]));
  }, []);
  useEffect(() => {
    cargarConflictos();
    const t = setInterval(cargarConflictos, 15000);   // el agente puede marcar conflictos en cualquier momento
    return () => clearInterval(t);
  }, [cargarConflictos]);

  const resolver = async (id: number, accion: "modificar" | "nuevo_circuito") => {
    await patientService.romexisResolver(id, accion);
    cargarConflictos();
  };

  return (
    <div className="flex flex-col items-center justify-center h-full text-center select-none relative">
      {/* Aviso de conflictos de Romexis (mismo ID, distinto nombre) */}
      {conflictos.length > 0 && (
        <div className="absolute top-3 left-1/2 -translate-x-1/2 w-full max-w-[640px] flex flex-col gap-2 px-3">
          {conflictos.map((c) => (
            <div key={c.id} className="text-left bg-[#FFFFFF] border border-[#C4B5FD] rounded-sm p-3 shadow-sm">
              <div className="flex items-center gap-1.5 text-[#5B21B6] text-[13px] font-semibold mb-1">
                <AlertTriangle className="w-4 h-4" /> Conflicto de ID en Romexis (Nº historia {c.num_historia})
              </div>
              <p className="text-xs text-slate-700">
                En Romexis el Nº <b>{c.num_historia}</b> figura como <b>{c.romexis_nombre} {c.romexis_apellidos}</b>,
                pero en la web es <b>{c.nombre} {c.apellidos}</b>. ¿Modificar el nombre en Romexis para que coincida?
              </p>
              <div className="flex gap-2 mt-2">
                <button type="button" onClick={() => resolver(c.id, "modificar")}
                  className="text-xs bg-[#013b82] text-white rounded-sm px-3 py-1.5 cursor-pointer">Sí, modificar en Romexis</button>
                <button type="button" onClick={() => resolver(c.id, "nuevo_circuito")}
                  className="text-xs bg-white border border-slate-300 text-slate-700 rounded-sm px-3 py-1.5 cursor-pointer">No (ese ID puede ser de otro paciente)</button>
              </div>
            </div>
          ))}
        </div>
      )}

      <Users className="w-14 h-14 text-slate-200 mb-3" strokeWidth={1.25} />
      <p className="text-[14px] text-slate-400">Seleccione un paciente de la lista para ver su historial</p>
      <p className="text-[12px] text-slate-300 mt-1">Use el buscador de arriba, o el botón <b className="text-slate-400">Nuevo +</b> para dar de alta</p>
    </div>
  );
}
