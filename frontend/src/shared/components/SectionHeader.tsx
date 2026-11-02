import React from "react";

interface SectionHeaderProps {
  title: string;
  icon?: React.ElementType;
  customIcon?: React.ReactNode;
  action?: React.ReactNode;
  variant?: "default" | "dark" | "blue";
  className?: string;
}

export const SectionHeader: React.FC<SectionHeaderProps> = ({
  title,
  icon: Icon,
  customIcon,
  action,
  variant = "default",
  className = "",
}) => {
  if (variant === "dark" || variant === "blue") {
    const bg = variant === "dark" ? "bg-[#1500A0]" : "bg-[#1ca0d1]";
    const fg = variant === "blue" ? "text-[#1500A0]" : "text-white";
    return (
      <div className={`flex items-center justify-between px-3 py-1.5 ${bg} ${fg} rounded-t-sm ${className}`}>
        <div className="flex items-center gap-2">
          {customIcon ? (
            <div className="w-6 h-6 rounded-full overflow-hidden bg-white/10 flex items-center justify-center p-0.5 border border-white/20">
              {customIcon}
            </div>
          ) : (
            Icon && <Icon className={`w-4 h-4 ${fg}`} />
          )}
          <h2 className="text-[13px] font-semibold">{title}</h2>
        </div>
        {action && <div>{action}</div>}
      </div>
    );
  }
  return (
    <div className={`flex items-center justify-between mb-2 pb-1.5 border-b border-[#e5e7eb] ${className}`}>
      <div className="flex items-center gap-2">
        {customIcon ? (
          <div className="w-6 h-6 rounded-full overflow-hidden bg-white flex items-center justify-center p-0.5">
            {customIcon}
          </div>
        ) : (
          Icon && <Icon className="w-4 h-4 text-[#1500A0]" />
        )}
        <h2 className="text-[14px] font-semibold text-[#34363A]">{title}</h2>
      </div>
      {action && <div>{action}</div>}
    </div>
  );
};
