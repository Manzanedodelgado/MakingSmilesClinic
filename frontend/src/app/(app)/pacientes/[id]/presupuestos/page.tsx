"use client";
import { useParams } from "next/navigation";
import { Presupuestos } from "@/features/patients/components/Presupuestos";

export default function PresupuestosPage() {
  const { id } = useParams<{ id: string }>();
  return <Presupuestos patientId={Number(id)} />;
}
