import React from "react";

interface ClinicalCardProps {
  children: React.ReactNode;
  className?: string;
  noPadding?: boolean;
  /** Padding reducido (p-2 en vez de p-3) — para formularios con muchas cards apiladas
   * (Filiación) donde ahorrar 8px por card evita scroll innecesario. */
  compact?: boolean;
}

export const ClinicalCard: React.FC<ClinicalCardProps> = ({ children, className = "", noPadding = false, compact = false }) => {
  const padding = noPadding ? "" : compact ? "p-1.5" : "p-3";
  return (
    <div className={`min-w-0 bg-white border border-[#E8EAEE] rounded-sm shadow-[0_2px_8px_rgba(30,40,60,0.10)] ${padding} ${className}`}>
      {children}
    </div>
  );
};
