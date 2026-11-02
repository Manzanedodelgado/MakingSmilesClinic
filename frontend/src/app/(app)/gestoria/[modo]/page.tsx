import { notFound } from "next/navigation";
import { GestoriaWorkspace } from "@/features/gestoria/components/GestoriaWorkspace";

// Producción / Facturación — modos de Gestoría (submenús del rail).
export default async function GestoriaModoPage({ params }: { params: Promise<{ modo: string }> }) {
  const { modo } = await params;
  if (modo !== "produccion" && modo !== "facturacion") notFound();
  return <GestoriaWorkspace modo={modo} />;
}
