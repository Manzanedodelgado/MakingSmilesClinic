"use client";
import { Suspense } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { DentIA } from "@/features/patients/components/dentia/DentIA";

function Contenido() {
  const { id } = useParams<{ id: string }>();
  const f = useSearchParams().get("f");
  if (!f) return <div className="p-10 text-slate-500">Abre DentIA desde una radiografía de Multimedia.</div>;
  return <DentIA key={f} patientId={Number(id)} fileId={f} />;
}

export default function DentiaPage() {
  return <Suspense fallback={null}><Contenido /></Suspense>;
}
