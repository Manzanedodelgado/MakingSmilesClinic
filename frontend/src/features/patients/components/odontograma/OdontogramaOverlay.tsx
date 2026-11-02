import { useState, useMemo, useCallback } from 'react';
import TratamientoSVG, { bracketCenter, ORDEN_ARCO_SUP, ORDEN_ARCO_INF } from './TratamientoSVG';
import { pathDesdePuntos, TODAS_LAS_PIEZAS, baseOdontograma } from './odontogramaUtils';
export type { PiezaFDI } from './odontogramaUtils';
export { TODAS_LAS_PIEZAS } from './odontogramaUtils';

export interface PiezaMarcada {
 pieza: string;
 tratamiento: string;
 precio?: string;
 color?: string;
 imagen?: string; // ruta alternativa p.ej. '/piezas/11/endodoncia.png'
 caras?: string; // caras afectadas (p.ej. "OM", "MOD"). Solo para tratamientos por cara (caries, obturación)
 isPlanificado?: boolean;
 isInicial?: boolean; // Para ocultar el fondeo de las muelas si la exodoncia es preexistente
}

// Coordenadas en porcentaje sobre odontograma.png (726×386). Centros de cada pieza.
export const TOOTH_COORDS: Record<string, { x: number; y: number }> = {
 '18': { x: 3.6, y: 18.5 }, '17': { x: 11.3, y: 18.5 }, '16': { x: 18.9, y: 18.8 }, '15': { x: 25.1, y: 17.5 },
 '14': { x: 30.3, y: 17.2 }, '13': { x: 35, y: 17.2 }, '12': { x: 40.5, y: 17.2 }, '11': { x: 45.6, y: 17 },
 '21': { x: 53.2, y: 16.7 }, '22': { x: 58.7, y: 16.5 }, '23': { x: 64.3, y: 15.9 }, '24': { x: 69.3, y: 16.7 },
 '25': { x: 74.7, y: 15.9 }, '26': { x: 80.6, y: 16.5 }, '27': { x: 88.8, y: 17 }, '28': { x: 95.2, y: 16.5 },
 '48': { x: 2.9, y: 80.2 }, '47': { x: 10.9, y: 79.9 }, '46': { x: 18.9, y: 80.4 }, '45': { x: 26.2, y: 80.7 },
 '44': { x: 31.3, y: 80.2 }, '43': { x: 36, y: 81 }, '42': { x: 41.5, y: 80.7 }, '41': { x: 47, y: 80.2 },
 '31': { x: 52.1, y: 79.9 }, '32': { x: 57.3, y: 79.7 }, '33': { x: 63.5, y: 81.5 }, '34': { x: 69.1, y: 81 },
 '35': { x: 74.9, y: 81.2 }, '36': { x: 82.5, y: 79.1 }, '37': { x: 90.6, y: 78.9 }, '38': { x: 97.2, y: 77.8 },
};

// Dimensiones del recorte por pieza (crops 44×175 sobre 710×359)
const PIEZA_W_PCT = (44 / 710) * 100; // ≈ 6.197%
const PIEZA_H_PCT = (175 / 359) * 100; // ≈ 48.746%
const LOWER_TOP_PCT = (184 / 359) * 100; // ≈ 51.253%

const PIEZAS_SUPERIORES = new Set([
 '18','17','16','15','14','13','12','11','21','22','23','24','25','26','27','28',
]);

function boxDePieza(pieza: string) {
 const coord = TOOTH_COORDS[pieza];
 if (!coord) return null;
 return {
 left: coord.x - PIEZA_W_PCT / 2,
 top: PIEZAS_SUPERIORES.has(pieza) ? 0 : LOWER_TOP_PCT,
 width: PIEZA_W_PCT,
 height: PIEZA_H_PCT,
 };
}


interface Props {
 modo: 'view' | 'edit';
 piezasMarcadas?: PiezaMarcada[];
 onPiezaClick?: (pieza: string) => void;
 piezaActiva?: string | null;
 className?: string;
 imgClassName?: string; // clases aplicadas a la <img> base (para controlar max-h/object-contain)
 edad?: number | null;  // si <13 → dentición infantil (sin molares 6/7/8, piezas más pequeñas)
}

// Erupción de los molares permanentes (sin predecesor de leche): posición → edad.
const ERUPCION_MOLAR: Record<string, number> = { '6': 6, '7': 12, '8': 18 };
// Edad de recambio leche→permanente por posición 1-5.
const EDAD_RECAMBIO: Record<string, number> = { '1': 6, '2': 8, '3': 11, '4': 11, '5': 12 };
const esMolar = (pieza: string) => ['6', '7', '8'].includes(pieza[1]);
// Numeración de leche (FDI 51-85) → posición de su homólogo permanente (51→11, 65→25, 85→45).
// Así un tratamiento registrado en un diente de leche cae en su sitio del odontograma.
const permDeLeche = (p: string): string => (/^[5-8][1-5]$/.test(p) ? `${+p[0] - 4}${p[1]}` : p);
// Factor de reducción de las piezas de leche (igual que en la generación de la imagen base).
const ESCALA_LECHE = 0.78;
// ¿la pieza es de LECHE a esa edad? (posición 1-5 antes de su recambio)
const esLecheEdad = (pieza: string, edad: number | null): boolean =>
 edad != null && edad < 13 && !!EDAD_RECAMBIO[pieza[1]] && edad < EDAD_RECAMBIO[pieza[1]];
// Plano oclusal (línea media donde muerden arriba/abajo) en el lienzo 726×386.
const PLANO_OCLUSAL = 193;
// Transform SVG para escalar un tratamiento al tamaño de la pieza de leche, anclando por la
// CORONA al plano oclusal (el diente de leche es más corto pero muerde en el mismo plano).
function transformLeche(pieza: string): string | undefined {
 const coord = TOOTH_COORDS[pieza];
 if (!coord) return undefined;
 const cx = (coord.x / 100) * 726;
 return `translate(${cx} ${PLANO_OCLUSAL}) scale(${ESCALA_LECHE}) translate(${-cx} ${-PLANO_OCLUSAL})`;
}

export default function OdontogramaOverlay({ modo, piezasMarcadas = [], onPiezaClick, piezaActiva, className = '', imgClassName = 'w-full h-auto block select-none', edad = null }: Props) {
 const [hover, setHover] = useState<string | null>(null);
 // Normalizamos: los dientes de leche (51-85) se traducen a la posición de su homólogo permanente.
 const marcadas = useMemo(() => piezasMarcadas.map(m => ({ ...m, pieza: permDeLeche(String(m.pieza)) })), [piezasMarcadas]);
 const marcadasMap = useMemo(() => new Map(marcadas.map(p => [String(p.pieza), p])), [marcadas]);
 const infantil = edad != null && edad < 13;

 // Centro de bracket ajustado: en diente de leche se escala 0.78 hacia el ancla (igual que la pieza),
 // para que los arcos de ortodoncia/retenedor caigan sobre la pieza reducida.
 const centroLeche = useCallback((pieza: string): { x: number; y: number } | null => {
 const c = bracketCenter(pieza);
 if (!c || !esLecheEdad(pieza, edad)) return c;
 const coord = TOOTH_COORDS[pieza];
 const cx = coord ? (coord.x / 100) * 726 : c.x;
 return { x: cx + (c.x - cx) * ESCALA_LECHE, y: PLANO_OCLUSAL + (c.y - PLANO_OCLUSAL) * ESCALA_LECHE };
 }, [edad]);

 return (
 <div className={`relative inline-block ${className}`}>
 {/* Capa 0: base por edad (dentición mixta) — ver baseOdontograma. */}
 <img src={baseOdontograma(edad)} alt="Odontograma" className={imgClassName} draggable={false} />

 {/* Capa 1a: variantes de tratamiento vía PNG (solo piezas con marcada.imagen) */}
 {marcadas.filter(m => m.imagen).map(marcada => {
 const p = String(marcada.pieza);
 const box = boxDePieza(p);
 if (!box) return null;
 let { left, top, width, height } = box;
 if (esLecheEdad(p, edad)) {          // diente de leche → corona anclada al plano oclusal
 const cx = left + width / 2;
 width *= ESCALA_LECHE; height *= ESCALA_LECHE;
 left = cx - width / 2;
 // superiores: corona abajo del recorte → anclar abajo. Inferiores: corona arriba → top sin cambio.
 if (PIEZAS_SUPERIORES.has(p)) top = box.top + box.height - height;
 }
 return (
 <img
 key={`var-${marcada.pieza}`}
 src={marcada.imagen}
 alt={`${marcada.pieza} ${marcada.tratamiento}`}
 draggable={false}
 className="absolute select-none pointer-events-none"
 style={{ left: `${left}%`, top: `${top}%`, width: `${width}%`, height: `${height}%` }}
 />
 );
 })}

 {/* Capa 1b: tratamientos vía SVG (escala automática por viewBox) */}
 <svg
 viewBox="0 0 726 386"
 preserveAspectRatio="xMidYMid meet"
 className="absolute inset-0 w-full h-full pointer-events-none"
 >
 {(() => {
 const RENDER_ORDER: Record<string, number> = { 'exodoncia': 0, 'ausencia': 0, 'ausente': 0, 'implante': 1, 'endodoncia': 2, 'caries': 3, 'obturacion': 3, 'perno': 2, 'reconstruccion-perno': 2, 'quistectomia': 2, 'ortodoncia': 3, 'limpieza': 3, 'raspado': 3, 'curetaje': 3, 'higiene': 3, 'protesis': 4, 'protesis removible': 4, 'protesis-removible': 4, 'corona': 5, 'corona-implante': 5 };
 const sorted = [...marcadas].filter(m => !m.imagen && m.tratamiento).sort((a, b) => (RENDER_ORDER[a.tratamiento] ?? 3) - (RENDER_ORDER[b.tratamiento] ?? 3));
 return sorted.map((m, i) => {
 const p = String(m.pieza);
 const svg = <TratamientoSVG key={`svg-${p}-${m.tratamiento}-${i}`} pieza={p} tratamiento={m.tratamiento} caras={m.caras} isPlanificado={m.isPlanificado} isInicial={m.isInicial} />;
 // Diente de leche → escalar el tratamiento al tamaño/posición de la pieza reducida.
 return esLecheEdad(p, edad) ? <g key={`gl-${p}-${i}`} transform={transformLeche(p)}>{svg}</g> : svg;
 });
 })()}
 {useMemo(() => {
 const bracketItems = marcadas.filter(m => {
 const t = (m.tratamiento || '').toLowerCase().trim();
 return t === 'ortodoncia' || t === 'bracket';
 });
 if (!bracketItems.length) return null;
 const brackets = new Set(bracketItems.map(m => String(m.pieza)));
 const esGris = bracketItems[0]?.isInicial;
 const color = esGris ? '#9aa0a6' : '#3c4043';
 const sup = ORDEN_ARCO_SUP.filter(p => brackets.has(p)).map(centroLeche).filter(Boolean) as { x: number; y: number }[];
 const inf = ORDEN_ARCO_INF.filter(p => brackets.has(p)).map(centroLeche).filter(Boolean) as { x: number; y: number }[];
 return (
 <g>
 {sup.length >= 2 && <path d={pathDesdePuntos(sup)} stroke={color} strokeWidth={1.3} fill="none" strokeLinecap="round" />}
 {inf.length >= 2 && <path d={pathDesdePuntos(inf)} stroke={color} strokeWidth={1.3} fill="none" strokeLinecap="round" />}
 </g>
 );
 }, [marcadas, centroLeche])}
 {/* Arcos de retenedor fijo */}
 {useMemo(() => {
 const retFijoItems = marcadas.filter(m => m.tratamiento === 'retenedor fijo');
 if (!retFijoItems.length) return null;
 const retFijo = new Set(retFijoItems.map(m => String(m.pieza)));
 const esGris = retFijoItems[0]?.isInicial;
 const color = esGris ? '#9aa0a6' : '#3c4043';
 const ANTERIOR_SUP = ['13','12','11','21','22','23'];
 const ANTERIOR_INF = ['43','42','41','31','32','33'];
 const supPts = ANTERIOR_SUP.filter(p => retFijo.has(p)).map(centroLeche).filter(Boolean) as { x: number; y: number }[];
 const infPts = ANTERIOR_INF.filter(p => retFijo.has(p)).map(centroLeche).filter(Boolean) as { x: number; y: number }[];
 return (
 <g>
 {supPts.length >= 2 && <path d={pathDesdePuntos(supPts)} stroke={color} strokeWidth={1.5} fill="none" strokeLinecap="round" />}
 {infPts.length >= 2 && <path d={pathDesdePuntos(infPts)} stroke={color} strokeWidth={1.5} fill="none" strokeLinecap="round" />}
 </g>
 );
 }, [marcadas, centroLeche])}
 {/* Arcos de ortodoncia invisible */}
 {useMemo(() => {
 const ortInvItems = marcadas.filter(m => m.tratamiento === 'ortodoncia invisible' || m.tratamiento === 'alineadores');
 if (!ortInvItems.length) return null;
 const ortInv = new Set(ortInvItems.map(m => String(m.pieza)));
 const esGris = ortInvItems[0]?.isInicial;
 const color = esGris ? '#9aa0a6' : '#1565C0';
 const sup = ORDEN_ARCO_SUP.filter(p => ortInv.has(p)).map(centroLeche).filter(Boolean) as { x: number; y: number }[];
 const inf = ORDEN_ARCO_INF.filter(p => ortInv.has(p)).map(centroLeche).filter(Boolean) as { x: number; y: number }[];
 return (
 <g>
 {sup.length >= 2 && <path d={pathDesdePuntos(sup)} stroke={color} strokeWidth={1.5} fill="none" strokeLinecap="round" />}
 {inf.length >= 2 && <path d={pathDesdePuntos(inf)} stroke={color} strokeWidth={1.5} fill="none" strokeLinecap="round" />}
 </g>
 );
 }, [marcadas, centroLeche])}
 </svg>

 {/* Capa 2: interactividad / estado */}
 <div className="absolute inset-0">
 {TODAS_LAS_PIEZAS.map(pieza => {
 const coord = TOOTH_COORDS[pieza];
 if (!coord) return null;
 if (infantil && esMolar(pieza) && (edad as number) < ERUPCION_MOLAR[pieza[1]]) return null;  // molar aún no erupcionado
 const marcada = marcadasMap.get(pieza);
 const activa = piezaActiva === pieza;
 const enHover = hover === pieza;
 // En diente de leche, el punto escala con la pieza anclada por la corona al plano oclusal (50%).
 const leche = esLecheEdad(pieza, edad);
 const cy = !leche ? coord.y : 50 + (coord.y - 50) * ESCALA_LECHE;

 if (modo === 'view') {
 if (!marcada) return null;
 return (
 <div
 key={pieza}
 className="absolute rounded-full pointer-events-auto cursor-help"
 style={{
 left: `${coord.x}%`,
 top: `${cy}%`,
 width: '18px',
 height: '18px',
 transform: 'translate(-50%, -50%)',
 background: enHover ? (marcada.color || '#3388FF') : 'transparent',
 border: enHover ? '2px solid white' : 'none',
 boxShadow: enHover ? '0 0 0 1px rgba(0,0,0,0.2)' : 'none',
 }}
 onMouseEnter={() => setHover(pieza)}
 onMouseLeave={() => setHover(null)}
 >
 {enHover && (
 <div
 className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 bg-[#1500A0] text-white text-[11px] rounded-sm shadow-lg px-2 py-1 whitespace-nowrap pointer-events-none z-50"
 >
 <div className="font-semibold">Pieza {pieza}</div>
 <div>{marcada.tratamiento}</div>
 {marcada.precio && <div className="text-[#2DD9C3] ">{marcada.precio}</div>}
 </div>
 )}
 </div>
 );
 }

 // modo edit: zonas clicables
 return (
 <button
 key={pieza}
 type="button"
 onClick={() => onPiezaClick?.(pieza)}
 onMouseEnter={() => setHover(pieza)}
 onMouseLeave={() => setHover(null)}
 className="absolute rounded-full cursor-pointer transition-all"
 style={{
 left: `${coord.x}%`,
 top: `${cy}%`,
 width: '22px',
 height: '22px',
 transform: 'translate(-50%, -50%)',
 background: activa ? '#2DD9C3' : marcada ? (marcada.color || '#3388FF') : enHover ? 'rgba(51,136,255,0.3)' : 'transparent',
 border: activa ? '2px solid #1500A0' : enHover ? '2px solid #3388FF' : marcada ? '2px solid white' : '2px dashed rgba(0,0,0,0.15)',
 boxShadow: marcada ? '0 0 0 1px rgba(0,0,0,0.2)' : 'none',
 }}
 title={`Pieza ${pieza}`}
 >
 <span className="text-[10px] font-semibold" style={{ color: activa || marcada ? 'white' : '#1500A0', opacity: enHover || activa || marcada ? 1 : 0 }}>{pieza}</span>
 </button>
 );
 })}
 </div>
 </div>
 );
}
