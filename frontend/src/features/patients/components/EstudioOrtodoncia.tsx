"use client";
/**
 * ESTUDIO DE ORTODONCIA (web) — muestra los estudios fotográficos que el doctor hace en la APP
 * (serie estándar de tomas), junto a sus radiografías y cefalometría, y permite imprimir / enviar
 * el resultado. Las fotos vienen de estudios_ortodoncia (backend) y se sirven por /media.
 */
import { useState, useEffect, useCallback } from "react";
import { Loader2, Braces, Printer, Send, ScanSearch, Crosshair } from "lucide-react";
import { SectionHeader } from "@/shared/components";
import { api, API_BASE } from "@/shared/lib/api";
import { useEventStream } from "@/shared/hooks/useEventStream";

type Foto = { id: string; tipo: string; url: string; ancho: number | null; alto: number | null };
type Estudio = { id: number; etapa: string; estado: string; fecha: string | null; notas: string | null; fotos: Foto[] };
type ImagenRx = { id: number; modalidad: string; modalidad_label: string; archivo_url: string };

const NOMBRE_TOMA: Record<string, string> = {
  frontal_reposo: "Frontal reposo", frontal_sonrisa: "Frontal sonrisa", perfil_derecho: "Perfil derecho",
  tres_cuartos_sonrisa: "Tres cuartos", intraoral_frontal: "Intraoral frontal",
  intraoral_lateral_derecha: "Lateral dcha.", intraoral_lateral_izquierda: "Lateral izq.",
  oclusal_superior: "Oclusal superior", oclusal_inferior: "Oclusal inferior", overjet_lateral: "Overjet",
};
const fmt = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString("es-ES") : "—");
const esDicom = (u: string) => u.toLowerCase().endsWith(".dcm");

export function EstudioOrtodoncia({ patientId }: { patientId: number }) {
  const [estudios, setEstudios] = useState<Estudio[]>([]);
  const [rx, setRx] = useState<ImagenRx[]>([]);
  const [sel, setSel] = useState(0);
  const [loading, setLoading] = useState(false);
  const [enviando, setEnviando] = useState(false);

  const cargar = useCallback(async () => {
    setLoading(true);
    try {
      const [e, r] = await Promise.all([
        api.get<{ estudios: Estudio[] }>(`/pacientes/${patientId}/estudios-ortodoncia`),
        api.get<ImagenRx[]>(`/pacientes/${patientId}/radiologia`).catch(() => []),
      ]);
      setEstudios(e.estudios); setRx(Array.isArray(r) ? r : []);
    } catch { setEstudios([]); }
    finally { setLoading(false); }
  }, [patientId]);
  useEffect(() => { void cargar(); }, [cargar]);

  // Tiempo real: mientras el doctor toma la serie de fotos desde la app, la ficha
  // web abierta en este mismo paciente muestra las fotos segun se suben.
  useEventStream({
    "estudio.foto": (d) => { if (d.paciente_id === patientId) void cargar(); },
    "estudio.foto_borrada": (d) => { if (d.paciente_id === patientId) void cargar(); },
  }, [patientId]);

  const est = estudios[sel];
  const cefalometricas = rx.filter((i) => i.modalidad === "lateral_cefalica" || i.modalidad === "panoramica");

  const imprimir = () => { if (est) window.open(`${API_BASE}/pacientes/${patientId}/estudios-ortodoncia/${est.id}/informe.pdf`, "_blank"); };
  const enviar = async (canal: "whatsapp" | "email") => {
    if (!est) return;
    setEnviando(true);
    try {
      await api.post(`/pacientes/${patientId}/estudios-ortodoncia/${est.id}/enviar`, { canal });
      alert(canal === "whatsapp" ? "Enviado por WhatsApp" : "Enviado por email");
    } catch (e) { alert(e instanceof Error ? e.message.slice(0, 160) : "No se pudo enviar"); }
    finally { setEnviando(false); }
  };

  return (
    <div className="flex flex-col h-full min-h-0">
      <SectionHeader className="h-[34px]" variant="dark" title="Estudio de ortodoncia" icon={Braces} />

      {loading ? (
        <div className="flex-1 grid place-items-center text-slate-400"><Loader2 className="w-5 h-5 animate-spin" /></div>
      ) : estudios.length === 0 ? (
        <div className="flex-1 grid place-items-center text-slate-400 text-sm text-center px-6">
          <div className="flex flex-col items-center gap-1"><ScanSearch className="w-6 h-6" />Sin estudios de ortodoncia. El doctor los crea desde la app (serie de fotos).</div>
        </div>
      ) : (
        <div className="flex-1 min-h-0 overflow-y-auto">
          {/* Barra: selector de estudio + acciones */}
          <div className="flex items-center gap-2 px-3 py-2 border-b border-slate-100 flex-wrap sticky top-0 bg-white z-10">
            <select value={sel} onChange={(e) => setSel(Number(e.target.value))}
              className="text-xs border border-slate-300 rounded-sm px-2 py-1 cursor-pointer">
              {estudios.map((e, i) => <option key={e.id} value={i}>{e.etapa.charAt(0).toUpperCase() + e.etapa.slice(1)} · {fmt(e.fecha)} · {e.fotos.length} fotos {e.estado === "completado" ? "✓" : ""}</option>)}
            </select>
            <div className="ml-auto flex items-center gap-1.5">
              <button type="button" onClick={imprimir} className="text-xs bg-white hover:bg-slate-200 text-slate-700 rounded-sm px-2.5 py-1.5 flex items-center gap-1 cursor-pointer"><Printer className="w-3.5 h-3.5" /> Imprimir</button>
              <button type="button" onClick={() => enviar("whatsapp")} disabled={enviando} className="text-xs bg-[#20BEAB]/15 hover:bg-[#20BEAB]/25 text-[#0F8C7D] rounded-sm px-2.5 py-1.5 flex items-center gap-1 cursor-pointer disabled:opacity-50"><Send className="w-3.5 h-3.5" /> WhatsApp</button>
              <button type="button" onClick={() => enviar("email")} disabled={enviando} className="text-xs bg-[#013b82]/10 hover:bg-[#013b82]/20 text-[#013b82] rounded-sm px-2.5 py-1.5 flex items-center gap-1 cursor-pointer disabled:opacity-50"><Send className="w-3.5 h-3.5" /> Email</button>
            </div>
          </div>

          {est && (
            <div className="p-3 flex flex-col gap-4">
              {/* Serie fotográfica */}
              <div>
                <div className="text-[11px] uppercase tracking-wide text-slate-400 mb-1.5">Serie fotográfica ({est.fotos.length})</div>
                {est.fotos.length === 0 ? <div className="text-xs text-slate-400">Sin fotos.</div> : (
                  <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
                    {est.fotos.map((f) => (
                      <div key={f.tipo} className="rounded-sm border border-slate-200 overflow-hidden bg-white">
                        <div className="aspect-square bg-slate-900">
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img src={`${API_BASE}${f.url}`} alt={NOMBRE_TOMA[f.tipo] ?? f.tipo} className="w-full h-full object-cover" loading="lazy" />
                        </div>
                        <div className="text-[10px] text-slate-600 px-1.5 py-1 truncate">{NOMBRE_TOMA[f.tipo] ?? f.tipo}</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Radiografías vinculadas */}
              {cefalometricas.length > 0 && (
                <div>
                  <div className="text-[11px] uppercase tracking-wide text-slate-400 mb-1.5">Radiografías</div>
                  <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
                    {cefalometricas.map((i) => (
                      <div key={i.id} className="rounded-sm border border-slate-200 overflow-hidden bg-white">
                        <div className="aspect-square bg-slate-900 relative">
                          {esDicom(i.archivo_url) ? <div className="w-full h-full grid place-items-center text-slate-400 text-xs">DICOM</div> : (
                            // eslint-disable-next-line @next/next/no-img-element
                            <img src={`${API_BASE}/radiologia/${i.id}/archivo`} alt={i.modalidad_label} className="w-full h-full object-contain" loading="lazy" />
                          )}
                          <span className="absolute top-1 left-1 text-[9px] bg-[#013b82] text-white px-1 py-0.5 rounded-sm">{i.modalidad_label}</span>
                        </div>
                        <div className="text-[10px] text-slate-500 px-1.5 py-1 flex items-center gap-1"><Crosshair className="w-2.5 h-2.5" /> {i.modalidad === "lateral_cefalica" ? "Cefalometría disponible" : "Radiografía"}</div>
                      </div>
                    ))}
                  </div>
                  <div className="text-[11px] text-slate-400 mt-1">La cefalometría de la lateral se traza en el panel de Radiología.</div>
                </div>
              )}

              {est.notas && <div className="text-xs bg-white rounded-sm p-2 text-slate-600"><b>Notas:</b> {est.notas}</div>}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
