"use client";
/** Campo de filiación con autoguardado al perder el foco. Estilos = config-styles (fuente única). */
import { useEffect, useId, useState } from "react";
import { Check, Loader2 } from "lucide-react";
import { INPUT, LABEL } from "@/shared/components";
import { useDirtyForm } from "../store/patientSession";

interface Props {
  label: string;
  value: string;
  onSave: (v: string) => Promise<void>;
  type?: "text" | "date" | "number" | "email";
  readOnly?: boolean;
  placeholder?: string;
}

export function CampoEdit({ label, value, onSave, type = "text", readOnly = false, placeholder }: Props) {
  const [val, setVal] = useState(value);
  const [estado, setEstado] = useState<"idle" | "guardando" | "ok" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const fieldId = useId();

  useEffect(() => { setVal(value); }, [value]);

  async function guardar() {
    if (val === value || readOnly) return;
    setEstado("guardando"); setError(null);
    try {
      await onSave(val);
      setEstado("ok");
      setTimeout(() => setEstado("idle"), 1200);
    } catch (e) {
      setEstado("error");
      setError(e instanceof Error ? e.message.replace(/^PUT.*?→ \d+ /, "").slice(0, 120) : "Error al guardar");
      setVal(value); // revertir al valor confirmado
    }
  }

  // Campo con texto editado y aún sin guardar → cuenta como cambio pendiente para el guard.
  useDirtyForm(`campo:${fieldId}`, !readOnly && val !== value, guardar);

  return (
    <div className="min-w-0">
      {label && (
        <label className={`${LABEL} !mb-0 leading-none truncate`}>
          {label}
          {estado === "guardando" && <Loader2 className="inline w-2.5 h-2.5 ml-1 animate-spin text-[#1ca0d1]" />}
          {estado === "ok" && <Check className="inline w-2.5 h-2.5 ml-1 text-[#0F8C7D]" />}
        </label>
      )}
      <input
        type={type}
        value={val ?? ""}
        placeholder={placeholder}
        readOnly={readOnly}
        onChange={(e) => setVal(e.target.value)}
        onBlur={guardar}
        onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
        className={`${INPUT} !py-0.5 !text-[12px] !rounded-md uppercase placeholder:normal-case ${readOnly ? "bg-white text-slate-400 cursor-not-allowed" : ""} ${estado === "error" ? "border-[#C026D3]" : ""}`}
      />
      {error && <p className="text-[9px] text-[#C026D3] leading-none">{error}</p>}
    </div>
  );
}
