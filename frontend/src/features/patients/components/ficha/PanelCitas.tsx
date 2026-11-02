"use client";
/** Las 5 últimas citas del paciente. No hay endpoint por paciente: se piden las de los últimos 10 años y se filtra (igual que CitaCockpit). */
import { useEffect, useState } from "react";
import { api } from "@/shared/lib/api";
import { ultimasCitas, fechaCorta } from "./fichaDatos";
import { FichaPanel, FichaVacio } from "./FichaPanel";
import { fichaTema as T } from "./fichaTema";

type CitaPaciente = { id: number; fecha: string; hora: string; tipo_nombre: string | null; estado_nombre: string | null; paciente_id?: number | null };
const ymd = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

export function PanelCitas({ patientId }: { patientId: number }) {
  const [citas, setCitas] = useState<CitaPaciente[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let vivo = true;
    setCitas(null); setError(false);
    const hoy = new Date();
    const desde = ymd(new Date(hoy.getFullYear() - 10, hoy.getMonth(), hoy.getDate()));
    api.get<{ citas: CitaPaciente[] }>(`/agenda/citas?desde=${desde}&hasta=${ymd(hoy)}`)
      .then((r) => { if (vivo) setCitas(ultimasCitas(r.citas.filter((c) => c.paciente_id === patientId), ymd(hoy))); })
      .catch(() => { if (vivo) setError(true); });
    return () => { vivo = false; };
  }, [patientId]);

  return (
    <FichaPanel titulo="Últimas citas">
      {error ? <FichaVacio texto="No se pudieron cargar las citas" />
        : citas === null ? <FichaVacio texto="Cargando…" />
        : citas.length === 0 ? <FichaVacio texto="Sin citas registradas" />
        : (
          <ul>
            {citas.map((c) => (
              <li key={c.id} className="px-3 py-1.5 border-b text-[12px]" style={{ borderColor: T.borde }}>
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-semibold" style={{ color: T.cabTexto }}>{fechaCorta(c.fecha)} · {c.hora}</span>
                  <span className="truncate text-[11px]" style={{ color: T.textoSuave }}>{c.estado_nombre ?? ""}</span>
                </div>
                <div className="text-[#333] leading-snug truncate">{c.tipo_nombre ?? "Cita"}</div>
              </li>
            ))}
          </ul>
        )}
    </FichaPanel>
  );
}
