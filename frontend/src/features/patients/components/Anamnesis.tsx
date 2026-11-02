"use client";
import { AlertTriangle } from "lucide-react";
/** Cuestionario de salud. Catálogo desde CONFIG (clinica.anamnesis). Críticos resaltados. */
import { ClinicalCard, SectionHeader } from "@/shared/components";
import type { AnamnesisCatalogo } from "../types/patient";

interface Props {
  catalogo: AnamnesisCatalogo;
  marcados: string[];
  onToggle: (item: string) => void;
  guardando: boolean;
}

export function Anamnesis({ catalogo, marcados, onToggle, guardando }: Props) {
  const set = new Set(marcados);
  const criticos = new Set(catalogo.criticos);
  return (
    <ClinicalCard noPadding className="h-full flex flex-col !rounded-md">
      <SectionHeader
        variant="dark"
        title="Cuestionario de salud — Anamnesis"
        customIcon={<AlertTriangle className="w-3.5 h-3.5 text-white" />}
        action={<span className="text-[10px] text-white/80 uppercase tracking-wide">{guardando ? "Guardando…" : `${marcados.length} marcados`}</span>}
      />
      <div className="flex-1 min-h-0 overflow-y-auto grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-1 p-1 auto-rows-min">
        {catalogo.secciones.map((sec) => {
          const n = sec.items.filter((i) => set.has(i)).length;
          return (
            <div key={sec.clave} className="border border-[#e5e7eb] rounded-sm overflow-hidden">
              <div className="flex items-center justify-between px-1.5 py-0.5 bg-[#FFFFFF] border-b border-[#e5e7eb]">
                <span className="text-[9px] font-semibold uppercase tracking-tight truncate" style={{ color: sec.color }}>{sec.titulo}</span>
                <span className="text-[9px] text-slate-400 shrink-0">{n}/{sec.items.length}</span>
              </div>
              <ul className="p-1 space-y-px">
                {sec.items.map((item) => {
                  const on = set.has(item);
                  const critico = on && criticos.has(item);
                  return (
                    <li key={item}>
                      <button
                        onClick={() => onToggle(item)}
                        title={item}
                        className={`w-full flex items-center gap-1 px-1 py-0.5 rounded-sm text-left text-[10px] leading-tight transition-colors ${on ? "bg-[#FFFFFF]" : "hover:bg-[#E6EDFF]"}`}
                      >
                        <span className={`w-3 h-3 rounded-sm border flex items-center justify-center shrink-0 ${on ? "bg-[#3388FF] border-[#3388FF]" : "border-[#cbd5e1]"}`}>
                          {on && <span className="w-1 h-1 bg-white rounded-full" />}
                        </span>
                        <span className={`truncate ${critico ? "text-[#1500A0] font-semibold" : on ? "text-[#333333]" : "text-slate-600"}`}>{item}</span>
                        {critico && <AlertTriangle className="w-2.5 h-2.5 text-[#1500A0] ml-auto shrink-0" />}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
      </div>
    </ClinicalCard>
  );
}
