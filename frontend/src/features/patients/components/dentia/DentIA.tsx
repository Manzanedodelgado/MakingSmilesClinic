"use client";
/**
 * DENTIA — análisis guiado de una radiografía en 4 pasos: 1 Procesar · 2 Patrones · 3 Plan · 4 Informe.
 *
 * · La IA SOLO sugiere lo que sabe detectar (numeración FDI, dientes incluidos, canal dentario inferior, seno
 *   maxilar); el resto de patrones los marca el doctor. Las sugerencias se aceptan o se descartan.
 * · El estado (paso, patrones, plan) se guarda solo, por imagen de Multimedia.
 * · El plan usa el catálogo y los precios de la tarifa del paciente y se convierte en un presupuesto real.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, ChevronRight, Contrast, Crosshair, Loader2, Moon, Printer, Sparkles, Sun, Undo2, X, ZoomIn, ZoomOut, Check } from "lucide-react";
import { patientService } from "../../services/patientService";
import type { DentiaLineaPlan, DentiaPatron, MultimediaItem, PacienteCabecera } from "../../types/patient";
import { CATEGORIAS, GRUPOS, PLANIFICABLES, nuevoId } from "./categorias";
import { ModalHallazgo, TablaPlan, importeLinea } from "./PlanPaso";

const PASOS = [["Procesar", 1], ["Patrones", 2], ["Plan", 3], ["Informe", 4]] as const;
const eur = (n: number) => n.toLocaleString("es-ES", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";

/** Estructuras que la IA devuelve con confianza baja (< 0,3): se dibujan discontinuas hasta que el doctor las confirma o las ajusta. */
const UMBRAL_CONFIANZA = 0.3;
const esBaja = (p: DentiaPatron) => p.origen === "ia" && p.categoria !== "pieza" && p.confianza != null && p.confianza < UMBRAL_CONFIANZA;

/** Caja [x1,y1,x2,y2] de un contorno y solapamiento (IoU) entre dos cajas: para no duplicar lo que el doctor ya validó. */
const cajaDe = (pts: number[][]) => { const xs = pts.map((q) => q[0]), ys = pts.map((q) => q[1]); return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)]; };
const iouCajas = (a: number[], b: number[]) => {
  const w = Math.max(0, Math.min(a[2], b[2]) - Math.max(a[0], b[0])), h = Math.max(0, Math.min(a[3], b[3]) - Math.max(a[1], b[1])), i = w * h;
  const u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i;
  return u > 0 ? i / u : 0;
};

/** Reduce un contorno a los puntos que importan (el servidor de IA da decenas): así se puede ajustar a mano. */
function simplificar(pts: number[][], tol: number): number[][] {
  if (pts.length <= 12) return pts;
  const dist = (p: number[], a: number[], b: number[]) => {
    const dx = b[0] - a[0], dy = b[1] - a[1], l = dx * dx + dy * dy;
    if (!l) return Math.hypot(p[0] - a[0], p[1] - a[1]);
    const t = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l));
    return Math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy));
  };
  const rdp = (arr: number[][]): number[][] => {
    if (arr.length < 3) return arr;
    let m = 0, k = 0;
    for (let i = 1; i < arr.length - 1; i++) { const d = dist(arr[i], arr[0], arr[arr.length - 1]); if (d > m) { m = d; k = i; } }
    if (m <= tol) return [arr[0], arr[arr.length - 1]];
    return [...rdp(arr.slice(0, k + 1)).slice(0, -1), ...rdp(arr.slice(k))];
  };
  const r = rdp(pts);
  return r.length >= 3 ? r : pts;
}

type Ajustes = { brillo: number; contraste: number; invertir: boolean; zoom: number };

export function DentIA({ patientId, fileId }: { patientId: number; fileId: string }) {
  const router = useRouter();
  const [cab, setCab] = useState<PacienteCabecera | null>(null);
  const [radios, setRadios] = useState<MultimediaItem[]>([]);
  const [paso, setPaso] = useState(1);
  const [patrones, setPatrones] = useState<DentiaPatron[]>([]);
  const [plan, setPlan] = useState<DentiaLineaPlan[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [guardado, setGuardado] = useState<"idle" | "guardando" | "ok" | "error">("idle");
  const listo = useRef(false);

  // visor
  const [dim, setDim] = useState<{ w: number; h: number } | null>(null);
  const [aj, setAj] = useState<Ajustes>({ brillo: 100, contraste: 100, invertir: false, zoom: 1 });
  const [panel, setPanel] = useState<"brillo" | "contraste" | null>(null);
  const [visibles, setVisibles] = useState<Set<string>>(() => new Set(Object.keys(CATEGORIAS)));
  const [verPiezas, setVerPiezas] = useState(true);
  const [verCuadros, setVerCuadros] = useState(false);
  const [verEtiquetas, setVerEtiquetas] = useState(true);

  // dibujo manual
  const [catActiva, setCatActiva] = useState<string>("obturacion");
  const [dibujando, setDibujando] = useState(false);
  const [tmp, setTmp] = useState<number[][]>([]);
  const [piezaTmp, setPiezaTmp] = useState("");
  // Añadir una pieza (cuadro de diente) a mano: dos esquinas opuestas + número FDI.
  const [modoPieza, setModoPieza] = useState(false);
  const [cajaTmp, setCajaTmp] = useState<number[][]>([]);
  const [numNuevo, setNumNuevo] = useState("");
  const [errNuevo, setErrNuevo] = useState<string | null>(null);
  const sinSeleccion = dibujando || modoPieza;   // mientras se dibuja, las zonas clicables no capturan el clic
  // La guarda de versión (ClienteObsoletoGuard) NO recarga la página mientras haya trabajo a medias aquí.
  const ocupadoRef = useRef(false);
  ocupadoRef.current = dibujando || modoPieza || tmp.length > 0 || cajaTmp.length > 0 || guardado === "guardando";
  useEffect(() => {
    const w = window as unknown as { __msOcupado?: () => boolean };
    w.__msOcupado = () => ocupadoRef.current;
    return () => { delete w.__msOcupado; };
  }, []);
  const [seleccion, setSeleccion] = useState<string | null>(null);

  // IA
  const [iaCargando, setIaCargando] = useState(false);
  const [iaMsg, setIaMsg] = useState<string | null>(null);
  const [propuesta, setPropuesta] = useState<DentiaPatron[] | null>(null);

  // plan / informe
  const [hallazgo, setHallazgo] = useState<DentiaPatron | null>(null);
  const [finPlan, setFinPlan] = useState(false);
  const [presupNum, setPresupNum] = useState<number | null>(null);
  const [creando, setCreando] = useState(false);

  const src = patientService.multimediaUrl(patientId, fileId);

  // ── carga ──
  useEffect(() => {
    let vivo = true;
    listo.current = false;
    setCargando(true); setError(null);
    Promise.all([
      patientService.dentiaObtener(patientId, fileId),
      patientService.cabecera(patientId).catch(() => null),
      patientService.multimedia(patientId).catch(() => null),
    ]).then(([a, c, m]) => {
      if (!vivo) return;
      setPaso(a.paso || 1); setPatrones(a.patrones); setPlan(a.plan);
      setCab(c); setRadios(m?.radiografias ?? []);
      listo.current = true;
    }).catch((e) => vivo && setError(e instanceof Error ? e.message : "No se pudo cargar el análisis"))
      .finally(() => vivo && setCargando(false));
    return () => { vivo = false; };
  }, [patientId, fileId]);

  // ── autoguardado (debounce) ──
  useEffect(() => {
    if (!listo.current) return;
    if (paso === 1 && patrones.length === 0 && plan.length === 0) return;   // solo mirar no crea análisis vacíos
    setGuardado("guardando");
    const t = setTimeout(() => {
      patientService.dentiaGuardar(patientId, { file_id: fileId, paso, patrones, plan })
        .then(() => setGuardado("ok")).catch(() => setGuardado("error"));
    }, 800);
    return () => clearTimeout(t);
  }, [paso, patrones, plan, patientId, fileId]);

  // ── derivados ──
  const lesiones = useMemo(() => patrones.filter((p) => p.categoria !== "pieza"), [patrones]);
  const cuenta = useMemo(() => {
    const c: Record<string, number> = {};
    for (const p of lesiones) c[p.categoria] = (c[p.categoria] ?? 0) + 1;
    return c;
  }, [lesiones]);
  const piezasIA = useMemo(() => patrones.filter((p) => p.categoria === "pieza"), [patrones]);
  const piezasConHallazgo = useMemo(() => new Set(lesiones.map((p) => p.pieza).filter(Boolean) as string[]), [lesiones]);
  // La IA no distingue implantes de dientes: una pieza que el doctor marca como «Implante» deja de contar y de mostrarse como diente.
  const piezasImplante = useMemo(() => new Set(patrones.filter((p) => p.categoria === "implante" && p.pieza).map((p) => p.pieza as string)), [patrones]);
  const sanos = piezasIA.filter((p) => !piezasConHallazgo.has(p.pieza ?? "") && !piezasImplante.has(p.pieza ?? "")).length;
  const total = plan.reduce((s, l) => s + importeLinea(l), 0);
  const filtro = `brightness(${aj.brillo}%) contrast(${aj.contraste}%)${aj.invertir ? " invert(1)" : ""}`;
  const nombre = cab ? `${cab.apellidos}, ${cab.nombre}` : "";

  // ── IA ──
  const detectar = useCallback(async () => {
    setIaCargando(true); setIaMsg(null);
    try {
      const r = await patientService.dentiaDetectar(patientId, fileId);
      const cajas: DentiaPatron[] = r.dientes.map((d) => ({
        id: `ia-pieza-${d.fdi}`, categoria: "pieza", origen: "ia", pieza: d.fdi, confianza: d.conf,
        puntos: [[d.bbox[0], d.bbox[1]], [d.bbox[2], d.bbox[1]], [d.bbox[2], d.bbox[3]], [d.bbox[0], d.bbox[3]]],
      }));
      // Un seno/nervio con máscara fragmentada llega como varios contornos: se descartan los fragmentos pequeños
      // (< 25 % del mayor de esa misma detección) para no llenar la imagen de ruido.
      const areaCaja = (pts: number[][]) => { const xs = pts.map((q) => q[0]), ys = pts.map((q) => q[1]); return (Math.max(...xs) - Math.min(...xs)) * (Math.max(...ys) - Math.min(...ys)); };
      const clave = (p: DentiaPatron) => `${p.categoria}|${p.confianza}`;
      const mayor: Record<string, number> = {};
      for (const p of r.patrones) mayor[clave(p)] = Math.max(mayor[clave(p)] ?? 0, areaCaja(p.puntos));
      const formas = r.patrones.filter((p) => areaCaja(p.puntos) >= 0.25 * mayor[clave(p)])
        .map((p) => ({ ...p, puntos: simplificar(p.puntos, Math.max(2, r.ancho / 450)) }));
      setPropuesta([...cajas, ...formas]);
      setDim((d) => d ?? { w: r.ancho, h: r.alto });
      setIaMsg(r.errores.length ? `Aviso: ${r.errores.join("; ")}` : null);
    } catch (e) {
      setIaMsg(e instanceof Error ? e.message : "La IA no está disponible");
    } finally { setIaCargando(false); }
  }, [patientId, fileId]);

  const aceptarPropuesta = () => {
    if (!propuesta) return;
    // Reemplaza solo la IA anterior. Lo del doctor (marcado a mano, ajustado o confirmado) manda: la IA no lo duplica
    // (misma pieza FDI, o misma estructura solapada > 30 %).
    setPatrones((prev) => {
      const mios = prev.filter((p) => p.origen !== "ia");
      const nuevos = propuesta.filter((n) => n.categoria === "pieza"
        ? !mios.some((m) => m.categoria === "pieza" && m.pieza === n.pieza)
        : !mios.some((m) => m.categoria === n.categoria && iouCajas(cajaDe(m.puntos), cajaDe(n.puntos)) > 0.3));
      return [...mios, ...nuevos];
    });
    setPropuesta(null);
    setPaso(2);
  };

  // ── dibujo ──
  const cat = CATEGORIAS[catActiva];
  const minPuntos = cat?.tipo === "linea" ? 2 : 3;
  // Clic → coordenadas de la IMAGEN. Se usa la transformación real del SVG (viewBox + «meet»): la radiografía queda
  // centrada con franjas negras si el visor es más ancho/alto que ella, y escalar con el cuadro entero del visor
  // desplazaba cada punto (hasta ~165 px; visto por el usuario con un implante, 31-oct-2026).
  const aImagen = (svg: SVGSVGElement, cx: number, cy: number): number[] | null => {
    if (!dim) return null;
    const ctm = svg.getScreenCTM();
    if (!ctm) return null;
    const pt = svg.createSVGPoint();
    pt.x = cx; pt.y = cy;
    const p = pt.matrixTransform(ctm.inverse());
    return [Math.round(Math.min(dim.w, Math.max(0, p.x))), Math.round(Math.min(dim.h, Math.max(0, p.y)))];
  };
  const puntoEnImagen = (e: React.MouseEvent<SVGSVGElement>): number[] | null => aImagen(e.currentTarget, e.clientX, e.clientY);

  // ── Reedición de la forma de un patrón (nervio, seno, hallazgo…): arrastrar puntos, añadir y quitar ──
  const editarPatron = (id: string, f: (pts: number[][]) => number[][]) =>
    setPatrones((prev) => prev.map((x) => (x.id === id ? { ...x, origen: "doctor", puntos: f(x.puntos) } : x)));   // editado a mano → ya no es «de la IA»
  const iniciarArrastre = (id: string, i: number, svg: SVGSVGElement) => {
    const mover = (ev: PointerEvent) => {
      const pt = aImagen(svg, ev.clientX, ev.clientY);
      if (pt) editarPatron(id, (pts) => pts.map((q, j) => (j === i ? pt : q)));
    };
    const fin = () => { window.removeEventListener("pointermove", mover); window.removeEventListener("pointerup", fin); };
    window.addEventListener("pointermove", mover);
    window.addEventListener("pointerup", fin);
  };
  const quitarVertice = (id: string, i: number) => {
    const p = patrones.find((x) => x.id === id);
    const minimo = CATEGORIAS[p?.categoria ?? ""]?.tipo === "linea" ? 2 : 3;
    if (!p || p.puntos.length <= minimo) return;
    editarPatron(id, (pts) => pts.filter((_, j) => j !== i));
  };
  const clicEnImagen = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!modoPieza && !dibujando) return;
    const pt = puntoEnImagen(e);
    if (!pt) return;
    if (modoPieza) { setCajaTmp((c) => (c.length >= 2 ? c : [...c, pt])); return; }
    setTmp((t) => [...t, pt]);
  };
  const cancelarPieza = () => { setModoPieza(false); setCajaTmp([]); setNumNuevo(""); setErrNuevo(null); };
  const anadirPieza = () => {
    if (cajaTmp.length < 2) return;
    const [a, b] = cajaTmp;
    if (Math.abs(a[0] - b[0]) < 8 || Math.abs(a[1] - b[1]) < 8) { setErrNuevo("El cuadro es demasiado pequeño: marca dos esquinas opuestas del diente"); return; }
    if (!/^[1-4][1-8]$/.test(numNuevo)) { setErrNuevo("Número FDI no válido (11-18, 21-28, 31-38, 41-48)"); return; }
    if (patrones.some((x) => x.categoria === "pieza" && x.pieza === numNuevo)) { setErrNuevo(`Ya existe la pieza ${numNuevo}: selecciónala para cambiarla`); return; }
    const id = nuevoId();
    setPatrones((p) => [...p, { id, categoria: "pieza", origen: "doctor", pieza: numNuevo,
      puntos: [[Math.min(a[0], b[0]), Math.min(a[1], b[1])], [Math.max(a[0], b[0]), Math.max(a[1], b[1])]] }]);
    cancelarPieza(); setSeleccion(id);
  };
  const consolidar = () => {
    if (tmp.length < minPuntos) return;
    const id = nuevoId();
    setPatrones((p) => [...p, { id, categoria: catActiva, origen: "doctor", pieza: piezaTmp.trim() || null, puntos: tmp }]);
    setTmp([]); setDibujando(false); setPiezaTmp(""); setSeleccion(id);
  };
  // Corrección de la numeración de la IA: el doctor cambia el número FDI de una pieza o la quita.
  const [numEdit, setNumEdit] = useState("");
  const [numErr, setNumErr] = useState<string | null>(null);
  useEffect(() => {
    const p = patrones.find((x) => x.id === seleccion);
    setNumEdit(p?.categoria === "pieza" ? (p.pieza ?? "") : ""); setNumErr(null);
  }, [seleccion]); // eslint-disable-line react-hooks/exhaustive-deps
  const cambiarPieza = (id: string, nuevo: string) => {
    if (!/^[1-4][1-8]$/.test(nuevo)) { setNumErr("Número FDI no válido (11-18, 21-28, 31-38, 41-48)"); return; }
    if (patrones.some((x) => x.categoria === "pieza" && x.id !== id && x.pieza === nuevo)) { setNumErr(`Ya existe la pieza ${nuevo}`); return; }
    setPatrones((prev) => prev.map((x) => (x.id === id ? { ...x, pieza: nuevo, origen: "doctor" } : x)));
    setNumErr(null);
  };
  const eliminar = (id: string) => { setPatrones((p) => p.filter((x) => x.id !== id)); setPlan((pl) => pl.filter((l) => l.patron_id !== id)); setSeleccion(null); };
  // Un clic enciende/apaga la capa de la categoría (chip de color = visible); al encenderla queda como la que se dibuja.
  const alternar = (k: string) => {
    const encender = !visibles.has(k);
    setVisibles((v) => { const n = new Set(v); if (n.has(k)) n.delete(k); else n.add(k); return n; });
    if (encender) setCatActiva(k);
  };

  // ── navegación ──
  const seguir = () => {
    if (paso === 3) { setFinPlan(true); return; }
    setPaso((p) => Math.min(4, p + 1));
  };
  const crearPresupuesto = async () => {
    if (!plan.length) return;
    setCreando(true); setError(null);
    try {
      const r = await patientService.crearPresupuesto(patientId, {
        titulo: "Presupuesto DentIA", fecha: new Date().toISOString().slice(0, 10),
        lineas: plan.map((l) => ({ tratamiento_id: l.tratamiento_id, pieza: l.pieza ?? null, precio: l.precio,
          cantidad: l.cantidad, descuento: l.descuento, descuento_pct: l.descuento_pct })),
      });
      setPresupNum(r.num); setFinPlan(false); setPaso(4);
    } catch (e) { setError(e instanceof Error ? e.message : "No se pudo crear el presupuesto"); }
    finally { setCreando(false); }
  };

  // ── capa SVG (patrones) ──
  const capa = (opts: { clicable: boolean; soloPlan?: boolean }) => {
    if (!dim) return null;
    const sw = Math.max(2, dim.w / 700), fs = Math.max(14, dim.w / 85);
    return (
      <svg viewBox={`0 0 ${dim.w} ${dim.h}`} preserveAspectRatio="xMidYMid meet"
        className={`absolute inset-0 w-full h-full ${sinSeleccion ? "cursor-crosshair" : ""}`} onClick={clicEnImagen}>
        {/* En el paso 1 la propuesta de la IA se VE sobre la imagen (vista previa) antes de aceptarla; no se guarda hasta aceptar. */}
        {(paso === 1 && propuesta ? propuesta : patrones).filter((p) => (opts.soloPlan ? PLANIFICABLES.has(p.categoria) : visibles.has(p.categoria) || p.categoria === "pieza")).map((p) => {
          const c = CATEGORIAS[p.categoria];
          const pts = p.puntos.map((q) => q.join(",")).join(" ");
          if (p.categoria === "pieza") {
            if (p.pieza && piezasImplante.has(p.pieza)) return null;
            const xs = p.puntos.map((q) => q[0]), ys = p.puntos.map((q) => q[1]);
            return (
              <g key={p.id}>
                {opts.clicable && !sinSeleccion && !opts.soloPlan && (
                  <rect x={Math.min(...xs)} y={Math.min(...ys)} width={Math.max(...xs) - Math.min(...xs)}
                    height={Math.max(...ys) - Math.min(...ys)} fill="transparent"
                    stroke={seleccion === p.id ? "#21A2E5" : "none"} strokeWidth={sw * 2}
                    style={{ cursor: "pointer", pointerEvents: "all" }}
                    onClick={(e) => { e.stopPropagation(); setSeleccion(p.id); }} />
                )}
                {verCuadros && <rect x={Math.min(...xs)} y={Math.min(...ys)} width={Math.max(...xs) - Math.min(...xs)}
                  height={Math.max(...ys) - Math.min(...ys)} fill="none" stroke="#21A2E5" strokeWidth={sw} />}
                {verPiezas && <text x={(Math.min(...xs) + Math.max(...xs)) / 2} y={(Math.min(...ys) + Math.max(...ys)) / 2}
                  pointerEvents="none" textAnchor="middle" dominantBaseline="middle" fontSize={fs} fontWeight={700} fill="#fff"
                  stroke="#0b1020" strokeWidth={sw} paintOrder="stroke">{p.pieza}</text>}
              </g>
            );
          }
          if (!c) return null;
          const sel = seleccion === p.id;
          const marcaPlan = opts.soloPlan;
          const baja = esBaja(p);
          const guion = baja ? `${sw * 4} ${sw * 3}` : undefined;
          const [cx, cy] = [p.puntos.reduce((s, q) => s + q[0], 0) / p.puntos.length, p.puntos.reduce((s, q) => s + q[1], 0) / p.puntos.length];
          const conPlan = plan.some((l) => l.patron_id === p.id);
          return (
            <g key={p.id} style={{ cursor: opts.clicable ? "pointer" : undefined, pointerEvents: opts.clicable && !sinSeleccion ? "auto" : "none" }}
              onClick={(e) => { if (!opts.clicable || sinSeleccion) return; e.stopPropagation(); marcaPlan ? setHallazgo(p) : setSeleccion(p.id); }}>
              {c.tipo === "linea"
                ? <polyline points={pts} fill="none" stroke={c.color} strokeWidth={sw * (sel ? 2.2 : 1.6)} strokeDasharray={guion} />
                : <polygon points={pts} fill={c.color} fillOpacity={marcaPlan ? 0.18 : baja ? 0.2 : 0.5} stroke={c.color} strokeWidth={sw * (sel ? 2.2 : 1.4)} strokeDasharray={guion} />}
              {baja && !marcaPlan && verEtiquetas && (paso === 1 && propuesta ? propuesta : patrones).find((x) => esBaja(x) && x.categoria === p.categoria && x.confianza === p.confianza)?.id === p.id && <text x={cx} y={cy} textAnchor="middle" dominantBaseline="middle" fontSize={fs * 0.75} fontWeight={700} fill="#fff"
                stroke="#0b1020" strokeWidth={sw} paintOrder="stroke" pointerEvents="none">{c.nombre} · baja confianza {Math.round((p.confianza ?? 0) * 100)} %</text>}
              {marcaPlan && (
                <g>
                  <circle cx={cx} cy={cy} r={fs * 0.65} fill={conPlan ? "#20BEAB" : "#21A2E5"} stroke="#fff" strokeWidth={sw} />
                  {verEtiquetas && <text x={cx + fs} y={cy - fs * 0.6} fontSize={fs * 0.9} fontWeight={700} fill="#fff" stroke="#0b1020"
                    strokeWidth={sw} paintOrder="stroke">{p.pieza ? `#${p.pieza} ` : ""}{c.nombre}</text>}
                </g>
              )}
              {!marcaPlan && verEtiquetas && p.pieza && <text x={cx} y={cy} textAnchor="middle" fontSize={fs * 0.9} fontWeight={700} fill="#fff"
                stroke="#0b1020" strokeWidth={sw} paintOrder="stroke">{p.pieza}</text>}
            </g>
          );
        })}
        {opts.clicable && !sinSeleccion && !opts.soloPlan && (() => {
          const sp = patrones.find((x) => x.id === seleccion && x.categoria !== "pieza");
          const cs = sp && CATEGORIAS[sp.categoria];
          if (!sp || !cs) return null;
          const n = sp.puntos.length, cerrado = cs.tipo !== "linea";
          const tramos = cerrado ? n : n - 1;
          return (
            <g>
              {Array.from({ length: tramos }, (_, i) => {
                const a = sp.puntos[i], b = sp.puntos[(i + 1) % n];
                const mx = Math.round((a[0] + b[0]) / 2), my = Math.round((a[1] + b[1]) / 2);
                return (
                  <circle key={`m${i}`} cx={mx} cy={my} r={sw * 2} fill="#fff" fillOpacity={0.55} stroke={cs.color} strokeWidth={sw}
                    style={{ cursor: "copy", pointerEvents: "all", touchAction: "none" }}
                    onPointerDown={(e) => {
                      e.stopPropagation(); e.preventDefault();
                      const svg = e.currentTarget.ownerSVGElement; if (!svg) return;
                      editarPatron(sp.id, (pts) => [...pts.slice(0, i + 1), [mx, my], ...pts.slice(i + 1)]);
                      iniciarArrastre(sp.id, i + 1, svg);
                    }}>
                    <title>Arrastra para añadir un punto</title>
                  </circle>
                );
              })}
              {sp.puntos.map((q, i) => (
                <circle key={`v${i}`} cx={q[0]} cy={q[1]} r={sw * 3.2} fill="#fff" stroke={cs.color} strokeWidth={sw * 1.2}
                  style={{ cursor: "grab", pointerEvents: "all", touchAction: "none" }}
                  onPointerDown={(e) => { e.stopPropagation(); e.preventDefault(); const svg = e.currentTarget.ownerSVGElement; if (svg) iniciarArrastre(sp.id, i, svg); }}
                  onDoubleClick={(e) => { e.stopPropagation(); quitarVertice(sp.id, i); }}>
                  <title>Arrastra para mover · doble clic para quitar</title>
                </circle>
              ))}
            </g>
          );
        })()}
        {cajaTmp.length > 0 && (
          <g pointerEvents="none">
            {cajaTmp.length === 2 && <rect x={Math.min(cajaTmp[0][0], cajaTmp[1][0])} y={Math.min(cajaTmp[0][1], cajaTmp[1][1])}
              width={Math.abs(cajaTmp[0][0] - cajaTmp[1][0])} height={Math.abs(cajaTmp[0][1] - cajaTmp[1][1])}
              fill="#21A2E5" fillOpacity={0.18} stroke="#21A2E5" strokeWidth={sw * 1.4} strokeDasharray={`${sw * 3} ${sw * 2}`} />}
            {cajaTmp.map((q, i) => <circle key={i} cx={q[0]} cy={q[1]} r={sw * 2} fill="#21A2E5" stroke="#fff" strokeWidth={sw / 2} />)}
          </g>
        )}
        {tmp.length > 0 && cat && (
          <g pointerEvents="none">
            <polyline points={tmp.map((q) => q.join(",")).join(" ")} fill="none" stroke={cat.color} strokeWidth={sw * 1.4} strokeDasharray={`${sw * 3} ${sw * 2}`} />
            {tmp.map((q, i) => <circle key={i} cx={q[0]} cy={q[1]} r={sw * 2} fill={cat.color} stroke="#fff" strokeWidth={sw / 2} />)}
          </g>
        )}
      </svg>
    );
  };

  const escena = (opts: { clicable: boolean; soloPlan?: boolean; fijo?: boolean }) => (
    <div className="relative" style={opts.fijo ? { width: "100%" } : { width: `${aj.zoom * 100}%`, height: `${aj.zoom * 100}%` }}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={src} alt="Radiografía" draggable={false} style={{ filter: filtro }}
        className={`block w-full select-none ${opts.fijo ? "h-auto" : "h-full object-contain"}`}
        onLoad={(e) => setDim({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })} />
      {capa(opts)}
    </div>
  );

  if (cargando) return <div className="p-10 text-slate-500 flex items-center gap-2"><Loader2 className="w-5 h-5 animate-spin" /> Cargando análisis…</div>;
  if (error && !listo.current) return <div className="p-10 text-fuchsia-700">{error}</div>;

  const chip = (k: string) => {
    const c = CATEGORIAS[k]; const n = cuenta[k] ?? 0; const on = visibles.has(k);
    return (
      <button key={k} type="button" onClick={() => alternar(k)} title={(c.ia ? "La IA puede proponerlo. " : "Marcado manual por el doctor. ") + "Clic: mostrar/ocultar en la imagen"}
        style={on && n > 0 ? { background: c.color, color: "#fff", borderColor: c.color } : catActiva === k ? { borderColor: c.color, color: c.color } : undefined}
        className={`flex items-center justify-between gap-2 h-6 px-2 rounded text-[11px] font-semibold border transition-colors ${on && n > 0 ? "" : "bg-slate-100 text-slate-500 border-slate-200 hover:bg-slate-200"}`}>
        <span className="truncate">{c.nombre}</span>
        {n > 0 && <span className="min-w-4 h-4 px-1 rounded-full bg-white text-[10px] leading-4 text-slate-700 text-center">{n}</span>}
      </button>
    );
  };

  return (
    <div className="flex flex-col h-[calc(100vh-126px)] overflow-hidden bg-sky-50/40">
      <style>{`@media print{body *{visibility:hidden}#dentia-informe,#dentia-informe *{visibility:visible}#dentia-informe{position:absolute;left:0;top:0;width:100%;background:#fff}}`}</style>

      {/* cabecera + pasos */}
      <div className="flex items-center gap-4 px-4 py-2 bg-white border-b border-sky-100 print:hidden">
        {/* Volver a donde estabas (la ficha con Multimedia); si se abrió en una pestaña nueva, a la ficha del paciente. */}
        <button type="button" title="Volver a Multimedia"
          onClick={() => { if (typeof window !== "undefined" && window.history.length > 1) router.back(); else router.push(`/pacientes/${patientId}/ficha`); }}
          className="shrink-0 h-10 px-3 rounded-md bg-[#21A2E5] hover:bg-[#065AED] text-white flex items-center gap-2 text-[13px] font-semibold">
          <ArrowLeft className="w-4 h-4" /> Volver
        </button>
        <div className="min-w-0">
          <div className="text-[15px] font-semibold text-slate-800 truncate">{nombre || "Paciente"}</div>
          <div className="text-[11px] text-slate-500">{cab?.edad != null ? `${cab.edad} años · ` : ""}Historial: {cab?.num_historia ?? "—"}{cab?.tarifa ? ` · Tarifa: ${cab.tarifa}` : ""}</div>
        </div>
        <div className="flex gap-2 ml-4">
          {PASOS.map(([n, i]) => (
            <button key={n} type="button" onClick={() => i <= paso || i === paso + 1 ? setPaso(i) : undefined}
              className={`w-[88px] h-10 rounded-md text-left px-2 border ${paso === i ? "bg-sky-600 border-sky-600 text-white" : i < paso ? "bg-sky-100 border-sky-200 text-sky-700" : "bg-white border-slate-200 text-slate-500"}`}>
              <div className="text-[9.5px] leading-3 opacity-80">Paso {i}</div><div className="text-[12px] leading-4 font-semibold">{n}</div>
            </button>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-2">
          <span className="text-[11px] text-slate-400" aria-live="polite">
            {guardado === "guardando" ? "Guardando…" : guardado === "ok" ? "Guardado" : guardado === "error" ? "No se pudo guardar" : ""}
          </span>
          <select value={fileId} onChange={(e) => router.push(`/pacientes/${patientId}/dentia?f=${encodeURIComponent(e.target.value)}`)}
            className="h-8 rounded-md border border-sky-200 bg-white px-2 text-[12px] text-sky-700 font-semibold max-w-[220px]" aria-label="Multimedia">
            {radios.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
            {!radios.some((r) => r.id === fileId) && <option value={fileId}>Imagen actual</option>}
          </select>
          {paso < 4 && (
            <button type="button" onClick={seguir} className="h-8 px-4 rounded-md bg-teal-600 hover:bg-teal-700 text-white text-[12px] font-semibold flex items-center gap-1.5">
              {paso === 3 ? "Confirmar este plan" : "Confirmar y seguir"} <ChevronRight className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>
      {error && <div className="px-4 py-1.5 text-[12px] bg-fuchsia-50 text-fuchsia-700 border-b border-fuchsia-200">{error}</div>}

      {/* PASO 1 — Procesar */}
      {paso === 1 && (
        <div className="flex-1 min-h-0 grid grid-cols-[1fr_380px] gap-4 p-4 print:hidden">
          <div className="rounded-md bg-black overflow-auto relative min-h-0">{escena({ clicable: false })}</div>
          <div className="rounded-md bg-white border border-sky-100 p-4 text-[13px] text-slate-700">
            <div className="text-[15px] font-semibold text-sky-700 mb-1">Procesar radiografía</div>
            <p className="text-slate-500 text-[12px] mb-3">La IA propone numeración de piezas, dientes incluidos, canal dentario inferior y seno maxilar. Son sugerencias: tú decides qué se acepta. El resto de patrones los marcas tú en el paso 2.</p>
            <button type="button" onClick={detectar} disabled={iaCargando}
              className="h-9 px-4 rounded-md bg-sky-600 hover:bg-sky-700 disabled:opacity-60 text-white text-[12.5px] font-semibold flex items-center gap-2">
              {iaCargando ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />} {iaCargando ? "Analizando…" : "Analizar con IA"}
            </button>
            {iaMsg && <p className="mt-3 text-[12px] text-violet-700 bg-violet-50 border border-violet-200 rounded p-2">{iaMsg}</p>}
            {propuesta && (
              <div className="mt-3 border border-sky-200 rounded-md p-3 bg-sky-50">
                <div className="font-semibold text-[12.5px] mb-1">Propuesta de la IA</div>
                <p className="text-[11.5px] text-slate-500 mb-1.5">Se ve sobre la imagen. No se guarda hasta que pulses «Aceptar y seguir»; luego podrás cambiar o quitar cada número.</p>
                <ul className="text-[12px] text-slate-600 mb-2">
                  <li>{propuesta.filter((p) => p.categoria === "pieza").length} piezas numeradas (FDI)</li>
                  {["incluido_impactado", "nervios_mandibulares", "senos_maxilares"].map((k) => (
                    <li key={k}>{propuesta.filter((p) => p.categoria === k).length} · {CATEGORIAS[k].nombre}</li>
                  ))}
                </ul>
                {propuesta.filter((p) => p.categoria === "senos_maxilares").length === 0 && (
                  <p className="text-[11.5px] text-fuchsia-800 bg-fuchsia-50 border border-fuchsia-200 rounded p-2 mb-2">
                    La IA no ha detectado los senos maxilares en esta imagen. Márcalos tú en el paso 2: elige «Senos maxilares» y pulsa «Nuevo patrón».
                  </p>
                )}
                {propuesta.some(esBaja) && (
                  <p className="text-[11.5px] text-sky-800 bg-sky-50 border border-sky-200 rounded p-2 mb-2">
                    Hay estructuras detectadas con baja confianza: se ven con línea discontinua. Revísalas y pulsa «Confirmar», o ajústalas, antes de fiarte.
                  </p>
                )}
                <p className="text-[11.5px] text-slate-600 mb-2">La IA no numera todas las piezas. Si falta alguna, añádela en el paso 2 con «Añadir pieza».</p>
                <p className="text-[11.5px] text-amber-700 bg-amber-50 border border-amber-200 rounded p-2 mb-2">
                  La IA no distingue implantes de dientes: puede numerar un implante como pieza o ignorarlo. Revisa las zonas con metal brillante y márcalas como «Implante» con su número de pieza.
                </p>
                <div className="flex gap-2">
                  <button type="button" onClick={aceptarPropuesta} className="h-8 px-3 rounded-md bg-teal-600 hover:bg-teal-700 text-white text-[12px] font-semibold flex items-center gap-1.5"><Check className="w-3.5 h-3.5" /> Aceptar y seguir</button>
                  <button type="button" onClick={() => setPropuesta(null)} className="h-8 px-3 rounded-md border border-slate-200 text-slate-600 text-[12px]">Descartar</button>
                </div>
              </div>
            )}
            <button type="button" onClick={() => setPaso(2)} className="mt-4 text-[12px] text-sky-700 underline">Seguir sin IA</button>
            <p className="mt-4 text-[11px] text-slate-400">Sugerencia automática: requiere validación del doctor.</p>
          </div>
        </div>
      )}

      {/* PASOS 2 y 3 — visor con herramientas */}
      {(paso === 2 || paso === 3) && (
        <>
          <div className={`flex px-4 pt-3 gap-0 print:hidden min-h-0 ${paso === 3 ? "h-[50%]" : "flex-1"}`}>
            <div className="flex flex-col gap-1.5 bg-slate-900 rounded-l-md p-1.5 relative z-10">
              {([["brillo", Sun, "Brillo"], ["contraste", Contrast, "Contraste"]] as const).map(([k, Icono, t]) => (
                <button key={k} type="button" title={t} aria-label={t} onClick={() => setPanel((p) => (p === k ? null : k))}
                  className={`w-8 h-8 rounded grid place-items-center ${panel === k ? "bg-sky-600 text-white" : "bg-slate-800 text-sky-300 hover:bg-slate-700"}`}><Icono className="w-4 h-4" /></button>
              ))}
              <button type="button" title="Invertir" aria-label="Invertir" onClick={() => setAj((a) => ({ ...a, invertir: !a.invertir }))}
                className={`w-8 h-8 rounded grid place-items-center ${aj.invertir ? "bg-sky-600 text-white" : "bg-slate-800 text-sky-300 hover:bg-slate-700"}`}><Moon className="w-4 h-4" /></button>
              <button type="button" title="Restablecer" aria-label="Restablecer" onClick={() => setAj({ brillo: 100, contraste: 100, invertir: false, zoom: 1 })}
                className="w-8 h-8 rounded grid place-items-center bg-slate-800 text-sky-300 hover:bg-slate-700"><Crosshair className="w-4 h-4" /></button>
              <button type="button" title="Acercar" aria-label="Acercar" onClick={() => setAj((a) => ({ ...a, zoom: Math.min(4, +(a.zoom + 0.25).toFixed(2)) }))}
                className="w-8 h-8 rounded grid place-items-center bg-slate-800 text-sky-300 hover:bg-slate-700"><ZoomIn className="w-4 h-4" /></button>
              <button type="button" title="Alejar" aria-label="Alejar" onClick={() => setAj((a) => ({ ...a, zoom: Math.max(1, +(a.zoom - 0.25).toFixed(2)) }))}
                className="w-8 h-8 rounded grid place-items-center bg-slate-800 text-sky-300 hover:bg-slate-700"><ZoomOut className="w-4 h-4" /></button>
              {panel && (
                <div className="absolute left-11 top-1 w-44 rounded-md bg-slate-900 border border-slate-700 p-2 text-[11px] text-slate-200">
                  {panel === "brillo"
                    ? <label>Brillo {aj.brillo}%<input type="range" min={40} max={200} value={aj.brillo} onChange={(e) => setAj((a) => ({ ...a, brillo: +e.target.value }))} className="w-full" /></label>
                    : <label>Contraste {aj.contraste}%<input type="range" min={40} max={250} value={aj.contraste} onChange={(e) => setAj((a) => ({ ...a, contraste: +e.target.value }))} className="w-full" /></label>}
                </div>
              )}
            </div>
            <div className="flex-1 bg-black rounded-r-md overflow-auto relative" style={{ backgroundImage: "linear-gradient(#0f172a 1px,transparent 1px),linear-gradient(90deg,#0f172a 1px,transparent 1px)", backgroundSize: "16px 16px" }}>
              <div className="w-full h-full">{escena({ clicable: true, soloPlan: paso === 3 })}</div>
            </div>
            {paso === 3 && <div className="w-0" />}
          </div>

          {paso === 2 && (
            <div className="px-4 py-2 bg-white border-t border-sky-100 print:hidden">
              <div className="flex items-center gap-3 mb-2 text-[11.5px] text-slate-600 flex-wrap">
                <label className="flex items-center gap-1.5"><input type="checkbox" checked={verPiezas} onChange={(e) => setVerPiezas(e.target.checked)} /> Piezas</label>
                <label className="flex items-center gap-1.5"><input type="checkbox" checked={verCuadros} onChange={(e) => setVerCuadros(e.target.checked)} /> Cuadros</label>
                <label className="flex items-center gap-1.5"><input type="checkbox" checked={verEtiquetas} onChange={(e) => setVerEtiquetas(e.target.checked)} /> Etiquetas</label>
                <span className="mx-2 h-4 w-px bg-slate-200" />
                {!dibujando && !modoPieza && (
                  <button type="button" onClick={() => { setModoPieza(true); setCajaTmp([]); setNumNuevo(""); setErrNuevo(null); setSeleccion(null); }}
                    title="Marca a mano un diente que la IA no ha numerado" className="h-7 px-3 rounded border border-sky-300 text-sky-700 font-semibold">Añadir pieza</button>
                )}
                {modoPieza && (
                  <>
                    <span className="text-sky-700 font-semibold">{cajaTmp.length < 2 ? `Haz clic en la esquina ${cajaTmp.length === 0 ? "superior izquierda" : "inferior derecha"} del diente` : "Escribe el número FDI"}</span>
                    <input value={numNuevo} onChange={(e) => { setNumNuevo(e.target.value.replace(/\D/g, "").slice(0, 2)); setErrNuevo(null); }}
                      onKeyDown={(e) => { if (e.key === "Enter") anadirPieza(); }} placeholder="FDI" aria-label="Número FDI de la nueva pieza"
                      disabled={cajaTmp.length < 2} className="h-7 w-16 rounded border border-slate-300 px-2 text-center disabled:opacity-40" />
                    <button type="button" onClick={() => setCajaTmp((c) => c.slice(0, -1))} disabled={!cajaTmp.length}
                      className="h-7 px-2 rounded border border-slate-200 disabled:opacity-40 flex items-center gap-1"><Undo2 className="w-3.5 h-3.5" /> Deshacer</button>
                    <button type="button" onClick={anadirPieza} disabled={cajaTmp.length < 2 || !numNuevo} className="h-7 px-3 rounded bg-teal-600 text-white font-semibold disabled:opacity-40">Añadir</button>
                    <button type="button" onClick={cancelarPieza} className="h-7 px-2 rounded border border-slate-200 flex items-center gap-1"><X className="w-3.5 h-3.5" /> Cancelar</button>
                    {errNuevo && <span className="text-fuchsia-700">{errNuevo}</span>}
                  </>
                )}
                {modoPieza
                  ? null
                  : !dibujando
                  ? <button type="button" onClick={() => { setDibujando(true); setTmp([]); setSeleccion(null); }} className="h-7 px-3 rounded border border-sky-300 text-sky-700 font-semibold">Nuevo patrón ({CATEGORIAS[catActiva]?.nombre})</button>
                  : (
                    <>
                      <input value={piezaTmp} onChange={(e) => setPiezaTmp(e.target.value.slice(0, 10))} placeholder="Pieza (FDI)" aria-label="Pieza" className="h-7 w-24 rounded border border-slate-200 px-2" />
                      <button type="button" onClick={() => setTmp((t) => t.slice(0, -1))} disabled={!tmp.length} className="h-7 px-2 rounded border border-slate-200 disabled:opacity-40 flex items-center gap-1"><Undo2 className="w-3.5 h-3.5" /> Deshacer punto</button>
                      <button type="button" onClick={consolidar} disabled={tmp.length < minPuntos} className="h-7 px-3 rounded bg-teal-600 text-white font-semibold disabled:opacity-40">Consolidar patrón</button>
                      <button type="button" onClick={() => { setDibujando(false); setTmp([]); }} className="h-7 px-2 rounded border border-slate-200 flex items-center gap-1"><X className="w-3.5 h-3.5" /> Cancelar</button>
                      <span className="text-slate-400">{tmp.length} puntos (mín. {minPuntos})</span>
                    </>
                  )}
                {seleccion && !dibujando && !modoPieza && (() => {
                  const p = patrones.find((x) => x.id === seleccion);
                  if (p?.categoria === "pieza") return (
                    <span className="ml-auto flex items-center gap-2">
                      <span className="font-semibold text-sky-700">Pieza {p.pieza}{p.origen === "ia" ? " · IA" : ""}</span>
                      <input value={numEdit} onChange={(e) => setNumEdit(e.target.value.replace(/\D/g, "").slice(0, 2))}
                        aria-label="Nuevo número FDI" className="w-14 h-7 rounded border border-slate-300 px-1 text-center" />
                      <button type="button" onClick={() => cambiarPieza(p.id, numEdit)} disabled={!numEdit || numEdit === p.pieza}
                        className="h-7 px-2 rounded bg-sky-600 text-white disabled:opacity-40">Cambiar número</button>
                      <button type="button" onClick={() => eliminar(p.id)} className="h-7 px-2 rounded border border-fuchsia-300 text-fuchsia-700">Quitar pieza</button>
                      {numErr && <span className="text-fuchsia-700">{numErr}</span>}
                    </span>
                  );
                  return p ? (
                    <span className="ml-auto flex items-center gap-2">
                      <span className="font-semibold" style={{ color: CATEGORIAS[p.categoria]?.color }}>{CATEGORIAS[p.categoria]?.nombre}{p.pieza ? ` · ${p.pieza}` : ""}{p.origen === "ia" ? " · IA" : ""}</span>
                      {esBaja(p) && (
                        <>
                          <span className="text-amber-700 font-semibold">Baja confianza ({Math.round((p.confianza ?? 0) * 100)} %): revísalo</span>
                          <button type="button" onClick={() => editarPatron(p.id, (pts) => pts)} title="Dar por bueno este contorno (pasa a línea continua)"
                            className="h-7 px-2 rounded bg-teal-600 text-white font-semibold">Confirmar</button>
                        </>
                      )}
                      <span className="text-slate-500">Arrastra los puntos para ajustar · arrastra un punto pequeño para añadir otro · doble clic en un punto para quitarlo</span>
                      <button type="button" onClick={() => eliminar(p.id)} className="h-7 px-2 rounded border border-fuchsia-300 text-fuchsia-700">Eliminar patrón</button>
                    </span>
                  ) : null;
                })()}
              </div>
              <div className="grid grid-cols-[130px_repeat(5,1fr)] gap-2">
                <div className="flex flex-col gap-1">
                  <div className="h-6 px-2 rounded text-[11px] font-semibold bg-slate-100 border border-slate-200 text-slate-600 flex justify-between"><span>Todos</span><span>{lesiones.length}</span></div>
                  <div className="h-6 px-2 rounded text-[11px] font-semibold bg-slate-100 border border-slate-200 text-slate-600 flex justify-between" title="Piezas numeradas por la IA sin hallazgo"><span>Sanos</span><span>{sanos}</span></div>
                  <div className="h-6 px-2 rounded text-[11px] font-semibold bg-slate-50 border border-dashed border-slate-300 text-slate-400" title="Requiere un modelo de segmentación que aún no está disponible">Partes del diente</div>
                </div>
                {GRUPOS.map((g, i) => <div key={i} className="flex flex-col gap-1">{g.map(chip)}</div>)}
              </div>
              <p className="mt-1.5 text-[10.5px] text-slate-400">Etiqueta con «IA» solo en senos, nervios mandibulares y dientes incluidos; el resto lo marca el doctor con «Nuevo patrón». Sugerencia automática: requiere validación del doctor.</p>
            </div>
          )}

          {paso === 3 && (
            <div className="bg-sky-50 print:hidden flex-1 min-h-0 overflow-auto">
              <div className="px-4 pt-2 text-[12px] text-sky-700">Por favor, haz clic en el hallazgo para seleccionar el tratamiento a realizar</div>
              <TablaPlan patientId={patientId} plan={plan} tarifa={cab?.tarifa ?? ""} onChange={setPlan} />
            </div>
          )}
        </>
      )}

      {/* PASO 4 — Informe */}
      {paso === 4 && (
        <div className="p-4 flex-1 min-h-0 overflow-auto">
          <div className="flex items-center gap-3 mb-3 print:hidden">
            {presupNum != null && <span className="text-[12.5px] text-teal-700 bg-teal-50 border border-teal-200 rounded px-3 py-1.5">Presupuesto nº {presupNum} creado en la ficha del paciente</span>}
            <button type="button" onClick={() => window.print()} className="h-8 px-3 rounded-md bg-sky-600 hover:bg-sky-700 text-white text-[12px] font-semibold flex items-center gap-1.5"><Printer className="w-4 h-4" /> Imprimir / guardar PDF</button>
            <button type="button" onClick={() => router.push(`/pacientes/${patientId}`)} className="h-8 px-3 rounded-md border border-slate-200 bg-white text-[12px] text-slate-600">Volver a la ficha</button>
          </div>
          <div id="dentia-informe" className="bg-white rounded-md border border-sky-100 p-6 max-w-[1100px] mx-auto">
            <div className="flex justify-between items-baseline border-b border-slate-200 pb-2 mb-3">
              <div><div className="text-[18px] font-semibold text-slate-800">Informe DentIA</div><div className="text-[12px] text-slate-500">{nombre} · Historial {cab?.num_historia ?? "—"}</div></div>
              <div className="text-[12px] text-slate-500">{new Date().toLocaleDateString("es-ES")}</div>
            </div>
            <div className="bg-black rounded relative">{escena({ clicable: false, fijo: true })}</div>
            <h3 className="mt-4 mb-1 text-[13px] font-semibold text-slate-700">Hallazgos</h3>
            <ul className="text-[12px] text-slate-700 columns-2 gap-6">
              {lesiones.length === 0 && <li className="text-slate-400">Sin hallazgos marcados</li>}
              {lesiones.map((p) => (
                <li key={p.id} className="break-inside-avoid"><span className="inline-block w-2.5 h-2.5 rounded-sm mr-1.5 align-middle" style={{ background: CATEGORIAS[p.categoria]?.color }} />
                  {CATEGORIAS[p.categoria]?.nombre}{p.pieza ? ` · pieza ${p.pieza}` : ""}{p.origen === "ia" ? " (sugerido por IA)" : ""}</li>
              ))}
            </ul>
            <h3 className="mt-4 mb-1 text-[13px] font-semibold text-slate-700">Plan de tratamiento</h3>
            <table className="w-full text-[12px]"><tbody>
              {plan.length === 0 && <tr><td className="text-slate-400">Sin plan</td></tr>}
              {plan.map((l, i) => (
                <tr key={i} className="border-b border-slate-100"><td className="py-1">{l.tratamiento}{l.pieza ? ` · pieza ${l.pieza}` : ""}{l.cantidad > 1 ? ` × ${l.cantidad}` : ""}</td><td className="py-1 text-right">{eur(importeLinea(l))}</td></tr>
              ))}
              {plan.length > 0 && <tr className="font-semibold"><td className="py-1.5 text-right">Total</td><td className="py-1.5 text-right">{eur(total)}</td></tr>}
            </tbody></table>
            <p className="mt-4 text-[10.5px] text-slate-400">Análisis asistido por IA: son sugerencias que requieren validación del doctor.</p>
          </div>
        </div>
      )}

      {/* modales */}
      {hallazgo && <ModalHallazgo patientId={patientId} patron={hallazgo} onAdd={(l) => setPlan((p) => [...p, l])} onClose={() => setHallazgo(null)} />}
      {finPlan && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 flex items-start justify-center pt-28" onClick={() => setFinPlan(false)}>
          <div className="w-[460px] max-w-[94vw] rounded-lg bg-white shadow-2xl p-6 text-center" onClick={(e) => e.stopPropagation()}>
            <div className="mx-auto w-12 h-12 rounded-full bg-sky-100 text-sky-600 grid place-items-center mb-3"><Check className="w-6 h-6" /></div>
            <div className="text-[13.5px] text-slate-700 mb-1">El análisis ha finalizado. Seleccione cómo desea continuar.</div>
            <div className="text-[12px] text-slate-500 mb-4">{plan.length} {plan.length === 1 ? "acto" : "actos"} · {eur(total)}</div>
            <div className="flex justify-center gap-2">
              <button type="button" onClick={() => router.push(`/pacientes/${patientId}`)} className="h-8 px-3 rounded-md bg-fuchsia-600 hover:bg-fuchsia-700 text-white text-[12px] font-semibold flex items-center gap-1"><X className="w-3.5 h-3.5" /> Salir</button>
              <button type="button" onClick={crearPresupuesto} disabled={!plan.length || creando}
                className="h-8 px-3 rounded-md bg-sky-100 text-sky-800 border border-sky-200 text-[12px] font-semibold disabled:opacity-50 flex items-center gap-1">{creando && <Loader2 className="w-3.5 h-3.5 animate-spin" />} Crear presupuesto + informe</button>
              <button type="button" onClick={() => { setFinPlan(false); setPaso(4); }} className="h-8 px-3 rounded-md bg-teal-600 hover:bg-teal-700 text-white text-[12px] font-semibold">Crear informe</button>
            </div>
            {error && <p className="mt-3 text-[12px] text-fuchsia-700">{error}</p>}
          </div>
        </div>
      )}
    </div>
  );
}
