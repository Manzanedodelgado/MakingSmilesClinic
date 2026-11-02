"use client";
/**
 * Estética 3D "clay" de INICIO (referencia: Uploads/Captura 2026-10-11 1.37.53): tablero azul
 * perforado, medallones en relieve con iconos azules, piezas blandas y brillantes.
 * Misma API que ClinicalCard / ClinicalButton / SectionHeader para no tocar la lógica de la página.
 */
import type { CSSProperties, ElementType, ReactNode } from "react";

export const TABLERO: CSSProperties = {
  backgroundColor: "#2F38E6",
  backgroundImage:
    "radial-gradient(rgba(9,14,120,0.45) 1.3px, transparent 1.8px), radial-gradient(120% 90% at 20% 0%, #4A55FF 0%, #2F38E6 55%, #2229C9 100%)",
  backgroundSize: "16px 16px, 100% 100%",
};

export const PIZARRA: CSSProperties = {
  background: "linear-gradient(160deg, #D8F3FF 0%, #A9E2FF 100%)",
  boxShadow: "inset 0 2px 0 rgba(255,255,255,.9), inset 0 -4px 0 rgba(20,90,170,.18), 0 16px 30px -12px rgba(8,12,110,.6)",
};

type Tono = "cian" | "melocoton" | "crema" | "lavanda";
const TONOS: Record<Tono, string> = {
  cian: "radial-gradient(circle at 32% 26%, #C9F4FF 0%, #6FDCFF 42%, #1FB3EC 100%)",
  melocoton: "radial-gradient(circle at 32% 26%, #FFE9FA 0%, #F09AE8 45%, #C026D3 100%)",
  crema: "radial-gradient(circle at 32% 26%, #FFFBE8 0%, #F6E7A8 45%, #E2C55E 100%)",
  lavanda: "radial-gradient(circle at 32% 26%, #F1F2FF 0%, #C4C9FF 45%, #8F99FF 100%)",
};

/** Medallón en relieve con el icono azul brillante. */
export function Medallon({ icon: Icon, tono = "cian", size = 22 }: { icon: ElementType; tono?: Tono; size?: number }) {
  return (
    <span aria-hidden className="relative grid shrink-0 place-items-center rounded-full"
      style={{
        width: size, height: size, background: TONOS[tono],
        boxShadow: "inset 0 2px 2px rgba(255,255,255,.85), inset 0 -3px 5px rgba(0,0,0,.16), 0 4px 8px -2px rgba(8,12,110,.45)",
      }}>
      <Icon className="text-[#2B4BFF]" style={{ width: size * 0.5, height: size * 0.5, filter: "drop-shadow(0 1.5px 0 rgba(255,255,255,.7)) drop-shadow(0 2px 2px rgba(10,20,140,.35))" }} strokeWidth={2.4} />
    </span>
  );
}

export function ClayCard({ children, className = "", compact = false }: { children: ReactNode; className?: string; compact?: boolean; noPadding?: boolean }) {
  return (
    <div className={`min-w-0 rounded-xl ${compact ? "p-1.5" : "p-3"} ${className}`}
      style={{
        background: "#FFFFFF",
        boxShadow: "inset 0 2px 0 rgba(255,255,255,.95), inset 0 -3px 0 rgba(30,50,170,.10), 0 14px 26px -12px rgba(6,10,100,.65)",
      }}>
      {children}
    </div>
  );
}

export function ClayHeader({ title, icon, tono, action }: { title: string; icon?: ElementType; tono?: Tono; action?: ReactNode; className?: string }) {
  return (
    <div className="mb-2 flex items-center gap-2">
      {icon && <Medallon icon={icon} tono={tono} />}
      <h2 className="text-[12px] font-semibold uppercase tracking-wide text-[#1A2290]">{title}</h2>
      {action && <div className="ml-auto">{action}</div>}
    </div>
  );
}

type Variante = "primary" | "secondary" | "save" | "accent" | "danger" | "ghost" | "nuevo";
const PIEZA: Record<"amarillo" | "blanco" | "teal" | "azul", { bg: string; fg: string; borde: string }> = {
  amarillo: { bg: "linear-gradient(180deg, #FFEC8A 0%, #F4CB3E 100%)", fg: "#1A2290", borde: "rgba(150,110,0,.35)" },
  blanco: { bg: "linear-gradient(180deg, #FFFFFF 0%, #E9EEFF 100%)", fg: "#1A2290", borde: "rgba(30,50,170,.22)" },
  teal: { bg: "linear-gradient(180deg, #8AF2E2 0%, #1ca0d1 100%)", fg: "#0E2A86", borde: "rgba(10,120,105,.40)" },
  azul: { bg: "linear-gradient(180deg, #5B66FF 0%, #2F38E6 100%)", fg: "#FFFFFF", borde: "rgba(10,14,110,.55)" },
};
const DE_VARIANTE: Record<Variante, keyof typeof PIEZA> = {
  primary: "amarillo", accent: "azul", danger: "azul", save: "teal", secondary: "blanco", ghost: "blanco", nuevo: "blanco",
};

export function ClayButton({ children, variant = "primary", icon: Icon, disabled, onClick, title, className = "", type = "button" }: {
  children?: ReactNode; variant?: Variante; icon?: ElementType; disabled?: boolean; onClick?: () => void; title?: string; className?: string;
  type?: "button" | "submit"; size?: "sm" | "md"; iconPosition?: "left" | "right";
}) {
  const p = PIEZA[DE_VARIANTE[variant]];
  return (
    <button type={type} onClick={onClick} disabled={disabled} title={title}
      className={`inline-flex items-center justify-center gap-1 px-2.5 py-1 rounded-full text-[12px] font-semibold uppercase tracking-wider whitespace-nowrap cursor-pointer
        transition-[transform,box-shadow,filter] duration-150 ease-out hover:brightness-[1.04] active:translate-y-[2px]
        [box-shadow:inset_0_2px_0_rgba(255,255,255,.75),inset_0_-3px_0_var(--b),0_5px_10px_-4px_rgba(6,10,100,.55)]
        active:[box-shadow:inset_0_2px_0_rgba(255,255,255,.6),inset_0_-1px_0_var(--b),0_2px_4px_-2px_rgba(6,10,100,.5)]
        disabled:opacity-45 disabled:cursor-not-allowed disabled:active:translate-y-0
        focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-offset-2 focus-visible:outline-[#FFE36B] ${className}`}
      style={{ background: p.bg, color: p.fg, ["--b" as string]: p.borde }}>
      {Icon && <Icon className="w-3.5 h-3.5" strokeWidth={2.4} />}
      {children}
    </button>
  );
}

/** Fila blanda dentro de una tarjeta. */
export const FILA = "rounded-lg bg-[#FFFFFF] px-2.5 py-1.5 [box-shadow:inset_0_1px_0_rgba(255,255,255,.9),inset_0_-2px_0_rgba(30,50,170,.08)]";
/** Campo hundido (input/select/textarea). */
export const HUNDIDO = "rounded-lg bg-[#FFFFFF] text-[#14213D] text-[12px] px-2 py-1 outline-none border-0 [box-shadow:inset_0_2px_4px_rgba(20,40,150,.18),inset_0_-1px_0_rgba(255,255,255,.9)] focus:[box-shadow:inset_0_2px_4px_rgba(20,40,150,.18),0_0_0_3px_#6FDCFF]";

/* ─────────────── Variante FIEL a la referencia (solo INICIO) ─────────────── */
const PATRON_CHEVRON = (() => {
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' width='18' height='18'><path d='M6 11.6 L9 8.6 L12 11.6' fill='none' stroke='rgba(255,255,255,0.16)' stroke-width='1.3' stroke-linecap='round' stroke-linejoin='round'/><path d='M6 10.4 L9 7.4 L12 10.4' fill='none' stroke='rgba(14,10,110,0.55)' stroke-width='1.3' stroke-linecap='round' stroke-linejoin='round'/></svg>`;
  return `url("data:image/svg+xml,${encodeURIComponent(svg)}")`;
})();

/** Tablero de la referencia: azul violeta con marcas "^" en relieve y luz suave arriba a la izquierda. */
export const TABLERO_REF: CSSProperties = {
  backgroundColor: "#3A3AE6",
  backgroundImage: `${PATRON_CHEVRON}, ${PATRON_CHEVRON}, radial-gradient(130% 100% at 15% 0%, #5050FF 0%, #3A3AE6 50%, #2B2CCB 100%)`,
  backgroundSize: "18px 18px, 18px 18px, 100% 100%",
  backgroundPosition: "0 0, 9px 9px, 0 0",
};

/** Pizarra blanca-celeste con marco azul grueso (como la de la izquierda de la referencia). */
export const PIZARRA_REF: CSSProperties = {
  background: "linear-gradient(165deg, #E9FAFF 0%, #C4EEFF 100%)",
  border: "6px solid #2EA8F2",
  boxShadow: "inset 0 2px 0 rgba(255,255,255,.95), inset 0 0 0 1px rgba(255,255,255,.6), 0 3px 0 #1C86D6, 0 14px 24px -10px rgba(8,10,110,.7)",
};

const CANTO: Record<Tono, string> = { cian: "#139BD6", melocoton: "#A21CAF", crema: "#C9A63E", lavanda: "#6F79EA" };

/** Moneda 3D: medallón con canto visible e icono azul macizo y brillante. Mismo tamaño que Medallon. */
export function Moneda({ icon: Icon, tono = "cian", size = 22 }: { icon: ElementType; tono?: Tono; size?: number }) {
  const canto = Math.max(2, Math.round(size / 11));
  return (
    <span aria-hidden className="relative grid shrink-0 place-items-center rounded-full"
      style={{
        width: size, height: size, background: TONOS[tono],
        boxShadow: `inset 0 0 0 ${Math.max(1, size / 22)}px rgba(255,255,255,.45), inset 0 ${canto}px ${canto}px rgba(255,255,255,.75), inset 0 -${canto}px ${canto * 1.5}px rgba(0,0,0,.14), 0 ${canto}px 0 ${CANTO[tono]}, 0 ${canto * 2}px ${canto * 3}px -${canto}px rgba(8,10,110,.55)`,
      }}>
      <Icon fill="#6E97FF" fillOpacity={0.9} className="text-[#2448E8]"
        style={{ width: size * 0.56, height: size * 0.56, filter: `drop-shadow(0 ${size / 22}px 0 rgba(255,255,255,.75)) drop-shadow(0 ${size / 14}px ${size / 14}px rgba(10,20,140,.45))` }}
        strokeWidth={2.2} />
    </span>
  );
}

/** Cabecera de tarjeta con Moneda (variante fiel; mismas medidas que ClayHeader). */
export function ClayHeaderRef({ title, icon, tono, action }: { title: string; icon?: ElementType; tono?: Tono; action?: ReactNode; className?: string }) {
  return (
    <div className="mb-2 flex items-center gap-2">
      {icon && <Moneda icon={icon} tono={tono} />}
      <h2 className="text-[12px] font-semibold uppercase tracking-wide text-[#1A2290]">{title}</h2>
      {action && <div className="ml-auto">{action}</div>}
    </div>
  );
}

/** Pinza de espuma amarilla perforada (borde derecho de la referencia). Decorativa. */
export function Pinza({ className = "", style }: { className?: string; style?: CSSProperties }) {
  return (
    <span aria-hidden className={`pointer-events-none absolute rounded-l-[10px] rounded-r-[4px] ${className}`}
      style={{
        background: "radial-gradient(rgba(150,110,0,.35) 0.9px, transparent 1.3px) 0 0 / 6px 6px, linear-gradient(90deg, #E9C22E 0%, #FFE45C 45%, #F2CF3A 100%)",
        boxShadow: "inset 0 2px 0 rgba(255,255,255,.55), inset -3px 0 0 rgba(150,110,0,.25), 0 6px 10px -4px rgba(0,0,40,.6)",
        ...style,
      }} />
  );
}

/** Tubo de cristal (trazo SVG translúcido con brillo). Decorativo. */
export function Tubo({ d, ancho = 9, encendido = false }: { d: string; ancho?: number; encendido?: boolean }) {
  return (
    <g fill="none" strokeLinecap="round">
      <path d={d} stroke="rgba(255,255,255,0.20)" strokeWidth={ancho} />
      {encendido && <path d={d} stroke="rgba(111,220,255,0.75)" strokeWidth={ancho - 4} style={{ filter: "drop-shadow(0 0 3px rgba(111,220,255,.9))" }} />}
      <path d={d} stroke="rgba(255,255,255,0.55)" strokeWidth={1.4} transform={`translate(-${ancho / 3.2},0)`} />
      <path d={d} stroke="rgba(255,255,255,0.35)" strokeWidth={1} transform={`translate(${ancho / 3.2},0)`} />
    </g>
  );
}
