/**
 * TratamientoSVG — renderiza la representación visual de un tratamiento
 * sobre una pieza del odontograma, en el sistema de coordenadas de la
 * imagen base `/odontograma.png` (726×386 px).
 *
 * Se usa dentro de un <svg viewBox="0 0 726 386" preserveAspectRatio="xMidYMid meet">.
 */
import { pathDesdePuntos, CARIES_TILES } from './odontogramaUtils';
import { TOOTH_COORDS } from './OdontogramaOverlay';

interface Punto { x: number; y: number; }

// Canales de endodoncia calibrados manualmente por el usuario sobre odontograma.png (726×386).
// Cada canal es una secuencia de puntos: 2 puntos = recta, 3+ = curva suave (bezier cuadrática).
export const CANALES_ENDO: Record<string, Punto[][]> = {
 // Maxilar derecho
 '18': [
 [{x:25,y:150.5},{x:13,y:122.5},{x:13,y:103.5}],
 [{x:36,y:151.5},{x:46,y:118.5},{x:36,y:97.5}],
 [{x:33,y:132.5},{x:27,y:100.5}],
 ],
 '17': [
 [{x:81,y:150.5},{x:71,y:123.5},{x:70,y:103.5}],
 [{x:95,y:149.5},{x:103,y:118.5},{x:91,y:97.5}],
 [{x:88,y:132.5},{x:81,y:99.5}],
 ],
 '16': [
 [{x:136,y:150.5},{x:120,y:123.5},{x:122,y:99.5}],
 [{x:148,y:149.5},{x:158,y:117.5},{x:149,y:94.5}],
 [{x:143,y:135.5},{x:134,y:96.5}],
 ],
 '15': [[{x:186,y:148.5},{x:188,y:116.5},{x:181,y:89.5}]],
 '14': [[{x:221,y:151.5},{x:221,y:109.5},{x:217,y:90.5}]],
 '13': [[{x:260,y:142.5},{x:259,y:97.5},{x:253,y:76.5}]],
 '12': [[{x:297,y:143.5},{x:297,y:100.5},{x:294,y:85.5}]],
 '11': [[{x:339,y:140.5},{x:337,y:95.5},{x:333,y:78.5}]],
 // Maxilar izquierdo
 '21': [[{x:385,y:138.5},{x:383,y:93.5},{x:388,y:78.5}]],
 '22': [[{x:422,y:144.5},{x:422,y:104.5},{x:424,y:86.5}]],
 '23': [[{x:462,y:142.5},{x:463,y:96.5},{x:466,y:76.5}]],
 '24': [[{x:503,y:149.5},{x:501,y:113.5},{x:506,y:92.5}]],
 '25': [[{x:540,y:151.5},{x:535,y:122.5},{x:544,y:92.5}]],
 '26': [
 [{x:577,y:147.5},{x:570,y:116.5},{x:578,y:94.5}],
 [{x:587,y:136.5},{x:595,y:99.5}],
 [{x:590,y:149.5},{x:605,y:117.5},{x:606,y:98.5}],
 ],
 '27': [
 [{x:634,y:150.5},{x:631,y:122.5},{x:639,y:101.5}],
 [{x:643,y:133.5},{x:650,y:101.5}],
 [{x:649,y:148.5},{x:661,y:123.5},{x:662,y:101.5}],
 ],
 '28': [
 [{x:701,y:148.5},{x:711,y:122.5},{x:710,y:102.5}],
 [{x:695,y:130.5},{x:700,y:100.5}],
 [{x:682,y:147.5},{x:682,y:116.5},{x:689,y:97.5}],
 ],
 // Mandíbula izquierda
 '31': [[{x:378,y:248.5},{x:381,y:297.5}]],
 '32': [[{x:415,y:248.5},{x:415,y:298.5}]],
 '33': [[{x:451,y:250.5},{x:455,y:284.5},{x:462,y:307.5}]],
 '34': [[{x:494,y:241.5},{x:501,y:298.5}]],
 '35': [[{x:537,y:242.5},{x:534,y:279.5},{x:539,y:299.5}]],
 '36': [
 [{x:570,y:236.5},{x:570,y:265.5},{x:583,y:293.5}],
 [{x:587,y:236.5},{x:600,y:265.5},{x:605,y:294.5}],
 ],
 '37': [
 [{x:632,y:239.5},{x:631,y:261.5},{x:644,y:283.5}],
 [{x:646,y:237.5},{x:657,y:257.5},{x:660,y:283.5}],
 ],
 '38': [
 [{x:682,y:242.5},{x:681,y:267.5},{x:695,y:286.5}],
 [{x:699,y:240.5},{x:710,y:260.5},{x:712,y:285.5}],
 ],
 // Mandíbula derecha
 '41': [[{x:342,y:246.5},{x:342,y:279.5},{x:340,y:295.5}]],
 '42': [[{x:309,y:248.5},{x:308,y:278.5},{x:303,y:295.5}]],
 '43': [[{x:265,y:249.5},{x:262,y:293.5},{x:259,y:305.5}]],
 '44': [[{x:231,y:241.5},{x:232,y:273.5},{x:228,y:294.5}]],
 '45': [[{x:194,y:239.5},{x:196,y:281.5},{x:190,y:296.5}]],
 '46': [
 [{x:132,y:240.5},{x:127,y:268.5},{x:121,y:290.5}],
 [{x:156,y:241.5},{x:156,y:271.5},{x:144,y:296.5}],
 ],
 '47': [
 [{x:79,y:238.5},{x:71,y:266.5},{x:70,y:283.5}],
 [{x:100,y:240.5},{x:97,y:267.5},{x:87,y:286.5}],
 ],
 '48': [
 [{x:23,y:238.5},{x:14,y:267.5},{x:15,y:283.5}],
 [{x:46,y:240.5},{x:41,y:268.5},{x:32,y:285.5}],
 ],
};

// (CARIES_TILES se ha movido a src/utils/odontogramaUtils.ts)

// Arcada superior vs inferior (define cómo se etiquetan los puntos)
const SUPERIORES = new Set(['18','17','16','15','14','13','12','11','21','22','23','24','25','26','27','28']);

// Devuelve para cada cara del diente un polígono (Punto[]) sobre el tile oclusal.
// Oclusal = zona central (tile reducido al 45% hacia el centroide).
// Para molares (8pts): puntos impares (1,3,5,7 → índices 0,2,4,6) son las caras, pares son corners.
// Sup: 0=V, 2=M, 4=P, 6=D | Inf: 0=L, 2=D, 4=V, 6=M
// Para no-molares (4pts): los 4 puntos son las caras directamente.
// Sup: 0=V, 1=M, 2=P, 3=D | Inf: 0=L, 1=D, 2=V, 3=M
function carasDePieza(pieza: string): Record<string, Punto[]> | null {
 const tile = CARIES_TILES[pieza];
 if (!tile) return null;
 const n = tile.length;
 const cx = tile.reduce((s, p) => s + p.x, 0) / n;
 const cy = tile.reduce((s, p) => s + p.y, 0) / n;
 const centroid = { x: cx, y: cy };
 const sup = SUPERIORES.has(pieza);

 let labelIdx: Record<string, number>;
 if (n === 8) {
 labelIdx = sup
 ? { V: 0, M: 2, P: 4, D: 6 }
 : { L: 0, D: 2, V: 4, M: 6 };
 } else {
 labelIdx = sup
 ? { V: 0, M: 1, P: 2, D: 3 }
 : { L: 0, D: 1, V: 2, M: 3 };
 }

 const result: Record<string, Punto[]> = {};
 for (const [cara, i] of Object.entries(labelIdx)) {
 const curr = tile[i];
 let prevCorner: Punto;
 let nextCorner: Punto;
 if (n === 8) {
 // corners ya existen en el tile
 prevCorner = tile[(i - 1 + n) % n];
 nextCorner = tile[(i + 1) % n];
 } else {
 // corners = puntos medios entre caras vecinas
 const prev = tile[(i - 1 + n) % n];
 const next = tile[(i + 1) % n];
 prevCorner = { x: (prev.x + curr.x) / 2, y: (prev.y + curr.y) / 2 };
 nextCorner = { x: (curr.x + next.x) / 2, y: (curr.y + next.y) / 2 };
 }
 result[cara] = [centroid, prevCorner, curr, nextCorner];
 }

 // Oclusal: tile reducido al 45% hacia centroide
 const k = 0.45;
 result['O'] = tile.map(p => ({
 x: cx + (p.x - cx) * k,
 y: cy + (p.y - cy) * k,
 }));

 return result;
}

// Punto cervical calibrado por pieza (coords SVG 726×386).
const CUELLOS_PUNTOS: Record<string, Punto> = {
 '11': {x:336,y:140.5}, '12': {x:292,y:145.5}, '13': {x:255,y:144.5}, '14': {x:218,y:152.5},
 '15': {x:185,y:151.5}, '16': {x:138,y:152.5}, '17': {x:88,y:150.5}, '18': {x:30,y:149.5},
 '21': {x:380,y:140.5}, '22': {x:424,y:145.5}, '23': {x:460,y:144.5}, '24': {x:503,y:151.5},
 '25': {x:537,y:152.5}, '26': {x:588,y:149.5}, '27': {x:642,y:150.5}, '28': {x:692,y:148.5},
 '31': {x:378,y:245.5}, '32': {x:415,y:248.5}, '33': {x:454,y:251.5}, '34': {x:499,y:243.5},
 '35': {x:533,y:243.5}, '36': {x:581,y:238.5}, '37': {x:640,y:240.5}, '38': {x:690,y:241.5},
 '41': {x:339,y:248.5}, '42': {x:307,y:249.5}, '43': {x:262,y:251.5}, '44': {x:228,y:242.5},
 '45': {x:195,y:241.5}, '46': {x:142,y:242.5}, '47': {x:90,y:242.5}, '48': {x:33,y:240.5},
};

const CARIES_COLOR = '#7C3AED'; // Violeta Fluor Intenso para la caries
const OBTURACION_COLOR = '#FF6FD8'; // Rosa claro fluor (obturaciones / reconstrucciones)

// Puntos calibrados de obturación en corona (3 por pieza: lateral izq, centro, lateral der).
// Coords SVG 726×386.
const OBTURACION_PUNTOS: Record<string, Punto[]> = {
 '18':[{x:8,y:165},{x:32,y:165},{x:55,y:166}], '17':[{x:65,y:166},{x:89,y:164},{x:112,y:167}],
 '16':[{x:119,y:168},{x:141,y:166},{x:166,y:170}], '15':[{x:175,y:172},{x:188,y:172},{x:202,y:173}],
 '14':[{x:209,y:174},{x:221,y:173},{x:239,y:174}], '13':[{x:243,y:173},{x:257,y:171},{x:274,y:172}],
 '12':[{x:283,y:172},{x:296,y:172},{x:309,y:172}], '11':[{x:318,y:175},{x:338,y:173},{x:357,y:175}],
 '21':[{x:363,y:176},{x:386,y:175},{x:402,y:174}], '22':[{x:409,y:175},{x:423,y:174},{x:436,y:174}],
 '23':[{x:446,y:174},{x:462,y:170},{x:477,y:171}], '24':[{x:485,y:173},{x:504,y:173},{x:516,y:175}],
 '25':[{x:523,y:174},{x:539,y:175},{x:552,y:174}], '26':[{x:560,y:172},{x:589,y:171},{x:607,y:170}],
 '27':[{x:619,y:170},{x:641,y:169},{x:662,y:168}], '28':[{x:670,y:169},{x:695,y:169},{x:715,y:168}],
 '48':[{x:12,y:218},{x:34,y:224},{x:59,y:225}], '47':[{x:68,y:224},{x:89,y:226},{x:111,y:228}],
 '46':[{x:120,y:226},{x:144,y:227},{x:170,y:225}], '45':[{x:181,y:225},{x:197,y:226},{x:211,y:223}],
 '44':[{x:216,y:223},{x:230,y:224},{x:249,y:223}], '43':[{x:252,y:223},{x:270,y:223},{x:282,y:220}],
 '42':[{x:292,y:222},{x:306,y:224},{x:320,y:220}], '41':[{x:329,y:220},{x:343,y:222},{x:353,y:219}],
 '31':[{x:366,y:219},{x:377,y:222},{x:389,y:219}], '32':[{x:400,y:220},{x:414,y:222},{x:426,y:220}],
 '33':[{x:436,y:219},{x:455,y:221},{x:468,y:220}], '34':[{x:480,y:220},{x:496,y:222},{x:509,y:219}],
 '35':[{x:518,y:219},{x:535,y:221},{x:551,y:218}], '36':[{x:557,y:219},{x:584,y:222},{x:605,y:217}],
 '37':[{x:615,y:219},{x:643,y:222},{x:662,y:216}], '38':[{x:668,y:220},{x:692,y:223},{x:711,y:215}],
};

function renderCarasColor(pieza: string, caras: string | undefined, color: string, keyPrefix: string, isFluor?: boolean) {
 const zonas = carasDePieza(pieza);
 if (!zonas) return null;
 const seleccion = (caras || 'O').toUpperCase().split('').filter(c => zonas[c] || c === 'C');
 if (!seleccion.length) return null;
 const pts = (arr: Punto[]) => arr.map(p => `${p.x},${p.y}`).join(' ');
 const cuello = seleccion.includes('C') ? CUELLOS_PUNTOS[pieza] : null;

 // Efecto flúor brillante (brillo interno y externo intenso)
 const filterStyle = isFluor ? { filter: `drop-shadow(0px 0px 4px ${color}) drop-shadow(0px 0px 2px #fff)` } : undefined;

 return (
 <g key={`${keyPrefix}-${pieza}`}>
 {seleccion.filter(c => c !== 'C').map(c => (
 <polygon key={c} points={pts(zonas[c])} fill={color} fillOpacity={isFluor ? 0.95 : 0.75} style={filterStyle} />
 ))}
 {cuello && (
 <ellipse key="C" cx={cuello.x} cy={cuello.y} rx={9} ry={3.5} fill={color} fillOpacity={isFluor ? 0.95 : 0.85} style={filterStyle} />
 )}
 </g>
 );
}

function renderCaries(pieza: string, caras?: string, isPlanificado?: boolean, isInicial?: boolean) {
 const colorFinal = isPlanificado ? '#C026D3' : (isInicial ? '#9aa0a6' : CARIES_COLOR);
 return renderCarasColor(pieza, caras, colorFinal, 'car', !isPlanificado);
}

function renderObturacion(pieza: string, caras?: string, isPlanificado?: boolean, isInicial?: boolean) {
 const pts = OBTURACION_PUNTOS[pieza];
 const colorFinal = isPlanificado ? '#C026D3' : (isInicial ? '#9aa0a6' : OBTURACION_COLOR);
 const carasNode = renderCarasColor(pieza, caras, colorFinal, 'obt');
 if (!pts) return carasNode;
 // Sin caras (p.ej. una "reconstrucción", que rehace la corona) → marca por defecto en la corona,
 // para que el tratamiento se vea igualmente (si no, no se pintaría nada).
 if (!caras) return (
 <g key={`obt-g-${pieza}`}>
 <ellipse cx={pts[1].x} cy={pts[1].y} rx={6} ry={7} fill={colorFinal} fillOpacity={0.8} stroke={isPlanificado ? 'none' : '#1ca0d1'} strokeWidth={isPlanificado ? 0 : 1.2} />
 {carasNode}
 </g>
 );
 const sel = caras.toUpperCase();
 const q = pieza[0];
 // Mesial hacia la línea media: cuadrantes 1 y 4 → mesial = punto 2 (der), distal = 0 (izq).
 // Cuadrantes 2 y 3 → mesial = 0 (izq), distal = 2 (der).
 const mesialDerecho = q === '1' || q === '4';
 const mesialIdx = mesialDerecho ? 2 : 0;
 const distalIdx = mesialDerecho ? 0 : 2;
 const centros: Punto[] = [];
 if (sel.includes('M')) centros.push(pts[mesialIdx]);
 if (sel.includes('D')) centros.push(pts[distalIdx]);
 if (sel.includes('V') || sel.includes('O')) centros.push(pts[1]);
 return (
 <g key={`obt-g-${pieza}`}>
 {centros.map((p) => (
 <ellipse key={`${p.x}-${p.y}`} cx={p.x} cy={p.y} rx={5.5} ry={6.5} fill={colorFinal} fillOpacity={0.8} stroke={isPlanificado ? 'none' : '#1ca0d1'} strokeWidth={isPlanificado ? 0 : 1.2} />
 ))}
 {carasNode}
 </g>
 );
}

function renderQuistectomia(pieza: string, isInicial?: boolean) {
 const canales = CANALES_ENDO[pieza];
 if (!canales?.length) return null;
 const apice = canales[0][canales[0].length - 1];
 const color = isInicial ? '#9aa0a6' : '#C026D3';
 const stroke = isInicial ? '#7f8c8d' : '#A21CAF';
 return (
 <g key={`quiste-${pieza}`}>
 <circle cx={apice.x} cy={apice.y} r={7} fill={color} fillOpacity={0.7} stroke={stroke} strokeWidth={1.2} />
 </g>
 );
}

function renderEndodoncia(pieza: string, isPlanificado?: boolean, isInicial?: boolean, conPerno?: boolean) {
 const canales = CANALES_ENDO[pieza];
 if (!canales?.length) return null;
 const colorFinal = isPlanificado ? '#C026D3' : (isInicial ? '#9aa0a6' : '#424242');
 const inicio = canales[0][0];
 const fin = canales[0][canales[0].length - 1];
 const dy = inicio.y - fin.y;
 const pernoX = inicio.x;
 const pernoY = inicio.y + (dy > 0 ? 12 : -12);
 return (
 <g key={`endo-${pieza}`}>
 {canales.map((puntos, i) => (
 <path
 key={`canal-${i}`}
 d={pathDesdePuntos(puntos)}
 stroke={colorFinal}
 strokeWidth={2.5}
 strokeLinecap="round"
 strokeLinejoin="round"
 fill="none"
 />
 ))}
 {conPerno && (
 <circle cx={pernoX} cy={pernoY} r={6} fill="#7C3AED" stroke="#1ca0d1" strokeWidth={1.2} />
 )}
 </g>
 );
}

interface Props {
 pieza: string;
 tratamiento: string;
 caras?: string; // p.ej. "OM" para caries oclusal+mesial
 isPlanificado?: boolean;
}

const IMPLANTE_COLOR = '#1DE9B6';

export const IMPLANTE_CALIBRADO: Record<string, { x: number; y: number; angle: number }> = {
 '11': { x: 336, y: 140.5, angle: -90 },
 '12': { x: 296, y: 146, angle: -90 },
 '13': { x: 256, y: 147, angle: -90.66 },
 '14': { x: 220, y: 152, angle: -91.32 },
 '15': { x: 185, y: 151.5, angle: -90 },
 '16': { x: 140, y: 152, angle: -90 },
 '17': { x: 88, y: 150.5, angle: -90 },
 '18': { x: 30, y: 149.5, angle: -91.05 },
 '21': { x: 385, y: 142, angle: -90 },
 '22': { x: 422, y: 146, angle: -90 },
 '23': { x: 460, y: 147, angle: -89.34 },
 '24': { x: 502, y: 153, angle: -88.68 },
 '25': { x: 539, y: 153, angle: -90 },
 '26': { x: 586, y: 152, angle: -90 },
 '27': { x: 638, y: 150.5, angle: -90 },
 '28': { x: 696, y: 149.5, angle: -88.95 },
 '41': { x: 340, y: 247, angle: 90 },
 '42': { x: 307, y: 249.5, angle: 88.71 },
 '43': { x: 267, y: 251, angle: 90.6 },
 '44': { x: 231, y: 245, angle: 90.65 },
 '45': { x: 195, y: 241.5, angle: 90 },
 '46': { x: 144, y: 241, angle: 90 },
 '47': { x: 90, y: 241, angle: 88.59 },
 '48': { x: 33, y: 240, angle: 87.1 },
 '31': { x: 379, y: 247, angle: 90 },
 '32': { x: 413, y: 247, angle: 91.29 },
 '33': { x: 453, y: 250, angle: 89.4 },
 '34': { x: 498, y: 242, angle: 89.35 },
 '35': { x: 536, y: 243, angle: 90 },
 '36': { x: 584, y: 241, angle: 90 },
 '37': { x: 642, y: 237, angle: 88.67 },
 '38': { x: 690, y: 241, angle: 90 },
};

// Líneas interdentales calibradas (SVG 726×386). 17 por arcada (0=borde izq, 16=borde der).
interface LineaInter { top: Punto; bottom: Punto; }
const LINEAS_SUP: LineaInter[] = [
 {top:{x:0,y:89},bottom:{x:2,y:191}}, {top:{x:56,y:91},bottom:{x:61,y:191}}, {top:{x:112,y:83},bottom:{x:114,y:192}},
 {top:{x:167,y:80},bottom:{x:171,y:193}}, {top:{x:205,y:76},bottom:{x:205,y:194}}, {top:{x:240,y:71},bottom:{x:239,y:196}},
 {top:{x:276,y:72},bottom:{x:279,y:194}}, {top:{x:311,y:73},bottom:{x:313,y:200}}, {top:{x:360,y:71},bottom:{x:359,y:197}},
 {top:{x:406,y:70},bottom:{x:406,y:194}}, {top:{x:443,y:69},bottom:{x:441,y:197}}, {top:{x:481,y:68},bottom:{x:481,y:194}},
 {top:{x:520,y:68},bottom:{x:518,y:193}}, {top:{x:554,y:70},bottom:{x:556,y:190}}, {top:{x:611,y:77},bottom:{x:617,y:186}},
 {top:{x:667,y:77},bottom:{x:665,y:191}}, {top:{x:719,y:74},bottom:{x:722,y:190}},
];
const LINEAS_INF: LineaInter[] = [
 {top:{x:0,y:201},bottom:{x:1,y:289}}, {top:{x:63,y:197},bottom:{x:60,y:285}}, {top:{x:117,y:201},bottom:{x:107,y:300}},
 {top:{x:175,y:200},bottom:{x:168,y:306}},{top:{x:213,y:198},bottom:{x:213,y:301}}, {top:{x:249,y:201},bottom:{x:246,y:312}},
 {top:{x:286,y:203},bottom:{x:287,y:317}},{top:{x:324,y:203},bottom:{x:323,y:312}}, {top:{x:359,y:205},bottom:{x:360,y:311}},
 {top:{x:396,y:205},bottom:{x:396,y:310}},{top:{x:432,y:203},bottom:{x:433,y:315}}, {top:{x:473,y:203},bottom:{x:480,y:314}},
 {top:{x:514,y:203},bottom:{x:518,y:312}},{top:{x:552,y:198},bottom:{x:559,y:305}}, {top:{x:609,y:201},bottom:{x:618,y:299}},
 {top:{x:663,y:198},bottom:{x:673,y:297}},{top:{x:718,y:198},bottom:{x:722,y:297}},
];

// Cada pieza = cuadrilátero entre dos líneas consecutivas.
// Orden: sup → 18,17,16,15,14,13,12,11,21,22,23,24,25,26,27,28 (índices 0..15 → líneas L,L+1)
// Orden: inf → 48,47,46,45,44,43,42,41,31,32,33,34,35,36,37,38
const ORDEN_SUP = ['18','17','16','15','14','13','12','11','21','22','23','24','25','26','27','28'] as const;
const ORDEN_INF = ['48','47','46','45','44','43','42','41','31','32','33','34','35','36','37','38'] as const;

// Líneas interdentales OCLUSALES (fila superior arriba, fila inferior abajo).
const LINEAS_SUP_OCL: LineaInter[] = [
 {top:{x:4,y:10},bottom:{x:5,y:49}}, {top:{x:57,y:11},bottom:{x:57,y:49}}, {top:{x:107,y:16},bottom:{x:110,y:57}},
 {top:{x:163,y:7},bottom:{x:164,y:58}}, {top:{x:202,y:4},bottom:{x:202,y:56}}, {top:{x:243,y:7},bottom:{x:240,y:69}},
 {top:{x:278,y:3},bottom:{x:279,y:54}}, {top:{x:314,y:4},bottom:{x:316,y:56}}, {top:{x:363,y:1},bottom:{x:366,y:63}},
 {top:{x:404,y:8},bottom:{x:408,y:56}}, {top:{x:442,y:2},bottom:{x:447,y:56}}, {top:{x:486,y:4},bottom:{x:478,y:70}},
 {top:{x:514,y:4},bottom:{x:516,y:53}}, {top:{x:552,y:6},bottom:{x:558,y:60}}, {top:{x:610,y:16},bottom:{x:618,y:62}},
 {top:{x:663,y:2},bottom:{x:665,y:55}}, {top:{x:719,y:6},bottom:{x:718,y:54}},
];
const LINEAS_INF_OCL: LineaInter[] = [
 {top:{x:2,y:313},bottom:{x:2,y:369}}, {top:{x:52,y:322},bottom:{x:53,y:371}}, {top:{x:110,y:317},bottom:{x:106,y:369}},
 {top:{x:166,y:320},bottom:{x:165,y:367}},{top:{x:207,y:313},bottom:{x:204,y:371}}, {top:{x:239,y:314},bottom:{x:248,y:373}},
 {top:{x:286,y:315},bottom:{x:287,y:375}},{top:{x:320,y:314},bottom:{x:317,y:373}}, {top:{x:364,y:322},bottom:{x:369,y:384}},
 {top:{x:406,y:317},bottom:{x:407,y:371}},{top:{x:440,y:319},bottom:{x:444,y:376}}, {top:{x:478,y:311},bottom:{x:482,y:374}},
 {top:{x:517,y:311},bottom:{x:520,y:368}},{top:{x:555,y:311},bottom:{x:563,y:377}}, {top:{x:613,y:312},bottom:{x:623,y:370}},
 {top:{x:670,y:311},bottom:{x:672,y:369}},{top:{x:720,y:313},bottom:{x:722,y:372}},
];

export const OCLUSALES_POLIGONOS: Record<string, Punto[]> = {
 '18':[{x:35,y:50},{x:17,y:49},{x:9,y:35},{x:12,y:18},{x:24,y:13},{x:42,y:13},{x:56,y:19},{x:54,y:31},{x:51,y:46}],
 '17':[{x:60,y:24},{x:71,y:16},{x:95,y:17},{x:106,y:29},{x:105,y:43},{x:94,y:54},{x:66,y:52},{x:59,y:45}],
 '16':[{x:119,y:15},{x:153,y:16},{x:162,y:28},{x:162,y:41},{x:156,y:52},{x:123,y:53},{x:114,y:41},{x:112,y:26}],
 '15':[{x:174,y:25},{x:175,y:41},{x:186,y:55},{x:195,y:55},{x:202,y:43},{x:202,y:21},{x:195,y:15},{x:180,y:14}],
 '14':[{x:211,y:14},{x:227,y:15},{x:233,y:23},{x:233,y:39},{x:227,y:52},{x:212,y:52},{x:206,y:40},{x:203,y:25}],
 '13':[{x:252,y:28},{x:264,y:10},{x:268,y:10},{x:278,y:31},{x:269,y:53},{x:263,y:52},{x:252,y:31}],
 '12':[{x:285,y:21},{x:297,y:14},{x:306,y:22},{x:306,y:37},{x:301,y:49},{x:289,y:49},{x:285,y:32}],
 '11':[{x:317,y:22},{x:329,y:13},{x:337,y:24},{x:336,y:36},{x:335,y:48},{x:321,y:49}],
 '21':[{x:398,y:49},{x:384,y:48},{x:383,y:36},{x:382,y:24},{x:390,y:13},{x:402,y:22}],
 '22':[{x:435,y:31},{x:431,y:48},{x:419,y:48},{x:414,y:36},{x:414,y:21},{x:423,y:13},{x:435,y:20}],
 '23':[{x:469,y:31},{x:458,y:52},{x:452,y:53},{x:443,y:31},{x:453,y:10},{x:457,y:10},{x:469,y:28}],
 '24':[{x:519,y:24},{x:516,y:39},{x:510,y:51},{x:495,y:51},{x:489,y:38},{x:489,y:22},{x:495,y:14},{x:511,y:13}],
 '25':[{x:544,y:12},{x:528,y:13},{x:521,y:19},{x:521,y:41},{x:528,y:53},{x:538,y:53},{x:548,y:39},{x:550,y:23}],
 '26':[{x:609,y:27},{x:607,y:42},{x:599,y:54},{x:565,y:53},{x:559,y:42},{x:559,y:29},{x:569,y:17},{x:602,y:16}],
 '27':[{x:662,y:43},{x:655,y:50},{x:627,y:52},{x:616,y:41},{x:615,y:27},{x:626,y:15},{x:650,y:14},{x:661,y:22}],
 '28':[{x:714,y:36},{x:705,y:46},{x:693,y:48},{x:682,y:48},{x:674,y:45},{x:669,y:36},{x:668,y:23},{x:674,y:16},{x:680,y:10},{x:697,y:10},{x:708,y:11},{x:716,y:21},{x:715,y:29}],
 '48':[{x:1,y:346},{x:0,y:338},{x:8,y:328},{x:19,y:327},{x:36,y:327},{x:42,y:333},{x:48,y:340},{x:47,y:353},{x:42,y:362},{x:34,y:365},{x:23,y:365},{x:11,y:363},{x:2,y:353}],
 '47':[{x:56,y:330},{x:67,y:322},{x:91,y:323},{x:102,y:335},{x:101,y:349},{x:90,y:360},{x:62,y:358},{x:55,y:351}],
 '46':[{x:118,y:322},{x:152,y:323},{x:161,y:335},{x:161,y:348},{x:155,y:359},{x:122,y:360},{x:113,y:348},{x:111,y:333}],
 '45':[{x:174,y:334},{x:175,y:350},{x:186,y:364},{x:195,y:364},{x:202,y:352},{x:202,y:330},{x:195,y:324},{x:180,y:323}],
 '44':[{x:214,y:325},{x:230,y:326},{x:236,y:334},{x:236,y:350},{x:230,y:363},{x:215,y:363},{x:209,y:351},{x:206,y:336}],
 '43':[{x:256,y:341},{x:268,y:323},{x:272,y:323},{x:282,y:344},{x:273,y:366},{x:267,y:365},{x:256,y:344}],
 '42':[{x:292,y:334},{x:304,y:327},{x:313,y:335},{x:313,y:350},{x:308,y:362},{x:296,y:362},{x:292,y:345}],
 '41':[{x:323,y:342},{x:326,y:330},{x:343,y:328},{x:346,y:341},{x:348,y:353},{x:335,y:363},{x:324,y:354}],
 '31':[{x:380,y:335},{x:385,y:327},{x:397,y:328},{x:401,y:330},{x:403,y:336},{x:404,y:344},{x:405,y:351},{x:399,y:356},{x:392,y:361},{x:386,y:357},{x:381,y:351},{x:381,y:344}],
 '32':[{x:434,y:344},{x:430,y:361},{x:418,y:361},{x:413,y:349},{x:413,y:334},{x:422,y:326},{x:434,y:333}],
 '33':[{x:468,y:345},{x:457,y:366},{x:451,y:367},{x:442,y:345},{x:452,y:324},{x:456,y:324},{x:468,y:342}],
 '34':[{x:519,y:336},{x:516,y:351},{x:510,y:363},{x:495,y:363},{x:489,y:350},{x:489,y:334},{x:495,y:326},{x:511,y:325}],
 '35':[{x:546,y:324},{x:530,y:325},{x:523,y:331},{x:523,y:353},{x:530,y:365},{x:540,y:365},{x:550,y:351},{x:552,y:335}],
 '36':[{x:613,y:334},{x:611,y:349},{x:603,y:361},{x:569,y:360},{x:563,y:349},{x:563,y:336},{x:573,y:324},{x:606,y:323}],
 '37':[{x:666,y:351},{x:659,y:358},{x:631,y:360},{x:620,y:349},{x:619,y:335},{x:630,y:323},{x:654,y:322},{x:665,y:330}],
 '38':[{x:719,y:352},{x:710,y:362},{x:698,y:364},{x:687,y:364},{x:679,y:361},{x:674,y:352},{x:673,y:339},{x:679,y:332},{x:685,y:326},{x:702,y:326},{x:713,y:327},{x:721,y:337},{x:720,y:345}],
};

function quadOclusalDePieza(pieza: string): Punto[] | null {
 if (OCLUSALES_POLIGONOS[pieza]) return OCLUSALES_POLIGONOS[pieza];
 let arr: LineaInter[], idx: number;
 const sup = ORDEN_SUP.indexOf(pieza as any);
 if (sup >= 0) { arr = LINEAS_SUP_OCL; idx = sup; }
 else {
 const inf = ORDEN_INF.indexOf(pieza as any);
 if (inf < 0) return null;
 arr = LINEAS_INF_OCL; idx = inf;
 }
 const L = arr[idx], R = arr[idx + 1];
 if (!L || !R) return null;
 return [L.top, R.top, R.bottom, L.bottom];
}

const BORRADOS_MANUALES: Record<string, Punto[]> = {
 '32': [{x:397,y:201},{x:430,y:202},{x:441,y:369},{x:411,y:366}]
};

function quadDePieza(pieza: string): Punto[] | null {
 if (BORRADOS_MANUALES[pieza]) return BORRADOS_MANUALES[pieza];
 let arr: LineaInter[], idx: number;
 const sup = ORDEN_SUP.indexOf(pieza as any);
 if (sup >= 0) { arr = LINEAS_SUP; idx = sup; }
 else {
 const inf = ORDEN_INF.indexOf(pieza as any);
 if (inf < 0) return null;
 arr = LINEAS_INF; idx = inf;
 }
 const L = arr[idx], R = arr[idx + 1];
 if (!L || !R) return null;
 return [L.top, R.top, R.bottom, L.bottom];
}

// Implante: usa calibrado manual de posición y ángulo.
function renderImplante(pieza: string, isPlanificado?: boolean, isInicial?: boolean) {
 const cal = IMPLANTE_CALIBRADO[pieza];
 const cuello = cal || CUELLOS_PUNTOS[pieza];
 if (!cuello) return null;
 const length = 40;
 const width = 10;
 const angle = cal ? cal.angle : (() => {
 const hoverPct = TOOTH_COORDS[pieza];
 if (!hoverPct) return -90;
 const hover = { x: hoverPct.x * 7.26, y: hoverPct.y * 3.86 };
 return (Math.atan2(hover.y - cuello.y, hover.x - cuello.x) * 180) / Math.PI;
 })();
 const threads = [];
 const numThreads = 7;
 const colorFinal = isPlanificado ? '#C026D3' : (isInicial ? '#9aa0a6' : IMPLANTE_COLOR);
 const strokeColorFinal = isPlanificado ? '#7A0F8E' : (isInicial ? '#7f8c8d' : '#1500A0');
 for (let i = 1; i < numThreads; i++) {
 const tx = (i / numThreads) * length;
 threads.push(
 <line key={`thread-${i}`} x1={tx} y1={-width / 2} x2={tx} y2={width / 2} stroke={strokeColorFinal} strokeWidth={0.7} />
 );
 }
 const quad = quadDePieza(pieza);
 return (
 <g key={`imp-${pieza}`}>
 {quad && (
 <polygon points={quad.map(p => `${p.x},${p.y}`).join(' ')} fill="white" />
 )}
 <g transform={`translate(${cuello.x},${cuello.y}) rotate(${angle})`}>
 <rect x={0} y={-width / 2} width={length} height={width} fill={colorFinal} fillOpacity={0.7} stroke={strokeColorFinal} strokeWidth={1} rx={2} />
 {threads}
 <polygon points={`${length},${-width / 2} ${length + 5},0 ${length},${width / 2}`} fill={colorFinal} fillOpacity={0.7} stroke={strokeColorFinal} strokeWidth={1} />
 </g>
 </g>
 );
}

const CORONA_COLOR = '#E9C22E';
const PROTESIS_COLOR = '#F8BBD0';

function lerpY(a: Punto, b: Punto, y: number): Punto {
 if (Math.abs(b.y - a.y) < 0.01) return { x: (a.x + b.x) / 2, y };
 const t = (y - a.y) / (b.y - a.y);
 return { x: a.x + t * (b.x - a.x), y };
}

// Corona sobre implante: borra solo el lado raíz y dibuja implante; el lado corona
// se deja visible (imagen base) y se tiñe con overlay lima.
function renderCoronaImplante(pieza: string, isPlanificado?: boolean, isInicial?: boolean) {
 const cal = IMPLANTE_CALIBRADO[pieza];
 const cuello = cal || CUELLOS_PUNTOS[pieza];
 const quad = quadDePieza(pieza);
 if (!cuello || !quad) return null;
 const length = 40;
 const width = 10;
 const angle = cal ? cal.angle : (() => {
 const hoverPct = TOOTH_COORDS[pieza];
 if (!hoverPct) return -90;
 const hover = { x: hoverPct.x * 7.26, y: hoverPct.y * 3.86 };
 return (Math.atan2(hover.y - cuello.y, hover.x - cuello.x) * 180) / Math.PI;
 })();
 const threads = [];
 
 const impColor = isPlanificado ? '#C026D3' : (isInicial ? '#9aa0a6' : IMPLANTE_COLOR);
 const impStroke = isPlanificado ? '#7A0F8E' : (isInicial ? '#7f8c8d' : '#1500A0');
 const corColor = isPlanificado ? '#C026D3' : (isInicial ? '#9aa0a6' : CORONA_COLOR);

 for (let i = 1; i < 7; i++) {
 const tx = (i / 7) * length;
 threads.push(<line key={`impl-${i}`} x1={tx} y1={-width / 2} x2={tx} y2={width / 2} stroke={impStroke} strokeWidth={0.7} />);
 }
 const [Lt, Rt, Rb, Lb] = quad;
 const sup = SUPERIORES.has(pieza);
 const crown = CORONAS_POLIGONOS[pieza];
 const outer = sup
 ? [{ x: Lt.x, y: 0 }, { x: Rt.x, y: 0 }, Rb, Lb]
 : [Lt, Rt, { x: Rb.x, y: 386 }, { x: Lb.x, y: 386 }];
 const outerPath = `M ${outer.map(p => `${p.x},${p.y}`).join(' L ')} Z`;
 const innerPath = crown ? `M ${crown.map(p => `${p.x},${p.y}`).join(' L ')} Z` : '';
 return (
 <g key={`ci-${pieza}`}>
 <path d={`${outerPath} ${innerPath}`} fill="white" fillRule="evenodd" />
 {crown && (
 <polygon points={crown.map(p => `${p.x},${p.y}`).join(' ')} fill={corColor} fillOpacity={0.4} />
 )}
 <g transform={`translate(${cuello.x},${cuello.y}) rotate(${angle})`}>
 <rect x={0} y={-width / 2} width={length} height={width} fill={impColor} fillOpacity={0.7} stroke={impStroke} strokeWidth={1} rx={2} />
 {threads}
 <polygon points={`${length},${-width / 2} ${length + 5},0 ${length},${width / 2}`} fill={impColor} fillOpacity={0.7} stroke={impStroke} strokeWidth={1} />
 </g>
 </g>
 );
}

// Limpieza/tartrectomía: línea azul claro por el borde gingival.
function renderLimpieza(pieza: string, isInicial?: boolean) {
 const cuello = CUELLOS_PUNTOS[pieza];
 if (!cuello) return null;
 const sup = SUPERIORES.has(pieza);
 const yOff = sup ? -2 : 2;
 const color = isInicial ? '#9aa0a6' : '#00BCD4';
 return (
 <g key={`limp-${pieza}`}>
 <line x1={cuello.x - 12} y1={cuello.y + yOff} x2={cuello.x + 12} y2={cuello.y + yOff}
 stroke={color} strokeWidth={3} strokeLinecap="round" strokeOpacity={0.8} />
 </g>
 );
}

// Raspado/Curetaje: igual que limpieza pero en rojo, desplazado al lado.
function renderRaspado(pieza: string, isInicial?: boolean) {
 const cuello = CUELLOS_PUNTOS[pieza];
 if (!cuello) return null;
 const sup = SUPERIORES.has(pieza);
 const yOff = sup ? -6 : 6;
 const color = isInicial ? '#9aa0a6' : '#E01B84';
 return (
 <g key={`rasp-${pieza}`}>
 <line x1={cuello.x - 12} y1={cuello.y + yOff} x2={cuello.x + 12} y2={cuello.y + yOff}
 stroke={color} strokeWidth={3} strokeLinecap="round" strokeOpacity={0.8} />
 </g>
 );
}

// Centro del bracket de una pieza (para archwire).
export function bracketCenter(pieza: string): Punto | null {
 const cuello = CUELLOS_PUNTOS[pieza];
 const quad = quadDePieza(pieza);
 if (!cuello || !quad) return null;
 const [Lt, Rt, Rb, Lb] = quad;
 const sup = SUPERIORES.has(pieza);
 const leftMid = lerpY(Lt, Lb, cuello.y);
 const rightMid = lerpY(Rt, Rb, cuello.y);
 const crownPts = sup ? [leftMid, rightMid, Rb, Lb] : [Lt, Rt, rightMid, leftMid];
 const cx = crownPts.reduce((s, p) => s + p.x, 0) / 4;
 const cy = crownPts.reduce((s, p) => s + p.y, 0) / 4;
 return { x: cx, y: cy };
}

export const ORDEN_ARCO_SUP = ORDEN_SUP;
export const ORDEN_ARCO_INF = ORDEN_INF;

// Retenedor removible: velo azul claro sobre corona + oclusal.
function renderRetenedorRemovible(pieza: string, isInicial?: boolean) {
 const crown = CORONAS_POLIGONOS[pieza];
 if (!crown) return null;
 const quadOcl = quadOclusalDePieza(pieza);
 const color = isInicial ? '#9aa0a6' : '#81D4FA';
 const clipId = `clip-ret-${pieza}`;
 return (
 <g key={`ret-${pieza}`}>
 <defs>
 <clipPath id={clipId}>
 <polygon points={crown.map(p => `${p.x},${p.y}`).join(' ')} />
 </clipPath>
 </defs>
 <image href="/odontograma.png" width={726} height={386} clipPath={`url(#${clipId})`} />
 <polygon points={crown.map(p => `${p.x},${p.y}`).join(' ')} fill={color} fillOpacity={0.4} />
 {quadOcl && <polygon points={quadOcl.map(p => `${p.x},${p.y}`).join(' ')} fill={color} fillOpacity={0.3} />}
 </g>
 );
}

// Retenedor fijo: línea gris oscuro de 13 a 23 (sup) o 43 a 33 (inf), sin bracket.
function renderRetenedorFijo(pieza: string, isInicial?: boolean) {
 // Solo renderiza el punto de conexión — el arco se dibuja en OdontogramaOverlay
 return null;
}

// Ortodoncia invisible: velo azul más oscuro sobre corona + oclusal + puntos en 5s, 6s, 7s.
function renderOrtodonciaInvisible(pieza: string, isInicial?: boolean) {
 const crown = CORONAS_POLIGONOS[pieza];
 if (!crown) return null;
 const quadOcl = quadOclusalDePieza(pieza);
 const color = isInicial ? '#9aa0a6' : '#42A5F5';
 const clipId = `clip-ortinv-${pieza}`;
 const pNum = pieza.slice(-1);
 const esMolarPremolar = ['5', '6', '7'].includes(pNum);
 const cuello = CUELLOS_PUNTOS[pieza];
 const sup = SUPERIORES.has(pieza);
 return (
 <g key={`ortinv-${pieza}`}>
 <defs>
 <clipPath id={clipId}>
 <polygon points={crown.map(p => `${p.x},${p.y}`).join(' ')} />
 </clipPath>
 </defs>
 <image href="/odontograma.png" width={726} height={386} clipPath={`url(#${clipId})`} />
 <polygon points={crown.map(p => `${p.x},${p.y}`).join(' ')} fill={color} fillOpacity={0.35} />
 {quadOcl && <polygon points={quadOcl.map(p => `${p.x},${p.y}`).join(' ')} fill={color} fillOpacity={0.25} />}
 {esMolarPremolar && cuello && (
 <circle cx={cuello.x} cy={cuello.y + (sup ? 12 : -12)} r={5} fill="#1565C0" fillOpacity={0.8} stroke="#0D47A1" strokeWidth={1} />
 )}
 </g>
 );
}

// Triángulos papilas — función base reutilizable
function renderTrianguloPapila(pieza: string, color: string, strokeColor: string, isInicial?: boolean, keyPrefix = 'tri') {
 const cuello = CUELLOS_PUNTOS[pieza];
 if (!cuello) return null;
 const sup = SUPERIORES.has(pieza);
 const fillColor = isInicial ? '#9aa0a6' : color;
 const stk = isInicial ? '#7f8c8d' : strokeColor;
 const h = 16, w = 12;
 const tipY = sup ? cuello.y - h - 2 : cuello.y + h + 2;
 const baseY = sup ? cuello.y - 1 : cuello.y + 1;
 return (
 <g key={`${keyPrefix}-${pieza}`}>
 <polygon points={`${cuello.x - w},${baseY} ${cuello.x + w},${baseY} ${cuello.x},${tipY}`}
 fill={fillColor} fillOpacity={0.7} stroke={stk} strokeWidth={0.8} />
 </g>
 );
}

// Injerto periodontal: rojizo
function renderInjerto(pieza: string, isInicial?: boolean) {
 return renderTrianguloPapila(pieza, '#A21CAF', '#7A0F8E', isInicial, 'inj');
}

// Alargamiento coronario: salmón
function renderAlargamiento(pieza: string, isInicial?: boolean) {
 return renderTrianguloPapila(pieza, '#C026D3', '#A21CAF', isInicial, 'alar');
}

// Gingivectomía: morado
function renderGingivectomia(pieza: string, isInicial?: boolean) {
 return renderTrianguloPapila(pieza, '#9C27B0', '#6A0080', isInicial, 'ging');
}

// Bracket de ortodoncia: pequeño rectángulo con ranura horizontal en centro de la corona.
function renderOrtodoncia(pieza: string, isPlanificado?: boolean, isInicial?: boolean) {
 const c = bracketCenter(pieza);
 if (!c) return null;
 const { x: cx, y: cy } = c;
 const w = 12, h = 8;
 const bg = isPlanificado ? '#C026D3' : (isInicial ? '#9aa0a6' : '#9aa0a6');
 const stroke = isPlanificado ? '#7A0F8E' : (isInicial ? '#7f8c8d' : '#3c4043');
 return (
 <g key={`ort-${pieza}`}>
 <rect x={cx - w / 2} y={cy - h / 2} width={w} height={h} fill={bg} stroke={stroke} strokeWidth={0.8} rx={1.2} />
 <line x1={cx - w / 2 + 1.5} y1={cy} x2={cx + w / 2 - 1.5} y2={cy} stroke={stroke} strokeWidth={1.4} strokeLinecap="round" />
 <circle cx={cx - w / 2 + 1.5} cy={cy - h / 2 + 1.5} r={0.9} fill={stroke} />
 <circle cx={cx + w / 2 - 1.5} cy={cy - h / 2 + 1.5} r={0.9} fill={stroke} />
 <circle cx={cx - w / 2 + 1.5} cy={cy + h / 2 - 1.5} r={0.9} fill={stroke} />
 <circle cx={cx + w / 2 - 1.5} cy={cy + h / 2 - 1.5} r={0.9} fill={stroke} />
 </g>
 );
}

// Ausencia: borra tanto la vista lateral como la oclusal.
function renderAusencia(pieza: string, isInicial?: boolean) {
 if (!isInicial) return null; // "solo en O2... si es ausencia quitas la pieza y no pones nada"
 const quad = quadDePieza(pieza);
 const quadOcl = quadOclusalDePieza(pieza);
 if (!quad) return null;
 return (
 <g key={`aus-${pieza}`}>
 <polygon points={quad.map(p => `${p.x},${p.y}`).join(' ')} fill="white" />
 {quadOcl && (
 <polygon points={quadOcl.map(p => `${p.x},${p.y}`).join(' ')} fill="white" />
 )}
 </g>
 );
}

// Exodoncia: aspa + borrado lateral y oclusal.
function renderExodoncia(pieza: string, isPlanificado?: boolean, isInicial?: boolean) {
 const hoverPct = TOOTH_COORDS[pieza];
 if (!hoverPct) return null;
 const cx = hoverPct.x * 7.26;
 const cy = hoverPct.y * 3.86;
 const r = 12;
 const col = isPlanificado ? '#C026D3' : (isInicial ? '#9aa0a6' : '#D500F9');

 const quad = quadDePieza(pieza);
 const quadOcl = quadOclusalDePieza(pieza);

 return (
 <g key={`exo-${pieza}`}>
 {quad && <polygon points={quad.map(p => `${p.x},${p.y}`).join(' ')} fill="white" />}
 {quadOcl && <polygon points={quadOcl.map(p => `${p.x},${p.y}`).join(' ')} fill="white" />}
 <line x1={cx - r} y1={cy - r} x2={cx + r} y2={cy + r} stroke={col} strokeWidth={2.5} strokeLinecap="round" />
 <line x1={cx + r} y1={cy - r} x2={cx - r} y2={cy + r} stroke={col} strokeWidth={2.5} strokeLinecap="round" />
 </g>
 );
}

// Corona sobre diente natural: tiñe la mitad coronal de la pieza.
// Polígonos calibrados de corona por pieza (SVG 726×386). Orden libre.
export const CORONAS_POLIGONOS: Record<string, Punto[]> = {
 '18':[{x:13,y:184},{x:7,y:170},{x:15,y:149},{x:47,y:151},{x:55,y:165},{x:57,y:169},{x:56,y:178},{x:47,y:185},{x:44,y:187},{x:29,y:182}],
 '17':[{x:68,y:152},{x:107,y:152},{x:112,y:163},{x:115,y:173},{x:108,y:183},{x:98,y:188},{x:88,y:181},{x:72,y:183},{x:64,y:173}],
 '16':[{x:120,y:154},{x:157,y:153},{x:161,y:154},{x:166,y:162},{x:169,y:169},{x:168,y:177},{x:166,y:183},{x:159,y:189},{x:145,y:186},{x:133,y:190},{x:125,y:186},{x:119,y:186},{x:113,y:177},{x:115,y:166}],
 '15':[{x:187,y:190},{x:171,y:181},{x:170,y:173},{x:173,y:159},{x:179,y:151},{x:185,y:149},{x:192,y:152},{x:199,y:159},{x:203,y:167},{x:204,y:173},{x:204,y:178},{x:198,y:183}],
 '14':[{x:206,y:182},{x:206,y:170},{x:210,y:157},{x:221,y:150},{x:227,y:153},{x:233,y:159},{x:235,y:164},{x:239,y:170},{x:239,y:179},{x:233,y:185},{x:224,y:190},{x:223,y:192},{x:212,y:186}],
 '13':[{x:258,y:193},{x:238,y:178},{x:244,y:157},{x:250,y:144},{x:258,y:142},{x:265,y:146},{x:270,y:159},{x:275,y:169},{x:275,y:181}],
 '12':[{x:288,y:188},{x:282,y:183},{x:280,y:176},{x:281,y:165},{x:284,y:155},{x:289,y:147},{x:296,y:144},{x:302,y:147},{x:305,y:155},{x:309,y:164},{x:309,y:172},{x:309,y:183},{x:307,y:187},{x:299,y:187}],
 '11':[{x:323,y:192},{x:317,y:186},{x:314,y:174},{x:318,y:161},{x:321,y:150},{x:328,y:142},{x:337,y:139},{x:345,y:143},{x:350,y:150},{x:352,y:159},{x:355,y:171},{x:354,y:182},{x:354,y:191},{x:341,y:192}],
 '21':[{x:377,y:192},{x:364,y:191},{x:364,y:182},{x:363,y:171},{x:366,y:159},{x:368,y:150},{x:373,y:143},{x:381,y:139},{x:390,y:142},{x:397,y:150},{x:400,y:161},{x:404,y:174},{x:401,y:186},{x:395,y:192}],
 '22':[{x:421,y:188},{x:413,y:188},{x:411,y:184},{x:411,y:173},{x:411,y:165},{x:415,y:156},{x:418,y:148},{x:424,y:145},{x:431,y:148},{x:436,y:156},{x:439,y:166},{x:440,y:177},{x:438,y:184},{x:432,y:189}],
 '23':[{x:445,y:180},{x:445,y:168},{x:450,y:158},{x:455,y:145},{x:462,y:141},{x:470,y:143},{x:476,y:156},{x:482,y:177},{x:462,y:192}],
 '24':[{x:512,y:186},{x:501,y:192},{x:500,y:190},{x:491,y:185},{x:485,y:179},{x:485,y:170},{x:489,y:164},{x:491,y:159},{x:497,y:153},{x:503,y:150},{x:514,y:157},{x:518,y:170},{x:518,y:182}],
 '25':[{x:527,y:184},{x:521,y:179},{x:521,y:174},{x:522,y:168},{x:526,y:160},{x:533,y:153},{x:540,y:150},{x:546,y:152},{x:552,y:160},{x:555,y:174},{x:554,y:182},{x:538,y:191}],
 '26':[{x:611,y:165},{x:613,y:176},{x:607,y:185},{x:601,y:185},{x:593,y:189},{x:581,y:185},{x:567,y:188},{x:560,y:182},{x:558,y:176},{x:557,y:168},{x:560,y:161},{x:565,y:153},{x:569,y:152},{x:606,y:153}],
 '27':[{x:666,y:173},{x:658,y:183},{x:642,y:181},{x:632,y:188},{x:622,y:183},{x:615,y:173},{x:618,y:163},{x:623,y:152},{x:662,y:152}],
 '28':[{x:695,y:181},{x:680,y:186},{x:677,y:184},{x:668,y:177},{x:667,y:168},{x:669,y:164},{x:677,y:150},{x:709,y:148},{x:717,y:169},{x:711,y:183}],
 '48':[{x:13,y:237},{x:32,y:242},{x:52,y:240},{x:57,y:236},{x:60,y:224},{x:58,y:210},{x:52,y:206},{x:39,y:211},{x:29,y:204},{x:23,y:205},{x:15,y:207},{x:11,y:217}],
 '47':[{x:68,y:238},{x:66,y:225},{x:69,y:211},{x:75,y:206},{x:84,y:204},{x:90,y:209},{x:101,y:208},{x:108,y:207},{x:114,y:213},{x:117,y:219},{x:117,y:227},{x:115,y:237},{x:107,y:240},{x:94,y:241},{x:83,y:240}],
 '46':[{x:124,y:239},{x:119,y:228},{x:120,y:216},{x:125,y:207},{x:135,y:208},{x:142,y:205},{x:148,y:211},{x:160,y:205},{x:166,y:210},{x:171,y:220},{x:170,y:230},{x:168,y:235},{x:154,y:239},{x:143,y:241}],
 '45':[{x:187,y:241},{x:180,y:230},{x:179,y:222},{x:180,y:216},{x:188,y:209},{x:197,y:204},{x:206,y:210},{x:209,y:214},{x:210,y:220},{x:211,y:230},{x:209,y:236},{x:197,y:241}],
 '44':[{x:226,y:243},{x:217,y:227},{x:215,y:215},{x:228,y:205},{x:233,y:207},{x:241,y:212},{x:247,y:217},{x:246,y:224},{x:244,y:234},{x:235,y:241}],
 '43':[{x:255,y:244},{x:251,y:229},{x:250,y:219},{x:258,y:210},{x:266,y:204},{x:274,y:209},{x:281,y:214},{x:283,y:218},{x:282,y:230},{x:280,y:239},{x:275,y:245},{x:266,y:251}],
 '42':[{x:300,y:246},{x:294,y:230},{x:291,y:217},{x:297,y:210},{x:305,y:210},{x:314,y:210},{x:318,y:213},{x:318,y:221},{x:317,y:231},{x:316,y:240},{x:305,y:246}],
 '41':[{x:332,y:240},{x:330,y:227},{x:329,y:214},{x:331,y:209},{x:343,y:209},{x:352,y:210},{x:355,y:213},{x:354,y:225},{x:351,y:236},{x:341,y:246}],
 '31':[{x:379,y:251},{x:367,y:239},{x:364,y:225},{x:362,y:211},{x:366,y:207},{x:377,y:206},{x:391,y:206},{x:394,y:212},{x:392,y:228},{x:390,y:243}],
 '32':[{x:414,y:246},{x:403,y:240},{x:402,y:231},{x:401,y:221},{x:401,y:213},{x:405,y:210},{x:414,y:210},{x:422,y:210},{x:428,y:217},{x:425,y:230},{x:419,y:246}],
 '33':[{x:454,y:251},{x:445,y:245},{x:440,y:239},{x:438,y:230},{x:437,y:218},{x:439,y:214},{x:446,y:209},{x:454,y:204},{x:462,y:210},{x:470,y:219},{x:469,y:229},{x:465,y:244}],
 '34':[{x:492,y:241},{x:483,y:234},{x:481,y:224},{x:480,y:217},{x:486,y:212},{x:494,y:207},{x:499,y:205},{x:512,y:215},{x:510,y:227},{x:501,y:243}],
 '35':[{x:532,y:240},{x:520,y:235},{x:518,y:229},{x:519,y:219},{x:520,y:213},{x:523,y:209},{x:532,y:203},{x:541,y:208},{x:549,y:215},{x:550,y:221},{x:549,y:229},{x:542,y:240}],
 '36':[{x:583,y:241},{x:572,y:239},{x:558,y:235},{x:556,y:230},{x:555,y:220},{x:560,y:210},{x:566,y:205},{x:578,y:211},{x:584,y:205},{x:591,y:208},{x:601,y:207},{x:606,y:216},{x:607,y:228},{x:602,y:239}],
 '37':[{x:647,y:238},{x:636,y:239},{x:623,y:238},{x:615,y:235},{x:613,y:225},{x:613,y:217},{x:616,y:211},{x:622,y:205},{x:629,y:206},{x:640,y:207},{x:646,y:202},{x:655,y:204},{x:661,y:209},{x:664,y:223},{x:662,y:236}],
 '38':[{x:713,y:216},{x:709,y:206},{x:701,y:204},{x:695,y:203},{x:685,y:210},{x:672,y:205},{x:666,y:209},{x:664,y:223},{x:667,y:235},{x:672,y:239},{x:692,y:241},{x:711,y:236}],
};

function renderProtesisRemovible(pieza: string, isPlanificado?: boolean, isInicial?: boolean) {
 const crown = CORONAS_POLIGONOS[pieza];
 if (!crown) return null;
 const quad = quadDePieza(pieza);
 const quadOcl = quadOclusalDePieza(pieza);
 const colorFinal = isPlanificado ? '#C026D3' : (isInicial ? '#9aa0a6' : PROTESIS_COLOR);
 const clipId = `clip-protrem-${pieza}`;
 return (
 <g key={`protrem-${pieza}`}>
 {quad && <polygon points={quad.map(p => `${p.x},${p.y}`).join(' ')} fill="white" />}
 {quadOcl && <polygon points={quadOcl.map(p => `${p.x},${p.y}`).join(' ')} fill="white" />}
 <defs>
 <clipPath id={clipId}>
 <polygon points={crown.map(p => `${p.x},${p.y}`).join(' ')} />
 </clipPath>
 </defs>
 <image href="/odontograma.png" width={726} height={386} clipPath={`url(#${clipId})`} />
 <polygon points={crown.map(p => `${p.x},${p.y}`).join(' ')} fill={colorFinal} fillOpacity={0.4} />
 {quadOcl && <polygon points={quadOcl.map(p => `${p.x},${p.y}`).join(' ')} fill={colorFinal} fillOpacity={0.3} />}
 </g>
 );
}

function renderCorona(pieza: string, isPlanificado?: boolean, isInicial?: boolean) {
 const crown = CORONAS_POLIGONOS[pieza];
 if (!crown) return null;
 const quadOcl = quadOclusalDePieza(pieza);
 const colorFinal = isPlanificado ? '#C026D3' : (isInicial ? '#9aa0a6' : CORONA_COLOR);
 const clipId = `clip-cor-${pieza}`;
 return (
 <g key={`cor-${pieza}`}>
 <defs>
 <clipPath id={clipId}>
 <polygon points={crown.map(p => `${p.x},${p.y}`).join(' ')} />
 </clipPath>
 </defs>
 <image href="/odontograma.png" width={726} height={386} clipPath={`url(#${clipId})`} />
 <polygon points={crown.map(p => `${p.x},${p.y}`).join(' ')} fill={colorFinal} fillOpacity={0.4} />
 {quadOcl && <polygon points={quadOcl.map(p => `${p.x},${p.y}`).join(' ')} fill={colorFinal} fillOpacity={0.3} />}
 </g>
 );
}

export default function TratamientoSVG({ pieza, tratamiento, caras, isPlanificado, isInicial }: Props & { isInicial?: boolean }) {
 const key = tratamiento.toLowerCase().trim();
 if (key === 'endodoncia') return renderEndodoncia(pieza, isPlanificado, isInicial, false);
 if (key === 'perno' || key === 'reconstruccion-perno') return renderEndodoncia(pieza, isPlanificado, isInicial, true);
 if (key === 'quistectomia') return renderQuistectomia(pieza, isInicial);
 if (key === 'caries') return renderCaries(pieza, caras, isPlanificado, isInicial);
 if (key === 'obturacion' || key === 'obturación') return renderObturacion(pieza, caras, isPlanificado, isInicial);
 if (key === 'implante') return renderImplante(pieza, isPlanificado, isInicial);
 if (key === 'corona-implante' || key === 'corona sobre implante') return renderCoronaImplante(pieza, isPlanificado, isInicial);
 if (key === 'corona') return renderCorona(pieza, isPlanificado, isInicial);
 if (key === 'protesis-removible' || key === 'protesis removible') return renderProtesisRemovible(pieza, isPlanificado, isInicial);
 if (key === 'protesis' || key === 'prótesis' || key === 'protesis-parcial' || key === 'parcial') return renderProtesisRemovible(pieza, isPlanificado, isInicial);
 if (key === 'ortodoncia' || key === 'bracket') return renderOrtodoncia(pieza, isPlanificado, isInicial);
 if (key === 'retenedor removible') return renderRetenedorRemovible(pieza, isInicial);
 if (key === 'retenedor fijo') return renderRetenedorFijo(pieza, isInicial);
 if (key === 'ortodoncia invisible' || key === 'alineadores') return renderOrtodonciaInvisible(pieza, isInicial);
 if (key === 'exodoncia' || key === 'extraccion') return renderExodoncia(pieza, isPlanificado, isInicial);
 if (key === 'ausencia' || key === 'ausente') return renderAusencia(pieza, isInicial);
 if (key === 'limpieza' || key === 'tartrectomia' || key === 'higiene') return renderLimpieza(pieza, isInicial);
 if (key === 'raspado' || key === 'curetaje') return renderRaspado(pieza, isInicial);
 if (key === 'gingivectomia') return renderGingivectomia(pieza, isInicial);
 if (key === 'alargamiento coronario' || key === 'alargamiento') return renderAlargamiento(pieza, isInicial);
 if (key === 'injerto' || key === 'injerto periodontal') return renderInjerto(pieza, isInicial);
 return null;
}
