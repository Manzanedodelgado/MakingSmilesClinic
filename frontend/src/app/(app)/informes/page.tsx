"use client";
import { InformesBuilder } from "@/features/informes/components/InformesBuilder";

export default function InformesPage() {
  return (
    <div className="flex flex-col h-full min-h-0 bg-[#FFFFFF]">
      <div className="flex-1 min-h-0 p-2.5">
        <InformesBuilder />
      </div>
    </div>
  );
}
