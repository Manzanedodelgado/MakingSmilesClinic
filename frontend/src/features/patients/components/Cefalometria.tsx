"use client";
/**
 * CEFALOMETRÍA — trazado guiado de Steiner sobre una telerradiografía lateral.
 *
 * Flujo: el doctor coloca los landmarks uno a uno (guiado), puede arrastrarlos para ajustar,
 * calibra (2 puntos de distancia conocida en mm) y calcula. El backend (motor de geometría
 * determinista) devuelve las medidas comparadas con la norma. Coordenadas = píxeles de imagen.
 */
import { useState, useEffect, useCallback, useRef } from "react";
import { Loader2, Check, X, Crosshair, Ruler, RotateCcw, FileDown, Wrench } from "lucide-react";
import { api, API_BASE } from "@/shared/lib/api";
import { Modal, ModalBody } from "@/shared/components";
import { ConstructorAnalisis } from "./ConstructorAnalisis";

type Punto = [number, number];
type LandmarkDef = { code: string; label: string; hint: string };
type Medida = { valor: number | null; label: string; norma: number | null; sd: number | null; unidad: string; desviacion: number | null };
type Trazado = {
  id: number; imagen_id: number; analisis: string;
  landmarks: Record<string, Punto>; calibracion: { p1: Punto; p2: Punto; mm: number } | null;
  mediciones: Record<string, Medida>; interpretacion: { clase: string | null; patron: string | null }; calibrada: boolean;
};

type AnalisisOpt = { analisis: string; label: string };

export function Cefalometria({ imagenId, onCerrar }: { imagenId: number; onCerrar?: () => void }) {
  const [analisis, setAnalisis] = useState("steiner");
  const [disponibles, setDisponibles] = useState<AnalisisOpt[]>([]);
  const [defs, setDefs] = useState<LandmarkDef[]>([]);
  const [landmarks, setLandmarks] = useState<Record<string, Punto>>({});
  const [calib, setCalib] = useState<{ p1: Punto; p2: Punto; mm: number } | null>(null);
  const [modo, setModo] = useState<"landmarks" | "calibrar">("landmarks");
  const [calibTmp, setCalibTmp] = useState<Punto[]>([]);
  const [mmInput, setMmInput] = useState("10");
  const [res, setRes] = useState<Trazado | null>(null);
  const [dim, setDim] = useState<{ w: number; h: number }>({ w: 1000, h: 800 });
  const [guardando, setGuardando] = useState(false);
  const [constructor, setConstructor] = useState(false);
  const [recarga, setRecarga] = useState(0);          // fuerza recarga de disponibles al crear/borrar
  const svgRef = useRef<SVGSVGElement>(null);
  const arrastrando = useRef<string | null>(null);

  // Definición guiada + trazado previo del análisis activo (recarga al cambiar de análisis)
  useEffect(() => {
    api.get<{ landmarks: LandmarkDef[]; disponibles: AnalisisOpt[] }>(`/cefalometria/definicion?analisis=${analisis}`)
      .then((d) => { setDefs(d.landmarks); setDisponibles(d.disponibles); }).catch(() => setDefs([]));
    setModo("landmarks"); setCalibTmp([]);
    api.get<Trazado[]>(`/radiologia/${imagenId}/cefalometria`).then((ts) => {
      const t = ts.find((x) => x.analisis === analisis);
      if (t) { setLandmarks(t.landmarks); setCalib(t.calibracion); setRes(t); }
      else { setLandmarks({}); setCalib(null); setRes(null); }
    }).catch(() => { setLandmarks({}); setCalib(null); setRes(null); });
  }, [imagenId, analisis, recarga]);

  // Tamaño natural de la imagen → viewBox en píxeles de imagen (mismos que usa el backend)
  useEffect(() => {
    const im = new Image();
    im.onload = () => setDim({ w: im.naturalWidth || 1000, h: im.naturalHeight || 800 });
    im.src = `${API_BASE}/radiologia/${imagenId}/archivo`;
  }, [imagenId]);

  const siguiente = defs.find((d) => !landmarks[d.code]);        // próximo landmark a colocar

  const aCoordSvg = useCallback((e: { clientX: number; clientY: number }): Punto | null => {
    const svg = svgRef.current;
    if (!svg) return null;
    const pt = svg.createSVGPoint(); pt.x = e.clientX; pt.y = e.clientY;
    const ctm = svg.getScreenCTM();
    if (!ctm) return null;
    const p = pt.matrixTransform(ctm.inverse());
    return [Math.round(p.x), Math.round(p.y)];
  }, []);

  const onClickLienzo = (e: React.MouseEvent) => {
    if (arrastrando.current) return;
    const c = aCoordSvg(e);
    if (!c) return;
    if (modo === "calibrar") {
      const next = [...calibTmp, c].slice(-2);
      setCalibTmp(next);
      if (next.length === 2) {
        const mm = parseFloat(mmInput) || 10;
        setCalib({ p1: next[0], p2: next[1], mm });
        setCalibTmp([]); setModo("landmarks");
      }
      return;
    }
    if (siguiente) setLandmarks((p) => ({ ...p, [siguiente.code]: c }));
  };

  // Arrastre de un landmark ya colocado
  const onPointerMove = (e: React.PointerEvent) => {
    if (!arrastrando.current) return;
    const c = aCoordSvg(e);
    if (c) setLandmarks((p) => ({ ...p, [arrastrando.current as string]: c }));
  };

  const calcular = async () => {
    setGuardando(true);
    try {
      const t = await api.post<Trazado>(`/radiologia/${imagenId}/cefalometria`, {
        analisis, landmarks, calibracion: calib,
      });
      setRes(t);
    } finally { setGuardando(false); }
  };
  const reset = () => { setLandmarks({}); setCalib(null); setRes(null); setCalibTmp([]); setModo("landmarks"); };

  const colorDesv = (m: Medida) => {
    if (m.desviacion == null || m.sd == null) return "text-slate-700";
    const z = Math.abs(m.desviacion) / m.sd;
    return z <= 1 ? "text-[#0F8C7D]" : z <= 2 ? "text-[#7C3AED]" : "text-[#C026D3]";
  };

  return (
    <div className="flex flex-col h-full min-h-0 bg-white">
      <div className="flex items-center justify-between px-3 py-2 bg-[#1500A0] text-white shrink-0">
        <b className="text-[13px] uppercase tracking-wide flex items-center gap-2"><Crosshair className="w-4 h-4" /> Cefalometría</b>
        <div className="flex items-center gap-2">
          <select value={analisis} onChange={(e) => setAnalisis(e.target.value)}
            className="text-xs bg-white/15 text-white rounded-sm px-1.5 py-1 cursor-pointer border border-white/20">
            {disponibles.map((a) => <option key={a.analisis} value={a.analisis} className="text-slate-800">{a.label}</option>)}
          </select>
          <button type="button" onClick={() => setConstructor(true)} title="Análisis a medida" className="text-white/80 hover:text-white cursor-pointer"><Wrench className="w-4 h-4" /></button>
          <button type="button" onClick={reset} title="Reiniciar trazado" className="text-white/80 hover:text-white cursor-pointer"><RotateCcw className="w-4 h-4" /></button>
          {onCerrar && <button type="button" onClick={onCerrar} className="text-white/80 hover:text-white cursor-pointer"><X className="w-4 h-4" /></button>}
        </div>
      </div>

      <div className="flex-1 min-h-0 flex">
        {/* Lienzo */}
        <div className="flex-1 min-w-0 bg-slate-900 relative overflow-hidden">
          <svg ref={svgRef} viewBox={`0 0 ${dim.w} ${dim.h}`} className="w-full h-full touch-none"
            onClick={onClickLienzo} onPointerMove={onPointerMove}
            onPointerUp={() => { arrastrando.current = null; }}>
            <image href={`${API_BASE}/radiologia/${imagenId}/archivo`} x={0} y={0} width={dim.w} height={dim.h} />
            {/* calibración */}
            {calib && (
              <g>
                <line x1={calib.p1[0]} y1={calib.p1[1]} x2={calib.p2[0]} y2={calib.p2[1]} stroke="#2DD9C3" strokeWidth={2} />
                <text x={(calib.p1[0] + calib.p2[0]) / 2} y={(calib.p1[1] + calib.p2[1]) / 2 - 6} fill="#2DD9C3" fontSize={16}>{calib.mm} mm</text>
              </g>
            )}
            {calibTmp.map((p, i) => <circle key={i} cx={p[0]} cy={p[1]} r={5} fill="#2DD9C3" />)}
            {/* landmarks */}
            {Object.entries(landmarks).map(([code, p]) => (
              <g key={code} onPointerDown={(e) => { e.stopPropagation(); arrastrando.current = code; }} className="cursor-move">
                <circle cx={p[0]} cy={p[1]} r={6} fill="#1ca0d1" stroke="#fff" strokeWidth={1.5} />
                <text x={p[0] + 9} y={p[1] + 4} fill="#00E5FF" fontSize={15} fontWeight={600}>{code}</text>
              </g>
            ))}
          </svg>
          {/* pista guiada */}
          <div className="absolute bottom-2 left-2 right-2 flex items-center justify-center pointer-events-none">
            <div className="bg-black/70 text-white text-xs rounded-sm px-3 py-1.5">
              {modo === "calibrar"
                ? `Calibración: marca 2 puntos separados ${mmInput} mm (${calibTmp.length}/2)`
                : siguiente
                  ? <>Coloca <b className="text-[#00E5FF]">{siguiente.label}</b> — {siguiente.hint}</>
                  : "Todos los puntos colocados. Puedes arrastrar para ajustar."}
            </div>
          </div>
        </div>

        {/* Panel derecho */}
        <div className="w-72 shrink-0 border-l border-slate-200 flex flex-col overflow-y-auto">
          <div className="p-2 border-b border-slate-100 flex flex-col gap-2">
            <div className="flex items-center gap-1.5">
              <input value={mmInput} onChange={(e) => setMmInput(e.target.value)} className="w-16 text-xs border border-slate-300 rounded-sm px-1.5 py-1" />
              <button type="button" onClick={() => { setModo(modo === "calibrar" ? "landmarks" : "calibrar"); setCalibTmp([]); }}
                className={`flex-1 text-xs rounded-sm px-2 py-1.5 flex items-center justify-center gap-1 cursor-pointer ${modo === "calibrar" ? "bg-[#2DD9C3] text-[#013b82]" : "bg-white text-slate-600 hover:bg-slate-200"}`}>
                <Ruler className="w-3.5 h-3.5" /> {calib ? "Recalibrar (mm)" : "Calibrar (mm)"}
              </button>
            </div>
            <button type="button" onClick={calcular} disabled={guardando || Object.keys(landmarks).length < 3}
              className="w-full text-xs bg-[#013b82] text-white rounded-sm px-2 py-2 flex items-center justify-center gap-1.5 cursor-pointer disabled:opacity-50">
              {guardando ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />} Calcular y guardar
            </button>
            {res && (
              <button type="button"
                onClick={() => window.open(`${API_BASE}/radiologia/${imagenId}/cefalometria/${analisis}/informe.pdf`, "_blank")}
                className="w-full text-xs bg-white hover:bg-slate-200 text-slate-700 rounded-sm px-2 py-1.5 flex items-center justify-center gap-1.5 cursor-pointer">
                <FileDown className="w-3.5 h-3.5" /> Informe PDF
              </button>
            )}
          </div>

          {/* Progreso landmarks */}
          <div className="p-2 grid grid-cols-2 gap-1">
            {defs.map((d) => (
              <button key={d.code} type="button"
                onClick={() => setLandmarks((p) => { const n = { ...p }; delete n[d.code]; return n; })}
                title={landmarks[d.code] ? "Quitar para recolocar" : d.hint}
                className={`text-[11px] rounded-sm px-1.5 py-1 text-left truncate cursor-pointer ${landmarks[d.code] ? "bg-[#1ca0d1]/15 text-[#013b82]" : "bg-white text-slate-400"}`}>
                {landmarks[d.code] ? "●" : "○"} {d.code} · {d.label.split(" ")[0]}
              </button>
            ))}
          </div>

          {/* Resultados */}
          {res && (
            <div className="p-2 border-t border-slate-100">
              <div className="text-[11px] uppercase tracking-wide text-slate-400 mb-1">Análisis {res.calibrada ? "" : "(sin mm)"}</div>
              <table className="w-full text-xs">
                <tbody>
                  {Object.values(res.mediciones).map((m) => (
                    <tr key={m.label} className="border-b border-slate-50">
                      <td className="py-1 text-slate-500 pr-1">{m.label}</td>
                      <td className={`py-1 text-right font-semibold ${colorDesv(m)}`}>{m.valor ?? "—"}{m.unidad}</td>
                      <td className="py-1 text-right text-slate-300 pl-1 w-10">{m.norma ?? ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {(res.interpretacion.clase || res.interpretacion.patron) && (
                <div className="mt-2 text-xs bg-white rounded-sm p-2 text-slate-600 space-y-0.5">
                  {res.interpretacion.clase && <div><b className="text-[#013b82]">Clase:</b> {res.interpretacion.clase}</div>}
                  {res.interpretacion.patron && <div><b className="text-[#013b82]">Patrón:</b> {res.interpretacion.patron}</div>}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {constructor && (
        <Modal title="Análisis a medida" size="md" onClose={() => setConstructor(false)} closeOnBackdrop={false} zIndex={70}
          className="h-[88vh] !max-w-[620px]">
          <ModalBody className="!p-0 !overflow-hidden">
            <ConstructorAnalisis onCerrar={() => setConstructor(false)} onCambio={() => setRecarga((n) => n + 1)} />
          </ModalBody>
        </Modal>
      )}
    </div>
  );
}
