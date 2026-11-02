/**
 * odontogramaUtils.ts — constantes y funciones puras del odontograma.
 * Separadas de los componentes React para cumplir con Fast Refresh de Vite:
 * los archivos que exportan componentes no deben exportar también constantes/funciones.
 */

export type PiezaFDI =
 | '18' | '17' | '16' | '15' | '14' | '13' | '12' | '11'
 | '21' | '22' | '23' | '24' | '25' | '26' | '27' | '28'
 | '48' | '47' | '46' | '45' | '44' | '43' | '42' | '41'
 | '31' | '32' | '33' | '34' | '35' | '36' | '37' | '38';

// Imagen base del odontograma según la edad (dentición MIXTA por recambio de cada pieza).
// Etapas en el mismo lienzo 726×386 que el adulto; ≥13 o sin fecha → adulto.
// Recambio: incisivo central 6, lateral 8, canino/1er premolar 11, 2º premolar 12;
// molares permanentes erupcionan a 6/12/18.
export function baseOdontograma(edad: number | null): string {
 const v = '?v=2';  // cache-busting tras corregir el oclusal de la 44 (fuerza recarga en navegador)
 if (edad == null || edad >= 13) return '/odontograma.png' + v;
 if (edad < 6) return '/odontograma-inf-4.png' + v;
 if (edad < 8) return '/odontograma-inf-7.png' + v;
 if (edad < 11) return '/odontograma-inf-9.png' + v;
 if (edad < 12) return '/odontograma-inf-11.png' + v;
 return '/odontograma-inf-12.png' + v;
}

export const TODAS_LAS_PIEZAS: PiezaFDI[] = [
 '18', '17', '16', '15', '14', '13', '12', '11',
 '21', '22', '23', '24', '25', '26', '27', '28',
 '48', '47', '46', '45', '44', '43', '42', '41',
 '31', '32', '33', '34', '35', '36', '37', '38',
];

interface Punto { x: number; y: number; }

// Path SVG smooth a partir de puntos (2 = recta, 3+ = curva cuadrática encadenada)
export function pathDesdePuntos(points: Punto[]): string {
 if (points.length < 2) return '';
 if (points.length === 2) return `M${points[0].x},${points[0].y} L${points[1].x},${points[1].y}`;
 let d = `M${points[0].x},${points[0].y}`;
 for (let i = 1; i < points.length - 1; i++) {
 const mid = { x: (points[i].x + points[i + 1].x) / 2, y: (points[i].y + points[i + 1].y) / 2 };
 d += ` Q${points[i].x},${points[i].y} ${mid.x},${mid.y}`;
 }
 d += ` L${points[points.length - 1].x},${points[points.length - 1].y}`;
 return d;
}

// Polígonos de tile oclusal calibrados sobre odontograma.png (726×386).
export const CARIES_TILES: Record<string, Punto[]> = {
 // Maxilar derecho
 '18': [{x:32,y:16.5},{x:46,y:19.5},{x:51,y:29.5},{x:49,y:42.5},{x:34,y:46.5},{x:19,y:43.5},{x:15,y:32.5},{x:18,y:18.5}],
 '17': [{x:83,y:20.5},{x:98,y:23.5},{x:101,y:35.5},{x:98,y:46.5},{x:84,y:49.5},{x:70,y:46.5},{x:64,y:35.5},{x:68,y:20.5}],
 '16': [{x:136,y:19.5},{x:153,y:21.5},{x:158,y:36.5},{x:153,y:49.5},{x:137,y:49.5},{x:125,y:46.5},{x:118,y:35.5},{x:122,y:22.5}],
 '15': [{x:189,y:18.5},{x:200,y:33.5},{x:191,y:49.5},{x:179,y:36.5}],
 '14': [{x:218,y:19.5},{x:227,y:34.5},{x:220,y:46.5},{x:209,y:34.5}],
 '13': [{x:264,y:14.5},{x:273,y:31.5},{x:266,y:46.5},{x:255,y:33.5}],
 '12': [{x:296,y:16.5},{x:303,y:29.5},{x:296,y:45.5},{x:285,y:31.5}],
 '11': [{x:327,y:17.5},{x:335,y:27.5},{x:328,y:46.5},{x:318,y:30.5}],
 // Maxilar izquierdo
 '21': [{x:392,y:16.5},{x:401,y:28.5},{x:390,y:44.5},{x:382,y:27.5}],
 '22': [{x:423,y:16.5},{x:431,y:26.5},{x:423,y:44.5},{x:415,y:26.5}],
 '23': [{x:454,y:14.5},{x:463,y:30.5},{x:454,y:46.5},{x:445,y:29.5}],
 '24': [{x:502,y:17.5},{x:509,y:33.5},{x:502,y:45.5},{x:493,y:32.5}],
 '25': [{x:533,y:16.5},{x:544,y:32.5},{x:533,y:47.5},{x:522,y:32.5}],
 '26': [{x:583,y:18.5},{x:599,y:21.5},{x:603,y:32.5},{x:597,y:46.5},{x:584,y:47.5},{x:568,y:45.5},{x:562,y:35.5},{x:568,y:20.5}],
 '27': [{x:641,y:18.5},{x:655,y:22.5},{x:657,y:34.5},{x:653,y:47.5},{x:637,y:49.5},{x:627,y:47.5},{x:622,y:34.5},{x:627,y:20.5}],
 '28': [{x:689,y:14.5},{x:705,y:17.5},{x:708,y:30.5},{x:707,y:43.5},{x:692,y:46.5},{x:678,y:42.5},{x:672,y:29.5},{x:676,y:16.5}],
 // Mandíbula izquierda
 '31': [{x:392,y:329.5},{x:400,y:343.5},{x:390,y:358.5},{x:383,y:343.5}],
 '32': [{x:422,y:329.5},{x:431,y:344.5},{x:425,y:360.5},{x:414,y:343.5}],
 '33': [{x:454,y:326.5},{x:463,y:344.5},{x:457,y:362.5},{x:445,y:344.5}],
 '34': [{x:502,y:325.5},{x:514,y:341.5},{x:503,y:358.5},{x:492,y:343.5}],
 '35': [{x:533,y:325.5},{x:548,y:341.5},{x:537,y:359.5},{x:523,y:341.5}],
 '36': [{x:586,y:326.5},{x:603,y:329.5},{x:607,y:341.5},{x:603,y:354.5},{x:585,y:355.5},{x:570,y:352.5},{x:565,y:342.5},{x:570,y:327.5}],
 '37': [{x:643,y:325.5},{x:656,y:328.5},{x:661,y:339.5},{x:660,y:353.5},{x:646,y:355.5},{x:627,y:353.5},{x:624,y:341.5},{x:629,y:327.5}],
 '38': [{x:696,y:328.5},{x:709,y:333.5},{x:715,y:345.5},{x:712,y:358.5},{x:697,y:360.5},{x:682,y:359.5},{x:676,y:344.5},{x:683,y:330.5}],
 // Mandíbula derecha
 '41': [{x:335,y:328.5},{x:346,y:343.5},{x:336,y:361.5},{x:328,y:344.5}],
 '42': [{x:301,y:331.5},{x:314,y:345.5},{x:302,y:360.5},{x:293,y:344.5}],
 '43': [{x:271,y:326.5},{x:282,y:344.5},{x:268,y:363.5},{x:256,y:342.5}],
 '44': [{x:218,y:326.5},{x:231,y:341.5},{x:222,y:360.5},{x:210,y:344.5}],
 '45': [{x:189,y:326.5},{x:202,y:342.5},{x:190,y:359.5},{x:178,y:341.5}],
 '46': [{x:136,y:324.5},{x:150,y:328.5},{x:156,y:340.5},{x:153,y:355.5},{x:137,y:356.5},{x:119,y:354.5},{x:114,y:342.5},{x:122,y:326.5}],
 '47': [{x:79,y:325.5},{x:92,y:328.5},{x:98,y:340.5},{x:93,y:353.5},{x:78,y:357.5},{x:62,y:352.5},{x:58,y:342.5},{x:65,y:326.5}],
 '48': [{x:24,y:329.5},{x:41,y:332.5},{x:46,y:344.5},{x:40,y:358.5},{x:25,y:360.5},{x:8,y:356.5},{x:6,y:345.5},{x:11,y:330.5}],
};

// ─── Parser Robusto: Extrae tratamiento y caras de una descripción ───────────
export const FACE_MAP: Record<string, string> = {
 oclusal: 'O', mesial: 'M', distal: 'D', vestibular: 'V', lingual: 'L', palatino: 'L', cervical: 'C'
};

export const SVG_COLOR: Record<string, string> = {
 caries: '#7C3AED',
 obturacion: '#FF6FD8',
 endodoncia: '#424242',
 corona: '#E9C22E',
 'corona-implante': '#E9C22E',
 implante: '#1DE9B6',
 ortodoncia: '#9aa0a6',
 exodoncia: '#D500F9',
 ausencia: '#D500F9',
 protesis: '#F8BBD0',
 'protesis-removible': '#F8BBD0',
 quistectomia: '#C026D3',
 limpieza: '#00BCD4',
 tartrectomia: '#00BCD4',
 higiene: '#00BCD4',
 raspado: '#E01B84',
 curetaje: '#E01B84',
 injerto: '#A21CAF',
 'injerto periodontal': '#A21CAF',
 gingivectomia: '#9C27B0',
 'alargamiento coronario': '#C026D3',
 alargamiento: '#C026D3',
 'retenedor removible': '#81D4FA',
 'retenedor fijo': '#3c4043',
 'ortodoncia invisible': '#42A5F5',
 alineadores: '#42A5F5',
 perno: '#7C3AED',
 'reconstruccion-perno': '#7C3AED',
};

export const PIEZAS_SUP = ['18','17','16','15','14','13','12','11','21','22','23','24','25','26','27','28'];
export const PIEZAS_INF = ['48','47','46','45','44','43','42','41','31','32','33','34','35','36','37','38'];

export function piezasImplicitas(key: string, desc: string): string[] {
 const text = desc.toLowerCase();
 if (key === 'ortodoncia' || key === 'ortodoncia invisible' || key === 'alineadores') {
 if (text.includes('superior')) return PIEZAS_SUP;
 if (text.includes('inferior')) return PIEZAS_INF;
 return [];
 }
 // Un retenedor siempre va sobre una arcada → si no se especifica, ambas (si no, no se dibujaría).
 if (key === 'retenedor removible') {
 if (text.includes('superior')) return PIEZAS_SUP;
 if (text.includes('inferior')) return PIEZAS_INF;
 return [...PIEZAS_SUP, ...PIEZAS_INF];
 }
 if (key === 'retenedor fijo') {
 if (text.includes('superior')) return ['13','12','11','21','22','23'];
 if (text.includes('inferior')) return ['43','42','41','31','32','33'];
 return ['43','42','41','31','32','33']; // sin arcada → inferior (lo habitual en retenedor fijo)
 }
 if (key === 'limpieza' || key === 'tartrectomia' || key === 'higiene' || key === 'raspado' || key === 'curetaje') {
 return [...PIEZAS_SUP, ...PIEZAS_INF];
 }
 return [];
}

export function parseTratamientoPresupuesto(desc: string): { key: string; caras?: string } {
 if (!desc) return { key: 'obturacion' };
 const text = desc.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
 let key = 'obturacion'; // default
 let caras = '';

 // 1. Detectar Key
 if (text.includes('quistectomia') || text.includes('quiste')) key = 'quistectomia';
 else if (text.includes('perno') || (text.includes('reconstruccion') && text.includes('fibra'))) key = 'perno';
 else if (text.includes('endodoncia')) key = 'endodoncia';
 else if (text.includes('implante') && text.includes('corona')) key = 'corona-implante';
 else if (text.includes('implante')) key = 'implante';
 else if (text.includes('corona') || text.includes('carilla')) key = 'corona';
 else if (text.includes('protesis') && text.includes('removible')) key = 'protesis-removible';
 else if (text.includes('protesis') || text.includes('parcial') || text.includes('puente')) key = 'protesis';
 else if (text.includes('ortodoncia') && text.includes('invisible') || text.includes('alineador')) key = 'ortodoncia invisible';
 else if (text.includes('retenedor') && text.includes('removible')) key = 'retenedor removible';
 else if (text.includes('retenedor') && text.includes('fijo')) key = 'retenedor fijo';
 else if (text.includes('ortodoncia') || text.includes('bracket')) key = 'ortodoncia';
 else if (text.includes('exodoncia') || text.includes('extraccion')) key = 'exodoncia';
 else if (text.includes('ausencia') || text.includes('ausente')) key = 'ausencia';
 else if (text.includes('caries')) key = 'caries';
 else if (text.includes('gingivectomia')) key = 'gingivectomia';
 else if (text.includes('alargamiento')) key = 'alargamiento coronario';
 else if (text.includes('injerto')) key = 'injerto';
 else if (text.includes('raspado') || text.includes('curetaje')) key = 'raspado';
 else if (text.includes('limpieza') || text.includes('tartrectomia') || text.includes('higiene') || text.includes('profilaxis')) key = 'limpieza';
 else if (text.includes('empaste') || text.includes('obturacion') || text.includes('reconstruccion')) key = 'obturacion';

 // 2. Detectar Caras (por iniciales pegadas tipo "MOD" o palabras completas)
 // Buscamos patrones tipo " MOD ", "(OD)", "V", etc.
 const facesRegex = /\b([OMDVLC]{1,5})\b/i;
 const match = desc.match(facesRegex);
 if (match) {
 caras = match[1].toUpperCase();
 } else {
 // Si no hay iniciales, buscamos palabras completas
 Object.entries(FACE_MAP).forEach(([word, char]) => {
 if (text.includes(word)) caras += char;
 });
 }

 return { key, caras: caras || undefined };
}
