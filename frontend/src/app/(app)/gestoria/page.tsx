import { redirect } from "next/navigation";

// Gestoría entra por Facturación; Facturación/Producción son submenús del rail.
export default function GestoriaPage() {
  redirect("/gestoria/facturacion");
}
