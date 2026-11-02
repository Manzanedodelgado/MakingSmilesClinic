/** Mensaje legible de un error de API.
 *
 * Fuente única (antes copiada en ~11 ficheros): extrae `detail` del JSON de
 * FastAPI cuando el mensaje lo contiene, o devuelve el texto limpio.
 */
export function errMsg(e: unknown): string {
  const raw = e instanceof Error ? e.message : String(e);
  const i = raw.indexOf("{");
  if (i >= 0) {
    try {
      const dd = JSON.parse(raw.slice(i)).detail;
      if (typeof dd === "string") return dd;
      if (Array.isArray(dd)) return dd.map((x) => x.msg).join(" · ");
    } catch {
      /* no es JSON: se devuelve el texto */
    }
  }
  return raw.replace(/\s*\{.*\}\s*$/, "") || "Error";
}
