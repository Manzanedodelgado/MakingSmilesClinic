// Tipos del editor de informes. Alineados con backend/api/informes_router.py + informes_catalogo.py.

export type TipoCampo = "texto" | "numero" | "fecha" | "bool";

export interface CampoCatalogo {
  key: string;
  label: string;
  tipo: TipoCampo;
  operadores: string[];   // claves de operador válidas para ese tipo
}

export interface RelacionCatalogo {
  key: string;
  label: string;
  campos: CampoCatalogo[];
}

export interface EntidadCatalogo {
  key: string;
  label: string;
  por_defecto: string[];  // columnas marcadas al abrir la entidad
  campos: CampoCatalogo[];
  relaciones?: RelacionCatalogo[];   // para filtros TIENE / NO TIENE … que cumplen …
}

// Filtro de relación: pacientes que TIENEN / NO TIENEN [relación] que cumple [subfiltros].
export interface RelFiltro {
  relacion: string;
  modo: "tiene" | "no_tiene";
  subfiltros: Filtro[];
}

export interface OperadorMeta {
  label: string;
  args: number;            // nº de valores que pide (0, 1 o 2)
  unidad?: boolean;        // pide unidad (días/meses/años)
  input?: string;          // "fecha" → input de fecha
}

export interface Catalogo {
  entidades: EntidadCatalogo[];
  operadores: Record<string, OperadorMeta>;
}

export interface Filtro {
  campo: string;
  op: string;
  valor?: string | number | null;
  valor2?: string | number | null;
  unidad?: string | null;  // dias | meses | anios
}

export interface Orden {
  campo: string;
  dir: "asc" | "desc";
}

export interface DefinicionInforme {
  columnas: string[];
  filtros: Filtro[];
  orden: Orden[];
  relaciones?: RelFiltro[];
  limite?: number | null;
}

export interface ConsultaInforme extends DefinicionInforme {
  entidad?: string;
  tabla?: string;
}

// Origen del informe: vista curada (entidad) o tabla cruda.
export interface TablaResumen { nombre: string; label: string; }
export interface CamposTabla { campos: CampoCatalogo[]; por_defecto: string[]; }

export interface ColumnaResultado {
  key: string;
  label: string;
  tipo: TipoCampo;
  tabla?: string;   // solo en informes multi-tabla
  campo?: string;
}

// ── Informe MULTI-TABLA (columnas de varias tablas, joins automáticos por FK) ──
export interface MultiCol { tabla: string; campo: string; tipo: TipoCampo; label: string; operadores: string[]; }
export interface MultiFiltro { tabla: string; campo: string; op: string; valor?: string | number | null; valor2?: string | number | null; unidad?: string | null; }
export interface MultiOrden { tabla: string; campo: string; dir: "asc" | "desc"; }
export interface ConsultaMulti {
  columnas: { tabla: string; campo: string }[];
  filtros: MultiFiltro[];
  orden: MultiOrden[];
  limite?: number | null;
}

export interface ResultadoInforme {
  columnas: ColumnaResultado[];
  filas: Record<string, unknown>[];
  total: number;
  limite: number;
  truncado: boolean;
}

export interface InformeGuardadoResumen {
  id: number;
  nombre: string;
  descripcion: string | null;
  entidad: string;
  actualizado: string | null;
}

export interface OrigenSel { tipo: "ent" | "tab" | "multi"; key: string; }
export interface InformeGuardado {
  id: number;
  nombre: string;
  descripcion: string | null;
  entidad: string;
  definicion: DefinicionInforme & PivoteConfig & { modo?: ModoInforme; sel?: OrigenSel };
}

// ── Tabla dinámica (pivot) ──
export type ModoInforme = "lista" | "pivote";
export type Agregacion = "count" | "sum" | "avg" | "min" | "max";

export interface Medida {
  agg: Agregacion;
  campo?: string | null;
}

export interface PivoteConfig {
  filas?: string[];
  columna?: string | null;
  medida?: Medida;
}

export interface ConsultaPivote {
  entidad?: string;
  tabla?: string;
  filas: string[];
  columna?: string | null;
  medida: Medida;
  filtros: Filtro[];
}

export interface FilaPivote {
  [campo: string]: unknown;
  __celdas?: Record<string, number | null>;  // valor_columna → medida (modo cruzado)
  __total?: number | null;                    // total de la fila (modo cruzado)
  __val?: number | null;                      // medida (modo agrupado sin columna)
}

export interface ResultadoPivote {
  dimensiones: { key: string; label: string }[];
  columnas: { valor: string; label: string }[] | null;
  medida_label: string;
  medida_tipo: TipoCampo;
  filas: FilaPivote[];
  n_filas: number;
}
