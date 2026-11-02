"use client";
import { X, Search } from "lucide-react";

/** Buscador de tabla reutilizable (mismo estilo en todas las pestañas de Gestoría). Muestra una
 * X para vaciar el contenido en cuanto hay texto escrito. */
export function Buscador({ value, onChange, placeholder = "Buscar…", className = "w-52" }: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  className?: string;
}) {
  return (
    <div className={`relative ${className}`}>
      <Search className="w-3.5 h-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
      <input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder}
        className="w-full pl-7 pr-6 py-1 border border-[#e5e7eb] rounded-sm text-[11px]" />
      {value && (
        <button type="button" onClick={() => onChange("")} aria-label="Limpiar búsqueda"
          className="absolute right-1.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-[#065AED]">
          <X className="w-3.5 h-3.5" />
        </button>
      )}
    </div>
  );
}

/** True si la consulta está vacía o alguno de los campos la contiene (sin distinguir mayúsculas). */
export const coincide = (q: string, ...campos: (string | number | null | undefined)[]) => {
  const t = q.trim().toLowerCase();
  return !t || campos.some((c) => String(c ?? "").toLowerCase().includes(t));
};
