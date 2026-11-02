"use client";
/**
 * Mapa de incertidumbre — la columna derecha de La Consulta Viva.
 * Lista las incógnitas abiertas (preguntas clínicas) con su confianza y deja cerrarlas.
 * Presentacional: recibe las incógnitas y los handlers; el estado vive en ConsultaViva.
 */
import { ChevronUp, Check, X, Lightbulb, Crosshair } from "lucide-react";
import type { Incognita } from "./incognitas";

const origenColor: Record<string, string> = {
  motivo: "#1500A0", alerta: "#C026D3", presupuesto: "#1ca0d1",
  odontograma: "#7C3AED", escucha: "#2DD9C3",
};

function barra(conf: number) {
  const color = conf >= 75 ? "#2DD9C3" : conf >= 45 ? "#7C3AED" : "#C026D3";
  return (
    <div className="flex items-center gap-1.5">
      <div className="flex-1 h-1.5 rounded-full bg-[#FFFFFF] overflow-hidden">
        <div className="h-full rounded-full transition-all" style={{ width: `${conf}%`, background: color }} />
      </div>
      <span className="text-[10px] font-bold tabular-nums w-8 text-right" style={{ color }}>{conf}%</span>
    </div>
  );
}

const eur = (n: number | null) => (n == null ? "" : ` · ${n.toLocaleString("es-ES", { minimumFractionDigits: 0 })} €`);

export function IncognitasPanel({
  incognitas, activaId, onSelect, onSubir, onProponer, onResolver, onDescartar,
}: {
  incognitas: Incognita[];
  activaId: string | null;
  onSelect: (id: string) => void;
  onSubir: (id: string) => void;
  onProponer: (id: string) => void;
  onResolver: (id: string) => void;
  onDescartar: (id: string) => void;
}) {
  const abiertas = incognitas.filter((i) => i.estado === "abierta");
  const cerradas = incognitas.filter((i) => i.estado !== "abierta");

  return (
    <div className="flex flex-col gap-2 h-full overflow-y-auto pr-0.5">
      {abiertas.length === 0 && (
        <p className="text-[12px] text-slate-400 italic px-1">No quedan preguntas pendientes.</p>
      )}

      {abiertas.map((i) => {
        const activa = i.id === activaId;
        return (
          <div key={i.id} onClick={() => onSelect(i.id)}
            className={`rounded-sm border p-2 cursor-pointer transition-colors ${activa ? "border-[#1ca0d1] bg-[#FFFFFF]" : "border-[#e5e7eb] bg-white hover:bg-[#E6EDFF]"}`}>
            <div className="flex items-start gap-1.5">
              <span className="mt-[3px] w-1.5 h-1.5 rounded-full shrink-0" style={{ background: origenColor[i.origen] }} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="text-[12px] font-semibold text-[#065AED] leading-tight">{i.pregunta}</span>
                  {i.pieza && <span className="text-[9px] font-mono text-[#1500A0] bg-[#FFFFFF] px-1 rounded-sm shrink-0">{i.pieza}</span>}
                </div>
                {i.hipotesis && i.hipotesis !== "—" && (
                  <p className="text-[10px] text-slate-500 mt-0.5">{i.hipotesis}</p>
                )}
              </div>
            </div>

            <div className="mt-1.5">{barra(i.confianza)}</div>

            {i.necesita && i.confianza < 75 && (
              <p className="text-[10px] text-[#0d5e7a] mt-1 flex items-center gap-1">
                <Crosshair className="w-3 h-3 shrink-0" /> falta: {i.necesita}
              </p>
            )}

            {i.evidencias.length > 0 && (
              <ul className="mt-1 flex flex-col gap-0.5">
                {i.evidencias.map((e, k) => (
                  <li key={k} className="text-[10px] text-[#374151] border-l-2 border-[#2DD9C3] pl-1.5">{e}</li>
                ))}
              </ul>
            )}

            {i.propuesta && (
              <div className="mt-1 inline-flex items-center gap-1 text-[10px] font-semibold text-[#1500A0] bg-[#FFFFFF] border border-[#c9cffb] rounded-sm px-1.5 py-0.5">
                <Lightbulb className="w-3 h-3" /> {i.propuesta.texto}{eur(i.propuesta.precio)}
              </div>
            )}

            <div className="flex items-center gap-1 mt-1.5" onClick={(e) => e.stopPropagation()}>
              <button onClick={() => onSubir(i.id)} title="Aumentar la seguridad de la respuesta"
                className="flex items-center gap-0.5 px-1.5 py-0.5 rounded-sm text-[10px] font-semibold border border-[#cfe1ff] text-[#1ca0d1] hover:bg-[#E6EDFF]">
                <ChevronUp className="w-3 h-3" /> subir %
              </button>
              <button onClick={() => onProponer(i.id)} title="Proponer tratamiento"
                className="flex items-center gap-0.5 px-1.5 py-0.5 rounded-sm text-[10px] font-semibold border border-[#c9cffb] text-[#1500A0] hover:bg-[#E6EDFF]">
                <Lightbulb className="w-3 h-3" /> proponer
              </button>
              <button onClick={() => onResolver(i.id)} title="Dar la pregunta por respondida"
                className="ml-auto flex items-center gap-0.5 px-1.5 py-0.5 rounded-sm text-[10px] font-semibold bg-[#2DD9C3] text-[#1500A0] hover:brightness-105">
                <Check className="w-3 h-3" /> respondida
              </button>
              <button onClick={() => onDescartar(i.id)} title="Descartar"
                className="text-slate-300 hover:text-[#C026D3]"><X className="w-3.5 h-3.5" /></button>
            </div>
          </div>
        );
      })}

      {cerradas.length > 0 && (
        <div className="mt-1 pt-2 border-t border-[#f0f2f5]">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400 mb-1">Cerradas ({cerradas.length})</p>
          {cerradas.map((i) => (
            <div key={i.id} className="flex items-center gap-1.5 text-[11px] text-slate-400 py-0.5">
              {i.estado === "resuelta"
                ? <Check className="w-3 h-3 text-[#2DD9C3] shrink-0" />
                : <X className="w-3 h-3 text-slate-300 shrink-0" />}
              <span className={`truncate ${i.estado === "descartada" ? "line-through" : ""}`}>{i.pregunta}</span>
              {i.propuesta && i.estado === "resuelta" && <span className="text-[#1500A0] shrink-0">→ {i.propuesta.texto}</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
