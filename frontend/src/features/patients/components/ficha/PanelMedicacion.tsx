"use client";
/** Medicación activa y últimas recetas emitidas del paciente. */
import { useEffect, useState } from "react";
import { patientService } from "../../services/patientService";
import type { MedicacionPaciente, RecetaEmitida } from "../../types/patient";
import { fechaCorta } from "./fichaDatos";
import { FichaPanel, FichaVacio } from "./FichaPanel";
import { fichaTema as T } from "./fichaTema";

const MAX_RECETAS = 5;

export function PanelMedicacion({ patientId }: { patientId: number }) {
  const [meds, setMeds] = useState<MedicacionPaciente[] | null>(null);
  const [recetas, setRecetas] = useState<RecetaEmitida[]>([]);
  const [error, setError] = useState(false);

  useEffect(() => {
    let vivo = true;
    setMeds(null); setRecetas([]); setError(false);
    Promise.allSettled([patientService.alertas(patientId), patientService.recetas(patientId)]).then(([a, r]) => {
      if (!vivo) return;
      if (a.status === "rejected" && r.status === "rejected") { setError(true); return; }
      setMeds(a.status === "fulfilled" ? [...a.value.medicaciones].sort((x, y) => Number(y.activo) - Number(x.activo)) : []);
      if (r.status === "fulfilled") {
        setRecetas([...r.value.recetas].sort((x, y) => (y.fecha ?? "").localeCompare(x.fecha ?? "")).slice(0, MAX_RECETAS));
      }
    });
    return () => { vivo = false; };
  }, [patientId]);

  const vacio = meds !== null && meds.length === 0 && recetas.length === 0;
  return (
    <FichaPanel titulo="Historia farmacológica">
      {error ? <FichaVacio texto="No se pudo cargar la medicación" />
        : meds === null ? <FichaVacio texto="Cargando…" />
        : vacio ? <FichaVacio texto="Sin medicación ni recetas" />
        : (
          <div className="text-[12px]">
            {meds.length > 0 && (
              <section className="px-3 py-2 border-b" style={{ borderColor: T.borde }}>
                <h3 className="text-[11px] font-semibold mb-1" style={{ color: T.acento }}>Medicación</h3>
                <ul className="flex flex-col gap-0.5">
                  {meds.map((m) => (
                    <li key={m.id} className={`text-[#333] ${m.activo ? "" : "opacity-55"}`}>
                      <span className="font-semibold">{m.farmaco}</span>
                      {[m.dosis, m.frecuencia].filter(Boolean).length > 0 && <span style={{ color: T.textoSuave }}> · {[m.dosis, m.frecuencia].filter(Boolean).join(" · ")}</span>}
                      {!m.activo && <span style={{ color: T.textoSuave }}> · suspendida</span>}
                    </li>
                  ))}
                </ul>
              </section>
            )}
            {recetas.length > 0 && (
              <section className="px-3 py-2">
                <h3 className="text-[11px] font-semibold mb-1" style={{ color: T.acento }}>Últimas recetas</h3>
                <ul className="flex flex-col gap-0.5">
                  {recetas.map((r) => (
                    <li key={r.id} className="text-[#333]">
                      <span className="font-semibold">{r.medicamento}</span>
                      <span style={{ color: T.textoSuave }}> · {fechaCorta(r.fecha)}{r.posologia ? ` · ${r.posologia}` : ""}</span>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>
        )}
    </FichaPanel>
  );
}
