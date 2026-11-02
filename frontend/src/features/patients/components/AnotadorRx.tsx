"use client";
/**
 * ANOTADOR DE RADIOGRAFÍAS — capa SVG sobre la imagen con herramientas de flecha, medida (longitud
 * en px), ángulo (3 puntos, grados) y texto. Se guardan todas juntas (PUT upsert por imagen).
 */
import { useState, useEffect, useCallback, useRef } from "react";
import { Loader2, X, Check, MousePointer2, ArrowUpRight, Ruler, Triangle, Type, Trash2, Save } from "lucide-react";
import { api, API_BASE } from "@/shared/lib/api";

type Punto = [number, number];
type Tipo = "flecha" | "medida" | "angulo" | "texto";
type Item = { tipo: Tipo; puntos: Punto[]; texto?: string; color?: string };

const HERR: { tool: Tipo | "sel"; icon: typeof MousePointer2; label: string; n: number }[] = [
  { tool: "sel", icon: MousePointer2, label: "Seleccionar", n: 0 },
  { tool: "flecha", icon: ArrowUpRight, label: "Flecha", n: 2 },
  { tool: "medida", icon: Ruler, label: "Medida", n: 2 },
  { tool: "angulo", icon: Triangle, label: "Ángulo", n: 3 },
  { tool: "texto", icon: Type, label: "Texto", n: 1 },
];
const COLORES = ["#00E5FF", "#2DD9C3", "#8B5CF6", "#C026D3", "#FFFFFF"];

const dist = (a: Punto, b: Punto) => Math.hypot(b[0] - a[0], b[1] - a[1]);
function anguloDeg(p1: Punto, v: Punto, p2: Punto) {
  const a = [p1[0] - v[0], p1[1] - v[1]], b = [p2[0] - v[0], p2[1] - v[1]];
  const cos = (a[0] * b[0] + a[1] * b[1]) / (Math.hypot(...a) * Math.hypot(...b) || 1);
  return Math.round((Math.acos(Math.max(-1, Math.min(1, cos))) * 180) / Math.PI);
}

export function AnotadorRx({ imagenId, onCerrar }: { imagenId: number; onCerrar?: () => void }) {
  const [items, setItems] = useState<Item[]>([]);
  const [tool, setTool] = useState<Tipo | "sel">("sel");
  const [color, setColor] = useState(COLORES[0]);
  const [draft, setDraft] = useState<Punto[]>([]);
  const [sel, setSel] = useState<number | null>(null);
  const [dim, setDim] = useState({ w: 1000, h: 800 });
  const [guardando, setGuardando] = useState(false);
  const [guardado, setGuardado] = useState(false);
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    api.get<{ items: Item[] }>(`/radiologia/${imagenId}/anotaciones`).then((d) => setItems(d.items || [])).catch(() => setItems([]));
    const im = new Image();
    im.onload = () => setDim({ w: im.naturalWidth || 1000, h: im.naturalHeight || 800 });
    im.src = `${API_BASE}/radiologia/${imagenId}/archivo`;
  }, [imagenId]);

  const aCoord = useCallback((e: { clientX: number; clientY: number }): Punto | null => {
    const svg = svgRef.current; if (!svg) return null;
    const pt = svg.createSVGPoint(); pt.x = e.clientX; pt.y = e.clientY;
    const ctm = svg.getScreenCTM(); if (!ctm) return null;
    const p = pt.matrixTransform(ctm.inverse());
    return [Math.round(p.x), Math.round(p.y)];
  }, []);

  const onClick = (e: React.MouseEvent) => {
    const c = aCoord(e); if (!c) return;
    if (tool === "sel") { setSel(null); return; }
    const need = HERR.find((h) => h.tool === tool)!.n;
    if (tool === "texto") {
      const t = window.prompt("Texto de la anotación:");
      if (t && t.trim()) setItems((p) => [...p, { tipo: "texto", puntos: [c], texto: t.trim(), color }]);
      return;
    }
    const next = [...draft, c];
    if (next.length >= need) {
      setItems((p) => [...p, { tipo: tool, puntos: next, color }]);
      setDraft([]);
    } else setDraft(next);
  };

  const borrarSel = () => { if (sel != null) { setItems((p) => p.filter((_, i) => i !== sel)); setSel(null); } };

  const guardar = async () => {
    setGuardando(true);
    try { await api.put(`/radiologia/${imagenId}/anotaciones`, { items }); setGuardado(true); setTimeout(() => setGuardado(false), 1500); }
    finally { setGuardando(false); }
  };

  return (
    <div className="flex flex-col h-full min-h-0 bg-white">
      <div className="flex items-center justify-between px-3 py-2 bg-[#1500A0] text-white shrink-0">
        <b className="text-[13px] uppercase tracking-wide">Anotar radiografía</b>
        {onCerrar && <button type="button" onClick={onCerrar} className="text-white/80 hover:text-white cursor-pointer"><X className="w-4 h-4" /></button>}
      </div>

      {/* Barra de herramientas */}
      <div className="flex items-center gap-1 px-2 py-1.5 border-b border-slate-100 flex-wrap">
        {HERR.map((h) => (
          <button key={h.tool} type="button" onClick={() => { setTool(h.tool); setDraft([]); }}
            title={h.label} className={`p-1.5 rounded-sm cursor-pointer ${tool === h.tool ? "bg-[#013b82] text-white" : "text-slate-500 hover:bg-[#E6EDFF]"}`}>
            <h.icon className="w-4 h-4" />
          </button>
        ))}
        <div className="w-px h-5 bg-slate-200 mx-1" />
        {COLORES.map((c) => (
          <button key={c} type="button" onClick={() => setColor(c)}
            className={`w-5 h-5 rounded-full cursor-pointer border ${color === c ? "ring-2 ring-[#013b82]" : "border-slate-300"}`}
            style={{ background: c }} title={c} />
        ))}
        <div className="w-px h-5 bg-slate-200 mx-1" />
        <button type="button" onClick={borrarSel} disabled={sel == null} title="Borrar selección"
          className="p-1.5 rounded-sm text-slate-500 hover:bg-[#E6EDFF] cursor-pointer disabled:opacity-30"><Trash2 className="w-4 h-4" /></button>
        <button type="button" onClick={guardar} disabled={guardando} title="Guardar anotaciones"
          className="ml-auto text-xs bg-[#2DD9C3] text-[#013b82] rounded-sm px-3 py-1.5 flex items-center gap-1.5 cursor-pointer disabled:opacity-50">
          {guardando ? <Loader2 className="w-4 h-4 animate-spin" /> : guardado ? <Check className="w-4 h-4" /> : <Save className="w-4 h-4" />}
          {guardado ? "Guardado" : "Guardar"}
        </button>
      </div>

      {/* Lienzo */}
      <div className="flex-1 min-h-0 bg-black grid place-items-center overflow-hidden">
        <svg ref={svgRef} viewBox={`0 0 ${dim.w} ${dim.h}`} className="max-w-full max-h-full" onClick={onClick} style={{ cursor: tool === "sel" ? "default" : "crosshair" }}>
          <defs>
            <marker id="pta" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">
              <path d="M0,0 L8,3 L0,6 Z" fill="context-stroke" />
            </marker>
          </defs>
          <image href={`${API_BASE}/radiologia/${imagenId}/archivo`} x={0} y={0} width={dim.w} height={dim.h} />
          {items.map((it, i) => (
            <ItemSvg key={i} it={it} seleccionado={sel === i} onSelect={(e) => { if (tool === "sel") { e.stopPropagation(); setSel(i); } }} />
          ))}
          {draft.map((p, i) => <circle key={i} cx={p[0]} cy={p[1]} r={3} fill="#00E5FF" />)}
        </svg>
      </div>
    </div>
  );
}

function ItemSvg({ it, seleccionado, onSelect }: { it: Item; seleccionado: boolean; onSelect: (e: React.MouseEvent) => void }) {
  const col = it.color || "#00E5FF";
  const anillo = seleccionado ? { filter: "drop-shadow(0 0 3px #fff)" } : undefined;
  const p = it.puntos;
  if (it.tipo === "texto") {
    return <text x={p[0][0]} y={p[0][1]} fill={col} fontSize={16} fontWeight={600} onClick={onSelect} style={{ cursor: "pointer", ...anillo }}>{it.texto}</text>;
  }
  if (it.tipo === "flecha") {
    return <line x1={p[0][0]} y1={p[0][1]} x2={p[1][0]} y2={p[1][1]} stroke={col} strokeWidth={2} markerEnd="url(#pta)" onClick={onSelect} style={{ cursor: "pointer", ...anillo }} />;
  }
  if (it.tipo === "medida") {
    const mid: Punto = [(p[0][0] + p[1][0]) / 2, (p[0][1] + p[1][1]) / 2];
    return (
      <g onClick={onSelect} style={{ cursor: "pointer", ...anillo }}>
        <line x1={p[0][0]} y1={p[0][1]} x2={p[1][0]} y2={p[1][1]} stroke={col} strokeWidth={2} />
        <text x={mid[0]} y={mid[1] - 5} fill={col} fontSize={14} fontWeight={600}>{Math.round(dist(p[0], p[1]))} px</text>
      </g>
    );
  }
  // ángulo (3 puntos: p1, vértice, p2)
  return (
    <g onClick={onSelect} style={{ cursor: "pointer", ...anillo }}>
      <polyline points={`${p[0][0]},${p[0][1]} ${p[1][0]},${p[1][1]} ${p[2][0]},${p[2][1]}`} fill="none" stroke={col} strokeWidth={2} />
      <text x={p[1][0] + 6} y={p[1][1] - 6} fill={col} fontSize={14} fontWeight={600}>{anguloDeg(p[0], p[1], p[2])}°</text>
    </g>
  );
}
