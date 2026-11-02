"use client";
/**
 * Indicadores WhatsApp/Voicebot de Alex — viven en la barra de subtipos de IA's
 * (a la derecha). Toggle sincronizado con `configuraciones` ia/agente.alex.canales.
 * Verde si activo y sano, salmón si activo pero con incidencia, gris si apagado.
 */
import { useEffect, useState } from "react";
import { api } from "@/shared/lib/api";
import { StatusChip, useHealthOk } from "./StatusChip";

type Blob = { canales?: { whatsapp?: boolean; voicebot?: boolean } } & Record<string, unknown>;

export function AlexChannelToggles() {
  const [cfg, setCfg] = useState<Blob>({});
  const [wa, setWa] = useState(false);   // opt-in: el agente NO responde solo hasta activarlo
  const [vb, setVb] = useState(false);
  const ok = useHealthOk();

  useEffect(() => {
    api.get<{ valores: Record<string, unknown> }>("/config?sistema=ia").then((x) => {
      const blob = (x.valores?.["agente.alex"] as Blob) || {};
      setCfg(blob);
      setWa(blob.canales?.whatsapp ?? false);
      setVb(blob.canales?.voicebot ?? false);
    }).catch(() => {});
  }, []);

  async function save(nextWa: boolean, nextVb: boolean) {
    setWa(nextWa); setVb(nextVb);
    try {
      // Releer justo antes de escribir: el header no se remonta al navegar, así que `cfg`
      // podría estar obsoleto y pisaría lo guardado en los paneles (persona/voz/capacidades…).
      const cur = await api.get<{ valores: Record<string, unknown> }>("/config?sistema=ia");
      const fresh = (cur.valores?.["agente.alex"] as Blob) || {};
      const blob: Blob = { ...fresh, canales: { whatsapp: nextWa, voicebot: nextVb } };
      setCfg(blob);
      await api.put("/config", { clave: "agente.alex", valor: blob, sistema: "ia" });
    } catch (e) { console.error("alex: no se pudo guardar canales", e); }
  }

  return (
    <div className="flex items-center gap-1.5">
      <StatusChip label="WhatsApp" on={wa} incidencia={wa && ok === false} onClick={() => save(!wa, vb)} />
      <StatusChip label="Voicebot" on={vb} incidencia={vb && ok === false} onClick={() => save(wa, !vb)} />
    </div>
  );
}
