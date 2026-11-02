import { api, API_BASE } from "@/shared/lib/api";
import type {
  ActoRealizado, Dashboard, DoctoresResp, Extracto, FacturaEmitida, FacturaHistorica, Gasto, ModeloFiscal,
  Movimiento, PacienteBusqueda, PagoPaciente, PatientTreatmentsResp, Proveedor, RevisionItem, Vencimiento,
} from "../types/gestoria";

const qs = (p: Record<string, string | undefined>) => {
  const e = Object.entries(p).filter(([, v]) => v != null && v !== "");
  return e.length ? "?" + e.map(([k, v]) => `${k}=${encodeURIComponent(v as string)}`).join("&") : "";
};

export const gestoriaService = {
  // Producción
  doctores: (desde: string, hasta: string) =>
    api.get<DoctoresResp>(`/gestoria/produccion/doctores${qs({ desde, hasta })}`),
  tratamientos: (desde?: string, hasta?: string) =>
    api.get<{ total: number; data: ActoRealizado[]; anios?: number[] }>(`/gestoria/produccion/tratamientos${qs({ desde, hasta })}`),
  actualizarTratamiento: (id: number, data: { descuento?: number; descuento_aplica_doctor?: boolean; coste_laboratorio?: number }) =>
    api.patch<{ id: number; descuento: number; descuentoAplicaDoctor: boolean; costeLaboratorio: number | null }>(`/gestoria/produccion/tratamientos/${id}`, data),
  pacienteTtos: (pacienteId: number) =>
    api.get<PatientTreatmentsResp>(`/gestoria/produccion/pacientes/${pacienteId}/tratamientos`),
  // Facturas a pacientes: EXENTAS de IVA (asistencia sanitaria, art. 20.Uno.3º LIVA) → sin iva_pct.
  facturarPaciente: (paciente_id: number, tto_ids: number[]) =>
    api.post<{ ok: boolean; numeroFactura: string }>("/gestoria/produccion/pacientes/factura", { paciente_id, tto_ids }),
  autofactura: (doctor_id: number, desde: string, hasta: string) =>
    api.post<{ ok: boolean; aLiquidar: number }>("/gestoria/produccion/autofactura", { doctor_id, desde, hasta }),
  buscarPaciente: (q: string) =>
    api.get<{ pacientes: PacienteBusqueda[] }>(`/pacientes/buscar?q=${encodeURIComponent(q)}`),

  // Facturación
  dashboard: (desde: string, hasta: string) =>
    api.get<Dashboard>(`/gestoria/dashboard${qs({ desde, hasta })}`),
  facturas: (anyo?: number, search?: string) =>
    api.get<{ total: number; data: FacturaEmitida[] }>(`/gestoria/facturas${qs({ anyo: anyo?.toString(), search })}`),
  gastos: (estado?: string, desde?: string, hasta?: string) =>
    api.get<{ data: Gasto[]; kpis: { total: number; totalGastos: number; pendiente: number } }>(`/gestoria/gastos${qs({ estado, desde, hasta })}`),
  duplicados: () => api.get<{ data: Gasto[] }>("/gestoria/duplicados"),
  actualizarGasto: (id: number, data: Record<string, unknown>) =>
    api.patch<{ id: number; estado: string; total: number }>(`/gestoria/gastos/${id}`, data),
  eliminarGasto: (id: number) => api.del(`/gestoria/gastos/${id}`),
  facturasHealth: () => api.get<{ estado: string; imapOk: boolean; driveOk: boolean; iaOk: boolean; enRevisar: number; problemas: string[] }>("/gestoria/facturas/health"),
  paginasGasto: (id: number) => api.get<{ paginas: string[] }>(`/gestoria/gastos/${id}/paginas`),
  // Descarga TODAS las facturas del filtro en un ZIP de PDFs (la cookie va en credentials).
  descargarFacturasZip: async (estado?: string, desde?: string, hasta?: string): Promise<void> => {
    const res = await fetch(`${API_BASE}/gestoria/facturas-recibidas/pdfs-zip${qs({ estado, desde, hasta })}`,
      { credentials: "include" });
    if (!res.ok) throw new Error(res.status === 404 ? "Ninguna factura del filtro tiene PDF" : `Error ${res.status}`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = "facturas.zip"; a.click();
    URL.revokeObjectURL(url);
  },
  // CSV de sección: EL MISMO fichero que Envío manda por email a la asesoría (una sola verdad).
  descargarSeccionCsv: async (tabla: "gastos" | "bancos", anyo: number): Promise<void> => {
    const res = await fetch(`${API_BASE}/gestoria/envio/csv${qs({ tabla, anyo: String(anyo) })}`,
      { credentials: "include" });
    if (!res.ok) throw new Error(res.status === 404 ? "Sin datos para ese año" : `Error ${res.status}`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `${tabla}_${anyo}.csv`; a.click();
    URL.revokeObjectURL(url);
  },
  // Extractos bancarios ARCHIVADOS: el fichero tal cual se subió, para la asesoría.
  listarExtractos: () => api.get<{ extractos: Extracto[] }>("/gestoria/extractos"),
  descargarExtracto: async (id: number, nombre: string): Promise<void> => {
    const res = await fetch(`${API_BASE}/gestoria/extractos/${id}/descargar`, { credentials: "include" });
    if (!res.ok) throw new Error(res.status === 404 ? "Fichero no disponible" : `Error ${res.status}`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = nombre; a.click();
    URL.revokeObjectURL(url);
  },
  subirFactura: (file: File) => api.upload<{ ok: boolean; id?: number; estado?: string; proveedor?: string; total?: number; duplicado?: boolean; error?: string }>("/gestoria/gastos/upload", file),
  // Ingesta del buzón: execute=false previsualiza (sin IA ni escrituras); true procesa las nuevas.
  procesarBuzon: (execute: boolean) => api.post<{
    ok: boolean; error?: string; carpeta: string; enCarpeta: number; yaEnBd: number; nuevos: number;
    procesados: number; facturasNuevas: number; facturasEnlazadas: number; aRevisar: number;
    descartadas: number; basura: number; incidencias: number; errores: number;
    revisadas: { ok: boolean; error?: string; enCarpeta: number; nuevos: number;
      registradas: number; conDatos: number; faltanDatos: number; errores: number };
  }>("/gestoria/buzon/procesar", { execute }),
  incidenciasCount: () => api.get<{ count: number }>("/gestoria/buzon/incidencias-count"),
  // Motor de conciliación: casa facturas + genera recurrentes (alquiler, parking, colaboradores, impuestos).
  cuadrarBanco: (execute: boolean) => api.post<{
    execute: boolean; conciliadas_existentes: number;
    generadas: { alquiler: number; parking: number; colaborador: number; renting: number };
    contabilizadas: { impuesto: number; retencion: number; ss: number; seguro: number };
    revision: number; requiere_datos: number;
  }>("/gestoria/banco/cuadrar", { execute }),
  // Bandeja de revisión: apuntes de los que la herramienta pide un dato (hoy: interés de préstamos).
  revisionPendiente: () => api.get<{ data: RevisionItem[] }>("/gestoria/banco/revision"),
  resolverPrestamo: (movimientoId: number, interes: number) =>
    api.post<{ ok: boolean; gastoId: number; interes: number; principal: number }>(
      `/gestoria/banco/revision/${movimientoId}/prestamo`, { interes }),
  movimientosDebeLibres: () => api.get<{ data: { id: number; label: string }[] }>("/gestoria/movimientos/debe-libres"),
  gastosLibres: () => api.get<{ data: { id: number; label: string }[] }>("/gestoria/gastos/libres"),
  asociarGasto: (gid: number, movimiento_id: number) => api.post<{ ok: boolean }>(`/gestoria/gastos/${gid}/asociar`, { movimiento_id }),
  desasociarGasto: (gid: number) => api.del(`/gestoria/gastos/${gid}/asociar`),
  corregirConcepto: (mid: number, concepto: string | null) =>
    api.patch<{ ok: boolean; concepto: string; original: string }>(`/gestoria/movimientos/${mid}/concepto`, { concepto }),
  asociarFacturasAuto: () => api.post<{ asociados: number; sinCoincidencia: number; facturasSinApunte: number }>("/gestoria/gastos/asociar-automatico", {}),
  proveedores: () => api.get<{ data: Proveedor[] }>("/gestoria/proveedores"),
  proveedoresCatalogos: () => api.get<{ categorias: string[]; formasPago: string[] }>("/gestoria/proveedores/catalogos"),
  proveedoresSinCategoria: () => api.get<{ count: number }>("/gestoria/proveedores/sin-categoria"),
  crearProveedor: (data: Record<string, unknown>) => api.post<{ id: number }>("/gestoria/proveedores", data),
  actualizarProveedor: (id: number, data: Record<string, unknown>) => api.patch<{ id: number }>(`/gestoria/proveedores/${id}`, data),
  eliminarProveedor: (id: number) => api.del(`/gestoria/proveedores/${id}`),
  fusionarProveedores: (canonico_id: number, ids: number[]) => api.post<{ fusionados: number }>("/gestoria/proveedores/fusionar", { canonico_id, ids }),
  pagosPacientes: (anyo?: number, forma?: string) => api.get<{ data: PagoPaciente[]; formas: string[] }>(`/gestoria/pagos-pacientes${qs({ anyo: anyo?.toString(), forma })}`),
  movimientosHaberLibres: () => api.get<{ data: { id: number; label: string }[] }>("/gestoria/movimientos/haber-libres"),
  // La IA razona sobre cada proveedor y clasifica los gastos sin categoría. Tarda (LLM por lotes).
  clasificarGastosIA: (execute: boolean) => api.post<{
    ok: boolean; error?: string; proveedores: number; respondidos: number;
    aplicados: number; revisar: number; porCategoria: Record<string, number>;
    muestra: { proveedor: string; categoria: string; confianza: string; nota: string }[];
  }>("/gestoria/gastos/clasificar-ia", { execute }),
  // Concilia liquidaciones del TPV ↔ pagos con tarjeta; execute=false previsualiza.
  conciliarTarjetas: (execute: boolean) => api.post<{
    execute: boolean; liquidaciones: number; conciliadas: number; pagos_marcados: number;
    comision_total: number; sin_cuadre: number;
    huecos: { cobro: string; lote: string; liquidacion: number; cubierto: number; falta: number; pagosEnLote: number }[];
  }>("/gestoria/pagos/conciliar-tarjetas", { execute }),
  asociarPago: (pid: number, movimiento_id: number) => api.post<{ ok: boolean }>(`/gestoria/pagos-pacientes/${pid}/asociar`, { movimiento_id }),
  desasociarPago: (pid: number) => api.del(`/gestoria/pagos-pacientes/${pid}/asociar`),
  movimientos: (tipo?: string, anyo?: number) =>
    api.get<{ data: Movimiento[]; kpis: { total: number; debe: number; haber: number; saldo: number } }>(`/gestoria/movimientos${qs({ tipo, anyo: anyo?.toString() })}`),
  crearMovimiento: (data: { fecha_operacion: string; concepto_banco: string; importe: number; categoria?: string }) =>
    api.post<{ id: number; tipo: string }>("/gestoria/movimientos", data),
  borrarMovimiento: (mid: number) => api.del(`/gestoria/movimientos/${mid}`),
  importarBancoXlsx: (file: File, iban?: string) =>
    api.upload<{ importados: number; omitidos: number; leidas: number; descartadas: number }>(
      "/gestoria/movimientos/import-xlsx", file, iban ? { iban } : undefined),
  calendarioTributario: (ejercicio: number) =>
    api.get<{ data: Vencimiento[] }>(`/gestoria/calendario-tributario${qs({ ejercicio: ejercicio.toString() })}`),
  generarModelo: (modelo: string, periodo: string, ejercicio: number) =>
    api.post<{ id: number }>("/gestoria/modelos-fiscales/generar", { modelo, periodo, ejercicio }),
  modelos: (ejercicio?: number) =>
    api.get<{ data: ModeloFiscal[]; kpis: { total: number; presentados: number; pendientes: number } }>(`/gestoria/modelos-fiscales${qs({ ejercicio: ejercicio?.toString() })}`),
  envioConfig: () =>
    api.get<{ destino: string | null; nombreAsesoria: string | null; remitente: string | null; smtpListo: boolean;
      auto: { activo: boolean; dia: number; tablas: string[]; ultimoEnvio: string | null } }>("/gestoria/envio/config"),
  // Programa el envío automático mensual a la asesoría (día del mes + secciones).
  guardarEnvioAuto: (activo: boolean, dia: number, tablas: string[]) =>
    api.put<{ activo: boolean; dia: number; tablas: string[]; ultimoEnvio: string | null }>(
      "/gestoria/envio/config", { activo, dia, tablas }),
  envio: (tablas: string[], anyo: number, destino?: string) =>
    api.post<{ ok: boolean; error?: string; destino?: string }>("/gestoria/envio", { tablas, anyo, destino }),

  // Archivo histórico de facturas (libros 2019-2024): tabla aislada de CONSULTA — jamás suma en Gestoría.
  historico: (q?: string, anio?: number) =>
    api.get<{ total: number; anios: number[]; data: FacturaHistorica[] }>(`/gestoria/historico${qs({ q, anio: anio?.toString() })}`),
  abrirHistoricoPdf: async (id: number): Promise<void> => {
    const res = await fetch(`${API_BASE}/gestoria/historico/${id}/pdf`, { credentials: "include" });
    if (!res.ok) throw new Error(res.status === 404 ? "PDF no disponible" : `Error ${res.status}`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank");
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  },
};

export const eur = (n: number) =>
  new Intl.NumberFormat("es-ES", { style: "currency", currency: "EUR" }).format(n || 0);

/** Fecha en formato español (DD/MM/AAAA) — el ÚNICO formato de fecha de Gestoría.
 * La API siempre devuelve ISO (AAAA-MM-DD); se convierte aquí para que todas las
 * pantallas (Facturas, Debe/Haber, Pagos, Histórico…) se lean igual. */
export const fecha = (f?: string | null): string => {
  if (!f) return "—";
  const iso = f.slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(iso) ? iso.split("-").reverse().join("/") : f;
};
