"use client";
import { useParams } from "next/navigation";
import { Odontograma } from "@/features/patients/components/Odontograma";

export default function OdontogramaPage() {
  const { id } = useParams<{ id: string }>();
  return <Odontograma patientId={Number(id)} />;
}
