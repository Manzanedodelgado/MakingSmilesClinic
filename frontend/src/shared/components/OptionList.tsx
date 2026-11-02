import React from "react";
import { Check } from "lucide-react";

/**
 * OptionList — lista de opciones tipo radio (estética Config SmilePro).
 * Compartida por AURA y Centinela (cero duplicación).
 */
export function OptionList({ opts, value, onChange }: { opts: { v: string; t: string; d: string }[]; value: string; onChange: (v: string) => void }) {
  return (
    <div className="flex flex-col gap-2">
      {opts.map((o) => (
        <button key={o.v} onClick={() => onChange(o.v)}
          className={`flex items-center gap-3 text-left rounded-sm px-3 py-2 border ${value === o.v ? "border-[#1ca0d1] bg-[#FFFFFF]" : "border-[#e5e7eb] bg-[#FFFFFF] hover:border-[#cbd5e1]"}`}>
          <div className={`w-4 h-4 rounded-full border-2 shrink-0 flex items-center justify-center ${value === o.v ? "border-[#1ca0d1]" : "border-slate-300"}`}>
            {value === o.v && <Check className="w-2.5 h-2.5 text-[#1ca0d1]" />}
          </div>
          <div><div className="text-[12px] font-semibold text-[#1500A0]">{o.t}</div><div className="text-[11px] text-[#7f8c8d]">{o.d}</div></div>
        </button>
      ))}
    </div>
  );
}
