"use client";
/**
 * Selector de ÁMBITO de un acto/línea — fuente única (DRY) usada por Nuevo acto y Presupuestos.
 *
 * El ámbito NO se adivina del nombre: lo dicta el catálogo (`tratamientos.tipo_actuacion`).
 *   diente → por pieza (FDI) · arcada → sup/inf · cuadrante → 1-4 · sextante → 1-6 · tratamiento → general (sin pieza)
 *
 * - `lockScope` (desde el catálogo) BLOQUEA el ámbito y solo deja elegir las opciones dentro
 *   (es lo que pasa en Nuevo acto: el tratamiento manda).
 * - Sin `lockScope` el ámbito es libre (selector completo) — modo histórico de Presupuestos.
 */

// Ámbito, de menor a mayor: diente, sextante (1-6), cuadrante (1-4 FDI),
// hemiarcada (der/izq), arcada (sup/inf) o boca completa.
export type Scope = "pieza" | "sextante" | "cuadrante" | "hemiarcada" | "arcada" | "boca";

export const scopeOf = (l: { pieza: string; zona_boca: string | null }): Scope => {
  const z = l.zona_boca?.split(",")[0];   // varias zonas separadas por coma → el ámbito lo da la 1ª
  return z?.startsWith("sextante") ? "sextante"
    : z?.startsWith("cuadrante") ? "cuadrante"
      : z?.startsWith("hemiarcada") ? "hemiarcada"
        : z?.startsWith("arcada") ? "arcada"
          : z === "boca_completa" ? "boca" : "pieza";
};

// Valor por defecto al elegir cada ámbito.
export const ZONA_DEFECTO: Record<Scope, string | null> = {
  pieza: null, sextante: "sextante_1", cuadrante: "cuadrante_1",
  hemiarcada: "hemiarcada_derecha", arcada: "arcada_superior", boca: "boca_completa",
};

// Etiqueta corta para el badge de ámbito (cabe en la columna estrecha junto a los chips).
const SCOPE_LABEL_SHORT: Record<Scope, string> = {
  pieza: "Pieza", sextante: "Sext", cuadrante: "Cuad", hemiarcada: "Hemi", arcada: "Arc", boca: "Boca",
};

/** Ámbito del catálogo (`tipo_actuacion`) → Scope bloqueado. "general" = acto sin pieza. */
export function scopeDeCatalogo(tipo_actuacion?: string | null): Scope | "general" | null {
  switch ((tipo_actuacion || "").toLowerCase()) {
    case "diente": return "pieza";
    case "arcada": return "arcada";
    case "cuadrante": return "cuadrante";
    case "sextante": return "sextante";
    case "tratamiento": return "general";
    default: return null;   // sin definir → libre
  }
}

/** Valor inicial de {pieza, zona_boca} para un ámbito recién fijado por el catálogo. */
export function valorInicialAmbito(amb: Scope | "general" | null): { pieza: string; zona_boca: string | null } {
  if (!amb || amb === "general" || amb === "pieza") return { pieza: "", zona_boca: null };
  return { pieza: "", zona_boca: ZONA_DEFECTO[amb] };
}

/** Etiqueta de UNA clave de zona. */
function unaZonaLabel(z: string): string {
  if (z.startsWith("sextante_")) return `Sextante ${z.split("_")[1]}`;
  if (z.startsWith("cuadrante_")) return `Cuadrante ${z.split("_")[1]}`;
  if (z === "hemiarcada_derecha") return "Hemiarcada der.";
  if (z === "hemiarcada_izquierda") return "Hemiarcada izq.";
  if (z === "arcada_superior") return "Arcada sup.";
  if (z === "arcada_inferior") return "Arcada inf.";
  if (z === "boca_completa") return "Boca completa";
  return z;
}

/** Etiqueta legible de pieza/zona para tablas (historial, etc.). Varias zonas → "Cuadrante 1, Cuadrante 3". */
export function zonaLabel(pieza: string | null, zona: string | null): string {
  if (pieza) return pieza;
  if (!zona) return "";
  return zona.split(",").filter(Boolean).map(unaZonaLabel).join(", ");
}

const CLS = "border border-[#e5e7eb] focus:border-[#1ca0d1] rounded-sm px-1 py-0.5 text-[11px] outline-none bg-white disabled:opacity-60 disabled:bg-[#FFFFFF]";

export function ZonaEditor({ pieza, zona_boca, onChange, disabled, lockScope }: {
  pieza: string;
  zona_boca: string | null;
  onChange: (p: { pieza: string; zona_boca: string | null }) => void;
  disabled?: boolean;
  lockScope?: Scope | "general" | null;   // si viene del catálogo, fija el ámbito
}) {
  // Acto general (tratamiento sin pieza): no hay nada que elegir.
  if (lockScope === "general") {
    return <span className="text-[11px] text-slate-400 italic px-1 py-0.5">General · sin pieza</span>;
  }

  const locked = !!lockScope;
  const scope: Scope = locked ? (lockScope as Scope) : scopeOf({ pieza, zona_boca });

  // Varias zonas (cuadrantes/sextantes/arcadas) → chips que se pulsan (multi-selección).
  // Se guardan separadas por coma en zona_boca. La pieza sigue siendo texto FDI.
  const tokens = (zona_boca || "").split(",").filter(Boolean);
  const has = (kw: string) => tokens.includes(kw);
  const toggle = (kw: string) => {
    const next = has(kw) ? tokens.filter((t) => t !== kw) : [...tokens, kw];
    onChange({ pieza: "", zona_boca: (next.length ? next : [kw]).join(",") });   // nunca dejar la zona vacía
  };
  const chip = (kw: string, label: string) => (
    <button key={kw} type="button" disabled={disabled} onClick={() => toggle(kw)}
      className={`px-1.5 py-0.5 text-[11px] rounded-sm border transition-colors disabled:opacity-60 ${has(kw)
        ? "bg-[#1500A0] text-white border-[#1500A0] font-semibold"
        : "bg-white text-[#64748b] border-[#e5e7eb] hover:border-[#1ca0d1]"}`}>{label}</button>
  );

  return (
    <div className="flex items-center gap-1 flex-wrap">
      {locked ? (
        <span className="text-[11px] font-semibold text-[#1500A0] bg-[#FFFFFF] border border-[#c7d8ff] rounded-sm px-1.5 py-0.5 whitespace-nowrap">{SCOPE_LABEL_SHORT[scope]}</span>
      ) : (
        <select value={scope} disabled={disabled} className={CLS}
          onChange={(e) => { const s = e.target.value as Scope; onChange({ pieza: "", zona_boca: ZONA_DEFECTO[s] }); }}>
          <option value="pieza">Pieza</option>
          <option value="sextante">Sextante</option>
          <option value="cuadrante">Cuadrante</option>
          <option value="hemiarcada">Hemiarcada</option>
          <option value="arcada">Arcada</option>
          <option value="boca">Boca</option>
        </select>
      )}

      {scope === "pieza" && (
        <input value={pieza} disabled={disabled} onChange={(e) => onChange({ pieza: e.target.value, zona_boca: null })} placeholder="Nº"
          className={`${CLS} w-16 text-center font-semibold text-[#1500A0]`} />
      )}
      {scope === "sextante" && [1, 2, 3, 4, 5, 6].map((n) => chip(`sextante_${n}`, String(n)))}
      {scope === "cuadrante" && [1, 2, 3, 4].map((n) => chip(`cuadrante_${n}`, String(n)))}
      {scope === "hemiarcada" && <>{chip("hemiarcada_derecha", "Der")}{chip("hemiarcada_izquierda", "Izq")}</>}
      {scope === "arcada" && <>{chip("arcada_superior", "Sup")}{chip("arcada_inferior", "Inf")}</>}
    </div>
  );
}
