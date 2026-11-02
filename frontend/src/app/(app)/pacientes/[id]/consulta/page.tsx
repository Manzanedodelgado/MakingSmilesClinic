"use client";
/**
 * LA CONSULTA VIVA del paciente: el paciente que tienes delante.
 */
import { use } from "react";
import { ConsultaViva } from "@/features/patients/components/consulta/ConsultaViva";

export default function ConsultaPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return <ConsultaViva patientId={Number(id)} />;
}
