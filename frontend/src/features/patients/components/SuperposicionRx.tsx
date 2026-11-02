"use client";
/**
 * SUPERPOSICIÓN DE RADIOGRAFÍAS — solapa dos imágenes del paciente para comparar (p. ej. inicial
 * vs final). La imagen superior se alinea a mano (arrastrar para mover, controles de escala/giro) y
 * se regula su opacidad. Comparación visual; no persiste (es una herramienta de lectura).
 */
import { useState, useEffect, useRef } from "react";
import { Loader2, X, Layers2, Move } from "lucide-react";
import { api, API_BASE } from "@/shared/lib/api";

type ImagenRx = { id: number; modalidad: string; modalidad_label: string; archivo_url: string };
const esDicom = (u: string) => u.toLowerCase().endsWith(".dcm");

export function SuperposicionRx({ patientId, onCerrar }: { patientId: number; onCerrar?: () => void }) {
  const [imgs, setImgs] = useState<ImagenRx[]>([]);
  const [loading, setLoading] = useState(false);
  const [baseId, setBaseId] = useState<number | null>(null);
  const [topId, setTopId] = useState<number | null>(null);
  const [opacidad, setOpacidad] = useState(50);
  const [escala, setEscala] = useState(100);
  const [giro, setGiro] = useState(0);
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const arrastre = useRef<{ x: number; y: number } | null>(null);

  useEffect(() => {
    setLoading(true);
    api.get<ImagenRx[]>(`/pacientes/${patientId}/radiologia`)
      .then((r) => {
        const rasterizadas = r.filter((i) => !esDicom(i.archivo_url));
        setImgs(rasterizadas);
        if (rasterizadas[0]) setBaseId(rasterizadas[0].id);
        if (rasterizadas[1]) setTopId(rasterizadas[1].id);
      })
      .catch(() => setImgs([]))
      .finally(() => setLoading(false));
  }, [patientId]);

  const onPointerDown = (e: React.PointerEvent) => { arrastre.current = { x: e.clientX - pos.x, y: e.clientY - pos.y }; (e.target as Element).setPointerCapture(e.pointerId); };
  const onPointerMove = (e: React.PointerEvent) => { if (arrastre.current) setPos({ x: e.clientX - arrastre.current.x, y: e.clientY - arrastre.current.y }); };
  const onPointerUp = () => { arrastre.current = null; };
  const reset = () => { setPos({ x: 0, y: 0 }); setEscala(100); setGiro(0); };
  const src = (id: number) => `${API_BASE}/radiologia/${id}/archivo`;

  return (
    <div className="flex flex-col h-full min-h-0 bg-white">
      <div className="flex items-center justify-between px-3 py-2 bg-[#1500A0] text-white shrink-0">
        <b className="text-[13px] uppercase tracking-wide flex items-center gap-2"><Layers2 className="w-4 h-4" /> Superposición de imágenes</b>
        {onCerrar && <button type="button" onClick={onCerrar} className="text-white/80 hover:text-white cursor-pointer"><X className="w-4 h-4" /></button>}
      </div>

      {loading ? (
        <div className="flex-1 grid place-items-center text-slate-400"><Loader2 className="w-6 h-6 animate-spin" /></div>
      ) : imgs.length < 2 ? (
        <div className="flex-1 grid place-items-center text-slate-400 text-sm text-center px-6">Se necesitan al menos 2 radiografías (no DICOM) para superponer.</div>
      ) : (
        <>
          <div className="flex items-center gap-2 px-3 py-2 border-b border-slate-100 flex-wrap text-xs">
            <span className="text-slate-500">Base</span>
            <select value={baseId ?? ""} onChange={(e) => setBaseId(Number(e.target.value))} className="border border-slate-300 rounded-sm px-1.5 py-1 cursor-pointer">
              {imgs.map((i) => <option key={i.id} value={i.id}>{i.modalidad_label} · #{i.id}</option>)}
            </select>
            <span className="text-slate-500 ml-2">Encima</span>
            <select value={topId ?? ""} onChange={(e) => setTopId(Number(e.target.value))} className="border border-slate-300 rounded-sm px-1.5 py-1 cursor-pointer">
              {imgs.map((i) => <option key={i.id} value={i.id}>{i.modalidad_label} · #{i.id}</option>)}
            </select>
            <button type="button" onClick={reset} className="ml-2 text-slate-500 hover:text-[#013b82] cursor-pointer">Reiniciar alineación</button>
          </div>

          <div className="flex-1 min-h-0 bg-black relative overflow-hidden grid place-items-center">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            {baseId != null && <img src={src(baseId)} alt="base" className="max-w-full max-h-full object-contain pointer-events-none select-none" draggable={false} />}
            {topId != null && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={src(topId)} alt="encima" draggable={false}
                onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp}
                className="absolute max-w-full max-h-full object-contain select-none touch-none"
                style={{ opacity: opacidad / 100, transform: `translate(${pos.x}px, ${pos.y}px) rotate(${giro}deg) scale(${escala / 100})`, cursor: "move" }} />
            )}
            <div className="absolute top-2 left-2 text-[10px] text-white/70 flex items-center gap-1 pointer-events-none"><Move className="w-3 h-3" /> arrastra la imagen de encima</div>
          </div>

          <div className="px-3 py-2 border-t border-slate-100 grid grid-cols-3 gap-3 text-xs">
            <label className="flex flex-col gap-0.5">Opacidad {opacidad}%
              <input type="range" min={0} max={100} value={opacidad} onChange={(e) => setOpacidad(Number(e.target.value))} className="accent-[#1ca0d1] cursor-pointer" /></label>
            <label className="flex flex-col gap-0.5">Escala {escala}%
              <input type="range" min={50} max={150} value={escala} onChange={(e) => setEscala(Number(e.target.value))} className="accent-[#1ca0d1] cursor-pointer" /></label>
            <label className="flex flex-col gap-0.5">Giro {giro}°
              <input type="range" min={-30} max={30} value={giro} onChange={(e) => setGiro(Number(e.target.value))} className="accent-[#1ca0d1] cursor-pointer" /></label>
          </div>
        </>
      )}
    </div>
  );
}
