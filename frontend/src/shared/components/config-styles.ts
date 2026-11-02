/**
 * config-styles.ts — Fuente única de verdad para estilos de Config.
 * Portado verbatim del estándar SmilePro para garantizar estética idéntica.
 * TODOS los ficheros de Config importan de aquí. Cero estilos ad-hoc.
 */

// ── Tipografía ──────────────────────────────────────────────────
export const LABEL = "text-[10px] text-[#1ca0d1] uppercase tracking-wide block mb-0.5 font-semibold";
export const DESC = "text-[11px] text-slate-500 leading-relaxed";
export const SECTION_SUB = "text-[12px] text-[#1500A0] mb-3";
export const CELL = "text-[12px] text-slate-600";
export const CELL_HEADER = "text-[11px] font-semibold text-[#1ca0d1] uppercase";
export const MONO = "text-[12px] font-mono text-[#1500A0]";
export const EMPTY = "text-[12px] text-slate-400 italic";

// ── Inputs ──────────────────────────────────────────────────────
const INPUT_BASE =
  "border border-[#e5e7eb] rounded-sm outline-none bg-white text-[#333333] hover:border-[#cbd5e1] focus:border-[#1ca0d1] focus:ring-1 focus:ring-[#1ca0d1]/20 transition-all duration-150";

export const INPUT = `w-full ${INPUT_BASE} text-[12px] px-2 py-1`;
export const INPUT_NARROW = `${INPUT_BASE} text-[12px] px-2 py-1`;
export const SELECT = `w-full ${INPUT_BASE} text-[12px] px-2 py-1 cursor-pointer`;
export const TEXTAREA = `w-full ${INPUT_BASE} text-[12px] px-2 py-1.5 resize-none`;

// ── Layout ──────────────────────────────────────────────────────
export const GRID2 = "grid grid-cols-1 md:grid-cols-2 gap-2.5";
export const GRID3 = "grid grid-cols-1 md:grid-cols-3 gap-2.5";
export const GRID4 = "grid grid-cols-2 md:grid-cols-4 gap-2.5";
export const ROW_BG = "bg-[#FFFFFF] border border-[#e5e7eb] rounded-sm px-2.5 py-1.5";

// ── Colores semánticos (excepciones, estados) ───────────────────
export const DANGER_TAG = "bg-[#FFFFFF] border border-[#E9A8F5] text-[#C026D3]";
export const INFO_TAG = "bg-[#FFFFFF] border border-[#7dd3fc] text-[#0369a1]";
export const SUCCESS_TAG = "bg-[#FFFFFF] border border-[#9FE6DB] text-[#0F8C7D]";

// ── Tabs ────────────────────────────────────────────────────────
export const TAB_ACTIVE = "text-[#1500A0] border-b-2 border-[#1ca0d1]";
export const TAB_INACTIVE = "text-slate-400 hover:text-slate-600 border-b-2 border-transparent";
export const TAB_BASE = "pb-2 text-[12px] uppercase tracking-widest transition-colors cursor-pointer";
