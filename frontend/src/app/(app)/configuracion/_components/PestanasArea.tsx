"use client";
import { conPestana, conSeccion, type TabDef } from "./NivelPicker";

/** Pestañas de un área con sus secciones: se elige a cuáles se accede. Con `techo` (el rol de la
 * persona) lo que el rol no incluye aparece tachado y no se puede activar. */
export function PestanasArea({ tabs, permisos, techo, onChange }: {
  tabs: TabDef[]; permisos: string[]; techo?: string[] | null; onChange: (nuevos: string[]) => void;
}) {
  const fuera = (c: string) => !!techo && !techo.includes(c);
  const chip = (on: boolean, off: boolean, fuerte: boolean) =>
    `px-2.5 py-1 rounded-sm border text-[11.5px] font-semibold transition-colors ${
      off ? "bg-white text-[#cbd5e1] border-[#e5e7eb] cursor-not-allowed line-through"
        : on ? (fuerte ? "bg-[#1500A0] text-white border-[#1500A0]" : "bg-[#1ca0d1] text-white border-[#1ca0d1]")
          : "bg-white text-[#94a3b8] border-[#e5e7eb] hover:border-[#1ca0d1]"}`;
  return (
    <div className="px-3 pb-2.5 pt-1 bg-[#FFFFFF] flex flex-col gap-1.5">
      {tabs.map((t) => {
        const on = permisos.includes(t.codigo);
        return (
          <div key={t.codigo} className="flex flex-wrap items-center gap-1.5">
            <button type="button" disabled={fuera(t.codigo)} aria-pressed={on} className={chip(on, fuera(t.codigo), true)}
              title={fuera(t.codigo) ? "Su rol no incluye esta pestaña" : undefined}
              onClick={() => onChange(conPestana(t, permisos, !on, techo))}>{t.nombre}</button>
            {(t.subs ?? []).map((x) => {
              const sOn = permisos.includes(x.codigo);
              return (
                <button key={x.codigo} type="button" disabled={fuera(x.codigo)} aria-pressed={sOn} className={chip(sOn, fuera(x.codigo), false)}
                  title={fuera(x.codigo) ? "Su rol no incluye esta sección" : undefined}
                  onClick={() => onChange(conSeccion(t, x.codigo, permisos, !sOn))}>{x.nombre}</button>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}
