"use client";
import { useParams } from "next/navigation";
import { FichaWorkspace } from "@/features/patients/components/FichaWorkspace";

export default function FichaPage() {
  const { id } = useParams<{ id: string }>();
  return <FichaWorkspace patientId={Number(id)} />;
}
