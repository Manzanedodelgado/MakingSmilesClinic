"use client";
/**
 * Config → Admin → Documentos. Contenedor de los documentos que la clínica emite/rellena,
 * con una barra interna por tipo. "Presupuestos" es el CRUD de plantillas prediseñadas que ya
 * existía (ConfigPresupuestos). Consentimientos / Primera visita / Recomendaciones / Cuestionarios
 * se cablean en su fase de contenido; reservan su pestaña sin fingir función.
 *
 * OJO: no confundir con Admin → "Diseño" (ConfigDocumentos), que es el editor de PLANTILLAS HTML
 * de los documentos (cómo se ven al imprimir). Aquí se gestiona el CATÁLOGO de cada tipo.
 */
import { useState } from "react";
import { AreaTabs } from "@/shared/components";
import { ConfigPresupuestos } from "./ConfigPresupuestos";
import { ConfigDocumentos } from "./ConfigDocumentos";

// Cada tipo = una plantilla imprimible del motor de documentos (misma que "Diseño"), acotada
// por baseId. Presupuestos es distinto: CRUD de plantillas prediseñadas de tratamiento.
const TIPOS = [
  { id: "presupuestos", label: "Presupuestos" },
  { id: "consentimientos", label: "Consentimientos", base: "consentimiento" },
  { id: "primera-visita", label: "Primera visita", base: "primeraVisita" },
  { id: "recomendaciones", label: "Recomendaciones", base: "recomendaciones" },
  { id: "cuestionarios", label: "Cuestionarios", base: "cuestionario" },
];

export function DocumentosAdmin() {
  const [tipo, setTipo] = useState("presupuestos");
  const cur = TIPOS.find((t) => t.id === tipo);
  return (
    <div className="flex flex-col h-full min-h-0">
      <AreaTabs tabs={TIPOS.map(({ id, label }) => ({ id, label }))} activeTab={tipo} onChange={setTipo} />
      <div className="flex-1 min-h-0 overflow-y-auto pt-4">
        {tipo === "presupuestos"
          ? <ConfigPresupuestos />
          : cur?.base && <ConfigDocumentos key={cur.base} soloBase={cur.base} />}
      </div>
    </div>
  );
}
