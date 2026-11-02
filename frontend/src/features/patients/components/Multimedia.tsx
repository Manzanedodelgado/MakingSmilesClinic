"use client";
//
/**
 * MULTIMEDIA — imágenes clínicas (izq, carrusel) y panorámicas (der, carrusel) del paciente.
 * El centro muestra la seleccionada, con emergente a pantalla completa. Origen: la carpeta de
 * Google Drive del paciente, servida por el proxy autenticado del backend (nunca Drive/tokens).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Loader2, Maximize2, X, ChevronLeft, ChevronRight, ChevronUp, ChevronDown, Camera, ScanLine, ImageOff, MonitorUp, Sparkles, Hash, Layers } from "lucide-react";
import { api, API_BASE } from "@/shared/lib/api";
import { MODAL_CLOSE } from "@/shared/components";
import { patientService } from "../services/patientService";
import type { IaAnalisis, MultimediaData, MultimediaItem } from "../types/patient";

const IA_COLOR: Record<string, string> = {
  impactado: "#ef4444", canal_dentario_inferior: "#f59e0b", seno_maxilar: "#22c55e",
};
const IA_NOMBRE: Record<string, string> = {
  impactado: "Impactado", canal_dentario_inferior: "Canal dentario inferior", seno_maxilar: "Seno maxilar",
};

const fecha = (s: string | null) => (s ? new Date(s).toLocaleDateString("es-ES") : "");

// Window Management API (Chrome): para lanzar el visor al monitor externo (escritorio extendido).
interface PantallaInfo {
  availLeft: number; availTop: number; availWidth: number; availHeight: number;
  left: number; top: number; width: number; height: number; isPrimary: boolean;
}
type WindowConPantallas = Window & {
  getScreenDetails?: () => Promise<{ screens: PantallaInfo[]; currentScreen: PantallaInfo }>;
};

// ── Carrusel vertical de miniaturas (módulo → identidad estable, no recarga imgs) ──
function Carrusel({
  titulo, icon: Icon, width, aspect, items, patientId, sel, onSel,
}: {
  titulo: string; icon: React.ElementType; width: number; aspect: string;
  items: MultimediaItem[]; patientId: number; sel: MultimediaItem | null; onSel: (it: MultimediaItem) => void;
}) {
  const scRef = useRef<HTMLDivElement>(null);
  const [over, setOver] = useState(false);

  useEffect(() => {
    const el = scRef.current;
    if (!el) return;
    const check = () => setOver(el.scrollHeight > el.clientHeight + 4);
    check();
    const ro = new ResizeObserver(check);
    ro.observe(el);
    return () => ro.disconnect();
  }, [items]);

  // Al cambiar la selección, trae la miniatura activa a la vista (navegación con flechas).
  useEffect(() => {
    if (!sel) return;
    scRef.current?.querySelector<HTMLElement>(`[data-id="${sel.id}"]`)
      ?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [sel]);

  const scroll = (dir: number) => scRef.current?.scrollBy({ top: dir * 160, behavior: "smooth" });

  return (
    <div className="shrink-0 border border-[#e5e7eb] rounded-sm bg-white flex flex-col" style={{ width }}>
      <div className="px-2 py-[5px] text-[12px] bg-white text-[#333] border-b-2 border-[#dee2e6] flex items-center gap-1.5">
        <Icon className="w-3.5 h-3.5" /> {titulo}
        <span className="ml-auto text-[#9aa7c2] font-normal">{items.length}</span>
      </div>
      {items.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-[11px] text-slate-400 italic p-3 text-center">
          Sin {titulo.toLowerCase()}
        </div>
      ) : (
        <div className="relative flex-1 min-h-0">
          {over && (
            <button type="button" onClick={() => scroll(-1)} aria-label="Anterior"
              className="absolute top-0 inset-x-0 z-10 h-5 flex items-center justify-center bg-gradient-to-b from-white via-white/90 to-transparent text-slate-500 hover:text-[#1ca0d1]">
              <ChevronUp className="w-4 h-4" />
            </button>
          )}
          <div ref={scRef} className="h-full overflow-auto px-2 py-2 flex flex-col gap-2 scrollbar-thin">
            {items.map((it) => (
              <button
                key={it.id}
                data-id={it.id}
                type="button"
                onClick={() => onSel(it)}
                title={`${it.name}${it.fecha ? ` · ${fecha(it.fecha)}` : ""}`}
                className={`shrink-0 w-full ${aspect} rounded-sm overflow-hidden border bg-white transition-all ${
                  sel?.id === it.id ? "border-[#1ca0d1] ring-2 ring-[#1ca0d1]/40" : "border-[#e5e7eb] hover:border-[#1ca0d1]"
                }`}
              >
                <img src={patientService.multimediaUrl(patientId, it.id, true)} alt={it.name}
                  loading="lazy" className="w-full h-full object-cover" />
              </button>
            ))}
          </div>
          {over && (
            <button type="button" onClick={() => scroll(1)} aria-label="Siguiente"
              className="absolute bottom-0 inset-x-0 z-10 h-5 flex items-center justify-center bg-gradient-to-t from-white via-white/90 to-transparent text-slate-500 hover:text-[#1ca0d1]">
              <ChevronDown className="w-4 h-4" />
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export function Multimedia({ patientId }: { patientId: number }) {
  const [data, setData] = useState<MultimediaData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sel, setSel] = useState<MultimediaItem | null>(null);
  const [imgLoading, setImgLoading] = useState(false);
  const [full, setFull] = useState(false);   // emergente a pantalla completa
  const [paciente, setPaciente] = useState("");   // nombre y apellidos → abajo-izquierda
  const [icono, setIcono] = useState("");         // icono del centro → abajo-derecha
  // Análisis IA (sugerencias): resultado por id de imagen, para no repetir la llamada al cambiar de imagen.
  const [ia, setIa] = useState<Record<string, IaAnalisis>>({});
  const [iaCargando, setIaCargando] = useState(false);
  const [iaError, setIaError] = useState<string | null>(null);
  // Dos capas independientes: números de pieza y estructuras (nervio, seno, incluidos). Ocultar una no oculta la otra.
  const [iaNum, setIaNum] = useState(true);
  const [iaEstr, setIaEstr] = useState(true);
  const iaVer = iaNum || iaEstr;

  // Rótulos de la emergente: paciente (cabecera) + icono del centro (/auth/me → centro_icono_url).
  useEffect(() => {
    let alive = true;
    patientService.cabecera(patientId)
      .then((c) => { if (alive) setPaciente(`${c.nombre} ${c.apellidos}`.trim()); }).catch(() => {});
    api.get<{ centro_icono_url?: string | null }>("/auth/me")
      .then((m) => { if (alive) setIcono(m.centro_icono_url ? `${API_BASE}${m.centro_icono_url}` : ""); }).catch(() => {});
    return () => { alive = false; };
  }, [patientId]);

  useEffect(() => {
    let alive = true;
    setLoading(true); setError(null); setSel(null); setData(null); setFull(false);
    patientService
      .multimedia(patientId)
      .then((d) => { if (alive) { setData(d); setSel(d.fotos[0] ?? d.radiografias[0] ?? null); } })
      .catch((e) => { if (alive) setError(e instanceof Error ? e.message : "No se pudo cargar"); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [patientId]);

  useEffect(() => { if (sel) setImgLoading(true); setIaError(null); }, [sel]);
  useEffect(() => { setIa({}); }, [patientId]);

  // Grupo (imágenes o panorámicas) al que pertenece la selección → para navegar prev/next.
  const grupo: MultimediaItem[] =
    data?.fotos.some((f) => f.id === sel?.id) ? data.fotos
    : data?.radiografias.some((r) => r.id === sel?.id) ? data!.radiografias
    : [];
  const idx = grupo.findIndex((g) => g.id === sel?.id);
  const esPanoramica = !!sel && !!data?.radiografias.some((r) => r.id === sel.id);
  const iaSel = sel ? ia[sel.id] : undefined;

  const analizar = useCallback(async () => {
    if (!sel || iaCargando) return;
    const id = sel.id;
    setIaCargando(true); setIaError(null);
    try {
      const r = await patientService.analizarIA(patientId, id);
      setIa((m) => ({ ...m, [id]: r })); setIaNum(true); setIaEstr(true);
    } catch (e) {
      setIaError(e instanceof Error ? e.message : "No se pudo analizar la imagen");
    } finally { setIaCargando(false); }
  }, [sel, patientId, iaCargando]);
  const nav = useCallback((d: number) => {
    if (idx < 0 || grupo.length < 2) return;
    setSel(grupo[(idx + d + grupo.length) % grupo.length]);
  }, [idx, grupo]);

  // "Lanzar": abre la imagen/RX seleccionada en un emergente a pantalla completa en el
  // monitor externo (escritorio extendido). Usa la Window Management API si está disponible;
  // si no (o sin 2º monitor / contexto no seguro), abre la ventana en la pantalla actual.
  const lanzar = useCallback(async () => {
    if (!sel) return;
    const src = window.location.origin + patientService.multimediaUrl(patientId, sel.id);
    const url = `/visor?src=${encodeURIComponent(src)}&name=${encodeURIComponent(sel.name)}`
      + `&paciente=${encodeURIComponent(paciente)}&icono=${encodeURIComponent(icono)}`;
    const popup = "menubar=no,toolbar=no,location=no,status=no";
    let feat = `width=1280,height=800,${popup}`;
    let ext: PantallaInfo | undefined;
    try {
      const getScreenDetails = (window as WindowConPantallas).getScreenDetails;
      if (getScreenDetails) {
        const d = await getScreenDetails.call(window);   // pide permiso "gestión de ventanas"
        ext = d.screens.find((s) => !s.isPrimary)
          ?? d.screens.find((s) => s.left !== d.currentScreen.left || s.top !== d.currentScreen.top);
        // dimensiones COMPLETAS de la pantalla externa → la ventana la cubre entera
        if (ext) feat = `left=${ext.left},top=${ext.top},width=${ext.width},height=${ext.height},${popup}`;
      }
    } catch { /* permiso denegado o API no disponible → ventana en la pantalla actual */ }

    const win = window.open(url, `rxviewer-${patientId}`, feat);
    if (!win) return;
    // El opener conserva el gesto del clic: al cargar la ventana, forzamos pantalla completa
    // sobre la pantalla destino (Window Management API). El propio /visor también lo reintenta.
    const opts = ext ? ({ screen: ext } as unknown as FullscreenOptions) : undefined;
    win.addEventListener("load", () => {
      win.focus();
      try { win.document.documentElement.requestFullscreen(opts)?.catch?.(() => {}); } catch { /* lo hará /visor */ }
    });
  }, [sel, patientId, paciente, icono]);

  // Teclado en pantalla completa: ←/→ navega, Esc cierra.
  useEffect(() => {
    if (!full) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setFull(false);
      else if (e.key === "ArrowLeft") nav(-1);
      else if (e.key === "ArrowRight") nav(1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [full, nav]);

  const fullSrc = sel ? patientService.multimediaUrl(patientId, sel.id) : "";

  // Capa SVG del análisis IA: misma en el visor y en la pantalla completa (el contenedor tiene el tamaño de la imagen).
  const capaIA = () => iaSel && (
    <svg viewBox={`0 0 ${iaSel.ancho} ${iaSel.alto}`} preserveAspectRatio="xMidYMid meet"
                  className="absolute inset-0 w-full h-full pointer-events-none">
                  {iaNum && iaSel.dientes.map((d) => (
                    <text key={d.fdi} x={(d.bbox[0] + d.bbox[2]) / 2} y={(d.bbox[1] + d.bbox[3]) / 2}
                      textAnchor="middle" dominantBaseline="middle" fontSize={Math.max(14, iaSel.ancho / 90)}
                      fontWeight={700} fill="#fff" stroke="#0b1020" strokeWidth={Math.max(2, iaSel.ancho / 700)}
                      paintOrder="stroke">{d.fdi}</text>
                  ))}
                  {iaEstr && iaSel.estructuras.map((e, i) => (
                    <g key={i}>
                      {e.contornos.map((c, j) => (
                        <polygon key={j} points={c.map((p) => p.join(",")).join(" ")} fill={IA_COLOR[e.clase]}
                          fillOpacity={e.baja_confianza ? 0.14 : 0.28} stroke={IA_COLOR[e.clase]} strokeWidth={Math.max(2, iaSel.ancho / 800)}
                          strokeDasharray={e.baja_confianza ? `${Math.max(6, iaSel.ancho / 250)} ${Math.max(4, iaSel.ancho / 350)}` : undefined} />
                      ))}
                    </g>
                  ))}
                </svg>
  );


  return (
    <div className="flex h-full min-h-0 gap-3 p-3 overflow-hidden">
      <Carrusel titulo="Imágenes" icon={Camera} width={160} aspect="aspect-square"
        items={data?.fotos ?? []} patientId={patientId} sel={sel} onSel={setSel} />

      {/* Visor central */}
      <div className="flex-1 min-w-0 relative border border-[#e5e7eb] rounded-sm bg-[#0b1020] flex flex-col items-center justify-center text-slate-500 overflow-hidden">
        {loading ? (
          <Loader2 className="w-7 h-7 animate-spin text-slate-500" />
        ) : error ? (
          <div className="text-center px-4">
            <ImageOff className="w-9 h-9 mb-2 mx-auto" strokeWidth={1.25} />
            <p className="text-[12px] text-[#C026D3]">{error}</p>
          </div>
        ) : data && !data.disponible ? (
          <div className="text-center px-4">
            <ImageOff className="w-10 h-10 mb-2 mx-auto" strokeWidth={1.25} />
            <p className="text-[12px]">{data.motivo ?? "Google Drive no configurado"}</p>
          </div>
        ) : sel ? (
          <>
            {imgLoading && <Loader2 className="w-7 h-7 animate-spin text-slate-500 absolute" />}
            <img
              src={fullSrc}
              alt={sel.name}
              onLoad={() => setImgLoading(false)}
              onError={() => setImgLoading(false)}
              onClick={() => setFull(true)}
              className={`object-contain cursor-zoom-in ${iaSel && iaVer ? "w-full h-full" : "max-w-full max-h-full"}`}
            />

            {/* Capa IA: mismo viewBox que la imagen y meet = mismo encaje que object-contain */}
            {iaSel && iaVer && capaIA()}

            {/* Lanzar al monitor externo (escritorio extendido) a pantalla completa */}
            {/* Barra de acciones: si el panel es estrecho los botones saltan de línea (antes se pisaban y DentIA
                quedaba cortado detrás del botón de expandir). right-12 deja libre el botón de pantalla completa. */}
            <div className="absolute top-2 left-2 right-12 z-10 flex flex-wrap items-center gap-1.5">
            <button type="button" onClick={lanzar} title="Lanzar a la otra pantalla a pantalla completa"
              className="h-8 px-2.5 rounded-md bg-black/40 hover:bg-black/60 text-white/90 flex items-center gap-1.5 text-[11px] font-semibold whitespace-nowrap">
              <MonitorUp className="w-4 h-4" /> Lanzar
            </button>

            {/* Análisis IA (solo panorámicas): numeración FDI, impactados, canal dentario inferior y seno maxilar */}
            {esPanoramica && (
              <div className="contents">
                <button type="button" onClick={analizar} disabled={iaCargando}
                  title="Numera las piezas y detecta impactados, canal dentario inferior y senos maxilares (sugerencia: la valida el doctor)"
                  className="h-8 px-2.5 rounded-md bg-black/40 hover:bg-black/60 disabled:opacity-60 text-white/90 flex items-center gap-1.5 text-[11px] font-semibold whitespace-nowrap">
                  {iaCargando ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
                  {iaCargando ? "Analizando…" : iaSel ? "Repetir análisis" : "Analizar IA"}
                </button>
                {sel && (
                  <a href={`/pacientes/${patientId}/dentia?f=${encodeURIComponent(sel.id)}`}
                    title="Análisis guiado en 4 pasos: patrones, plan de tratamiento y presupuesto"
                    className="h-8 px-2.5 rounded-md bg-sky-600/80 hover:bg-sky-600 text-white flex items-center gap-1.5 text-[11px] font-semibold whitespace-nowrap">
                    <ScanLine className="w-4 h-4" /> DentIA
                  </a>
                )}
                {iaSel && (
                  <>
                    <button type="button" onClick={() => setIaNum((v) => !v)} aria-pressed={iaNum} aria-label="Números de pieza"
                      title={iaNum ? "Ocultar números de pieza" : "Mostrar números de pieza"}
                      className={`w-8 h-8 rounded-md text-white flex items-center justify-center ${iaNum ? "bg-sky-600/80 hover:bg-sky-600" : "bg-black/40 hover:bg-black/60 text-white/70"}`}>
                      <Hash className="w-4 h-4" />
                    </button>
                    <button type="button" onClick={() => setIaEstr((v) => !v)} aria-pressed={iaEstr} aria-label="Nervio, seno e incluidos"
                      title={iaEstr ? "Ocultar nervio, seno e incluidos" : "Mostrar nervio, seno e incluidos"}
                      className={`w-8 h-8 rounded-md text-white flex items-center justify-center ${iaEstr ? "bg-sky-600/80 hover:bg-sky-600" : "bg-black/40 hover:bg-black/60 text-white/70"}`}>
                      <Layers className="w-4 h-4" />
                    </button>
                  </>
                )}
              </div>
            )}
            </div>
            {iaError && (
              <div className="absolute bottom-10 left-2 max-w-[80%] rounded-md bg-[#C026D3]/90 text-white text-[11px] px-2.5 py-1.5">{iaError}</div>
            )}
            {iaSel && iaVer && (
              <div className="absolute bottom-8 left-2 rounded-md bg-black/55 text-white text-[10px] px-2.5 py-1.5 leading-4 max-w-[70%]">
                {Object.keys(IA_NOMBRE).map((k) => {
                  const n = iaSel.estructuras.filter((e) => e.clase === k);
                  return (
                    <div key={k} className="flex items-center gap-1.5">
                      <span className="inline-block w-2.5 h-2.5 rounded-sm" style={{ background: IA_COLOR[k] }} />
                      {IA_NOMBRE[k]}: {n.length}{k === "impactado" && n.length > 0 ? ` (${n.map((e) => e.fdi ?? "?").join(", ")})` : ""}
                    </div>
                  );
                })}
                <div className="text-white/60 mt-0.5">{iaSel.dientes.length} piezas numeradas · sugerencia, la valida el doctor</div>
                {iaSel.errores.length > 0 && <div className="text-amber-300 mt-0.5">{iaSel.errores.join(" · ")}</div>}
              </div>
            )}

            {/* Expandir a pantalla completa (misma pantalla) */}
            <button type="button" onClick={() => setFull(true)} title="Pantalla completa"
              className="absolute top-2 right-2 w-8 h-8 rounded-md bg-black/40 hover:bg-black/60 text-white/90 flex items-center justify-center">
              <Maximize2 className="w-4 h-4" />
            </button>

            {/* Navegación dentro del grupo */}
            {grupo.length > 1 && (
              <>
                <button type="button" onClick={() => nav(-1)} aria-label="Anterior"
                  className="absolute left-2 top-1/2 -translate-y-1/2 w-8 h-8 rounded-full bg-black/40 hover:bg-black/60 text-white flex items-center justify-center">
                  <ChevronLeft className="w-5 h-5" />
                </button>
                <button type="button" onClick={() => nav(1)} aria-label="Siguiente"
                  className="absolute right-2 top-1/2 -translate-y-1/2 w-8 h-8 rounded-full bg-black/40 hover:bg-black/60 text-white flex items-center justify-center">
                  <ChevronRight className="w-5 h-5" />
                </button>
              </>
            )}

            <div className="absolute bottom-0 inset-x-0 px-3 py-1.5 bg-black/45 text-white text-[10px] flex items-center justify-between">
              <span className="truncate">{sel.name}</span>
              <span className="text-white/70 shrink-0 ml-2">
                {grupo.length > 1 && <>{idx + 1}/{grupo.length}{sel.fecha ? " · " : ""}</>}
                {sel.fecha && fecha(sel.fecha)}
              </span>
            </div>
          </>
        ) : (
          <div className="text-center px-4">
            <ImageOff className="w-10 h-10 mb-2 mx-auto" strokeWidth={1.25} />
            <p className="text-[12px]">Sin imágenes en Drive</p>
            <p className="text-[10px] text-slate-600 mt-1">Este paciente aún no tiene imágenes ni panorámicas</p>
          </div>
        )}
      </div>

      <Carrusel titulo="Panorámicas" icon={ScanLine} width={200} aspect="aspect-video"
        items={data?.radiografias ?? []} patientId={patientId} sel={sel} onSel={setSel} />

      {/* Emergente a pantalla completa. Va en un portal sobre <body> con z-index por encima de TODO: dentro de la
          ficha lo tapaban la barra superior y el menú lateral (el botón de cerrar quedaba oculto, sin forma de volver). */}
      {full && sel && typeof document !== "undefined" && createPortal(
        <div className="fixed inset-0 z-[10000] bg-white flex items-center justify-center" onClick={() => setFull(false)}>
          <div className="relative" onClick={(e) => e.stopPropagation()}>
            <img src={fullSrc} alt={sel.name} className="block max-w-[94vw] max-h-[84vh] object-contain select-none" />
            {iaSel && iaVer && capaIA()}
          </div>

          {/* Barra superior: Volver · IA · DentIA */}
          <div className="absolute top-4 left-4 right-4 flex items-center gap-2 flex-wrap" onClick={(e) => e.stopPropagation()}>
            <button type="button" onClick={() => setFull(false)} title="Volver (Esc)"
              className="h-10 px-4 rounded-md bg-[#21A2E5] hover:bg-[#065AED] text-white flex items-center gap-2 text-[13px] font-semibold shadow-sm">
              <ChevronLeft className="w-5 h-5" /> Volver
            </button>
            {esPanoramica && (
              <>
                <button type="button" onClick={analizar} disabled={iaCargando}
                  title="Numera las piezas y detecta impactados, canal dentario inferior y senos maxilares (sugerencia: la valida el doctor)"
                  className="h-10 px-4 rounded-md bg-slate-800 hover:bg-slate-900 disabled:opacity-60 text-white flex items-center gap-2 text-[13px] font-semibold shadow-sm">
                  {iaCargando ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
                  {iaCargando ? "Analizando…" : iaSel ? "Repetir análisis" : "Analizar IA"}
                </button>
                <a href={`/pacientes/${patientId}/dentia?f=${encodeURIComponent(sel.id)}`}
                  title="Análisis guiado en 4 pasos: patrones, plan de tratamiento y presupuesto"
                  className="h-10 px-4 rounded-md bg-[#C026D3] hover:bg-[#A21CAF] text-white flex items-center gap-2 text-[13px] font-semibold shadow-sm">
                  <ScanLine className="w-4 h-4" /> DentIA
                </a>
                {iaSel && (
                  <>
                    <button type="button" onClick={() => setIaNum((v) => !v)} aria-pressed={iaNum}
                      title={iaNum ? "Ocultar números de pieza" : "Mostrar números de pieza"}
                      className={`h-10 px-3 rounded-md flex items-center gap-2 text-[13px] font-semibold ${iaNum ? "bg-[#21A2E5] text-white hover:bg-[#065AED]" : "bg-slate-200 text-slate-700 hover:bg-slate-300"}`}>
                      <Hash className="w-4 h-4" /> Números
                    </button>
                    <button type="button" onClick={() => setIaEstr((v) => !v)} aria-pressed={iaEstr}
                      title={iaEstr ? "Ocultar nervio, seno e incluidos" : "Mostrar nervio, seno e incluidos"}
                      className={`h-10 px-3 rounded-md flex items-center gap-2 text-[13px] font-semibold ${iaEstr ? "bg-[#21A2E5] text-white hover:bg-[#065AED]" : "bg-slate-200 text-slate-700 hover:bg-slate-300"}`}>
                      <Layers className="w-4 h-4" /> Nervio y seno
                    </button>
                  </>
                )}
              </>
            )}
            {iaError && <span className="rounded-md bg-[#C026D3] text-white text-[12px] px-3 py-2">{iaError}</span>}
            {iaSel && iaVer && (
              <span className="rounded-md bg-slate-100 text-slate-700 text-[12px] px-3 py-2">
                {iaSel.dientes.length} piezas numeradas · sugerencia, la valida el doctor
              </span>
            )}
            {iaSel && iaSel.errores.length > 0 && (
              <span className="rounded-md bg-amber-100 text-amber-800 text-[12px] px-3 py-2">{iaSel.errores.join(" · ")}</span>
            )}
          </div>

          {grupo.length > 1 && (
            <>
              <button type="button" onClick={(e) => { e.stopPropagation(); nav(-1); }} aria-label="Anterior"
                className={`absolute left-4 top-1/2 -translate-y-1/2 ${MODAL_CLOSE} !w-11 !h-11 shadow`}>
                <ChevronLeft className="w-6 h-6" />
              </button>
              <button type="button" onClick={(e) => { e.stopPropagation(); nav(1); }} aria-label="Siguiente"
                className={`absolute right-4 top-1/2 -translate-y-1/2 ${MODAL_CLOSE} !w-11 !h-11 shadow`}>
                <ChevronRight className="w-6 h-6" />
              </button>
            </>
          )}

          {/* Abajo: nombre del paciente (izq) · icono del centro (der) */}
          <div className="absolute bottom-4 inset-x-0 px-6 flex items-end justify-between gap-4 pointer-events-none">
            <div className="text-slate-800 text-[15px] font-semibold">
              {paciente}
              {grupo.length > 1 && <span className="text-slate-400 text-[12px] ml-2">{idx + 1}/{grupo.length}</span>}
            </div>
            {icono && <img src={icono} alt="" className="h-12 max-w-[180px] object-contain" />}
          </div>
        </div>,
        document.body,
      )}
    </div>
  );
}
