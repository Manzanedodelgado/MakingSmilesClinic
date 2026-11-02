"use client";
/**
 * Config → Automatizaciones / Flujos. Reutiliza VERBATIM los componentes del antiguo
 * módulo Motion (Reglas/Editor/Plantillas/Flujos), que ya leen/escriben la API /motion
 * (reglas = plantillas_mensaje; maestro = agente.alex.automatizacion). La cabecera y las
 * pestañas las pone el sub-shell de Configuración (configuracion/layout.tsx); aquí solo
 * el contenido de la sub-sección elegida por la URL.
 */
import { useCallback, useEffect, useState } from "react";
import { MotionReglas } from "../../motion/_components/MotionReglas";
import { MotionFlujos } from "../../motion/_components/MotionFlujos";
import { MotionEditor } from "../../motion/_components/MotionEditor";
import { PlantillasIA } from "./PlantillasIA";
import { api } from "@/shared/lib/api";
import type { ReglasResponse } from "../../motion/_components/types";

export function MotionArea({ zona, sub }: { zona: "automatizaciones" | "flujos"; sub: string }) {
  const [reglas, setReglas] = useState<ReglasResponse | null>(null);
  const cargar = useCallback(() => {
    api.get<ReglasResponse>("/motion/reglas").then(setReglas).catch(() => {});
  }, []);
  useEffect(() => { cargar(); }, [cargar]);

  if (zona === "flujos") {
    if (sub === "editor") return <MotionEditor reglas={reglas} onGuardado={cargar} />;
    return <MotionFlujos />;
  }
  // Automatizaciones — con el indicador "Motor activo/apagado" que Motion mostraba en su
  // cabecera (el motor arranca cuando el maestro está ON y WhatsApp conectado).
  const motorOn = !!reglas && reglas.maestro && reglas.whatsapp_activo;
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-end">
        <span className={`flex items-center gap-1.5 text-[10px] font-semibold uppercase ${motorOn ? "text-[#0F8C7D]" : "text-[#94a3b8]"}`}>
          <span className={`w-2 h-2 rounded-full ${motorOn ? "bg-[#2DD9C3] animate-pulse" : "bg-slate-300"}`} />
          {motorOn ? "Motor activo" : "Motor apagado"}
        </span>
      </div>
      {sub === "editor" ? <MotionEditor reglas={reglas} onGuardado={cargar} />
        : sub === "plantillas" ? <PlantillasIA />
        : <MotionReglas reglas={reglas} onCambio={cargar} />}
    </div>
  );
}
