"use client";
import { AlertTriangle, Calendar, CheckCircle2, GitBranch, HelpCircle, MessageSquare, XCircle } from "lucide-react";
/**
 * Motion › Flujos — los flujos conversacionales REALES de WhatsApp (máquina de estados
 * del backend: domain/services/whatsapp_flujos). Tarjetas informativas: detonante + pasos.
 * Se leen de /motion/flujos (no hardcodeado en el front).
 */
import { useEffect, useState } from "react";
import { api } from "@/shared/lib/api";
import { ClinicalCard } from "@/shared/components";

interface Flujo { id: string; nombre: string; detonante: string; pasos: string[] }

const ICONO: Record<string, { icon: React.ElementType; color: string }> = {
  urgencia: { icon: AlertTriangle, color: "#C026D3" },
  reservar: { icon: Calendar, color: "#3388FF" },
  confirmar: { icon: CheckCircle2, color: "#2DD9C3" },
  cancelar: { icon: XCircle, color: "#1ca0d1" },
  consultar: { icon: HelpCircle, color: "#1500A0" },
  general: { icon: MessageSquare, color: "#7f8c8d" },
};

export function MotionFlujos() {
  const [flujos, setFlujos] = useState<Flujo[] | null>(null);

  useEffect(() => {
    api.get<{ data: Flujo[] }>("/motion/flujos").then((r) => setFlujos(r.data)).catch(() => setFlujos([]));
  }, []);

  if (!flujos) return <div className="text-[12px] text-slate-400 italic py-10 text-center">Cargando…</div>;

  return (
    <div className="max-w-5xl space-y-3">
      <div className="flex items-center gap-2">
        <GitBranch className="w-4 h-4 text-[#1ca0d1]" />
        <span className="text-[12px] font-semibold text-[#1500A0]">{flujos.length} flujos conversacionales</span>
        <span className="text-[10px] font-semibold uppercase text-[#2DD9C3] bg-[#FFFFFF] border border-[#2DD9C3]/40 rounded-sm px-2 py-0.5">Máquina de estados</span>
      </div>
      <p className="text-[11px] text-[#7f8c8d]">
        Cómo responde el asistente a los mensajes ENTRANTES de los pacientes por WhatsApp. Se activa con el agente Alex (Config › IA&apos;s).
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {flujos.map((f) => {
          const { icon: Icon, color } = ICONO[f.id] ?? ICONO.general;
          return (
            <ClinicalCard key={f.id} className="!p-3">
              <div className="flex items-center gap-2.5 mb-2.5">
                <div className="w-8 h-8 rounded-sm flex items-center justify-center shrink-0" style={{ backgroundColor: color + "18" }}>
                  <Icon className="w-4 h-4" style={{ color }} />
                </div>
                <div className="min-w-0">
                  <p className="text-[12px] font-semibold text-[#1500A0]">{f.nombre}</p>
                  <p className="text-[10px] text-[#7f8c8d] truncate">{f.detonante}</p>
                </div>
              </div>
              <div className="space-y-1">
                {f.pasos.map((paso, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <div className="w-5 h-5 rounded-sm bg-[#FFFFFF] border border-[#e5e7eb] flex items-center justify-center shrink-0">
                      <span className="text-[10px] font-semibold text-[#7f8c8d]">{i + 1}</span>
                    </div>
                    <span className="text-[10px] text-[#333]">{paso}</span>
                  </div>
                ))}
              </div>
            </ClinicalCard>
          );
        })}
      </div>
    </div>
  );
}
