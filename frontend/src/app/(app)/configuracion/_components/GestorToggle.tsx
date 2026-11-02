"use client";
/**
 * Indicador de Gestor (facturas y contabilidad) — barra de subtipos de IA's (derecha).
 * Sincronizado con `configuraciones` gestor/gestor.config.activa.
 */
import { useEffect, useState } from "react";
import { api } from "@/shared/lib/api";
import { StatusChip, useHealthOk } from "./StatusChip";

type Blob = { activa?: boolean } & Record<string, unknown>;

export function GestorToggle() {
  const [cfg, setCfg] = useState<Blob>({});
  const [on, setOn] = useState(true);
  const ok = useHealthOk();

  useEffect(() => {
    api.get<{ valores: Record<string, unknown> }>("/config?sistema=gestor").then((x) => {
      const blob = (x.valores?.["gestor.config"] as Blob) || {};
      setCfg(blob); setOn(blob.activa ?? true);
    }).catch(() => {});
  }, []);

  async function toggle() {
    const next = !on; setOn(next);
    try {
      // Releer antes de escribir para no pisar lo guardado en el panel de Gestor.
      const cur = await api.get<{ valores: Record<string, unknown> }>("/config?sistema=gestor");
      const fresh = (cur.valores?.["gestor.config"] as Blob) || {};
      const blob: Blob = { ...fresh, activa: next };
      setCfg(blob);
      await api.put("/config", { clave: "gestor.config", valor: blob, sistema: "gestor" });
    } catch (e) { console.error("gestor: no se pudo guardar", e); }
  }

  return <StatusChip label="Gestor IA" on={on} incidencia={on && ok === false} onClick={toggle} />;
}
