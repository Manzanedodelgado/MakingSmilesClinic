// Etiqueta de "conversación urgente": desde el 17-sep-2026 es SIEMPRE manual (columna
// `conversaciones.urgente`, marcada por el equipo desde el menú ⋮). Antes se detectaba
// por texto ("ahora", "ya"...) y daba falsos positivos constantes — se retiró esa heurística.
export function esUrgente(arg: { urgente?: boolean | null } | null | undefined): boolean {
  return !!arg?.urgente;
}
