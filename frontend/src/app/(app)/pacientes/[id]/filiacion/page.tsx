"use client";
import { useParams } from "next/navigation";
import { Filiacion } from "@/features/patients/components/Filiacion";

export default function FiliacionPage() {
  const { id } = useParams<{ id: string }>();
  return <Filiacion patientId={Number(id)} />;
}
