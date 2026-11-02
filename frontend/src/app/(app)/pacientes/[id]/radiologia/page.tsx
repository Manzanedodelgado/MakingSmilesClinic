"use client";
import { useParams } from "next/navigation";
import { Radiologia } from "@/features/patients/components/Radiologia";

export default function RadiologiaPage() {
  const { id } = useParams<{ id: string }>();
  return <Radiologia patientId={Number(id)} />;
}
