"use client";
import { useEffect, useState } from "react";
import { api } from "@/shared/lib/api";

// Cache a nivel de módulo: se pide una vez por carga.
let _cache: Record<string, unknown> | null = null;

export function useMe() {
  const [me, setMe] = useState<Record<string, unknown> | null>(_cache ?? null);
  const [loading, setLoading] = useState(_cache == null);

  useEffect(() => {
    if (_cache != null) { setMe(_cache); setLoading(false); return; }
    let alive = true;
    api.get<Record<string, unknown>>("/auth/me")
      .then((data) => { _cache = data; if (alive) { setMe(_cache); setLoading(false); } })
      .catch(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);

  return {
    me,
    loading,
    usuario_id: (me?.usuario_id as number) ?? null,
    colaborador_id: (me?.colaborador_id as number) ?? null,
    nombre_completo: (me?.nombre_completo as string) ?? null,
    rol_nombre: (me?.rol_nombre as string) ?? null,
  };
}
