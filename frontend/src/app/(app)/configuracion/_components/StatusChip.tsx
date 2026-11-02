"use client";
import { ToggleLeft, ToggleRight } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@/shared/lib/api";

/** Sondea /health una vez; null mientras carga. Señal de incidencia de plataforma.
 *
 * /health real devuelve {api, database, llm, ...} — NUNCA un campo `status` (no existe).
 * Comparar contra `status` siempre daba `undefined === "ok"` → false, así que estos chips
 * marcaban "INCIDENCIA" en rojo cada vez que el canal estaba encendido, sin importar si la
 * plataforma iba bien o mal. Se comprueba `api` (disponibilidad general del backend). */
export function useHealthOk() {
  const [ok, setOk] = useState<boolean | null>(null);
  useEffect(() => {
    let alive = true;
    api.get<{ api: string }>("/health")
      .then((h) => { if (alive) setOk(h.api === "ok"); })
      .catch(() => { if (alive) setOk(false); });
    return () => { alive = false; };
  }, []);
  return ok;
}

/**
 * Indicador de la barra de IA's. Tres estados:
 *  - activo a voluntad y sano        → verde
 *  - activo a voluntad pero caído     → salmón (incidencia)
 *  - apagado a voluntad               → gris
 */
export function StatusChip({ label, on, incidencia = false, onClick }: { label: string; on: boolean; incidencia?: boolean; onClick: () => void }) {
  const estado = !on ? "off" : incidencia ? "incidencia" : "on";
  const cls = {
    on: "border-[#9FE6DB] text-[#0F8C7D] bg-[#FFFFFF]",
    incidencia: "border-[#E9A8F5] text-[#A21CAF] bg-[#FFFFFF]",
    off: "border-[#e5e7eb] text-slate-400 bg-white",
  }[estado];
  return (
    <button onClick={onClick} title={`${label} ${!on ? "OFF" : incidencia ? "INCIDENCIA" : "ON"}`}
      className={`flex items-center gap-1 px-1.5 py-0.5 rounded-sm border text-[10px] font-semibold uppercase tracking-wide ${cls}`}>
      {!on
        ? <ToggleLeft className="w-3.5 h-3.5 text-slate-300" />
        : <ToggleRight className={`w-3.5 h-3.5 ${incidencia ? "text-[#C026D3]" : "text-[#2DD9C3]"}`} />}
      {label}
    </button>
  );
}
