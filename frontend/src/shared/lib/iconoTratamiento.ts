// Mapea el nombre de un tratamiento a un icono en color de /public/icons/color (1 PNG por icono).
// Set en color aportado por el centro. Por palabras clave; si no encaja, diente genérico.
// Conceptos que el set no trae propios (implante, prótesis, radiografía, limpieza) → color más cercano.
const REGLAS: [RegExp, string][] = [
  [/endodonci|conducto|reendodonci/i, "taladro"],
  [/ortodonci|bracket|alineador|invisalign|retenedor|ortodon/i, "brackets"],
  [/implante|injerto|cirug|exodonci|extracci|quistect/i, "herramientas"],
  [/corona|funda|carilla|incrustaci|onlay|inlay|protesi|dentadura|esquelet|removible/i, "corona"],
  [/anestesi|infiltr|jeringa/i, "jeringa"],
  [/radiograf|panoram|\brx\b|escaner|\btac\b|cbct|ortopant|revisi|diagn[oó]stic|primera visita/i, "estetoscopio"],
  [/limpieza|higiene|tartrect|profilaxis|fluor|sellad|periodonci|raspado|curetaje|blanqueam|est[eé]tic/i, "diente"],
  [/caries|obturaci|empaste|reconstrucci|composite|pasividad/i, "caries"],
];

export function iconoTratamiento(nombre: string | null | undefined): string {
  const n = nombre || "";
  for (const [re, icono] of REGLAS) if (re.test(n)) return `/icons/color/${icono}.png`;
  return "/icons/color/diente.png";
}
