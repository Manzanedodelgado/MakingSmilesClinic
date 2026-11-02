import { redirect } from "next/navigation";

// Índice del paciente → FICHA (tab por defecto, como el .37).
export default async function PacienteIndex({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  redirect(`/pacientes/${id}/ficha`);
}
