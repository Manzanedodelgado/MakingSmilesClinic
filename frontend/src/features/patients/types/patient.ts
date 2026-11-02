// Tipos del área Pacientes. Alineados 1:1 con backend/api/pacientes_router.py (BBDD nueva).

export interface PacienteBusqueda {
  id: number;
  num_historia: string | null;
  nombre: string;
  apellidos: string;
  nif: string | null;
  telefono: string | null;
}

export interface PacienteCabecera {
  id: number;
  num_historia: string | null;
  nombre: string;
  apellidos: string;
  nif: string | null;
  edad: number | null;
  telefono_movil: string | null;
  tarifa: string | null;
  alertas_activas: number;
  alertas_lista: string[];
  activo: boolean;
}

export interface TarifasPaciente {
  catalogo: { id: number; nombre: string }[];
  asignadas: number[];
}

export interface Filiacion {
  id: number;
  tiene_foto: boolean;
  num_historia: string | null;
  nombre: string | null;
  apellidos: string | null;
  nif: string | null;
  fecha_nacimiento: string | null;
  direccion: string | null;
  cp: string | null;
  poblacion_id: number | null;
  telefono_fijo: string | null;
  telefono_fijo2: string | null;
  telefono_movil: string | null;
  email: string | null;
  descuento: number | null;
  notas: string | null;
  fecha_alta: string | null;
  acepta_lopd: boolean;
  acepta_info: boolean;
  acepta_whatsapp: boolean;
  acepta_bots: boolean;
  activo: boolean;
  edad: number | null;
  // Responsable legal + datos médicos → columnas propias de pacientes.
  responsable_nombre: string | null;
  responsable_nif: string | null;
  responsable_parentesco: string | null;
  grupo_sanguineo: string | null;
  peso: number | null;
  altura: number | null;
  medico_cabecera: string | null;
  tel_medico: string | null;
  especialista: string | null;
  tarifas: TarifasPaciente;
  anamnesis: string[];
  // Facturación → tabla clientes · Seguro → tabla paciente_seguros.
  facturacion: { razon_social: string | null; nif: string | null; direccion: string | null; iban: string | null; titular_cuenta: string | null; forma_pago: string | null };
  seguro: { aseguradora?: string | null; num_poliza?: string | null; num_ss?: string | null };
}

export interface AnamnesisSeccion {
  clave: string;
  titulo: string;
  icono: string;
  color: string;
  items: string[];
}

export interface AnamnesisCatalogo {
  secciones: AnamnesisSeccion[];
  criticos: string[];
}

export interface MovimientoEcon {
  id: number;
  concepto: string;
  fecha: string | null;
  num_factura: string | null;
  importe: number;
  abonado: number;
  pendiente: number;
  estado: "LIQUIDADO" | "PARCIAL" | "PENDIENTE" | "INCOBRABLE" | "A FAVOR";
  tratamiento_realizado_id?: number | null;
}

export interface PagoSuelto {
  id: number;
  fecha: string;
  importe: number;
  neto: number | null;          // financiación: lo que recibe la clínica (coste = importe − neto)
  forma_pago: string | null;
  num_recibo: string | null;
  referencia?: string | null;
  saldo: number;                // lo que queda sin descontar (0 en pagos migrados)
  presupuesto_id: number | null;
  asociado_a: string;           // "A cuenta" | título del presupuesto | "Tratamientos" | "Histórico GELITE"
}

export interface PlanEconomico {
  movimientos: MovimientoEcon[];
  pagos: PagoSuelto[];
  totales: { cargado: number; abonado: number; pendiente: number; costeFinanciero: number; saldo_a_favor: number; saldo_historico: number; saldo_total: number };
}

export interface FormaPago { id: number; nombre: string; grupo: string }
export interface Financiera { id: number; nombre: string; comision_pct: number }

export interface CobroInput {
  deuda_id?: number;            // sin cargo → pago a cuenta (o al presupuesto indicado)
  presupuesto_id?: number;      // saldo asociado a un presupuesto aceptado
  fecha: string;
  importe: number;              // BRUTO (100% que paga el paciente)
  forma_pago_id: number;       // catálogo único formas_pago
  neto?: number;                // lo que recibe la clínica (tras comisión financiera)
  // Campos de financiación
  financiera_id?: number;
  entrada?: number;
  num_cuotas?: number;
  interes_pct?: number;
  cuota_mensual?: number;
}

export interface PresupuestoLinea {
  id: number;
  pieza: string | null;
  zona_boca: string | null;        // cuadrante_N | arcada_superior | arcada_inferior | boca_completa
  colaborador_id: number | null;   // doctor de la línea
  estado: string | null;
  tratamiento_id: number | null;
  tratamiento: string;
  tipo_actuacion?: string | null;   // ámbito del catálogo (diente|arcada|cuadrante|sextante|tratamiento)
  es_mensualidad?: boolean;         // tratamiento de mensualidad → Uds = nº de mensualidades
  realizada?: boolean;              // la línea ya tiene un acto realizado enlazado
  cantidad: number;
  precio: number;
  descuento?: number;               // valor del descuento (€ o %, según descuento_pct)
  descuento_pct?: boolean;          // true → `descuento` es un porcentaje; false → importe en €
}

export interface Presupuesto {
  id: number;
  num: number | null;
  fecha: string | null;
  titulo: string | null;
  notas: string | null;
  colaborador_id: number | null;   // doctor de cabecera (el que sale impreso)
  estado: string;
  estado_id: number | null;
  total: number;
  pendiente: number;
  lineas: PresupuestoLinea[];
}

export interface Presupuestos {
  presupuestos: Presupuesto[];
  total_presupuestado: number;
  total_pagado: number;
  total_pendiente: number;
  colaboradores?: { id: number; nombre: string; corto?: string; es_doctor?: boolean }[];   // corto = nombre + inicial apellido (líneas); es_doctor=false → higienista (solo líneas, no titular)
}

export interface TratamientoCatalogo {
  id: number;
  codigo: string | null;
  nombre: string;
  precio: number;
  // Ámbito del catálogo (fuente de verdad): diente|arcada|cuadrante|sextante|tratamiento.
  tipo_actuacion?: string | null;
  es_mensualidad?: boolean;   // tratamiento de mensualidad → Uds = nº de mensualidades
}

// Plantilla de presupuesto (prediseñado) y sus líneas (precio según la tarifa del paciente).
export interface PresupuestoPredisenadoLinea {
  tratamiento_id: number;
  tratamiento: string;
  codigo: string | null;
  precio: number;
  tipo_actuacion?: string | null;
  es_mensualidad?: boolean;
  pieza?: string | null;
  zona_boca?: string | null;
  cantidad?: number;
  descuento?: number;
  descuento_pct?: boolean;
}
export interface PresupuestoPredisenado {
  id: number;
  titulo: string;
  categoria: string;
  notas: string | null;
  lineas: PresupuestoPredisenadoLinea[];
}

export interface LineaInput {
  tratamiento_id: number;
  pieza?: string | null;
  zona_boca?: string | null;
  colaborador_id?: number | null;
  precio: number;
  cantidad?: number;
  descuento?: number;               // valor del descuento (€ o %, según descuento_pct)
  descuento_pct?: boolean;          // true → `descuento` es un porcentaje; false → importe en €
}

export interface PresupuestoInput {
  titulo?: string | null;
  notas?: string | null;
  estado_id?: number | null;
  fecha?: string | null;
  colaborador_id?: number | null;   // doctor de cabecera (el que sale impreso)
  lineas: LineaInput[];
}

// Consentimiento informado COEM (generado/firmado).
export interface Consentimiento {
  id: number;
  tipo: string;
  estado: string;                 // pendiente | firmado | revocado
  archivo_url: string | null;
  firma_url: string | null;
  fecha: string | null;
}
export interface ConsentPlantilla { key: string; label: string; }

// Documento archivado en la ficha (subido o generado), clasificado por tipo/categoría.
export interface DocArchivado {
  id: number;
  tipo: string | null;            // categoría: Facturas | Recibo | Primera visita | Informes | Otros
  descripcion: string | null;
  archivo_url: string | null;
  fecha: string | null;
  factura_origen_id?: number | null;
  motivo_rectificacion?: string | null;
}

export interface RecetaEmitida {
  id: number;
  fecha: string | null;
  medicamento: string;
  posologia: string | null;
  pauta?: string | null;
  duracion?: string | null;
  envases?: number | null;
  unidades?: number | null;
  doctor: string;
  num_receta: string | null;
  n_lineas: number;
}

export interface ActoInput {
  tratamiento_id?: number | null;
  piezas?: string | null;
  zona_boca?: string | null;
  fecha: string;
  importe?: number | null;
  notas?: string | null;
  presupuesto_linea_id?: number | null;
  colaborador_id?: number | null;
  previsto_id?: number | null;   // si viene del plan: consume ese previsto al realizarlo
}

// Plan de tratamientos PREVISTOS (lo pendiente tras aceptar), agrupado por presupuesto.
export interface PrevistoItem {
  id: number;
  tratamiento_id: number | null;
  tratamiento: string;
  tipo_actuacion?: string | null;
  pieza: string | null;
  zona_boca: string | null;
  importe: number;
  colaborador_id: number | null;
  etiqueta: string | null;       // p.ej. "Mensualidad 3/6"
  linea_id: number;              // presupuesto_linea_id de origen
}
export interface PrevistoGroup {
  id: number;
  num: number | null;
  estado: string;
  fecha: string | null;
  previstos: PrevistoItem[];
}

export interface PlanProximaItem {
  linea_id?: number | null;
  tratamiento: string;
  pieza?: string | null;
  minutos: number;
}
export interface PlanProxima {
  id: number;
  minutos: number;
  nota: string | null;
  presupuesto_id: number | null;
  colaborador_id: number | null;
  items: PlanProximaItem[];
  estado: string;
  fecha: string | null;
}
export interface PlanProximaInput {
  minutos: number;
  nota?: string | null;
  presupuesto_id?: number | null;
  items: PlanProximaItem[];
}

export interface ActoClinico {
  id: number;
  fecha: string | null;
  piezas: string | null;
  zona_boca?: string | null;   // ámbito amplio (arcada/cuadrante/sextante/boca) cuando no es por pieza
  doctor: string;
  tratamiento: string;
  observaciones: string | null;
  importe: number;
  estado: string;
  facturado: boolean;   // ya facturado a su doctor (día 10 del mes siguiente) → avisar al editar/borrar
  fracasado?: boolean;
  factura_activa?: boolean;
  factura_numero?: string | null;
}

export interface FichaActos {
  actos: ActoClinico[];
  indicadores: {
    ultima_higiene: string | null;
    ultima_panoramica: string | null;
    ultima_visita: string | null;
  };
}

export interface OdontogramaPrevio {
  pieza: string | null;
  cara: string | null;
  estado: string | null;
  tratamiento: string;
  fecha: string | null;
}

export interface OdontogramaRealizado {
  piezas: string | null;
  tratamiento: string;
  fecha: string | null;
}

// Hallazgo editable del odontograma (contrato `teeth`, idéntico al .37).
export interface Hallazgo {
  pieza: string;
  estado: string;        // CARIES, OBTURACIÓN, CORONA, IMPLANTE… (mayúsculas)
  cara?: string;         // OMDVLC o "-"
  obs?: string;          // descripción/tratamiento libre
  tipoRegistro: string;  // INICIAL | REALIZADO | PRESUPUESTADO
  fecha: string;         // dd/mm/yyyy o "—"
}
export interface OdontogramaData {
  teeth: Hallazgo[];
  realizados?: { piezas: string; tratamiento: string; fecha: string }[];
}

export interface AlertaMedica {
  id: number;
  texto: string;
  severidad: string | null;
  activo: boolean;
  fecha: string | null;
}
export interface MedicacionPaciente {
  id: number;
  farmaco: string;
  dosis: string | null;
  frecuencia: string | null;
  pauta: string | null;
  desde: string | null;
  activo: boolean;
}
export interface AlertasData {
  alertas: AlertaMedica[];
  medicaciones: MedicacionPaciente[];
  notas: string | null;
}

export interface CitaCascabel {
  id: number;
  fecha: string | null;
  hora: string | null;
  estado: string;
  pasada: boolean;
  texto: string | null;
}
export interface CascabelData {
  scorePorcentaje: number | null;
  citasAsistidas: number;
  citasNoShow: number;
  citasTotal: number;
  citas: CitaCascabel[];
  recalls: unknown[];
  consents: unknown[];
  outcomes: unknown[];
}

export interface PerioSitio { ps: number; rec: number; ss: boolean; ip: boolean; }
export interface PerioPieza { v: PerioSitio[]; p: PerioSitio[]; mob: number; }
export interface PeriodontogramaData {
  piezas: Record<string, PerioPieza>;
  bop: number;
  bolsas4: number;
  fecha: string | null;
  exploracion_id?: number | null;
}
export interface PerioEstudio {
  exploracion_id: number;
  fecha: string | null;
  bop: number;
  bolsas4: number;
  n_piezas: number;
}

// Campos "core" que persisten directos en `pacientes` (PUT /pacientes/{id}).
export type CampoCore =
  | "nombre" | "apellidos" | "nif" | "fecha_nacimiento" | "direccion" | "cp"
  | "telefono_fijo" | "telefono_fijo2" | "telefono_movil" | "email" | "descuento" | "notas"
  | "acepta_lopd" | "acepta_info" | "acepta_whatsapp" | "acepta_bots";

// Multimedia: imágenes del paciente desde su carpeta de Google Drive.
export interface MultimediaItem { id: string; name: string; fecha: string | null; mime: string | null; }
export interface MultimediaData {
  disponible: boolean;
  motivo?: string;
  carpeta?: string | null;
  fotos: MultimediaItem[];
  radiografias: MultimediaItem[];
}
// Análisis IA de una ortopantomografía (sugerencias; las valida el doctor).
export interface IaDiente { fdi: string; conf: number; bbox: number[]; }
export interface IaEstructura {
  clase: "impactado" | "canal_dentario_inferior" | "seno_maxilar";
  conf: number; bbox: number[]; contornos: number[][][]; fdi: string | null;
  baja_confianza?: boolean;   // el servidor de IA la marca cuando conf < 0,3 (p. ej. senos con el umbral propio de 0,03)
}
export interface IaAnalisis {
  ancho: number; alto: number; segundos: number; aviso: string;
  dientes: IaDiente[]; estructuras: IaEstructura[]; errores: string[];
}

// ── DentIA: análisis guiado de una radiografía (patrones + plan) ──
export interface DentiaPatron {
  id: string; categoria: string; origen: "doctor" | "ia"; pieza?: string | null;
  puntos: number[][]; confianza?: number | null; nota?: string | null;
}
export interface DentiaLineaPlan {
  patron_id?: string | null; tratamiento_id: number; tratamiento: string; codigo?: string | null;
  pieza?: string | null; precio: number; cantidad: number; descuento: number; descuento_pct: boolean; nota?: string | null;
}
export interface DentiaAnalisis {
  file_id: string; existe: boolean; paso: number; patrones: DentiaPatron[]; plan: DentiaLineaPlan[];
}
export interface DentiaDetectado {
  ancho: number; alto: number; patrones: DentiaPatron[];
  dientes: { fdi: string; conf: number; bbox: number[] }[]; aviso?: string; errores: string[];
}
