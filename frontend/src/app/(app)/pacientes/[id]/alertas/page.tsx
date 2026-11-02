"use client";
import { useParams } from "next/navigation";
import { Alertas } from "@/features/patients/components/Alertas";

export default function AlertasPage() {
  const { id } = useParams<{ id: string }>();
  return <Alertas patientId={Number(id)} />;
}
