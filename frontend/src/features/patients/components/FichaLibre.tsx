"use client";
/**
 * Lienzo libre de las 4 cajas de la ficha: posición/tamaño en px, sin celdas ni
 * márgenes que recorten. Cada caja vive donde se suelta —encima de las demás y de
 * los márgenes si así se coloca— y nada las recoloca solas. La tocada sube al frente.
 *
 * Mover: desde cualquier punto de la caja EXCEPTO controles (botones, enlaces,
 * campos), para poder seguir pulsando todo lo de dentro. El clic sin arrastrar
 * sigue funcionando en todas partes.
 * Escalar: desde las 4 esquinas (◢◣◤◥).
 */
import { useEffect, useRef } from "react";
import { ClinicalCard } from "@/shared/components";
import { FICHA_LAYOUT_IDS, type FichaBoxId } from "./fichaLayoutDefault";

export type CajaGeo = { x: number; y: number; w: number; h: number };
export const CAJA_MIN = { w: 200, h: 140 };
export const CAJA_ALTO_MAX = 2400;

type Modo = "mover" | "se" | "sw" | "ne" | "nw";

/** Los controles trabajan con normalidad: sobre ellos no empieza ningún arrastre. */
const ES_CONTROL = "button, a, input, select, textarea, [contenteditable='true']";

export function FichaLibre({ geo, orden, cajaPorId, onAncho, alFrente, ponerGeo }: {
  geo: Record<FichaBoxId, CajaGeo> | null;
  orden: FichaBoxId[];
  cajaPorId: Record<FichaBoxId, React.ReactNode>;
  onAncho: (w: number) => void;
  alFrente: (id: FichaBoxId) => void;
  ponerGeo: (id: FichaBoxId, b: CajaGeo) => void;
}) {
  const lienzoRef = useRef<HTMLDivElement>(null);
  const arrastre = useRef<{ id: FichaBoxId; modo: Modo; x0: number; y0: number;
    g0: CajaGeo; bw: number } | null>(null);

  useEffect(() => {
    const el = lienzoRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => onAncho(e.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const mover = (e: PointerEvent) => {
      const a = arrastre.current;
      if (!a) return;
      const dx = e.clientX - a.x0, dy = e.clientY - a.y0;
      const g = a.g0;
      if (a.modo === "mover") {
        ponerGeo(a.id, { ...g,
          x: Math.min(Math.max(0, g.x + dx), Math.max(0, a.bw - g.w)),
          y: Math.max(0, g.y + dy) });
        return;
      }
      // Esquinas: cada una ancla el vértice opuesto.
      let { x, y, w, h } = g;
      if (a.modo === "se" || a.modo === "ne") w = Math.min(Math.max(CAJA_MIN.w, g.w + dx), a.bw - g.x);
      if (a.modo === "sw" || a.modo === "nw") { w = Math.min(Math.max(CAJA_MIN.w, g.w - dx), g.x + g.w); x = g.x + g.w - w; }
      if (a.modo === "se" || a.modo === "sw") h = Math.min(Math.max(CAJA_MIN.h, g.h + dy), CAJA_ALTO_MAX);
      if (a.modo === "ne" || a.modo === "nw") { h = Math.min(Math.max(CAJA_MIN.h, g.h - dy), g.y + g.h); y = g.y + g.h - h; }
      ponerGeo(a.id, { x: Math.round(x), y: Math.round(y), w: Math.round(w), h: Math.round(h) });
    };
    const soltar = () => { arrastre.current = null; };
    window.addEventListener("pointermove", mover);
    window.addEventListener("pointerup", soltar);
    window.addEventListener("pointercancel", soltar);
    return () => {
      window.removeEventListener("pointermove", mover);
      window.removeEventListener("pointerup", soltar);
      window.removeEventListener("pointercancel", soltar);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const empezar = (e: React.PointerEvent, id: FichaBoxId, modo: Modo, b: CajaGeo) => {
    const lienzo = lienzoRef.current;
    if (!lienzo) return;
    e.preventDefault(); e.stopPropagation();
    alFrente(id);
    (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
    arrastre.current = { id, modo, x0: e.clientX, y0: e.clientY, g0: { ...b }, bw: lienzo.getBoundingClientRect().width };
  };

  /** Toda la superficie mueve salvo controles (el clic sin arrastrar sigue yendo). */
  const intentarMover = (e: React.PointerEvent, id: FichaBoxId, b: CajaGeo) => {
    alFrente(id);
    if (e.button !== 0) return;
    if ((e.target as HTMLElement).closest(ES_CONTROL)) return;
    empezar(e, id, "mover", b);
  };

  const alto = geo ? Math.max(480, ...FICHA_LAYOUT_IDS.map((id) => geo[id].y + geo[id].h)) + 16 : 480;

  return (
    <div className="flex-1 min-h-0 overflow-auto">
      <div ref={lienzoRef} className="relative" style={{ height: alto }}>
        {!geo ? (
          <p className="text-[12px] text-slate-400 p-4">Colocando cajas…</p>
        ) : FICHA_LAYOUT_IDS.map((id) => {
          const b = geo[id];
          return (
            <section key={id} data-id={id}
              onPointerDown={(e) => intentarMover(e, id, b)}
              className="absolute"
              style={{ left: b.x, top: b.y, width: b.w, height: b.h, zIndex: 10 + orden.indexOf(id) }}>
              <ClinicalCard noPadding className="group relative flex flex-col h-full overflow-hidden select-none">
                <div className="caja-drag-handle absolute top-0 inset-x-0 z-10 pointer-events-none bg-[#1500A0]/85 text-[10px] text-white font-semibold uppercase tracking-wide px-2 py-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  :: arrastra para mover · esquinas para escalar
                </div>
                {cajaPorId[id]}
                <Esquina modo="nw" titulo="Redimensionar (arriba-izquierda)" onDown={(e) => empezar(e, id, "nw", b)} />
                <Esquina modo="ne" titulo="Redimensionar (arriba-derecha)" onDown={(e) => empezar(e, id, "ne", b)} />
                <Esquina modo="sw" titulo="Redimensionar (abajo-izquierda)" onDown={(e) => empezar(e, id, "sw", b)} />
                <Esquina modo="se" titulo="Redimensionar (abajo-derecha)" onDown={(e) => empezar(e, id, "se", b)} />
              </ClinicalCard>
            </section>
          );
        })}
      </div>
    </div>
  );
}

function Esquina({ modo, titulo, onDown }: {
  modo: Exclude<Modo, "mover">; titulo: string; onDown: (e: React.PointerEvent) => void;
}) {
  const pos = modo === "nw" ? "left-0 top-0" : modo === "ne" ? "right-0 top-0"
    : modo === "sw" ? "left-0 bottom-0" : "right-0 bottom-0";
  const gira = modo === "nw" ? "rotate-180" : modo === "ne" ? "rotate-90" : modo === "sw" ? "-rotate-90" : "";
  const cursor = modo === "nw" || modo === "se" ? "cursor-nwse-resize" : "cursor-nesw-resize";
  return (
    <div onPointerDown={onDown}
      aria-label={`Redimensionar ${modo}`} title={titulo}
      className={`absolute ${pos} z-10 w-5 h-5 ${cursor} touch-none grid place-items-center p-0.5 text-[#1500A0]/70 hover:text-[#1500A0] opacity-0 group-hover:opacity-100 transition-opacity`}>
      <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden className={gira}>
        <path d="M11 1 L11 11 L1 11 Z M8 11 L8 6 L4 11 Z" fill="currentColor" opacity="0.9" />
      </svg>
    </div>
  );
}
