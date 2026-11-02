import React from "react";
import { LucideIcon } from "lucide-react";

type ButtonVariant = "primary" | "secondary" | "danger" | "ghost" | "accent" | "save" | "nuevo";
type ButtonSize = "sm" | "md";

interface ClinicalButtonProps {
  children: React.ReactNode;
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: LucideIcon;
  iconPosition?: "left" | "right";
  disabled?: boolean;
  className?: string;
  onClick?: () => void;
  type?: "button" | "submit" | "reset";
  title?: string;
}

const variantClasses: Record<ButtonVariant, string> = {
  primary: "bg-[#2DD9C3] hover:bg-[#20BEAB] text-[#1500A0] border-transparent",
  secondary: "bg-white border border-[#e5e7eb] text-slate-600 hover:bg-[#E6EDFF]",
  danger: "bg-[#1500A0] hover:bg-[#0d0080] text-white border-transparent",
  ghost: "bg-transparent border border-transparent text-slate-600 hover:bg-[#E6EDFF]",
  accent: "bg-[#1500A0] hover:brightness-110 text-white border-transparent",
  // Estándar único de TODOS los botones "Guardar": teal + texto navy + borde teal oscuro.
  save: "bg-[#2DD9C3] hover:bg-[#20BEAB] text-[#1500A0] border border-[#1AA897]",
  // Estándar de TODOS los botones "Nuevo …": blanco con borde gris + texto azul.
  nuevo: "bg-white hover:bg-[#E6EDFF] border border-[#9ca3af] text-[#1500A0]",
};

const sizeClasses: Record<ButtonSize, string> = {
  sm: "px-2.5 py-1 text-[12px] gap-1",
  md: "px-4 py-1.5 text-[12px] gap-1.5",
};

export const ClinicalButton: React.FC<ClinicalButtonProps> = ({
  children,
  variant = "primary",
  size = "sm",
  icon: Icon,
  iconPosition = "left",
  disabled = false,
  className = "",
  onClick,
  type = "button",
  title,
}) => {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={`inline-flex items-center justify-center rounded-sm font-semibold uppercase tracking-wider cursor-pointer transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed ${variantClasses[variant]} ${sizeClasses[size]} ${className}`}
    >
      {Icon && iconPosition === "left" && <Icon className="w-3.5 h-3.5" />}
      {children}
      {Icon && iconPosition === "right" && <Icon className="w-3.5 h-3.5" />}
    </button>
  );
};
