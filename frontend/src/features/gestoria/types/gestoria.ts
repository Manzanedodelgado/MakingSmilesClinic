// Tipos del área Gestoría (espejo del backend).

export interface DoctorLiquidacion {
  doctorId: number | null;
  doctor: string;
  email: string | null;
  tratamientos: number;
  implantes: number;
  prodBruta: number;
  acuerdoPct: number;
  comisionBruta: number;
  deduceLaboratorio: boolean;
  gastosLabReales: number;
  baseIrpf: number;
  irpfPct: number;
  deduccionIrpf: number;
  produccionNeta: number;
}

export interface DoctoresResp {
  periodo: { desde: string; hasta: string };
  doctores: number;
  totalTratamientos: number;
  prodBruta: number;
  prodNeta: number;
  data: DoctorLiquidacion[];
}

export interface ActoRealizado {
  id: number;
  fecha: string | null;
  tratamiento: string;
  piezas: string | null;
  doctor: string;
  paciente: string;
  importe: number;
  descuento: number;
  descuentoAplicaDoctor: boolean;
  /** Coste de laboratorio del acto. null = sin informar (distinto de un coste de 0 €). */
  costeLaboratorio: number | null;
  facturado: boolean;
}

export interface PatientTreatment {
  ident: string;
  fecha: string | null;
  concepto: string;
  doctor: string;
  importe: number;
  descuento: number;
  neto: number;
  facturado: boolean;
  facturaNumero: string | null;
  abonado: boolean;
}

export interface PatientTreatmentsResp {
  paciente: { id: number; nombre: string; nif: string | null };
  data: PatientTreatment[];
}

export interface Dashboard {
  periodo: { desde: string; hasta: string };
  ingresos: number;
  gastos: number;
  balance: number;
  facturasEmitidas: number;
}

export interface FacturaEmitida {
  id: number;
  numero: string;
  fecha: string;
  cliente: string;
  nif: string | null;
  concepto: string | null;
  estado: string;
  verifactu: boolean;
}

export interface Gasto {
  id: number;
  fecha: string;
  proveedor: string | null;
  cifEmisor?: string | null;
  incidencia?: string | null;
  concepto: string | null;
  numeroFactura: string | null;
  baseImponible: number;
  ivaPct: number;
  retencion?: number;
  suplido?: number;
  total: number;
  divisa?: string | null;
  tipoDocumento?: string | null;
  estado: string;
  formaPago?: string | null;
  archivoPdfUrl: string | null;
  correoUrl?: string | null;
  /** Plazo o cuenta que traía la factura ("Vencimiento 30 días"): NO es forma de pago. */
  condicionesPago?: string | null;
  movimientoId?: number | null;
  movimientoConcepto?: string | null;
  /** Nº de facturas que comparten ese apunte. >1 ⇒ el pago fue unificado. */
  movimientoFacturas?: number;
}

export interface Proveedor {
  id: number;
  nombre: string;
  cif: string | null;
  emailContacto: string | null;
  telefono: string | null;
  direccion: string | null;
  iban: string | null;
  categoria: string | null;
  formaPago: string | null;
  esLaboratorio: boolean;
  numFacturas: number;
}

export interface Vencimiento {
  modelo: string;
  periodo: string;
  descripcion: string;
  fechaLimite: string;
  estado: "pendiente" | "vencido" | "presentado";
  cuota: number | null;
  id: number | null;
}

export interface PagoPaciente {
  id: number;
  fecha: string;
  nombre: string | null;
  apellidos: string | null;
  paciente: string;
  importe: number;
  esDevolucion: boolean;
  formaPago: string | null;
  numRecibo: string | null;
  movimientoId: number | null;
  movimientoConcepto: string | null;
  liquidado: boolean;
  liquidacionId: number | null;
  liquidacionConcepto: string | null;
}

/** Factura (o pago) REAL a la que está conciliado un apunte bancario. */
export interface MovimientoAsociado {
  tipo: "factura" | "pago";
  id: number;
  proveedor: string | null;
  numero: string | null;
  fecha: string | null;
  total: number;
  tienePdf: boolean;
  /** Presente solo si el apunte pagó VARIAS facturas de golpe (pago unificado). */
  unificado?: { id: number; numero: string | null; fecha: string | null; total: number; tienePdf: boolean }[];
  totalUnificado?: number;
}

export interface Movimiento {
  id: number;
  fechaOperacion: string;
  conceptoBanco: string;
  /** Literal del extracto, presente SOLO si el concepto se ha corregido a mano. */
  conceptoOriginal?: string | null;
  importe: number;
  categoria: string | null;
  estadoConcil: string;
  tipo: "debe" | "haber";
  gastoId: number | null;
  pagoId: number | null;
  documentoAdminId: number | null;
  asociado: MovimientoAsociado | null;
}

/** Fichero de extracto bancario archivado tal cual se subió (soporte para la asesoría). */
export interface Extracto {
  id: number;
  nombre: string;
  fecha: string | null;
  tamano: number;
  mime: string | null;
  subidoPor: string;
  importados: number;
  omitidos: number;
}

export interface ModeloFiscal {
  id: number;
  modelo: string;
  ejercicio: number;
  periodo: string;
  estado: string;
  fechaLimite: string | null;
  cuota: number | null;
}

export interface RevisionItem {
  movimientoId: number;
  fecha: string;
  concepto: string;
  importe: number;
  pide: string;      // dato que la herramienta solicita (hoy: "interes")
  motivo: string;
}

export interface PacienteBusqueda {
  id: number;
  nombre: string;
  apellidos: string;
  num_historia: string | null;
}

// Archivo histórico de facturas (libros 2019-2024) — tabla aislada, solo consulta.
export interface FacturaHistorica {
  id: number;
  anio: number;
  mes: number | null;
  numFactura: string | null;
  fecha: string | null;
  abonada: string | null;
  areaGasto: string | null;
  proveedor: string | null;
  nif: string | null;
  detalle: string | null;
  base: number | null;
  iva: number | null;
  retencion: number | null;
  total: number | null;
  formaPago: string | null;
  origen: "libro" | "pdf";
  tienePdf: boolean;
}
