"use client";
import { useParams } from "next/navigation";
import { PlanEcon } from "@/features/patients/components/PlanEcon";

export default function PlanEconPage() {
  const { id } = useParams<{ id: string }>();
  return <PlanEcon patientId={Number(id)} />;
}
