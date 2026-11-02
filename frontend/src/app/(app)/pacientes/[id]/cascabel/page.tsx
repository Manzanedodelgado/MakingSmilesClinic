"use client";
import { useParams } from "next/navigation";
import { Cascabel } from "@/features/patients/components/Cascabel";

export default function CascabelPage() {
  const { id } = useParams<{ id: string }>();
  return <Cascabel patientId={Number(id)} />;
}
