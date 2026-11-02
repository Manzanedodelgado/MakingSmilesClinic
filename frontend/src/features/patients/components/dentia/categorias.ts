/** DentIA — categorías de patrón (panel «Patrones»), colores (paleta del proyecto: sin rojo, naranja ni verde)
 *  y opciones de tratamiento sugeridas por hallazgo. */
export interface Categoria {
  clave: string; nombre: string; color: string;
  tipo: "linea" | "area";            // línea abierta (hueso) o polígono cerrado
  ia?: boolean;                      // la IA actual sabe proponerla
  pendiente?: string;                // sin modelo: solo marcado manual (texto del aviso)
}

export const CATEGORIAS: Record<string, Categoria> = {
  linea_osea:              { clave: "linea_osea", nombre: "Línea ósea", color: "#D946EF", tipo: "linea" },
  linea_periodontal:       { clave: "linea_periodontal", nombre: "Línea periodontal", color: "#0891B2", tipo: "linea" },
  l_osea_periodontal:      { clave: "l_osea_periodontal", nombre: "L. ósea - L. periodontal", color: "#22D3EE", tipo: "area" },
  senos_maxilares:         { clave: "senos_maxilares", nombre: "Senos maxilares", color: "#EAB308", tipo: "area", ia: true },
  nervios_mandibulares:    { clave: "nervios_mandibulares", nombre: "Nervios mandibulares", color: "#7C3AED", tipo: "area", ia: true },
  atm:                     { clave: "atm", nombre: "ATM - Articulación temporomandibular", color: "#A78BFA", tipo: "area" },
  radiolucencia:           { clave: "radiolucencia", nombre: "Radiolucencia", color: "#C026D3", tipo: "area" },
  radiolucidez_periapical: { clave: "radiolucidez_periapical", nombre: "Radiolucidez periapical", color: "#F472B6", tipo: "area" },
  ausencia:                { clave: "ausencia", nombre: "Ausencia", color: "#94A3B8", tipo: "area" },
  restos_radiculares:      { clave: "restos_radiculares", nombre: "Restos radiculares", color: "#0F8C7D", tipo: "area" },
  incluido_impactado:      { clave: "incluido_impactado", nombre: "Diente incluido / impactado", color: "#FF007F", tipo: "area", ia: true },
  pontico:                 { clave: "pontico", nombre: "Póntico", color: "#FBBF24", tipo: "area" },
  corona:                  { clave: "corona", nombre: "Corona", color: "#CA8A04", tipo: "area" },
  implante:                { clave: "implante", nombre: "Implante", color: "#21A2E5", tipo: "area" },
  obturacion:              { clave: "obturacion", nombre: "Obturación", color: "#065AED", tipo: "area" },
  endodoncia:              { clave: "endodoncia", nombre: "Endodoncia", color: "#20BEAB", tipo: "area" },
};

/** Disposición del panel inferior (columnas, como en dentIA). */
export const GRUPOS: string[][] = [
  ["linea_osea", "linea_periodontal", "l_osea_periodontal"],
  ["senos_maxilares", "nervios_mandibulares", "atm"],
  ["radiolucencia", "radiolucidez_periapical"],
  ["ausencia", "restos_radiculares", "incluido_impactado"],
  ["pontico", "corona", "implante", "obturacion", "endodoncia"],
];

/** Opciones de tratamiento por hallazgo: etiqueta + texto con el que se busca en el catálogo de la tarifa. */
export interface OpcionTrat { etiqueta: string; q: string }
const OPC_CARIES: OpcionTrat[] = [
  { etiqueta: "Obturación", q: "obtur" }, { etiqueta: "Obturación + Endodoncia", q: "endodon" }, { etiqueta: "Exodoncia", q: "exodon" },
];
export const OPCIONES: Record<string, OpcionTrat[]> = {
  radiolucencia: OPC_CARIES,
  radiolucidez_periapical: [{ etiqueta: "Endodoncia", q: "endodon" }, { etiqueta: "Exodoncia", q: "exodon" }, { etiqueta: "Cirugía apical", q: "apic" }],
  obturacion: [{ etiqueta: "Reobturación", q: "obtur" }, { etiqueta: "Endodoncia", q: "endodon" }, { etiqueta: "Exodoncia", q: "exodon" }],
  endodoncia: [{ etiqueta: "Reendodoncia", q: "endodon" }, { etiqueta: "Corona", q: "corona" }, { etiqueta: "Exodoncia", q: "exodon" }],
  ausencia: [{ etiqueta: "Implante", q: "implante" }, { etiqueta: "Puente", q: "puente" }, { etiqueta: "Prótesis", q: "protesis" }],
  restos_radiculares: [{ etiqueta: "Exodoncia de resto radicular", q: "resto" }, { etiqueta: "Exodoncia", q: "exodon" }],
  incluido_impactado: [{ etiqueta: "Exodoncia cordal", q: "cordal" }, { etiqueta: "Exodoncia quirúrgica", q: "exodon" }],
  corona: [{ etiqueta: "Corona", q: "corona" }, { etiqueta: "Endodoncia", q: "endodon" }],
  implante: [{ etiqueta: "Implante", q: "implante" }, { etiqueta: "Corona sobre implante", q: "corona" }],
  pontico: [{ etiqueta: "Puente", q: "puente" }],
};
export const OPCIONES_DEFECTO: OpcionTrat[] = [
  { etiqueta: "Obturación", q: "obtur" }, { etiqueta: "Endodoncia", q: "endodon" }, { etiqueta: "Exodoncia", q: "exodon" },
  { etiqueta: "Corona", q: "corona" }, { etiqueta: "Implante", q: "implante" },
];

/** Hallazgos sobre los que se planifica tratamiento (los de «Sanos», piezas y estructuras no se tratan). */
export const PLANIFICABLES = new Set(Object.keys(CATEGORIAS).filter((k) =>
  !["senos_maxilares", "nervios_mandibulares", "atm", "linea_osea", "linea_periodontal", "l_osea_periodontal"].includes(k)));

export const nuevoId = () => Math.random().toString(36).slice(2, 10);
