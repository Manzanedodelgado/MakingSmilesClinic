"use client";
import { useEffect, useState } from "react";
import { ChevronDown } from "lucide-react";
import { patientService } from "../services/patientService";

interface MedicamentoReceta {
  medicamento: string;
  posologia?: string;
  pauta?: string;
  duracion?: string;
  envases?: number;
  unidades?: number;
}

interface RecetaFrecuenteSelectorProps {
  patientId: number;
  onSelect: (medicamentos: MedicamentoReceta[]) => void;
}

export function RecetaFrecuenteSelector({ patientId, onSelect }: RecetaFrecuenteSelectorProps) {
  const [frecuentes, setFrecuentes] = useState<Array<{ id: number; nombre: string; medicamentos: MedicamentoReceta[] }>>([]);
  const [cargando, setCargando] = useState(false);
  const [abierto, setAbierto] = useState(false);

  useEffect(() => {
    cargarRecetas();
  }, [patientId]);

  const cargarRecetas = async () => {
    setCargando(true);
    try {
      const res = await patientService.recetasFrecuentes(patientId);
      setFrecuentes((res.recetas_frecuentes || []) as Array<{ id: number; nombre: string; medicamentos: MedicamentoReceta[] }>);
    } catch (e) {
      console.error("Error cargando recetas frecuentes:", e);
    } finally {
      setCargando(false);
    }
  };

  const handleSeleccionar = (medicamentos: MedicamentoReceta[]) => {
    onSelect(medicamentos);
    setAbierto(false);
  };

  if (cargando || frecuentes.length === 0) return null;

  return (
    <div className="relative">
      <button
        onClick={() => setAbierto(!abierto)}
        className="w-full px-3 py-2 text-left border border-gray-300 rounded-lg focus:ring-2 focus:ring-cyan-500 focus:border-transparent text-sm flex items-center justify-between hover:bg-[#E6EDFF] transition"
      >
        <span className="text-gray-600">Cargar plantilla frecuente...</span>
        <ChevronDown className={`w-4 h-4 transition-transform ${abierto ? "rotate-180" : ""}`} />
      </button>

      {abierto && (
        <div className="absolute top-full mt-1 w-full bg-white border border-gray-200 rounded-lg shadow-lg z-20 max-h-64 overflow-y-auto">
          {frecuentes.map((plantilla) => (
            <button
              key={plantilla.id}
              onClick={() => handleSeleccionar(plantilla.medicamentos)}
              className="w-full text-left px-3 py-2 hover:bg-[#E6EDFF] border-b border-gray-100 last:border-b-0 transition text-sm"
            >
              <div className="font-medium text-gray-900">{plantilla.nombre}</div>
              <div className="text-gray-600 text-xs">
                {plantilla.medicamentos.length} medicamento{plantilla.medicamentos.length !== 1 ? "s" : ""}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
