import { Placeholder } from "../../_components/Placeholder";
import { TablasExplorer } from "../../_components/TablasExplorer";
import { ConfigDocumentos } from "../../_components/ConfigDocumentos";
import { ConfigPresupuestos } from "../../_components/ConfigPresupuestos";
import { DocumentosAdmin } from "../../_components/DocumentosAdmin";

const TITULOS: Record<string, string> = {
  tablas: "Explorador de Base de Datos",
  metricas: "Métricas",
  diseno: "Diseño",
  documentos: "Documentos",
};

export default async function AdminSubPage({ params }: { params: Promise<{ sub: string }> }) {
  const { sub } = await params;
  if (sub === "tablas") return <TablasExplorer />;
  if (sub === "diseno") return <ConfigDocumentos />;                   // editor de plantillas HTML (cómo se ven)
  if (sub === "documentos") return <DocumentosAdmin />;               // catálogo por tipo (Presupuestos/Consentimientos/…)
  if (sub === "plantillas-presupuesto") return <ConfigPresupuestos />; // alias histórico → ahora dentro de Documentos
  return <Placeholder titulo={TITULOS[sub] ?? sub} />;
}
