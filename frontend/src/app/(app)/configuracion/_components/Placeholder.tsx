import { ClinicalCard } from "@/shared/components";

/** Sub-sección aún no construida — mantiene la estética y deja claro el estado. */
export function Placeholder({ titulo, nota }: { titulo: string; nota?: string }) {
  return (
    <ClinicalCard>
      <div className="py-10 flex flex-col items-center justify-center text-center gap-2">
        <h2 className="text-[14px] font-semibold text-[#1500A0] uppercase tracking-wide">{titulo}</h2>
        <p className="text-[12px] text-slate-500 max-w-md leading-relaxed">
          {nota ?? "Sección en construcción. La estructura y la estética ya están en su sitio; el contenido funcional llega en el siguiente paso."}
        </p>
      </div>
    </ClinicalCard>
  );
}
