"use client";
import { X, Search } from "lucide-react";

export type EstadoFiltro = "activos" | "inactivos" | "todos";
const TABS: { id: EstadoFiltro; label: string }[] = [
  { id: "activos", label: "Activos" },
  { id: "inactivos", label: "Inactivos" },
  { id: "todos", label: "Todos" },
];

/**
 * Cabecera de filtro de listas de Config (Personal/Colaboradores) — réplica del
 * estándar SmilePro: buscador + pestañas Activos/Inactivos/Todos + contador.
 */
export function ListFilter({
  search, onSearch, estado, onEstado, count, sustantivo,
}: {
  search: string; onSearch: (v: string) => void;
  estado: EstadoFiltro; onEstado: (e: EstadoFiltro) => void;
  count: number; sustantivo: string;
}) {
  return (
    <div className="border-b border-[#e5e7eb]">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-[#e5e7eb]">
        <Search className="w-3.5 h-3.5 text-[#7f8c8d] shrink-0" />
        <input
          value={search}
          onChange={(e) => onSearch(e.target.value)}
          placeholder="Buscar…"
          className="text-[12px] outline-none bg-transparent w-full text-[#333] placeholder:text-[#c5cbd3]"
        />
        {search && (
          <button type="button" onClick={() => onSearch("")} className="shrink-0 text-[#7f8c8d] hover:text-[#C026D3]">
            <X className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
      <div className="flex items-center px-1">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => onEstado(t.id)}
            className={`px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider border-b-2 transition-colors ${
              estado === t.id
                ? "text-[#1500A0] border-[#1ca0d1]"
                : "text-[#7f8c8d] border-transparent hover:text-[#1500A0]"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div className="px-3 py-1 bg-[#FFFFFF] text-[10px] text-[#7f8c8d] uppercase tracking-wide">
        {count} {sustantivo}
      </div>
    </div>
  );
}
