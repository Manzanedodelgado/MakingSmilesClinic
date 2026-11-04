import { Suspense } from "react";
import ComunicacionClient from "./ComunicacionClient";

export default function ComunicacionPage() {
  return (
    <Suspense fallback={<div className="flex h-screen items-center justify-center text-[#7f8c8d]">Cargando...</div>}>
      <ComunicacionClient />
    </Suspense>
  );
}
