// Servicio del editor de informes → backend /informes/*.
import { api, API_BASE } from "@/shared/lib/api";
import type {
  Catalogo, ConsultaInforme, ResultadoInforme, ConsultaPivote, ResultadoPivote,
  ConsultaMulti, InformeGuardadoResumen, InformeGuardado, TablaResumen, CamposTabla,
} from "./types";

// Descarga un CSV del backend (POST con la consulta → blob → link). Fuente única de exportar/multiExportar.
async function descargarCsv(path: string, body: unknown, filename: string): Promise<void> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    credentials: "include",
  });
  if (!res.ok) throw new Error(`Export ${res.status}`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

export const informesService = {
  catalogo: () => api.get<Catalogo>("/informes/entidades"),
  tablas: () => api.get<{ tablas: TablaResumen[] }>("/informes/tablas"),
  tablaCampos: (nombre: string) => api.get<CamposTabla>(`/informes/tabla/${nombre}/campos`),
  ejecutar: (q: ConsultaInforme) => api.post<ResultadoInforme>("/informes/ejecutar", q),
  pivote: (q: ConsultaPivote) => api.post<ResultadoPivote>("/informes/pivote", q),
  multiEjecutar: (q: ConsultaMulti) => api.post<ResultadoInforme>("/informes/multi/ejecutar", q),
  multiExportar: (q: ConsultaMulti) => descargarCsv("/informes/multi/exportar", q, "informe_multi.csv"),
  guardados: () => api.get<InformeGuardadoResumen[]>("/informes/guardados"),
  obtener: (id: number) => api.get<InformeGuardado>(`/informes/guardados/${id}`),
  crear: (body: { nombre: string; descripcion?: string | null; entidad: string; definicion: unknown }) =>
    api.post<{ id: number }>("/informes/guardados", body),
  actualizar: (id: number, body: { nombre: string; descripcion?: string | null; entidad: string; definicion: unknown }) =>
    api.put<{ id: number }>(`/informes/guardados/${id}`, body),
  borrar: (id: number) => api.del(`/informes/guardados/${id}`),

  // Export CSV: POST con la consulta → descarga el fichero (la cookie va en credentials).
  exportar: (q: ConsultaInforme) => descargarCsv("/informes/exportar", q, `informe_${q.entidad}.csv`),
};
