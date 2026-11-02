"use client";
/** Las alertas más importantes del paciente (por gravedad), con las ya resueltas marcadas. */
import { useEffect, useState } from "react";
import { patientService } from "../../services/patientService";
import type { AlertaMedica } from "../../types/patient";
import { alertasImportantes, fechaCorta } from "./fichaDatos";
import { FichaPanel, FichaVacio } from "./FichaPanel";
import { fichaTema as T } from "./fichaTema";

const COLOR: Record<string, string> = { GRAVE: "#C026D3", MODERADA: "#7C3AED", LEVE: "#20BEAB" };

export function PanelAlertas({ patientId }: { patientId: number }) {
  const [lista, setLista] = useState<AlertaMedica[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let vivo = true;
    setLista(null); setError(false);
    patientService.alertas(patientId)
      .then((d) => { if (vivo) setLista(alertasImportantes(d.alertas)); })
      .catch(() => { if (vivo) setError(true); });
    return () => { vivo = false; };
  }, [patientId]);

  return (
    <FichaPanel titulo="Alertas">
      {error ? <FichaVacio texto="No se pudieron cargar las alertas" />
        : lista === null ? <FichaVacio texto="Cargando…" />
        : lista.length === 0 ? <FichaVacio texto="Sin alertas registradas" />
        : (
          <ul>
            {lista.map((a) => (
              <li key={a.id} className={`px-3 py-1.5 border-b text-[12px] flex gap-2 items-start ${a.activo ? "" : "opacity-55"}`} style={{ borderColor: T.borde }}>
                <span className="mt-[5px] w-2 h-2 rounded-full shrink-0" style={{ background: COLOR[(a.severidad ?? "").toUpperCase()] ?? T.textoSuave }} />
                <span className="min-w-0">
                  <span className="text-[#333] leading-snug">{a.texto}</span>
                  <span className="block text-[11px]" style={{ color: T.textoSuave }}>{fechaCorta(a.fecha)}{a.activo ? "" : " · resuelta"}</span>
                </span>
              </li>
            ))}
          </ul>
        )}
    </FichaPanel>
  );
}
