/**
 * Cliente API — versión del 12-sep recuperada de la caché de webpack, con las correcciones
 * necesarias para que funcione contra este backend:
 *   1. API_BASE = "/api" (no ""): las rutas se pasan sin prefijo (`api.get("/auth/login")`)
 *      y next.config.ts reescribe /api/:path* → backend. Con "" el fetch iba a /auth/login → 404.
 *   2. 401 → redirige a /login (estaba en la versión anterior y se había perdido).
 *   3. Soporte de respuestas binarias (blob): imprimirPresupuesto/imprimirJustificante
 *      esperan un Blob para URL.createObjectURL.
 *   4. upload() no fuerza Content-Type: FormData necesita su propio multipart + boundary.
 * Auth por cookie httpOnly (credentials:"include"). NADA en localStorage.
 */
export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "/api";

/** Mensaje de error legible: usa el `detail` de FastAPI si viene; si no, el texto crudo. */
async function _error(res: Response, path: string): Promise<Error> {
  const texto = await res.text().catch(() => "");
  try {
    const j = JSON.parse(texto);
    if (typeof j?.detail === "string" && j.detail.trim()) return new Error(j.detail);
  } catch { /* no era JSON */ }
  return new Error(`API ${res.status}: ${texto || res.statusText} (${path})`);
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const esFormData = options.body instanceof FormData;
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      // FormData pone su propio Content-Type con boundary: no se toca.
      ...(esFormData ? {} : { "Content-Type": "application/json" }),
      ...(options.headers || {}),
    },
    credentials: "include",
    cache: "no-store",
  });

  if (res.status === 401 && typeof window !== "undefined") {
    if (!location.pathname.startsWith("/login")) location.href = "/login";
    throw new Error("No autenticado");
  }
  if (!res.ok) throw await _error(res, path);
  if (res.status === 204) return undefined as T;

  const tipo = res.headers.get("content-type") || "";
  if (tipo.includes("application/json")) return res.json() as Promise<T>;
  // PDF y demás binarios → Blob (lo consumen imprimirPresupuesto / imprimirJustificante).
  if (tipo.includes("application/pdf") || tipo.includes("octet-stream") || tipo.includes("image/")) {
    return res.blob() as Promise<T>;
  }
  return res.text() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>(path, { method: "GET" }),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PUT", body: body === undefined ? undefined : JSON.stringify(body) }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", body: body === undefined ? undefined : JSON.stringify(body) }),
  delete: <T = void>(path: string) => request<T>(path, { method: "DELETE" }),
  /** Alias usado en gran parte del código base. */
  del: <T = void>(path: string) => request<T>(path, { method: "DELETE" }),
  upload: <T = { url: string }>(path: string, file: File, extraFields?: Record<string, string>) => {
    const fd = new FormData();
    fd.append("file", file);
    if (extraFields) for (const [k, v] of Object.entries(extraFields)) fd.append(k, v);
    return request<T>(path, { method: "POST", body: fd });
  },
};
