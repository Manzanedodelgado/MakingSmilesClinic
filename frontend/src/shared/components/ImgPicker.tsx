"use client";
import { ImageIcon } from "lucide-react";
import { useRef } from "react";

/** Selector de imagen reutilizable (preview + subir + quitar). Usado en Config > Clínica > Centro
 * y en Superuser > Apariencia — misma UI para "una imagen = un campo" en todo el proyecto. */
export function ImgPicker({ label, url, onPick, onClear }: { label: string; url: string; onPick: (f?: File) => void; onClear: () => void }) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <div className="flex flex-col gap-1 p-2 border border-[#e5e7eb] bg-[#FFFFFF] rounded-sm">
      <span className="text-[10px] font-semibold text-[#1ca0d1] uppercase tracking-wide block truncate">{label}</span>
      <div className="w-full h-9 bg-white border border-[#e5e7eb] flex items-center justify-center overflow-hidden shrink-0 rounded-sm relative group">
        {url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={url} alt={label} className="max-w-full max-h-full object-contain" />
        ) : (
          <ImageIcon className="w-5 h-5 text-[#7f8c8d]" />
        )}
        {url && (
          <button onClick={onClear} className="absolute inset-0 bg-[#1500A0]/80 text-white text-[10px] font-semibold opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
            Quitar
          </button>
        )}
      </div>
      <input type="file" accept="image/*" ref={ref}
        onChange={(e) => { onPick(e.target.files?.[0]); e.target.value = ""; }}
        className="block w-full text-[10px] text-[#7f8c8d] file:mr-2 file:py-0.5 file:px-2 file:rounded-sm file:border-0 file:text-[10px] file:font-semibold file:bg-[#2DD9C3] file:text-[#1500A0] hover:file:bg-[#20BEAB] cursor-pointer" />
    </div>
  );
}
