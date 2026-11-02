"use client";
/**
 * Indicador de CENTINELA (salud del sistema) — barra de subtipos de IA's (derecha).
 * Sincronizado con `configuraciones` centinela/centinela.config.activa (la clave de
 * almacenamiento y el sistema siguen siendo `centinela`). OJO: Centinela NO es Victor —
 * Victor es el agente conversacional del doctor/equipo (application/services/victor_service.py);
 * Centinela es la vigilancia de la salud del sistema, como dice domain/config/agentes.py.
 */
import { useEffect, useState } from "react";
import { api } from "@/shared/lib/api";
import { StatusChip } from "./StatusChip";

type Blob = { activa?: boolean } & Record<string, unknown>;

export function CentinelaToggle() {
  const [cfg, setCfg] = useState<Blob>({});
  const [on, setOn] = useState(true);
  const [nivel, setNivel] = useState<string | null>(null);

  useEffect(() => {
    api.get<{ valores: Record<string, unknown> }>("/config?sistema=centinela").then((x) => {
      const blob = (x.valores?.["centinela.config"] as Blob) || {};
      setCfg(blob); setOn(blob.activa ?? true);
    }).catch(() => {});
    // Último nivel REAL conocido (de Auditoria, sin ejecutar chequeos) — antes se basaba en
    // /health, que siempre devuelve ok y por tanto nunca podía encender el aviso de verdad.
    api.get<{ nivel: string | null }>("/config/centinela/nivel").then((r) => setNivel(r.nivel)).catch(() => {});
  }, []);

  async function toggle() {
    const next = !on; setOn(next);
    try {
      // Releer antes de escribir para no pisar lo guardado en el panel de Centinela (el header
      // no se remonta al navegar y `cfg` podría estar obsoleto).
      const cur = await api.get<{ valores: Record<string, unknown> }>("/config?sistema=centinela");
      const fresh = (cur.valores?.["centinela.config"] as Blob) || {};
      const blob: Blob = { ...fresh, activa: next };
      setCfg(blob);
      await api.put("/config", { clave: "centinela.config", valor: blob, sistema: "centinela" });
    } catch (e) { console.error("centinela: no se pudo guardar", e); }
  }

  return <StatusChip label="Centinela" on={on} incidencia={on && (nivel === "warn" || nivel === "error")} onClick={toggle} />;
}
