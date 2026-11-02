import { api, API_BASE } from "@/shared/lib/api";
import type {
  ActoInput, AlertasData, AnamnesisCatalogo, CascabelData, FichaActos, Filiacion, Hallazgo,
  OdontogramaData, PacienteBusqueda, PacienteCabecera, PeriodontogramaData, PerioEstudio,
  PerioSitio, PlanEconomico, PlanProxima, PlanProximaInput, PresupuestoInput, Presupuestos,
  RecetaEmitida, TarifasPaciente, TratamientoCatalogo, MultimediaData, IaAnalisis, DentiaAnalisis, DentiaDetectado, DentiaPatron, DentiaLineaPlan,
  PresupuestoPredisenado, PrevistoGroup, Consentimiento, ConsentPlantilla, CobroInput, FormaPago,
  DocArchivado, Financiera,
} from "../types/patient";

export type RomexisSyncItem = {
  id: number; paciente_id: number; num_historia: string; apellidos: string; nombre: string;
  estado: string; romexis_apellidos: string | null; romexis_nombre: string | null; detalle: string | null;
};

/** Alta: campos de FILIACIÓN de columna directa. Nº historia lo asigna el backend (no editable). */
export type NuevoPacienteBody = {
  nombre: string; apellidos: string;
  fecha_nacimiento?: string | null; nif?: string | null; descuento?: number | null;
  telefono_movil?: string | null; telefono_fijo?: string | null; telefono_fijo2?: string | null;
  email?: string | null; direccion?: string | null; cp?: string | null;
  responsable_nombre?: string | null; responsable_nif?: string | null; responsable_parentesco?: string | null;
  grupo_sanguineo?: string | null; peso?: number | null; altura?: number | null;
  medico_cabecera?: string | null; tel_medico?: string | null; especialista?: string | null;
  acepta_lopd?: boolean | null; acepta_info?: boolean | null; acepta_whatsapp?: boolean | null; acepta_bots?: boolean | null;
  notas?: string | null; num_historia?: string | null;
};

// Capa de acceso al backend del área Pacientes. Auth por cookie httpOnly (api).
export const patientService = {
  /** Alta de paciente en la web → dispara el puente a Romexis (mismo NumPac/nombre/apellidos/fecha). */
  crearPaciente: (body: NuevoPacienteBody) =>
    api.post<{ id: number; num_historia: string; romexis_sync_id: number }>("/pacientes/nuevo", body),
  /** Conflictos de sincronización con Romexis pendientes de decidir (mismo ID, distinto nombre). */
  romexisConflictos: () => api.get<{ sync: RomexisSyncItem[] }>("/romexis-sync?estado=conflicto_id"),
  romexisResolver: (id: number, accion: "modificar" | "nuevo_circuito") =>
    api.post<{ ok: boolean; estado: string }>(`/romexis-sync/${id}/resolver`, { accion }),

  /** `limite` sube el tramo devuelto; `total` dice cuántos hay en realidad. */
  buscar: (q: string, limite?: number) =>
    api.get<{ pacientes: PacienteBusqueda[]; total: number; mostrados: number }>(
      `/pacientes/buscar?q=${encodeURIComponent(q)}${limite ? `&limite=${limite}` : ""}`),

  cabecera: (id: number) => api.get<PacienteCabecera>(`/pacientes/${id}`),

  filiacion: (id: number) => api.get<Filiacion>(`/pacientes/${id}/filiacion`),

  actualizar: (id: number, cambios: Record<string, unknown>) =>
    api.put<{ id: number }>(`/pacientes/${id}`, cambios),

  setTarifas: (id: number, tarifa_ids: number[]) =>
    api.put<TarifasPaciente>(`/pacientes/${id}/tarifas`, { tarifa_ids }),

  // Foto de perfil: sirve por proxy autenticado (anti-IDOR, igual que Multimedia), nunca cruda.
  fotoUrl: (id: number) => `${API_BASE}/pacientes/${id}/foto`,
  subirFoto: (id: number, file: File) => api.upload<{ ok: true }>(`/pacientes/${id}/foto`, file),
  fotoDesdeDrive: (id: number) => api.post<{ ok: true }>(`/pacientes/${id}/foto/drive`),
  borrarFoto: (id: number) => api.del(`/pacientes/${id}/foto`),

  anamnesisCatalogo: () => api.get<AnamnesisCatalogo>(`/pacientes/anamnesis/catalogo`),

  setAnamnesis: (id: number, items: string[]) =>
    api.put<{ id: number; anamnesis: string[] }>(`/pacientes/${id}/anamnesis`, { items }),

  setFacturacion: (id: number, datos: Record<string, string>) =>
    api.put<{ id: number; cliente_id: number }>(`/pacientes/${id}/facturacion`, datos),

  setSeguro: (id: number, datos: Record<string, string>) =>
    api.put<{ id: number }>(`/pacientes/${id}/seguro`, datos),

  plan: (id: number) => api.get<PlanEconomico>(`/pacientes/${id}/plan`),
  formasPago: () => api.get<{ formas: FormaPago[] }>("/pacientes/formas-pago"),
  financieras: () => api.get<{ financieras: Financiera[] }>("/pacientes/financieras"),
  registrarCobro: (id: number, data: CobroInput) =>
    api.post<{ ok: boolean; pagoId: number; costeFinanciero: number; saldo: number }>(`/pacientes/${id}/pagos`, data),

  liberarPago: (pacienteId: number, pagoId: number) =>
    api.patch<{ ok: boolean; saldo: number }>(`/pacientes/${pacienteId}/pagos/${pagoId}/liberar`),

  reasignarPago: (pacienteId: number, pagoId: number, presupuestoId: number | null) =>
    api.patch<{ ok: boolean; saldo: number }>(`/pacientes/${pacienteId}/pagos/${pagoId}/reasignar`, { presupuesto_id: presupuestoId }),
  traspasarSaldo: (pacienteId: number, pacienteDestinoId: number, importe: number, fecha: string) =>
    api.post<{ ok: boolean; importe: number }>(`/pacientes/${pacienteId}/saldo/traspasar`,
      { paciente_destino_id: pacienteDestinoId, importe, fecha }),
  devolverSaldo: (pacienteId: number, importe: number, fecha: string, motivo: string) =>
    api.post<{ ok: boolean; importe: number }>(`/pacientes/${pacienteId}/saldo/devolver`,
      { importe, fecha, motivo }),
  marcarTratamientoFracasado: (pacienteId: number, actoId: number) =>
    api.post<{ ok: boolean; importe_abonado: number; saldo_generado: number }>(
      `/pacientes/${pacienteId}/actos/${actoId}/marcar-fracasado`, {}),

  presupuestos: (id: number) => api.get<Presupuestos>(`/pacientes/${id}/presupuestos`),

  actos: (id: number) => api.get<FichaActos>(`/pacientes/${id}/actos`),

  // Multimedia (fotos/RX) desde la carpeta de Google Drive del paciente.
  multimedia: (id: number) => api.get<MultimediaData>(`/pacientes/${id}/multimedia`),
  // URL del proxy autenticado (cookie httpOnly same-origin) para usar directamente en <img src>.
  multimediaUrl: (id: number, fileId: string, thumb = false) =>
    `${API_BASE}/pacientes/${id}/multimedia/${encodeURIComponent(fileId)}${thumb ? "?thumb=1" : ""}`,

  // Análisis IA de una panorámica: numeración FDI, impactados, canal dentario inferior y seno maxilar.
  // DentIA: estado del análisis por imagen, guardado y detección por IA (sugerencias).
  dentiaObtener: (id: number, fileId: string) =>
    api.get<DentiaAnalisis>(`/pacientes/${id}/dentia?file_id=${encodeURIComponent(fileId)}`),
  dentiaGuardar: (id: number, body: { file_id: string; paso: number; patrones: DentiaPatron[]; plan: DentiaLineaPlan[] }) =>
    api.put<DentiaAnalisis>(`/pacientes/${id}/dentia`, body),
  dentiaDetectar: (id: number, fileId: string) =>
    api.post<DentiaDetectado>(`/pacientes/${id}/dentia/detectar`, { file_id: fileId }),
  analizarIA: (id: number, fileId: string) =>
    api.post<IaAnalisis>(`/pacientes/${id}/multimedia/${encodeURIComponent(fileId)}/analizar-ia`),

  odontograma: (id: number) => api.get<OdontogramaData>(`/pacientes/${id}/odontograma`),

  guardarOdontograma: (id: number, teeth: Hallazgo[]) =>
    api.put<{ ok: boolean; n: number }>(`/pacientes/${id}/odontograma`, { teeth }),

  periodontograma: (id: number, exploracionId?: number) =>
    api.get<PeriodontogramaData>(`/pacientes/${id}/periodontograma${exploracionId != null ? `?exploracion_id=${exploracionId}` : ""}`),

  periodontogramaEstudios: (id: number) =>
    api.get<{ estudios: PerioEstudio[] }>(`/pacientes/${id}/periodontograma/estudios`),

  guardarPeriodontograma: (id: number, piezas: Record<string, { v: PerioSitio[]; p: PerioSitio[]; mob: number }>) =>
    api.post<{ exploracion_id: number; n: number }>(`/pacientes/${id}/periodontograma`, { piezas }),

  catalogoTratamientos: (id: number, q: string) =>
    api.get<{ tratamientos: TratamientoCatalogo[] }>(`/pacientes/${id}/catalogo-tratamientos?q=${encodeURIComponent(q)}`),

  // Plantillas de presupuesto (prediseñados) con precio según la tarifa del paciente.
  presupuestosPredisenados: (id: number) =>
    api.get<{ predisenados: PresupuestoPredisenado[] }>(`/pacientes/${id}/presupuestos-predisenados`),

  crearPresupuesto: (id: number, body: PresupuestoInput) =>
    api.post<{ id: number; num: number; anuladas_previas?: number }>(`/pacientes/${id}/presupuestos`, body),

  // Parte B: tratamientos hechos en la visita → presupuesto Entregado→Aceptado→Previsto→Realizado (atómico).
  realizarEnCita: (id: number, lineas: { tratamiento_id: number; pieza?: string | null; precio: number; cantidad?: number }[], colaboradorId: number) =>
    api.post<{ presupuesto_id: number; num: number; realizados: number; anuladas_previas: number }>(
      `/pacientes/${id}/presupuestos/realizar-en-cita`, { lineas, colaborador_id: colaboradorId }),

  editarPresupuesto: (id: number, preId: number, body: PresupuestoInput) =>
    api.put<{ id: number; num: number }>(`/pacientes/${id}/presupuestos/${preId}`, body),

  borrarPresupuesto: (id: number, preId: number) =>
    api.del(`/pacientes/${id}/presupuestos/${preId}`),

  // Flujo del presupuesto: entregar / reabrir / anular / aceptar (total o parcial).
  entregarPresupuesto: (id: number, preId: number) =>
    api.post<{ id: number; estado_id: number }>(`/pacientes/${id}/presupuestos/${preId}/entregar`, {}),
  reabrirPresupuesto: (id: number, preId: number) =>
    api.post<{ id: number; estado_id: number }>(`/pacientes/${id}/presupuestos/${preId}/reabrir`, {}),
  anularPresupuesto: (id: number, preId: number) =>
    api.post<{ id: number; estado_id: number }>(`/pacientes/${id}/presupuestos/${preId}/anular`, {}),
  aceptarPresupuesto: (id: number, preId: number, body: { lineas_aceptadas: number[]; resto: "mantener" | "anular" }) =>
    api.post<{ id: number; estado_id: number; nuevo_presupuesto_id: number | null }>(`/pacientes/${id}/presupuestos/${preId}/aceptar`, body),
  duplicarPresupuesto: (id: number, preId: number) =>
    api.post<{ id: number; num: number }>(`/pacientes/${id}/presupuestos/${preId}/duplicar`, {}),
  cancelarPresupuesto: (id: number, preId: number, body: { lineas: number[] }) =>
    api.post<{ id: number; estado_id: number; canceladas: number }>(`/pacientes/${id}/presupuestos/${preId}/cancelar`, body),

  recetas: (id: number) => api.get<{ recetas: RecetaEmitida[] }>(`/pacientes/${id}/recetas`),

  // Consentimientos informados COEM (plantillas PDF · generar · firmar).
  consentPlantillas: () => api.get<{ plantillas: ConsentPlantilla[] }>(`/consentimientos/plantillas`),
  consentListar: (id: number) => api.get<Consentimiento[]>(`/consentimientos/paciente/${id}`),
  consentGenerar: (body: { paciente_id: number; plantilla: string; colaborador_id?: number | null }) =>
    api.post<Consentimiento>(`/consentimientos`, body),
  consentFirmar: (cid: number, firma: string) => api.post<Consentimiento>(`/consentimientos/${cid}/firmar`, { firma }),
  consentBorrar: (cid: number) => api.del(`/consentimientos/${cid}`),

  // Archivo de documentos del paciente (subidos o generados), por tipo/categoría.
  docListar: (id: number, tipo?: string) =>
    api.get<DocArchivado[]>(`/pacientes/${id}/documentos${tipo && tipo !== "Todos" ? `?tipo=${encodeURIComponent(tipo)}` : ""}`),
  docSubir: (id: number, file: File, tipo: string, descripcion?: string) =>
    api.upload<DocArchivado>(`/pacientes/${id}/documentos`, file, { tipo, descripcion: descripcion ?? "" }),
  docBorrar: (id: number, docId: number) => api.del(`/pacientes/${id}/documentos/${docId}`),
  facturasVinculadas: (id: number) => api.get<Array<{ factura_id: number | null; numero: string; fecha?: string | null; estado: string; verifactu: boolean; rectificativa_url?: string | null; rectificativa_descripcion?: string | null }>>(`/pacientes/${id}/documentos/facturas-vinculadas`),
  rectificarFactura: (id: number, facturaId: number, motivo: string, file: File) =>
    api.upload<DocArchivado>(`/pacientes/${id}/documentos/rectificar-factura`, file, { factura_id: String(facturaId), motivo }),

  alertas: (id: number) => api.get<AlertasData>(`/pacientes/${id}/alertas`),

  crearAlerta: (id: number, texto: string, severidad: string | null) =>
    api.post<{ id: number }>(`/pacientes/${id}/alertas`, { texto, severidad }),

  toggleAlerta: (id: number, alertaId: number, activo: boolean) =>
    api.put<{ id: number; activo: boolean }>(`/pacientes/${id}/alertas/${alertaId}`, { activo }),

  crearMedicacion: (id: number, body: { farmaco: string; dosis?: string | null; frecuencia?: string | null }) =>
    api.post<{ id: number }>(`/pacientes/${id}/medicaciones`, body),

  cascabel: (id: number) => api.get<CascabelData>(`/pacientes/${id}/cascabel`),

  crearActo: (id: number, body: ActoInput) =>
    api.post<{ id: number }>(`/pacientes/${id}/actos`, body),
  editarActo: (id: number, actoId: number, body: Partial<ActoInput>) =>
    api.put<{ id: number }>(`/pacientes/${id}/actos/${actoId}`, body),
  borrarActo: (id: number, actoId: number) =>
    api.del(`/pacientes/${id}/actos/${actoId}`),

  // Plan de previstos (lo pendiente tras aceptar) agrupado por presupuesto — para 'Tratamiento planificado'.
  previstos: (id: number) => api.get<{ presupuestos: PrevistoGroup[] }>(`/pacientes/${id}/previstos`),

  planProxima: (id: number) => api.get<{ plan: PlanProxima | null }>(`/pacientes/${id}/plan-proxima`),

  guardarPlanProxima: (id: number, body: PlanProximaInput) =>
    api.put<{ id: number }>(`/pacientes/${id}/plan-proxima`, body),

  borrarPlanProxima: (id: number) => api.del(`/pacientes/${id}/plan-proxima`),

  // La Consulta Viva — cerebro: enruta una evidencia hablada al mapa de incógnitas (LLM).
  consultaAnalizar: (
    id: number,
    body: { evidencia: string; incognitas: { id: string; pregunta: string; pieza: string | null; confianza: number; propuesta: string | null }[] },
  ) => api.post<ConsultaDecision>(`/pacientes/${id}/consulta/analizar`, body),

  // Cierre de la visita → registra los actos decididos (resuelve nombre→catálogo).
  consultaCerrar: (
    id: number,
    body: { nota: string | null; tratamientos: { texto: string; pieza: string | null; precio: number | null }[] },
  ) => api.post<{ registrados: { id: number; tratamiento: string; tratamiento_id: number | null; pieza: string | null }[]; n: number }>(`/pacientes/${id}/consulta/cerrar`, body),

  // Escucha Activa — de la conversación de la visita saca 4 borradores (SOAP, presupuesto, receta, mensaje).
  consultaEscucha: (id: number, texto: string) =>
    api.post<EscuchaExtraido>(`/pacientes/${id}/consulta/escucha`, { texto }),
  // Guardados al CONFIRMAR cada borrador.
  guardarSoap: (id: number, soap: { subjetivo: string; objetivo: string; analisis: string; plan: string }) =>
    api.post<{ ok: boolean; soap_id: number; cita_id: number }>(`/pacientes/${id}/consulta/soap`, soap),
  guardarReceta: (id: number, medicamentos: { medicamento: string; posologia?: string; pauta?: string; duracion?: string; envases?: number; unidades?: number }[], extra?: {
    diagnostico?: string; instrucciones?: string; urgencia?: boolean; desabastecimiento?: boolean; motivo_sustitucion?: string;
  }) =>
    api.post<{ ok: boolean; receta_id: number; n: number }>(`/pacientes/${id}/consulta/receta`, { medicamentos, ...extra }),

  // Detección de camino: 1 (ejecución), 2 (primera visita), 3 (revisión).
  detectarCamino: (id: number, cita_id?: number) =>
    api.get<{ camino: 1 | 2 | 3; es_nuevo: boolean; anamnesis_completa: boolean; cita_confirmada: boolean; tiene_previstos: boolean }>(
      `/pacientes/${id}/consulta/camino${cita_id ? `?cita_id=${cita_id}` : ""}`
    ),

  // Recomendaciones: catálogo y guardado.
  recomendacionesCatalogo: () =>
    api.get<{ secciones: { clave: string; titulo: string; icono: string; color: string; items: string[] }[] }>(`/pacientes/recomendaciones/catalogo`),
  guardarRecomendaciones: (id: number, items: string[], cita_id?: number) =>
    api.post<{ ok: boolean; recomendacion_id: number; items_count: number; texto_generado: string | null }>(
      `/pacientes/${id}/consulta/recomendaciones`, { items, cita_id }
    ),

  // Recetas frecuentes (plantillas reutilizables)
  recetasFrecuentes: (id: number) =>
    api.get<{ recetas_frecuentes: Array<{ id: number; nombre: string; medicamentos: unknown[] }> }>(
      `/pacientes/${id}/consulta/recetas-frecuentes`
    ),

  crearRecetaFrecuente: (id: number, nombre: string, medicamentos: { medicamento: string; posologia?: string; pauta?: string; duracion?: string; envases?: number; unidades?: number }[]) =>
    api.post<{ ok: boolean; id: number; nombre: string; medicamentos: unknown[] }>(
      `/pacientes/${id}/consulta/recetas-frecuentes`, { nombre, medicamentos }
    ),

  actualizarRecetaFrecuente: (id: number, recetaId: number, nombre: string, medicamentos: { medicamento: string; posologia?: string; pauta?: string; duracion?: string; envases?: number; unidades?: number }[]) =>
    api.put<{ ok: boolean; id: number; nombre: string; medicamentos: unknown[] }>(
      `/pacientes/${id}/consulta/recetas-frecuentes/${recetaId}`, { nombre, medicamentos }
    ),

  borrarRecetaFrecuente: (id: number, recetaId: number) =>
    api.del(`/pacientes/${id}/consulta/recetas-frecuentes/${recetaId}`),
};

export interface EscuchaExtraido {
  ok?: boolean;
  soap: { subjetivo: string; objetivo: string; analisis: string; plan: string };
  presupuesto: { tratamiento: string; tratamiento_id: number | null; pieza: string | null; cantidad: number; precio: number }[];
  receta: { medicamento: string; posologia?: string; pauta?: string; duracion?: string; envases?: number; unidades?: number }[];
  mensaje: string;
  telefono: string | null;
}

export interface ConsultaDecision {
  pieza: string | null;
  targetId: string | null;
  deltaConf: number;
  propuesta: { texto: string; precio: number | null } | null;
  nueva: { pregunta: string; pieza: string | null; hipotesis?: string; confianza?: number; propuesta?: { texto: string; precio: number | null } | null; origen?: string } | null;
  explica: string;
}
