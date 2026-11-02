import React from "react";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "outline" | "secondary";
  size?: "sm" | "md" | "lg";
  children: React.ReactNode;
  disabled?: boolean;
  className?: string;
}

export function Button({
  variant = "primary",
  size = "md",
  children,
  disabled = false,
  className,
  ...props
}: ButtonProps) {
  const baseClasses = "inline-flex items-center justify-center font-medium rounded-lg transition-colors";

  const variantClasses = {
    primary: "bg-blue-600 text-white hover:bg-blue-700 disabled:bg-gray-400",
    outline: "border border-gray-300 text-gray-700 hover:bg-[#E6EDFF] disabled:bg-white",
    secondary: "bg-gray-200 text-gray-800 hover:bg-gray-300 disabled:bg-gray-300",
  };

  const sizeClasses = {
    sm: "px-2 py-1 text-sm",
    md: "px-4 py-2 text-base",
    lg: "px-6 py-3 text-lg",
  };

  return (
    <button
      disabled={disabled}
      className={`${baseClasses} ${variantClasses[variant]} ${sizeClasses[size]} ${className || ""}`}
      {...props}
    >
      {children}
    </button>
  );
}
