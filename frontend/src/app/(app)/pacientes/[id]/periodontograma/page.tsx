"use client";
import { useParams } from "next/navigation";
import { Periodontograma } from "@/features/patients/components/periodontograma/Periodontograma";

export default function PeriodontogramaPage() {
  const { id } = useParams<{ id: string }>();
  return <Periodontograma patientId={Number(id)} />;
}
