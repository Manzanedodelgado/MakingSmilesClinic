"use client";
import { useParams } from "next/navigation";
import { Documentos } from "@/features/patients/components/Documentos";

export default function DocumentosPage() {
  const { id } = useParams<{ id: string }>();
  return <Documentos patientId={Number(id)} />;
}
