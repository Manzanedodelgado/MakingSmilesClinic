"use client";
import { useEffect, useState } from "react";
import { api } from "@/shared/lib/api";

// Permisos finos del usuario (de /auth/me). Cache a nivel de módulo: se pide una vez por carga.
let _cache: string[] | null = null;

export function usePermisos() {
  const [permisos, setPermisos] = useState<string[]>(_cache ?? []);
  const [loading, setLoading] = useState(_cache == null);

  useEffect(() => {
    if (_cache != null) { setPermisos(_cache); setLoading(false); return; }
    let alive = true;
    api.get<{ permisos?: string[] }>("/auth/me")
      .then((m) => { _cache = m.permisos ?? []; if (alive) { setPermisos(_cache); setLoading(false); } })
      .catch(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);

  const has = (c: string) => permisos.includes(c);
  return {
    permisos,
    loading,
    has,
    // Sección de una pestaña (p. ej. tieneSeccion("gestoria.tab.facturacion", "pagos")).
    tieneSeccion: (pestana: string, seccion: string) => has(`${pestana}.${seccion}`),
    // Gestoría: lectura completa vs. lectura restringida a Facturación; y si puede escribir.
    gestoriaCompleta: has("gestoria.ver"),
    gestoriaFacturacion: has("gestoria.ver") || has("gestoria.facturacion.ver"),
    puedeEditarGestoria: has("gestoria.editar"),
  };
}
