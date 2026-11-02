"use client";
import { Briefcase } from "lucide-react";
import { useEffect, useState } from "react";
import { AreaTabs } from "@/shared/components";
import { usePermisos } from "@/shared/hooks/usePermisos";
import { ProdTratamientos } from "./ProdTratamientos";
import { ProdDoctores } from "./ProdDoctores";
import { ProdPacientes } from "./ProdPacientes";
import { Gastos, DebeHaber, Pagos, Modelos, Envio } from "./FacturacionViews";
import { HistoricoFacturas } from "./HistoricoFacturas";
import { GestorChat } from "./GestorChat";

const TABS_PROD = [{ id: "tratamientos", label: "Tratamientos" }, { id: "doctores", label: "Doctores" }, { id: "pacientes", label: "Pacientes" }];
// Base (lectura restringida a Facturación): solo Debe/Haber + Facturas. El resto exige lectura completa.
const TABS_FACT_BASE = [
  { id: "debehaber", label: "Debe / Haber" },
  { id: "facturas", label: "Facturas" },
];
const TABS_FACT_COMPLETO = [
  { id: "pagos", label: "Pagos" },
  { id: "impuestos", label: "Impuestos" },
  { id: "envio", label: "Envío" },
  { id: "historico", label: "Histórico" },   // archivo documental 2019-2024 (solo consulta)
  { id: "gestor", label: "Gestor IA" },      // chat con el Gestor (solo lectura; exige gestoria.ver)
];

export function GestoriaWorkspace({ modo }: { modo: "produccion" | "facturacion" }) {
  const { gestoriaCompleta, tieneSeccion } = usePermisos();
  const [prod, setProd] = useState("doctores");
  const [fact, setFact] = useState("debehaber");
  // Deep-link desde INICIO: /gestoria?tab=facturas abre esa pestaña directamente. Sin esto,
  // el panel de pulso te deja en la sección pero no en la pestaña donde está el problema.
  useEffect(() => {
    const t = new URLSearchParams(window.location.search).get("tab");
    if (!t) return;
    if (modo === "facturacion") setFact(t); else setProd(t);
  }, [modo]);

  if (modo === "facturacion") {
    // Lectura completa: solo las secciones que su perfil permite. Restringido (asesoría): Debe/Haber + Facturas.
    const tabs = gestoriaCompleta ? [...TABS_FACT_BASE, ...TABS_FACT_COMPLETO].filter((t) => tieneSeccion("gestoria.tab.facturacion", t.id)) : TABS_FACT_BASE;
    // Si cae en una sección que no puede ver, lo llevamos a la primera permitida.
    const activa = tabs.some((t) => t.id === fact) ? fact : (tabs[0]?.id ?? "debehaber");
    if (tabs.length === 0) return <p className="p-6 text-[12px] italic text-[#94a3b8]">Tu perfil no tiene acceso a ninguna sección de Facturación.</p>;
    return (
      <div className="flex flex-col h-full min-h-0">
        {/* Debe/Haber integra su buscador en la línea de pestañas (ahorra fila); el resto usa las pestañas normales. */}
        {activa === "debehaber" ? (
          <DebeHaber tabs={tabs} activeTab={activa} onChange={setFact} />
        ) : (
          <>
            <AreaTabs tabs={tabs} activeTab={activa} onChange={setFact} className="pt-2" />
            {activa === "facturas" && <Gastos />}
            {activa === "pagos" && gestoriaCompleta && <Pagos />}
            {activa === "impuestos" && gestoriaCompleta && <Modelos />}
            {activa === "envio" && gestoriaCompleta && <Envio />}
            {activa === "historico" && gestoriaCompleta && <HistoricoFacturas />}
            {activa === "gestor" && gestoriaCompleta && <GestorChat />}
          </>
        )}
      </div>
    );
  }
  const tabsProd = TABS_PROD.filter((t) => tieneSeccion("gestoria.tab.produccion", t.id));
  const activaProd = tabsProd.some((t) => t.id === prod) ? prod : (tabsProd[0]?.id ?? "");
  if (tabsProd.length === 0) return <p className="p-6 text-[12px] italic text-[#94a3b8]">Tu perfil no tiene acceso a ninguna sección de Producción.</p>;
  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Cada pestaña integra su buscador en la línea de pestañas (como Facturación) */}
      {activaProd === "tratamientos" && <ProdTratamientos tabs={tabsProd} activeTab={activaProd} onChange={setProd} />}
      {activaProd === "doctores" && <ProdDoctores tabs={tabsProd} activeTab={activaProd} onChange={setProd} />}
      {activaProd === "pacientes" && <ProdPacientes tabs={tabsProd} activeTab={activaProd} onChange={setProd} />}
    </div>
  );
}
