"use client";
import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";

export interface MedicamentoReceta {
  medicamento: string;
  posologia?: string;
  pauta?: string;
  duracion?: string;
  envases?: number;
  unidades?: number;
}

export const medicamentoVacio = (): MedicamentoReceta => ({
  medicamento: "", posologia: "", pauta: "", duracion: "",
  envases: undefined, unidades: undefined,
});

/** Lógica del editor de medicamentos (antes copiada en RecetaModal y RecetaFrecuenteModal). */
export function useMedicamentos(inicial?: MedicamentoReceta[]) {
  const [medicamentos, setMedicamentos] = useState<MedicamentoReceta[]>(
    inicial && inicial.length ? inicial : [medicamentoVacio()]);
  const add = () => setMedicamentos([...medicamentos, medicamentoVacio()]);
  const remove = (index: number) => setMedicamentos(medicamentos.filter((_, i) => i !== index));
  const change = (index: number, field: keyof MedicamentoReceta, value: string | number | undefined) =>
    setMedicamentos(medicamentos.map((m, i) => (i === index ? { ...m, [field]: value } : m)));
  const normalizados = () => medicamentos
    .filter((m) => m.medicamento.trim())
    .map((m) => ({
      medicamento: m.medicamento,
      posologia: m.posologia || undefined,
      pauta: m.pauta || undefined,
      duracion: m.duracion || undefined,
      envases: m.envases,
      unidades: m.unidades,
    }));
  return { medicamentos, setMedicamentos, add, remove, change, normalizados };
}

const inputCls = "px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-cyan-500 focus:border-transparent text-sm";

/** Filas del editor (misma UI en ambos modales; solo cambia el botón de quitar). */
export function ListaMedicamentos({ medicamentos, onChange, onRemove, onAdd, quitar }: {
  medicamentos: MedicamentoReceta[];
  onChange: (index: number, field: keyof MedicamentoReceta, value: string | number | undefined) => void;
  onRemove: (index: number) => void;
  onAdd: () => void;
  quitar: "icono" | "texto";
}) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-900 mb-3">Medicamentos</h3>
      <div className="space-y-4">
        {medicamentos.map((med, idx) => (
          <div key={idx} className="border border-gray-200 rounded-lg p-3 space-y-2">
            <div className="flex gap-2 items-end">
              <input type="text" value={med.medicamento}
                onChange={(e) => onChange(idx, "medicamento", e.target.value)}
                placeholder="Nombre del medicamento *"
                className={`flex-1 ${inputCls}`} />
              {medicamentos.length > 1 && (
                <button onClick={() => onRemove(idx)}
                  className="p-2 text-gray-500 hover:text-[#C026D3] transition">
                  {quitar === "icono" ? <Trash2 className="w-4 h-4" /> : "✕"}
                </button>
              )}
            </div>
            <div className="grid grid-cols-2 gap-2">
              <input type="text" value={med.posologia || ""}
                onChange={(e) => onChange(idx, "posologia", e.target.value)}
                placeholder="Posología (ej: 500mg)" className={inputCls} />
              <input type="text" value={med.pauta || ""}
                onChange={(e) => onChange(idx, "pauta", e.target.value)}
                placeholder="Pauta (ej: cada 8h)" className={inputCls} />
            </div>
            <div className="grid grid-cols-3 gap-2">
              <input type="text" value={med.duracion || ""}
                onChange={(e) => onChange(idx, "duracion", e.target.value)}
                placeholder="Duración (ej: 10 días)" className={inputCls} />
              <input type="number" value={med.envases || ""}
                onChange={(e) => onChange(idx, "envases", e.target.value ? parseInt(e.target.value) : undefined)}
                placeholder="Envases" className={inputCls} />
              <input type="number" value={med.unidades || ""}
                onChange={(e) => onChange(idx, "unidades", e.target.value ? parseInt(e.target.value) : undefined)}
                placeholder="Unidades" className={inputCls} />
            </div>
          </div>
        ))}
      </div>
      <button onClick={onAdd}
        className="mt-3 text-sm text-cyan-600 hover:text-cyan-700 font-medium flex items-center gap-1">
        {quitar === "icono" ? <><Plus className="w-4 h-4" /> Añadir medicamento</> : "+ Añadir medicamento"}
      </button>
    </div>
  );
}
