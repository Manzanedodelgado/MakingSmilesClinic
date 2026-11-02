"use client";
/** Galería de iconos — set en color del centro en /public/icons/color (1 PNG por icono). */

const ICONOS = [
  "diente", "caries", "corona", "brackets", "taladro", "herramientas",
  "jeringa", "estetoscopio", "pastilla", "suero", "corazon-manos",
  "silla-dental", "dentista", "clinica",
];

export default function IconosPage() {
  return (
    <div className="flex-1 overflow-y-auto bg-white p-6">
      <div className="mb-4">
        <h1 className="text-[16px] font-semibold text-[#065AED] uppercase tracking-wide">Iconos</h1>
        <p className="text-[12px] text-slate-500 mt-1">{ICONOS.length} iconos en color en <code className="text-[#1500A0]">/public/icons/color/</code>. Uso: <code className="text-[#1500A0]">{'<img src="/icons/color/diente.png" />'}</code></p>
      </div>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(120px,1fr))] gap-3">
        {ICONOS.map((n) => (
          <div key={n} className="flex flex-col items-center gap-2 border border-[#e5e7eb] rounded-lg p-4 hover:bg-[#E6EDFF] transition-colors">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={`/icons/color/${n}.png`} alt={n} width={56} height={56} />
            <span className="text-[11px] font-semibold text-[#1500A0] text-center break-all">{n}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
