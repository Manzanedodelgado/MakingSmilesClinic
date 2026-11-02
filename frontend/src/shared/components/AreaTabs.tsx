"use client";
import React from "react";

interface AreaTab {
  id: string;
  label: string;
}

interface AreaTabsProps {
  tabs: AreaTab[];
  activeTab: string;
  onChange: (id: string) => void;
  className?: string;
  right?: React.ReactNode; // contenido opcional anclado a la derecha de la barra
}

// Pestañas de submenú de área — texto + subrayado cian, igual que SmilePro:
// misma fuente, tamaño y márgenes.
export const AreaTabs: React.FC<AreaTabsProps> = ({ tabs, activeTab, onChange, className = "", right }) => (
  <div className={`flex-shrink-0 flex flex-wrap items-center gap-y-1 gap-x-0 bg-white border-b border-[#e5e7eb] px-3 ${className}`}>
    {tabs.map((tab) => {
      const isActive = tab.id === activeTab;
      return (
        <button
          key={tab.id}
          type="button"
          onClick={() => onChange(tab.id)}
          className={`px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider whitespace-nowrap transition-colors border-b-2 ${
            isActive
              ? "text-[#1500A0] border-[#1ca0d1] bg-[#FFFFFF]"
              : "text-[#7f8c8d] border-transparent hover:text-[#1500A0] hover:bg-[#E6EDFF]"
          }`}
        >
          {tab.label}
        </button>
      );
    })}
    {right && <div className="ml-auto flex flex-wrap items-center justify-end gap-1.5 py-1 pr-1">{right}</div>}
  </div>
);
